"""What the model must answer, and the text it is given.

The model answers whether a message is an invoice and, for one that is
not, which near miss it is, with a quote. It names no supplier and no
folder (prompt ``v4``): where an invoice goes follows from the folder it
lies in.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict

from ...records import MailMessage

__all__ = ["MAX_ANSWER_TEXT", "MAX_TEXT", "Answer", "parts", "render"]

# The text of a mail is cut here. An invoice says what it is near the top.
MAX_TEXT = 6000

# The longest quote or value an answer may hold. A longer one is refused as
# not fitting the schema, so an answer cannot copy the mail into the state
# file. Checked after parsing, the schema sent to the model is unchanged.
MAX_ANSWER_TEXT = 300


def _short(value: str) -> str:
    if len(value) > MAX_ANSWER_TEXT:
        raise ValueError(f"longer than {MAX_ANSWER_TEXT} characters")
    return value


Short = Annotated[str, AfterValidator(_short)]


class Answer(BaseModel):
    """The answer of the model."""

    model_config = ConfigDict(extra="forbid")

    label: Literal["invoice", "other"]
    near_miss: Literal[
        "reminder", "quotation", "order_confirmation", "payment_receipt", "none"
    ]
    quote: Short


def render(message: MailMessage) -> str:
    """The content of one call: sender, subject, attachments, text."""
    sender = message.sender
    lines = []
    if sender is not None:
        named = f"{sender.name} <{sender.email}>" if sender.name else sender.email
        lines.append(f"From: {named}")
    lines.append(f"Subject: {message.subject or ''}")
    if message.attachments:
        files = ", ".join(
            f"{a.filename or '(no name)'} ({a.content_type})"
            for a in message.attachments
        )
        lines.append(f"Attachments: {files}")
    return "\n".join(lines) + "\n\n" + message.text[:MAX_TEXT]


def parts(message: MailMessage) -> list[str]:
    """The parts of the mail :func:`render` gives the model, without its
    frame: what a quote is looked up in."""
    files = [a.filename for a in message.attachments if a.filename]
    return [_named(message), message.subject or "", *files, message.text[:MAX_TEXT]]


def _named(message: MailMessage) -> str:
    sender = message.sender
    if sender is None:
        return ""
    return f"{sender.name} <{sender.email}>" if sender.name else sender.email
