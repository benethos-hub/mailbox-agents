"""Whether an agent can start: its settings, and what it reads besides.

``status`` asks this of every agent without starting one, ``worker`` asks
it before it starts. See SPECS.md section 7.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..contract import Agent
from ..errors import ConfigError, ContractError
from ..settings import Settings

__all__ = ["MAILBOX_SETTINGS", "MODEL_SETTINGS", "Readiness", "readiness", "required"]

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
    name: str
    version: str
    missing: tuple[str, ...]
    problem: str | None

    @property
    def ready(self) -> bool:
        return not self.missing and self.problem is None


def readiness(agent: type[Agent], settings: Settings) -> Readiness:
    """Whether ``agent`` could start with ``settings``: the settings it
    misses, or what its preparation found wrong."""
    missing = tuple(settings.missing(required(agent)))
    problem = None
    if not missing:
        try:
            agent(settings).prepare()
        except (ConfigError, ContractError) as exc:
            problem = exc.message
    return Readiness(agent.name, agent.version, missing, problem)
