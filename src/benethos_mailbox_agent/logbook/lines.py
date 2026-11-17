"""The catalogue: every line the package writes, one function each.

A function takes only what a line may carry. An error is described by its
class and its code, never by its message.
"""

from __future__ import annotations

from .output import LOGGER

__all__ = [
    "action_done",
    "action_refused",
    "answer_refused",
    "backfill_done",
    "describe",
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


def describe(error: BaseException) -> str:
    """What a line may say about ``error``: its class, and its code if any."""
    code = getattr(error, "code", None)
    name = type(error).__name__
    return f"{name}({code})" if isinstance(code, str) and code else name


# --- lifecycle -------------------------------------------------------------


def started(agent: str, version: str, stage: str) -> None:
    LOGGER.info("agent=%s started version=%s stage=%s", agent, version, stage)


def stopped(agent: str, reason: str) -> None:
    LOGGER.info("agent=%s stopped reason=%s", agent, reason)


def migrated(agent: str, version: int) -> None:
    LOGGER.info("agent=%s state file at schema version %d", agent, version)


def metrics_serving(agent: str, port: int) -> None:
    LOGGER.info("agent=%s metrics on port %d", agent, port)


# --- the loop --------------------------------------------------------------


def feed_read(agent: str, changes: int, selected: int) -> None:
    LOGGER.info("agent=%s feed changes=%d selected=%d", agent, changes, selected)


def feed_expired(agent: str) -> None:
    LOGGER.warning("agent=%s feed state expired, starting anew", agent)


def backfill_done(agent: str, messages: int, days: int) -> None:
    LOGGER.info("agent=%s backfill messages=%d days=%d", agent, messages, days)


def tick_done(agent: str, actions: int) -> None:
    LOGGER.info("agent=%s tick actions=%d", agent, actions)


def pass_done(agent: str, seconds: float, pending: int) -> None:
    LOGGER.debug("agent=%s pass done in %.2fs pending=%d", agent, seconds, pending)


def pass_failed(agent: str, error: BaseException) -> None:
    LOGGER.error("agent=%s pass failed error=%s", agent, describe(error))


def upstream_away(agent: str, error: BaseException, wait: float) -> None:
    LOGGER.warning(
        "agent=%s upstream away error=%s retry in %.0fs",
        agent,
        describe(error),
        wait,
    )


# --- one message -----------------------------------------------------------


def message_state(agent: str, message_id: str, state: str) -> None:
    LOGGER.info("agent=%s message=%s state=%s", agent, message_id, state)


def step_done(agent: str, message_id: str, step: str, ms: int) -> None:
    LOGGER.debug(
        "agent=%s message=%s step=%s done in %dms", agent, message_id, step, ms
    )


def step_failed(agent: str, message_id: str, step: str, error: BaseException) -> None:
    LOGGER.warning(
        "agent=%s message=%s step=%s failed error=%s",
        agent,
        message_id,
        step,
        describe(error),
    )


def answer_refused(agent: str, message_id: str, reason: str) -> None:
    LOGGER.warning(
        "agent=%s message=%s answer refused reason=%s", agent, message_id, reason
    )


def evidence_missing(agent: str, message_id: str, field: str) -> None:
    LOGGER.info(
        "agent=%s message=%s quote not found field=%s", agent, message_id, field
    )


def action_done(
    agent: str, message_id: str, action: str, stage: str, executed: bool
) -> None:
    LOGGER.info(
        "agent=%s message=%s action=%s stage=%s executed=%s",
        agent,
        message_id,
        action,
        stage,
        "yes" if executed else "no",
    )


def action_refused(
    agent: str, message_id: str, action: str, error: BaseException
) -> None:
    LOGGER.warning(
        "agent=%s message=%s action=%s refused error=%s",
        agent,
        message_id,
        action,
        describe(error),
    )
