"""Whether an agent can start: its settings, and what it reads besides.

``status`` asks this of every agent without starting one. :func:`start`
builds the agent a command runs, once. See docs/specs/agent-contract.md.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..contract import Agent, discover
from ..errors import ConfigError, ContractError
from ..settings import Settings

__all__ = [
    "MAILBOX_SETTINGS",
    "MODEL_SETTINGS",
    "Readiness",
    "readiness",
    "required",
    "start",
    "uses_model",
]

# What every agent needs, and what an agent that asks the model needs too.
MAILBOX_SETTINGS = ("service_url", "service_token")
MODEL_SETTINGS = ("gateway_url", "gateway_key", "model")


def uses_model(agent: type[Agent]) -> bool:
    return agent.limits.model_calls_per_message > 0


def required(agent: type[Agent]) -> tuple[str, ...]:
    """The settings ``agent`` needs before it starts."""
    found = MAILBOX_SETTINGS + (MODEL_SETTINGS if uses_model(agent) else ())
    return found + tuple(n for n in agent.requires.settings if n not in found)


@dataclass(frozen=True)
class Readiness:
    """Whether an agent could start. ``agent`` is the agent built and
    prepared, when it is ready, so a caller asks it without preparing a
    second one."""

    name: str
    version: str
    missing: tuple[str, ...]
    problem: str | None
    agent: Agent | None = None

    @property
    def ready(self) -> bool:
        return not self.missing and self.problem is None


def _own_keyword(agent: type[Agent], settings: Settings) -> None:
    """A :class:`ConfigError` when ``MAILBOX_AGENTS_KEYWORD`` is the
    keyword of another agent. Set in env settings that several agents
    share, it gives them one keyword, and an agent that skips its marked
    mail would skip what the other one marked."""
    if settings.keyword is None:
        return
    for other in discover().values():
        if other.name != agent.name and other.default_keyword == settings.keyword:
            raise ConfigError(
                f"MAILBOX_AGENTS_KEYWORD is the keyword of {other.name}: "
                "give each agent its own env file"
            )


def readiness(agent: type[Agent], settings: Settings) -> Readiness:
    """Whether ``agent`` could start with ``settings``: the settings it
    misses, or what its preparation found wrong, or else the agent
    prepared."""
    missing = tuple(settings.missing(required(agent)))
    if missing:
        return Readiness(agent.name, agent.version, missing, None)
    try:
        _own_keyword(agent, settings)
        prepared = agent(settings)
        prepared.prepare()
    except (ConfigError, ContractError) as exc:
        return Readiness(agent.name, agent.version, missing, exc.message)
    return Readiness(agent.name, agent.version, missing, None, prepared)


def start(cls: type[Agent], settings: Settings) -> Agent:
    """The agent, once its settings and its preparation are found ready.
    It is built and prepared once, what it reads besides read once."""
    missing = settings.missing(required(cls))
    if missing:
        raise ConfigError(f"{cls.name} misses settings: {', '.join(missing)}")
    try:
        _own_keyword(cls, settings)
        agent = cls(settings)
        agent.prepare()
    except (ConfigError, ContractError) as exc:
        raise ConfigError(f"{cls.name} is not ready: {exc.message}") from None
    return agent
