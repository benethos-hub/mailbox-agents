"""What the model must answer, and the text it is given."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict

from ...records import MailMessage

__all__ = [
    "FIELDS",
    "MAX_NAME",
    "MAX_SUBJECT",
    "MAX_TEXT",
    "Inquiry",
    "Label",
    "Quoted",
    "parts",
    "render",
]

# The fields of an inquiry, each optional, with what it means. The prompt
# names them, the schema holds one entry per name.
FIELDS: dict[str, str] = {
    "role": "the role or task",
    "start": "when it starts",
    "end": "when it ends",
    "duration": "how long it lasts",
    "workload": "how much of a week, such as days or hours",
    "location": "the place of work",
    "remote_share": "how much of it is remote",
    "contract_form": "the form of contract, such as freelance or employed",
    "intermediary": "the agency writing for a client, by name",
    "end_client": "the client the work is for",
    "rate": "the rate or budget",
    "required_skills": "the skills it needs",
    "desired_skills": "the skills that would be good to have",
    "deadline": "the deadline to apply",
}

MAX_TEXT = 8000

# The sender's name and the subject are cut here. A stranger chooses
# both, so no mail can blow up a call. The same cut goes to the model and
# to the evidence check.
MAX_SUBJECT = 300
MAX_NAME = 300

# The longest quote or value an answer may hold. A longer one is refused as
# not fitting the schema, so an answer cannot copy the mail into the state
# file. Checked after parsing, the schema sent to the model is unchanged.
MAX_ANSWER_TEXT = 300


def _short(value: str) -> str:
    if len(value) > MAX_ANSWER_TEXT:
        raise ValueError(f"longer than {MAX_ANSWER_TEXT} characters")
    return value


Short = Annotated[str, AfterValidator(_short)]


class Label(BaseModel):
    """Whether the message is a project inquiry."""

    model_config = ConfigDict(extra="forbid")

    label: Literal["inquiry", "other"]
    quote: Short


class Quoted(BaseModel):
    """One field: its value, and the passage of the mail that says it."""

    model_config = ConfigDict(extra="forbid")

    value: Short
    quote: Short


class Inquiry(Label):
    """The label and, for an inquiry, its fields. A field the mail does not
    fill is null as a whole: one union per field keeps the schema within
    the 16 parameters with union types the Claude API compiles."""

    role: Quoted | None
    start: Quoted | None
    end: Quoted | None
    duration: Quoted | None
    workload: Quoted | None
    location: Quoted | None
    remote_share: Quoted | None
    contract_form: Quoted | None
    intermediary: Quoted | None
    end_client: Quoted | None
    rate: Quoted | None
    required_skills: Quoted | None
    desired_skills: Quoted | None
    deadline: Quoted | None


def render(message: MailMessage) -> str:
    """The content of one call: sender, subject and text."""
    lines = []
    if message.sender is not None:
        lines.append(f"From: {_named(message)}")
    lines.append(f"Subject: {_subject(message)}")
    return "\n".join(lines) + "\n\n" + message.text[:MAX_TEXT]


def parts(message: MailMessage) -> list[str]:
    """The parts of the mail :func:`render` gives the model, without its
    frame: what a quote is looked up in."""
    return [_named(message), _subject(message), message.text[:MAX_TEXT]]


def _named(message: MailMessage) -> str:
    sender = message.sender
    if sender is None:
        return ""
    name = (sender.name or "")[:MAX_NAME]
    return f"{name} <{sender.email}>" if name else sender.email


def _subject(message: MailMessage) -> str:
    return (message.subject or "")[:MAX_SUBJECT]
