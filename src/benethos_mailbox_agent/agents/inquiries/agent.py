"""``inquiries``: is this a project inquiry?

The model labels a message in the inbox ``inquiry`` or ``other``, with a
quote the code finds in the mail. An inquiry gets the keyword. The rules
beside it know phrases, dates and rates, and the sender domains and
phrases of a patterns file. See SPECS.md section 10.3.
"""

from __future__ import annotations

from functools import cached_property

from ...contract import (
    Action,
    ActionRequest,
    Agent,
    Context,
    Limits,
    Route,
    Trigger,
)
from ...contract.prompts import load_prompt
from ...records import LABEL, Decision, Event, Evidence, MailMessage
from .baseline import baseline
from .patterns import Patterns, load_patterns
from .schema import Label, render

__all__ = ["Inquiries"]


class Inquiries(Agent):
    name = "inquiries"
    version = "1"
    description = "Marks project inquiries."
    triggers = Trigger(events=frozenset({"message.created"}))
    actions = frozenset({Action.ADD_KEYWORD})
    limits = Limits(model_calls_per_message=1, model_calls_per_day=2000)
    default_keyword = "inquiry"
    prompt_version = "v1"

    def prepare(self) -> None:
        _ = self.patterns

    @cached_property
    def patterns(self) -> Patterns:
        return load_patterns(self.settings.inquiries_patterns_file)

    @cached_property
    def system(self) -> str:
        return load_prompt(__package__ or "", "system", self.prompt_version)

    def select(self, event: Event) -> Route | None:
        return Route.DECIDE if event.type == "message.created" else None

    def admit(self, message: MailMessage) -> bool:
        return message.in_role("inbox")

    def baseline(self, message: MailMessage) -> Decision:
        return baseline(message, self.patterns)

    async def decide(self, message: MailMessage, context: Context) -> Decision:
        answer = await context.model.ask(
            system=self.system, content=render(message), schema=Label
        )
        return Decision(
            label=answer.label,
            source="model",
            evidence=(Evidence(field=LABEL, value=answer.label, quote=answer.quote),),
        )

    async def effect(
        self, decision: Decision, message: MailMessage, context: Context
    ) -> list[ActionRequest]:
        if decision.label != "inquiry":
            return []
        return [
            ActionRequest(
                Action.ADD_KEYWORD, message.ref, keyword=self.keyword, why="inquiry"
            )
        ]
