"""What the model must answer about a sent message, and the text it is given."""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict

from ...records import MailMessage
from .text import own_text

__all__ = ["MAX_TEXT", "Answer", "render"]

# The text written is cut here. A request stands near its end, which a long
# message keeps by being cut from the front.
MAX_TEXT = 4000

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
    model_config = ConfigDict(extra="forbid")

    expects_reply: bool
    quote: Short


def render(message: MailMessage) -> str:
    """Recipients, subject and the text the sender wrote, without what it
    quotes."""
    to = ", ".join(a.email for a in (*message.to, *message.cc)) or "(none)"
    text = own_text(message.text)
    return f"To: {to}\nSubject: {message.subject or ''}\n\n{text[-MAX_TEXT:]}"


def parts(message: MailMessage) -> list[str]:
    """The parts of the mail :func:`render` gives the model, without its
    frame: what a quote is looked up in."""
    to = ", ".join(a.email for a in (*message.to, *message.cc))
    return [to, message.subject or "", own_text(message.text)[-MAX_TEXT:]]
