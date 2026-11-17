"""What the runtime tests share: an agent for the tests, a clock, and the
pieces wired over the fakes of ``fakes.py``."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from benethos_mailbox_agent.contract import (
    Action,
    ActionRequest,
    Agent,
    Context,
    Route,
    Trigger,
)
from benethos_mailbox_agent.llm.gateway import Gateway
from benethos_mailbox_agent.records import (
    LABEL,
    Decision,
    Event,
    Evidence,
    MailMessage,
)
from benethos_mailbox_agent.settings import Settings
from benethos_mailbox_agent.sources.mailbox import Mailbox, connect
from benethos_mailbox_agent.store import Store
from fakes import FakeGateway, FakeService

START = datetime(2026, 11, 17, 9, 0, tzinfo=UTC)


class Clock:
    """A clock a test moves by hand."""

    def __init__(self, start: datetime = START) -> None:
        self.moment = start

    def __call__(self) -> datetime:
        return self.moment

    def advance(self, **delta: float) -> None:
        self.moment += timedelta(**delta)


class EchoAnswer(BaseModel):
    label: Literal["match", "other"]
    quote: str


def render(message: MailMessage) -> str:
    return f"Subject: {message.subject or ''}\n\n{message.text}"


class Echo(Agent):
    """Asks the model whether a message in the inbox matches, and sets its
    keyword on one that does."""

    name = "echo"
    version = "1"
    description = "an agent for the runtime tests"
    triggers = Trigger(events=frozenset({"message.created"}))
    actions = frozenset({Action.ADD_KEYWORD, Action.MOVE_TO_FOLDER})
    default_keyword = "echo"
    prompt_version = "p1"

    def select(self, event: Event) -> Route | None:
        return Route.DECIDE if event.type in self.triggers.events else None

    def admit(self, message: MailMessage) -> bool:
        return message.in_role("inbox")

    def baseline(self, message: MailMessage) -> Decision:
        found = "invoice" in (message.subject or "").lower()
        return Decision(label="match" if found else "other", source="baseline")

    async def decide(self, message: MailMessage, context: Context) -> Decision:
        answer = await context.model.ask(
            system="Say whether it matches.", content=render(message), schema=EchoAnswer
        )
        return Decision(
            label=answer.label,
            source="model",
            evidence=(Evidence(field=LABEL, value=answer.label, quote=answer.quote),),
        )

    async def effect(
        self, decision: Decision, message: MailMessage, context: Context
    ) -> list[ActionRequest]:
        if decision.label != "match":
            return []
        return [ActionRequest(Action.ADD_KEYWORD, message.ref, keyword=self.keyword)]


@dataclass
class Collected:
    """The effects a step runner handed on, for a test without an executor."""

    requests: list[ActionRequest] = field(default_factory=list)

    async def __call__(self, requests: list[ActionRequest]) -> None:
        self.requests.extend(requests)


@dataclass
class Wired:
    service: FakeService
    fake_gateway: FakeGateway
    mailbox: Mailbox
    gateway: Gateway
    store: Store
    clock: Clock


@asynccontextmanager
async def wired(tmp_path: Path) -> AsyncIterator[Wired]:
    """The fakes, a mailbox and a gateway over them, a state file, a clock."""
    service, fake_gateway = FakeService(), FakeGateway()
    async with (
        connect(
            "https://mailbox.example.test",
            "service-token",
            transport=service.transport(),
        ) as mailbox,
        Gateway(
            "https://gateway.example.test/v1",
            "gateway-key",
            "alias",
            transport=fake_gateway.transport(),
        ) as gateway,
    ):
        with Store.open(tmp_path / "echo.db") as store:
            yield Wired(service, fake_gateway, mailbox, gateway, store, Clock())


def settings(**values: object) -> Settings:
    return Settings(model="alias", **values)  # type: ignore[arg-type]
