"""``invoices``: is this message an invoice?

The model answers whether a message is an invoice, and for one that is
not, which near miss it is. The agent looks at the inbox and at the
folders its settings name. An invoice gets the keyword. One in a folder it
looks in moves into the subfolder below that folder, made when missing, so
the folder says whose invoice it is. One in the inbox stays there, unless
an inbox folder is set. Who put a message into a folder does not matter:
``sorting``, a rule of the mail server or the owner by hand. The agent
knows nothing of groups and names no supplier (agent version 4). See
docs/specs/agents/invoices.md.
"""

from __future__ import annotations

from collections import Counter
from functools import cached_property

from ...contract import (
    Action,
    ActionRequest,
    Agent,
    Context,
    Limits,
    Route,
    Shown,
    Trigger,
)
from ...contract.prompts import load_prompt
from ...records import LABEL, Decision, Event, Evidence, FolderRef, MailMessage
from .baseline import baseline
from .folders import Places
from .schema import Answer, parts, render

__all__ = ["Invoices"]


class Invoices(Agent):
    name = "invoices"
    version = "4"
    description = (
        "Marks invoices, and moves one into the subfolder of the folder it lies in."
    )
    triggers = Trigger(events=frozenset({"message.created"}))
    actions = frozenset(
        {Action.ADD_KEYWORD, Action.MOVE_TO_FOLDER, Action.CREATE_FOLDER}
    )
    limits = Limits(model_calls_per_message=1, model_calls_per_day=2000)
    default_keyword = "invoice"
    prompt_version = "v4"

    # -- what it reads besides its settings -----------------------------------

    def prepare(self) -> None:
        """Read the folders now, so a wrong setting stops the start."""
        _ = self.places

    @cached_property
    def places(self) -> Places:
        found = self.settings
        return Places.read(
            found.invoices_folders,
            found.invoices_subfolder,
            found.invoices_inbox_folder,
        )

    def folders_needed(self) -> tuple[str, ...]:
        return self.places.needed()

    def may_create(self, path: str) -> bool:
        return self.places.may_create(path)

    @cached_property
    def system(self) -> str:
        return load_prompt(__package__ or "", "system", self.prompt_version)

    # -- the contract -------------------------------------------------------------

    def select(self, event: Event) -> Route | None:
        return Route.DECIDE if event.type == "message.created" else None

    def admit(self, message: MailMessage) -> bool:
        return self._looked_in(message) is not None

    def baseline(self, message: MailMessage) -> Decision:
        return baseline(message)

    async def decide(self, message: MailMessage, context: Context) -> Decision:
        answer = await context.model.ask(
            system=self.system,
            content=render(message),
            evidence=parts(message),
            schema=Answer,
        )
        label, quote, near_miss = answer.label, answer.quote, answer.near_miss
        evidence = [Evidence(field=LABEL, value=label, quote=quote)]
        fields: dict[str, str] = {}
        if label == "other" and near_miss != "none":
            fields["near_miss"] = near_miss
            evidence.append(Evidence(field="near_miss", value=near_miss, quote=quote))
        return Decision(
            label=label, source="model", fields=fields, evidence=tuple(evidence)
        )

    async def effect(
        self, decision: Decision, message: MailMessage, context: Context
    ) -> list[ActionRequest]:
        if decision.label != "invoice":
            return []
        requests = [
            ActionRequest(
                Action.ADD_KEYWORD, message.ref, keyword=self.keyword, why="invoice"
            )
        ]
        # Where it lies when the agent acts, not when it was decided.
        folder = self._looked_in(message)
        if folder is not None:
            requests += self._file(message, folder)
        return requests

    def summarize(self, shown: list[Shown]) -> list[str]:
        """The senders of invoices no supplier of the list was found for,
        with how many each sent: candidates for the list."""
        counted = Counter(
            item.sender.lower()
            for item in shown
            if item.sender
            and item.decision.label == "invoice"
            and item.decision.actionable
            and "supplier" not in item.decision.fields
        )
        if not counted:
            return []
        return ["candidates for the supplier list:"] + [
            f"  {sender} ({count} invoice{'s' if count > 1 else ''})"
            for sender, count in counted.most_common()
        ]

    # -- where an invoice goes ------------------------------------------------------

    def _looked_in(self, message: MailMessage) -> FolderRef | None:
        """The folder of the message the agent looks in, if any."""
        return next((f for f in message.folders if self.places.looks_in(f)), None)

    def _file(self, message: MailMessage, folder: FolderRef) -> list[ActionRequest]:
        """The folders to make and the move, for an invoice in ``folder``:
        to the inbox folder from the inbox, to the subfolder from a folder
        it looks in. Nothing when the settings name no place."""
        target = self.places.target(folder)
        if target is None:
            return []
        if folder.role == "inbox":
            return [
                ActionRequest(
                    Action.MOVE_TO_FOLDER, message.ref, folder=target, why="inbox"
                )
            ]
        return [
            ActionRequest(
                Action.CREATE_FOLDER, message.ref, folder=path, why="subfolder"
            )
            for path in self.places.steps(folder)
        ] + [
            ActionRequest(
                Action.MOVE_TO_FOLDER, message.ref, folder=target, why="subfolder"
            )
        ]
