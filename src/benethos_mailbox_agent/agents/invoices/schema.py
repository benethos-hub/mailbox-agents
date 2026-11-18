"""What the model must answer, and the text it is given.

The supplier the model may name is one of the list's names or null, as an
enum in the schema: no other value passes the validation, so no answer can
name a folder that is not on the list.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, create_model

from ...records import MailMessage

__all__ = ["LABELS", "MAX_TEXT", "NEAR_MISSES", "Answer", "answer_schema", "render"]

LABELS = ("invoice", "other")
NEAR_MISSES = ("reminder", "quotation", "order_confirmation", "payment_receipt", "none")

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
    """The answer, its supplier narrowed to the list by answer_schema."""

    model_config = ConfigDict(extra="forbid")

    label: Literal["invoice", "other"]
    near_miss: Literal[
        "reminder", "quotation", "order_confirmation", "payment_receipt", "none"
    ]
    quote: Short
    supplier: str | None
    supplier_quote: Short | None


def answer_schema(names: tuple[str, ...]) -> type[Answer]:
    """The schema of an answer, its supplier one of ``names`` or null."""
    supplier: Any = Literal[names] | None if names else type(None)
    return create_model(
        "InvoiceAnswer",
        __base__=Answer,
        supplier=(supplier, ...),
    )


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
