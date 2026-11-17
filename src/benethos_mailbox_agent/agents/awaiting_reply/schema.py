"""What the model must answer about a sent message, and the text it is given."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ...records import MailMessage
from .text import own_text

__all__ = ["MAX_TEXT", "Answer", "render"]

# The text written is cut here. A request stands near its end, which a long
# message keeps by being cut from the front.
MAX_TEXT = 4000


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expects_reply: bool
    quote: str


def render(message: MailMessage) -> str:
    """Recipients, subject and the text the sender wrote, without what it
    quotes."""
    to = ", ".join(a.email for a in (*message.to, *message.cc)) or "(none)"
    text = own_text(message.text)
    return f"To: {to}\nSubject: {message.subject or ''}\n\n{text[-MAX_TEXT:]}"
