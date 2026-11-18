"""The action executor: the runtime's lock on what an agent may do.

An agent asks, this module decides. It carries out only an action the
agent declared, a keyword only if it is the agent's own, a move only into a
folder that exists and is not the trash or junk, nor below them. A
message in the trash or junk is left alone. What the stage allows is
carried out, the rest is recorded as what would have been done. Every
action records what was there before, so it can be taken back. An action
whose result is already there is not taken again. See SPECS.md sections 7,
8 and 11.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol

from .. import logbook
from ..contract import Action, ActionRequest, Agent
from ..errors import ActionRefusedError, MailboxRefusedError
from ..records import FolderRef, MailMessage, MessageRef
from ..store import Store
from .metrics import Metrics

__all__ = ["FORBIDDEN_ROLES", "STAGE_ALLOWS", "Executor", "Writer"]

# What each stage carries out. The rest is recorded only.
STAGE_ALLOWS: dict[str, frozenset[Action]] = {
    "shadow": frozenset(),
    "keyword": frozenset({Action.ADD_KEYWORD, Action.REMOVE_KEYWORD}),
    "full": frozenset(Action),
}

# Folders no agent moves a message into: a move there is a deletion.
FORBIDDEN_ROLES = frozenset({"trash", "junk", "spam"})


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

    async def run(self, request: ActionRequest) -> bool:
        """Take one action, or record it. Answers whether it was recorded.

        A refused action is logged and not recorded, whether the executor
        or the mailbox service refused it, the write itself included. A
        mailbox service that is away is raised to the loop.
        """
        try:
            self._admissible(request)
            message = await self._mailbox.message(request.ref)
            planned = await self._plan(request, message)
            if planned is None:
                return False
            argument, before, target = planned
            executed = request.action in STAGE_ALLOWS[self.stage]
            if executed:
                await self._take(request, target)
        except (ActionRefusedError, MailboxRefusedError) as exc:
            logbook.action_refused(
                self.agent.name, request.ref.message_id, request.action.value, exc
            )
            self.metrics.step_failed(exc.code)
            return False
        self._store.add_action(
            request.ref,
            action=request.action.value,
            argument=argument,
            before=before,
            stage=self.stage,
            executed=executed,
            now=self._now(),
        )
        self.metrics.action(request.action.value, executed)
        logbook.action_done(
            self.agent.name,
            request.ref.message_id,
            request.action.value,
            self.stage,
            executed,
        )
        return True

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
            raise ActionRefusedError("the message is in the trash or junk")
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
        present = keyword in message.keywords
        if (request.action is Action.ADD_KEYWORD) == present:
            return None
        return keyword, {"keywords": list(message.keywords)}, keyword

    async def _forbidden(self, account_id: str, folder: FolderRef) -> bool:
        """Whether ``folder`` is the trash or junk, or lies below them."""
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
