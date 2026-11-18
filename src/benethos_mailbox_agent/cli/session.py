"""The pieces of one agent's process, wired: the mailbox, the gateway, the
state file and the worker over them."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import (
    AbstractAsyncContextManager,
    AsyncExitStack,
    asynccontextmanager,
)
from datetime import UTC, datetime
from typing import Any, TypeVar

from pydantic import BaseModel

from ..contract import Agent
from ..errors import ConfigError, ContractError
from ..llm.gateway import Gateway, Reply
from ..runtime.loop import Worker
from ..runtime.readiness import required, uses_model
from ..settings import Settings
from ..sources.mailbox import Mailbox, connect
from ..store import Store, path_for

__all__ = [
    "TRANSPORTS",
    "NoModel",
    "Session",
    "now",
    "session",
    "start_agent",
    "upstreams",
]

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
    """The agent, once its settings and its preparation are found ready.
    It is built and prepared once, what it reads besides read once."""
    missing = settings.missing(required(cls))
    if missing:
        raise ConfigError(f"{cls.name} misses settings: {', '.join(missing)}")
    try:
        agent = cls(settings)
        agent.prepare()
    except (ConfigError, ContractError) as exc:
        raise ConfigError(f"{cls.name} is not ready: {exc.message}") from None
    return agent


def mailbox_for(settings: Settings) -> AbstractAsyncContextManager[Mailbox]:
    """The mailbox service as the settings name it."""
    return connect(
        settings.service_url or "",
        settings.secret("service_token"),
        allow_http=settings.service_allow_http,
        transport=TRANSPORTS.get("service"),
    )


@asynccontextmanager
async def upstreams(
    agent: Agent, settings: Settings
) -> AsyncIterator[tuple[Mailbox, Gateway | NoModel]]:
    """The mailbox service, and the gateway for an agent that asks a model."""
    async with AsyncExitStack() as stack:
        mailbox = await stack.enter_async_context(mailbox_for(settings))
        gateway: Gateway | NoModel = NoModel()
        if uses_model(type(agent)):
            gateway = await stack.enter_async_context(
                Gateway(
                    settings.gateway_url or "",
                    settings.secret("gateway_key"),
                    settings.model or "",
                    timeout=settings.gateway_timeout_seconds,
                    allow_http=settings.gateway_allow_http,
                    transport=TRANSPORTS.get("gateway"),
                )
            )
        yield mailbox, gateway


@asynccontextmanager
async def session(cls: type[Agent], settings: Settings) -> AsyncIterator[Session]:
    agent = start_agent(cls, settings)
    async with AsyncExitStack() as stack:
        mailbox, gateway = await stack.enter_async_context(upstreams(agent, settings))
        store = stack.enter_context(Store.open(path_for(settings.data_dir, agent.name)))
        worker = Worker(
            agent=agent, store=store, mailbox=mailbox, gateway=gateway, now=now
        )
        yield Session(agent, store, mailbox, worker)
