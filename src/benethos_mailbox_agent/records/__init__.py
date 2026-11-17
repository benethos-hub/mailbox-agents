"""The models passed between the layers. Data only, no behaviour beyond
what reads a field."""

from __future__ import annotations

from .decisions import LABEL, Decision, Evidence, StepResult
from .mail import (
    Address,
    Attachment,
    Event,
    FolderRef,
    MailMessage,
    MessageRef,
    Thread,
)

__all__ = [
    "LABEL",
    "Address",
    "Attachment",
    "Decision",
    "Event",
    "Evidence",
    "FolderRef",
    "MailMessage",
    "MessageRef",
    "StepResult",
    "Thread",
]
