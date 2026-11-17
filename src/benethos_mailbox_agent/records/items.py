"""An open item: a sent message that waits for something by a deadline."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from .mail import MessageRef

__all__ = ["OpenItem"]


class OpenItem(BaseModel):
    """One row of the table ``open_items``, SPECS.md section 9.

    ``keyword_set`` says whether the agent has put its keyword on the
    message, so a keyword a person takes off can be told from one never
    set. ``closed`` and ``reason`` are empty while the item is open.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    ref: MessageRef
    thread_id: str | None
    opened: datetime
    due: datetime
    keyword_set: bool = False
    closed: datetime | None = None
    reason: str | None = None

    @property
    def is_open(self) -> bool:
        return self.closed is None
