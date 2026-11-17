"""What the model must answer, and the text it is given."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from ...records import MailMessage

__all__ = ["MAX_TEXT", "Label", "render"]

MAX_TEXT = 8000


class Label(BaseModel):
    """Whether the message is a project inquiry."""

    model_config = ConfigDict(extra="forbid")

    label: Literal["inquiry", "other"]
    quote: str


def render(message: MailMessage) -> str:
    """The content of one call: sender, subject and text."""
    sender = message.sender
    lines = []
    if sender is not None:
        named = f"{sender.name} <{sender.email}>" if sender.name else sender.email
        lines.append(f"From: {named}")
    lines.append(f"Subject: {message.subject or ''}")
    return "\n".join(lines) + "\n\n" + message.text[:MAX_TEXT]
