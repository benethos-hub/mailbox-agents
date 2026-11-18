"""The models passed between the layers. Data only, no behaviour beyond
what reads a field."""

from __future__ import annotations

from .decisions import LABEL, Decision, Evidence, Step, StepResult
from .items import OpenItem
from .mail import (
    EVENTS,
    Address,
    Attachment,
    Event,
    FolderRef,
    MailMessage,
    MessageRef,
    Thread,
)

__all__ = [
    "EVENTS",
    "LABEL",
    "Address",
    "Attachment",
    "Decision",
    "Event",
    "Evidence",
    "FolderRef",
    "MailMessage",
    "MessageRef",
    "OpenItem",
    "Step",
    "StepResult",
    "Thread",
]
