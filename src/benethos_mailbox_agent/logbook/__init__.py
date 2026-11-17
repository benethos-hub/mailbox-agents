"""Every line on stderr, one function per line.

No other module of the package imports :mod:`logging`. A module that has
something to say calls the function here that says it, and the function
decides what of it a line may carry: ids, states, counts, durations and
the class and code of an error. Never a subject, a sender, the text of a
mail, an attachment name, a token or a key, and never the message of an
error, which may quote what an upstream answered. See SPECS.md section 11.
"""

from __future__ import annotations

from .lines import (
    action_done,
    action_refused,
    answer_refused,
    backfill_done,
    evidence_missing,
    feed_expired,
    feed_read,
    message_state,
    metrics_serving,
    migrated,
    pass_done,
    pass_failed,
    started,
    step_done,
    step_failed,
    stopped,
    tick_done,
    upstream_away,
)
from .output import LIBRARIES, configure

__all__ = [
    "LIBRARIES",
    "action_done",
    "action_refused",
    "answer_refused",
    "backfill_done",
    "configure",
    "evidence_missing",
    "feed_expired",
    "feed_read",
    "message_state",
    "metrics_serving",
    "migrated",
    "pass_done",
    "pass_failed",
    "started",
    "step_done",
    "step_failed",
    "stopped",
    "tick_done",
    "upstream_away",
]
