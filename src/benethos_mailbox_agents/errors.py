"""The error hierarchy, and ``redact``.

Every error of this package derives from :class:`MailboxAgentError`, whose
message is redacted on construction: a secret registered with
:func:`register_secret` never survives into the text of an error, however
it got there. A log line names the class of an error and its ``code``,
never its message, see ``logbook``.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import ValidationError

__all__ = [
    "ActionRefusedError",
    "AnswerRefusedError",
    "ChangesExpiredError",
    "ConfigError",
    "ContractError",
    "GatewayUnavailableError",
    "LimitReachedError",
    "MailboxAgentError",
    "MailboxRefusedError",
    "MailboxUnavailableError",
    "MessageGoneError",
    "StateFileError",
    "UnavailableError",
    "describe_invalid",
    "forget_secrets",
    "redact",
    "register_secret",
]

_REDACTED = "[redacted]"

# A secret shorter than this is not registered: replacing every "a" in a
# text would make the text useless and protect nothing.
_SHORTEST = 6

_SECRETS: set[str] = set()


def register_secret(secret: str | None) -> None:
    """Remember ``secret``, so :func:`redact` takes it out of any text."""
    if secret and len(secret) >= _SHORTEST:
        _SECRETS.add(secret)


def forget_secrets() -> None:
    """Forget every registered secret. For tests."""
    _SECRETS.clear()


def describe_invalid(exc: Exception, name: Callable[[str], str] = str) -> str:
    """What is wrong, as a :class:`ConfigError` may say it: for a validation
    error the place and the rule of each problem, the place passed through
    ``name``, never the input, which may be a secret or a piece of mail. For
    another error its class."""
    if not isinstance(exc, ValidationError):
        return type(exc).__name__
    return ", ".join(
        f"{name('.'.join(str(p) for p in e['loc']))}: {e['msg']}"
        for e in exc.errors(include_input=False, include_url=False)
    )


def redact(text: str) -> str:
    """Replace every registered secret in ``text`` with a placeholder.

    The longest first, so a secret that contains another is replaced whole.
    """
    for secret in sorted(_SECRETS, key=len, reverse=True):
        text = text.replace(secret, _REDACTED)
    return text


class MailboxAgentError(Exception):
    """Base class of every error this package raises on purpose.

    ``code`` is what a log line may say about the error besides its class.
    The message may quote what an upstream answered, so it is never logged.
    """

    code: str = "error"

    def __init__(self, message: str) -> None:
        super().__init__(redact(message))

    @property
    def message(self) -> str:
        return str(self)


class ConfigError(MailboxAgentError):
    """A setting or a configuration file is missing or wrong."""

    code = "config"


class ContractError(MailboxAgentError):
    """An agent class breaks the contract of docs/specs/agent-contract.md, or the
    registry cannot find the agent named."""

    code = "contract"


class UnavailableError(MailboxAgentError):
    """An upstream did not answer. A normal condition: the work waits and
    is taken up again, nothing is decided without it."""

    code = "unavailable"


class MailboxUnavailableError(UnavailableError):
    """The mailbox service did not answer, or answered with a 5xx or 429."""

    code = "mailbox_unavailable"


class GatewayUnavailableError(UnavailableError):
    """The model gateway did not answer, or answered with a 5xx, 408 or
    429."""

    code = "gateway_unavailable"


class ChangesExpiredError(MailboxAgentError):
    """The stored feed state is older than the service keeps changes for."""

    code = "changes_expired"


class MailboxRefusedError(MailboxAgentError):
    """The mailbox service refused a request with a 4xx, its ``status``,
    or the request was not sent, as it could only be refused: no status."""

    code = "mailbox_refused"

    def __init__(self, message: str, *, status: int | None = None, reason: str) -> None:
        super().__init__(message)
        self.status = status
        self.reason = reason


class MessageGoneError(MailboxRefusedError):
    """The message is not there any more: deleted, or moved out of reach.
    The same ``code`` as its base, so logs and metrics count it alike."""


class AnswerRefusedError(MailboxAgentError):
    """An answer of the model failed the schema or the gateway refused the
    request. ``reason`` is ``schema`` or ``request``."""

    code = "answer_refused"

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


class StateFileError(MailboxAgentError):
    """The state file cannot be read or written: it is no SQLite file, it
    is damaged, or the disk is full. Nothing goes on without it."""

    code = "state_file"


class LimitReachedError(MailboxAgentError):
    """An agent asked for more model calls than its limits allow.
    ``per_day`` tells the daily limit, which passes with the day, from the
    limit per message, which does not."""

    code = "limit_reached"

    def __init__(self, message: str, *, per_day: bool) -> None:
        super().__init__(message)
        self.per_day = per_day


class ActionRefusedError(MailboxAgentError):
    """The runtime refused an action: one the agent did not declare, an
    account it does not work on, a keyword not its own, a folder that does
    not exist, or a message or folder in or below the trash, junk or
    spam."""

    code = "action_refused"
