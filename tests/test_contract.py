"""The agent contract and the registry."""

from __future__ import annotations

import importlib
import re
import textwrap
import uuid
from pathlib import Path
from typing import Any

import pytest

from benethos_mailbox_agent.contract import (
    REVERSED_BY,
    Action,
    ActionRequest,
    Agent,
    Context,
    Limits,
    Requires,
    Route,
    Trigger,
    discover,
    load,
)
from benethos_mailbox_agent.errors import ContractError
from benethos_mailbox_agent.records import Decision, Event, MailMessage
from benethos_mailbox_agent.settings import Settings

ROOT = Path(__file__).resolve().parent.parent


class Sample(Agent):
    name = "sample"
    version = "1"
    description = "an agent for the tests"
    triggers = Trigger(events=frozenset({"message.created"}))
    actions = frozenset({Action.ADD_KEYWORD})
    default_keyword = "sample"

    def select(self, event: Event) -> Route | None:
        return Route.DECIDE

    def baseline(self, message: MailMessage) -> Decision:
        return Decision(label="other", source="baseline")

    async def decide(self, message: MailMessage, context: Context) -> Decision:
        return Decision(label="other", source="model")

    async def effect(
        self, decision: Decision, message: MailMessage, context: Context
    ) -> list[ActionRequest]:
        return []


def _variant(**attributes: Any) -> type[Agent]:
    return type("Variant", (Sample,), attributes)


def test_a_valid_agent_takes_its_keyword_from_the_settings() -> None:
    assert Sample(Settings()).keyword == "sample"
    assert Sample(Settings(keyword="mine")).keyword == "mine"


async def test_the_defaults_of_the_optional_methods() -> None:
    agent = Sample(Settings())
    message = MailMessage.model_validate(
        {"ref": {"account_id": "a", "message_id": "m"}}
    )
    context: Any = None

    assert agent.admit(message)
    assert await agent.observe(message, context) == []
    assert agent.prepare() is None


@pytest.mark.parametrize(
    ("attributes", "complaint"),
    [
        ({"name": "Not-Valid"}, "lowercase"),
        ({"version": ""}, "must not be empty"),
        ({"triggers": Trigger(events=frozenset({"message.read"}))}, "unknown events"),
        ({"triggers": Trigger(events=frozenset())}, "no event and no tick"),
        ({"actions": {Action.ADD_KEYWORD}}, "actions"),
        ({"actions": frozenset({"delete"})}, "actions"),
        ({"limits": Limits(model_calls_per_message=-1)}, "negative"),
        ({"requires": Requires(settings=("no_such",))}, "unknown settings"),
        ({"default_keyword": "two words"}, "one word"),
    ],
)
def test_a_wrong_declaration_is_refused(
    attributes: dict[str, Any], complaint: str
) -> None:
    with pytest.raises(ContractError, match=complaint):
        _variant(**attributes)(Settings())


def test_a_missing_declaration_is_named() -> None:
    class Bare(Agent):
        def select(self, event: Event) -> Route | None:
            return None

        def baseline(self, message: MailMessage) -> Decision:
            raise NotImplementedError

        async def decide(self, message: MailMessage, context: Context) -> Decision:
            raise NotImplementedError

        async def effect(
            self, decision: Decision, message: MailMessage, context: Context
        ) -> list[ActionRequest]:
            raise NotImplementedError

    with pytest.raises(ContractError, match="name must be declared"):
        Bare(Settings())


def test_every_action_has_a_way_back() -> None:
    assert set(REVERSED_BY) == set(Action)


def test_the_actions_of_specs_section_7_are_the_code() -> None:
    text = (ROOT / "SPECS.md").read_text(encoding="utf-8")
    section = text[text.index("\n## 7. ") : text.index("\n## 8. ")]
    table = section[section.index("| Action |") :]
    named = re.findall(r"^\| `([a-z_]+)` \|", table, flags=re.MULTILINE)

    assert set(named) == {action.value for action in Action}


AGENT_SOURCE = """
from benethos_mailbox_agent.contract import Action, Agent, Route, Trigger
from benethos_mailbox_agent.records import Decision


class {cls}(Agent):
    name = "{name}"
    version = "1"
    description = "found by the registry"
    triggers = Trigger(events=frozenset(), tick=True)
    actions = frozenset({{Action.ADD_KEYWORD}})
    default_keyword = "x"

    def select(self, event):
        return None

    def baseline(self, message):
        return Decision(label="x", source="baseline")

    async def decide(self, message, context):
        return Decision(label="x", source="model")

    async def effect(self, decision, message, context):
        return []
"""


@pytest.fixture
def package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """A package of agents in a temporary folder, importable by its name."""
    package_name = f"fake_agents_{uuid.uuid4().hex}"
    root = tmp_path / package_name
    root.mkdir()
    (root / "__init__.py").write_text("", encoding="utf-8")
    for name in ("beta", "alpha"):
        (root / name).mkdir()
        (root / name / "__init__.py").write_text("", encoding="utf-8")
        (root / name / "agent.py").write_text(
            AGENT_SOURCE.format(cls=name.title(), name=name), encoding="utf-8"
        )
    (root / "_private").mkdir()
    (root / "half").mkdir()
    (root / "half" / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    return package_name


def test_the_registry_finds_every_agent_by_name(package: str) -> None:
    assert list(discover(package)) == ["alpha", "beta"]
    assert load("beta", package).name == "beta"


def test_an_unknown_agent_names_those_there_are(package: str) -> None:
    with pytest.raises(ContractError, match="there are: alpha, beta"):
        load("gamma", package)


def test_a_module_with_two_agents_is_refused(
    package: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = AGENT_SOURCE.format(cls="One", name="two")
    source += textwrap.dedent(AGENT_SOURCE.format(cls="Two", name="two"))
    (tmp_path / package / "two").mkdir()
    (tmp_path / package / "two" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / package / "two" / "agent.py").write_text(source, encoding="utf-8")

    importlib.invalidate_caches()

    with pytest.raises(ContractError, match="defines 2 agent classes"):
        discover(package)


def test_a_name_unlike_its_package_is_refused(package: str, tmp_path: Path) -> None:
    (tmp_path / package / "gamma").mkdir()
    (tmp_path / package / "gamma" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / package / "gamma" / "agent.py").write_text(
        AGENT_SOURCE.format(cls="Gamma", name="delta"), encoding="utf-8"
    )

    importlib.invalidate_caches()

    with pytest.raises(ContractError, match="differs from its package"):
        discover(package)


def test_sample_has_no_tick_by_default() -> None:
    assert Sample.triggers.tick is False
    assert isinstance(Sample.actions, frozenset)
