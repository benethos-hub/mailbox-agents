"""The pieces of one agent's process, wired: the mailbox, the gateway, the
state file and the worker over them."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import UTC, datetime
from typing import Any, TypeVar

from pydantic import BaseModel

from ..contract import Agent
from ..errors import ConfigError
from ..llm.gateway import Gateway, Reply
from ..runtime.loop import Worker
from ..runtime.readiness import readiness, uses_model
from ..settings import Settings
from ..sources.mailbox import Mailbox, connect
from ..store import Store, path_for

__all__ = ["TRANSPORTS", "NoModel", "Session", "now", "session"]

T = TypeVar("T", bound=BaseModel)

# Transports for the two upstreams, by "service" and "gateway". Empty in a
# real process. A test puts its mocks here.
TRANSPORTS: dict[str, Any] = {}


def now() -> datetime:
    return datetime.now(UTC)


class NoModel:
    """The gateway of an agent that asks no model."""

    model = ""

    async def ask(self, *, system: str, content: str, schema: type[T]) -> Reply[T]:
        raise ConfigError("this agent asks no model")


class Session:
    """What one command works with."""

    def __init__(
        self, agent: Agent, store: Store, mailbox: Mailbox, worker: Worker
    ) -> None:
        self.agent = agent
        self.store = store
        self.mailbox = mailbox
        self.worker = worker


def start_agent(cls: type[Agent], settings: Settings) -> Agent:
    """The agent, once its settings and its preparation are found ready."""
    found = readiness(cls, settings)
    if found.missing:
        raise ConfigError(f"{cls.name} misses settings: {', '.join(found.missing)}")
    if found.problem:
        raise ConfigError(f"{cls.name} is not ready: {found.problem}")
    agent = cls(settings)
    agent.prepare()
    return agent


@asynccontextmanager
async def session(cls: type[Agent], settings: Settings) -> AsyncIterator[Session]:
    agent = start_agent(cls, settings)
    async with AsyncExitStack() as stack:
        mailbox = await stack.enter_async_context(
            connect(
                settings.service_url or "",
                settings.secret("service_token"),
                allow_http=settings.service_allow_http,
                transport=TRANSPORTS.get("service"),
            )
        )
        gateway: Gateway | NoModel = NoModel()
        if uses_model(cls):
            gateway = await stack.enter_async_context(
                Gateway(
                    settings.gateway_url or "",
                    settings.secret("gateway_key"),
                    settings.model or "",
                    timeout=settings.gateway_timeout_seconds,
                    transport=TRANSPORTS.get("gateway"),
                )
            )
        store = stack.enter_context(Store.open(path_for(settings.data_dir, agent.name)))
        worker = Worker(
            agent=agent, store=store, mailbox=mailbox, gateway=gateway, now=now
        )
        yield Session(agent, store, mailbox, worker)
