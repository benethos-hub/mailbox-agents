"""What an agent may reach while it works, each as a narrow protocol.

The runtime hands an agent a :class:`Context`. Through it the agent asks
the model, reads a thread and keeps its open items, and nothing else: it
never holds the mailbox client, the gateway client or the state file, so
it cannot take an action past the runtime. See docs/specs/agent-contract.md
and docs/specs/safety.md.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, TypeVar

from pydantic import BaseModel

from ..records import MailMessage, MessageRef, OpenItem, Thread
from ..settings import Settings

__all__ = ["Context", "Items", "Model", "Reader"]

T = TypeVar("T", bound=BaseModel)


class Model(Protocol):
    """One model call with a schema, as the runtime offers it to an agent.

    The runtime counts the calls against the agent's limits, records model,
    tokens and duration, and keeps ``evidence``, the parts of the mail in
    ``content`` without the frame around them, for the evidence check. The
    answer is validated against ``schema`` before it is returned.
    """

    async def ask(
        self,
        *,
        system: str,
        content: str,
        schema: type[T],
        evidence: Sequence[str],
    ) -> T: ...


class Reader(Protocol):
    """The mailbox, read-only."""

    async def message(self, ref: MessageRef) -> MailMessage: ...

    async def thread(self, account_id: str, thread_id: str) -> Thread: ...


class Items(Protocol):
    """The open items of an agent with deadlines, docs/specs/state.md."""

    async def open(self, ref: MessageRef, thread_id: str | None, due: datetime) -> None:
        """Open an item for a message that has none, an item there already
        left as it is."""

    async def restart(self, ref: MessageRef, due: datetime) -> None:
        """Start an item again with a new deadline, unless a person closed it
        by taking the keyword off."""

    async def get(self, ref: MessageRef) -> OpenItem | None: ...

    async def in_thread(self, account_id: str, thread_id: str) -> list[OpenItem]: ...

    async def due(self, now: datetime) -> list[OpenItem]: ...

    async def mark_keyword(self, ref: MessageRef, keyword_set: bool) -> None: ...

    async def close(self, ref: MessageRef, reason: str) -> None: ...


@dataclass(frozen=True)
class Context:
    """What one step of an agent may reach."""

    settings: Settings
    model: Model
    reader: Reader
    items: Items
    now: Callable[[], datetime]
