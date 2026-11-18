"""The action executor: the runtime's lock on what an agent may do.

An agent asks, this module decides. It carries out only an action the
agent declared, a keyword only if it is the agent's own, a move only into a
folder that exists and is not the trash, junk or spam, nor below them.
A message in one of them is left alone. What the stage allows is
carried out, the rest is recorded as what would have been done. Every
action records what was there before, so it can be taken back. An action
whose result is already there is not taken again. See docs/specs/agent-contract.md,
docs/specs/runtime.md and docs/specs/safety.md.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from ..contract import Action, ActionRequest, Agent
from ..errors import ActionRefusedError, MailboxRefusedError, MessageGoneError
from ..logbook import actions, record
from ..records import FolderRef, MailMessage, MessageRef
from ..store import Store
from .metrics import Metrics

__all__ = ["FORBIDDEN_ROLES", "STAGE_ALLOWS", "Executor", "Outcome", "Writer"]

# What each stage carries out. The rest is recorded only.
STAGE_ALLOWS: dict[str, frozenset[Action]] = {
    "shadow": frozenset(),
    "keyword": frozenset({Action.ADD_KEYWORD, Action.REMOVE_KEYWORD}),
    "full": frozenset(Action),
}

# Folders no agent moves a message into: a move there is a deletion.
FORBIDDEN_ROLES = frozenset({"trash", "junk", "spam"})


class Outcome(StrEnum):
    """What became of one action."""

    DONE = "done"  # the stage allows it, it was taken
    PRESENT = "present"  # its result was already there
    RECORDED = "recorded"  # the stage does not allow it, it was recorded only
    REFUSED = "refused"  # the executor or the mailbox service refused it
    GONE = "gone"  # the message is not there any more


class Writer(Protocol):
    """What the executor needs of the mailbox."""

    async def message(self, ref: MessageRef) -> MailMessage: ...

    async def folder_at(self, account_id: str, path: str) -> FolderRef | None: ...

    async def folders(self, account_id: str) -> dict[str, FolderRef]: ...

    async def add_keyword(self, ref: MessageRef, keyword: str) -> None: ...

    async def remove_keyword(self, ref: MessageRef, keyword: str) -> None: ...

    async def move(self, ref: MessageRef, folder_id: str) -> None: ...


class Executor:
    """Carries out the actions of one agent, in its stage."""

    def __init__(
        self,
        *,
        agent: Agent,
        store: Store,
        mailbox: Writer,
        now: Callable[[], datetime],
        metrics: Metrics | None = None,
    ) -> None:
        self.metrics = metrics or Metrics(
            agent.name, agent.version, agent.settings.stage
        )
        self.agent = agent
        self.stage = agent.settings.stage
        self._store = store
        self._mailbox = mailbox
        self._now = now

    async def __call__(self, requests: list[ActionRequest]) -> None:
        for request in requests:
            await self.run(request)

    async def run(self, request: ActionRequest) -> Outcome:
        """Take one action, or record it. Answers what became of it.

        The action is recorded with what was there before, and only then
        taken, so a crash between the two leaves what is needed to take it
        back. A refused action is logged and not recorded, whether the
        executor or the mailbox service refused it, the write itself
        included. A mailbox service that is away is raised to the loop.
        """
        try:
            self._admissible(request)
            message = await self._mailbox.message(request.ref)
            planned = await self._plan(request, message)
        except (ActionRefusedError, MailboxRefusedError) as exc:
            return self._refused(request, exc)
        if planned is None:
            return Outcome.PRESENT
        argument, before, target = planned
        executed = request.action in STAGE_ALLOWS[self.stage]
        recorded = self._store.add_action(
            request.ref,
            action=request.action.value,
            argument=argument,
            before=before,
            stage=self.stage,
            executed=False,
            now=self._now(),
        )
        if executed:
            try:
                await self._take(request, target)
            except MailboxRefusedError as exc:
                self._store.drop_action(recorded)
                return self._refused(request, exc)
            self._store.mark_action_executed(recorded)
        self.metrics.action(request.action.value, executed)
        done = actions.Done if executed else actions.Recorded
        record(
            done(
                agent=self.agent.name,
                message_id=request.ref.message_id,
                action=request.action.value,
                stage=self.stage,
                reason=request.why,
            )
        )
        return Outcome.DONE if executed else Outcome.RECORDED

    def _refused(
        self, request: ActionRequest, exc: ActionRefusedError | MailboxRefusedError
    ) -> Outcome:
        """Log the refusal and count it. Answers ``GONE`` when the message is
        not there any more, ``REFUSED`` otherwise."""
        record(
            actions.Refused(
                agent=self.agent.name,
                message_id=request.ref.message_id,
                action=request.action.value,
                error=exc,
            )
        )
        self.metrics.step_failed(exc.code)
        return Outcome.GONE if isinstance(exc, MessageGoneError) else Outcome.REFUSED

    def _admissible(self, request: ActionRequest) -> None:
        if request.action not in self.agent.actions:
            raise ActionRefusedError(
                f"{self.agent.name} did not declare {request.action}"
            )
        accounts = self.agent.settings.accounts
        if accounts and request.ref.account_id not in accounts:
            raise ActionRefusedError("the account is not one the agent works on")
        if request.action is Action.MOVE_TO_FOLDER:
            if not request.folder:
                raise ActionRefusedError("a move names no folder")
        elif request.keyword != self.agent.keyword:
            raise ActionRefusedError("an agent sets and takes off its own keyword only")

    async def _plan(
        self, request: ActionRequest, message: MailMessage
    ) -> tuple[str, dict[str, Any], str] | None:
        """The argument to record, what was there before and the target, or
        None when the result is already there."""
        if any(f.role in FORBIDDEN_ROLES for f in message.folders):
            raise ActionRefusedError("the message is in the trash, junk or spam")
        if request.action is Action.MOVE_TO_FOLDER:
            path = request.folder or ""  # never empty, _admissible checked it
            folder = await self._mailbox.folder_at(request.ref.account_id, path)
            if folder is None:
                raise ActionRefusedError("the target folder does not exist")
            if await self._forbidden(request.ref.account_id, folder):
                raise ActionRefusedError("no agent moves a message there")
            before = [f.id for f in message.folders]
            if before == [folder.id]:
                return None
            return folder.path, {"folders": before}, folder.id
        keyword = self.agent.keyword
        # IMAP keywords ignore case, and a service may answer them in lower
        # case (measured 2026-11-18 at Stalwart through service 0.7.5).
        present = keyword.casefold() in {k.casefold() for k in message.keywords}
        if (request.action is Action.ADD_KEYWORD) == present:
            return None
        return keyword, {"keywords": list(message.keywords)}, keyword

    async def _forbidden(self, account_id: str, folder: FolderRef) -> bool:
        """Whether ``folder`` is the trash, junk or spam, or lies below one."""
        if folder.role in FORBIDDEN_ROLES:
            return True
        known = await self._mailbox.folders(account_id)
        return any(
            folder.path.startswith(f"{other.path}/")
            for other in known.values()
            if other.role in FORBIDDEN_ROLES
        )

    async def _take(self, request: ActionRequest, target: str) -> None:
        if request.action is Action.ADD_KEYWORD:
            await self._mailbox.add_keyword(request.ref, target)
        elif request.action is Action.REMOVE_KEYWORD:
            await self._mailbox.remove_keyword(request.ref, target)
        else:
            await self._mailbox.move(request.ref, target)
