"""The agent inquiries: the label, its evaluation, and later its fields."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from benethos_mailbox_agent.agents.inquiries.agent import Inquiries
from benethos_mailbox_agent.agents.inquiries.patterns import DATE, RATE, load_patterns
from benethos_mailbox_agent.errors import ConfigError
from benethos_mailbox_agent.evaluation.gold import load_gold
from benethos_mailbox_agent.evaluation.report import build
from benethos_mailbox_agent.evaluation.run import evaluate
from benethos_mailbox_agent.records import MailMessage, MessageRef
from benethos_mailbox_agent.runtime.loop import Worker
from fakes import ACCOUNT, invented
from helpers import Wired, settings, wired

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(__file__).resolve().parent / "data"
PATTERNS = ROOT / "config" / "benethos-mailbox-agent" / "inquiries.example.json"
MESSAGES = {m["id"]: m for m in invented("invented-inquiries.json")}


def agent(stage: str = "full", **values: Any) -> Inquiries:
    return Inquiries(settings(stage=stage, **values))


@pytest.fixture
async def world(tmp_path: Path) -> AsyncIterator[Wired]:
    async with wired(tmp_path) as found:
        for message in MESSAGES.values():
            found.service.add(message, change=None)
        yield found


def _message(message_id: str) -> MailMessage:
    raw = MESSAGES[message_id]
    return MailMessage.model_validate(
        {
            "ref": {"account_id": ACCOUNT, "message_id": message_id},
            "subject": raw["subject"],
            "sender": raw["from"],
            "text": raw["text_body"],
        }
    )


# -- the patterns and the rules ---------------------------------------------------


@pytest.mark.parametrize(
    ("text", "date", "rate"),
    [
        ("ab 01.02.2027", True, False),
        ("Start 2027-01-15", True, False),
        ("bis 95 EUR", False, True),
        ("90 €/h", False, True),
        ("EUR 700", False, True),
        ("Version 3.11", False, False),
    ],
)
def test_dates_and_rates(text: str, date: bool, rate: bool) -> None:
    assert bool(DATE.search(text)) is date
    assert bool(RATE.search(text)) is rate


def test_the_patterns_file(tmp_path: Path) -> None:
    found = load_patterns(PATTERNS)

    assert found.sender_known("jana@staffing.example")
    assert found.sender_known("x@eu.staffing.example")
    assert not found.sender_known("x@client.example")
    assert not found.sender_known(None)
    assert load_patterns(None).domains == ()

    broken = tmp_path / "p.json"
    broken.write_text('{"domains": [""]}', encoding="utf-8")
    with pytest.raises(ConfigError, match="ValidationError"):
        load_patterns(broken)
    with pytest.raises(ConfigError, match="cannot be read"):
        load_patterns(tmp_path / "none.json")


def test_the_baseline_on_the_invented_set() -> None:
    rules = agent(inquiries_patterns_file=PATTERNS)
    found = {
        item.message_id: rules.baseline(_message(item.message_id)).label
        for item in load_gold(DATA / "gold-inquiries.jsonl")
    }

    assert found == {
        "inq-staffing": "inquiry",
        "inq-direct": "inquiry",
        "inq-english": "inquiry",
        "job-digest": "other",
        "meeting": "other",
        "invoice": "other",
        "personal": "other",
    }


def test_a_wrong_patterns_file_stops_the_start(tmp_path: Path) -> None:
    broken = tmp_path / "p.json"
    broken.write_text("{", encoding="utf-8")

    with pytest.raises(ConfigError):
        agent(inquiries_patterns_file=broken).prepare()


# -- the label -----------------------------------------------------------------------


async def run(world: Wired, message_id: str) -> str:
    ref = MessageRef(account_id=ACCOUNT, message_id=message_id)
    worker = Worker(
        agent=agent(),
        store=world.store,
        mailbox=world.mailbox,
        gateway=world.gateway,
        now=world.clock,
    )
    world.store.enqueue(ref, world.clock())
    await worker.process_due()
    row = world.store.message(ref)
    assert row is not None
    return row.state


def keywords(world: Wired, message_id: str) -> list[str]:
    return world.service.messages[(ACCOUNT, message_id)]["keywords"]


async def test_an_inquiry_is_marked(world: Wired) -> None:
    world.fake_gateway.answer({"label": "inquiry", "quote": "suchen wir ab 01.02.2027"})

    assert await run(world, "inq-staffing") == "done"
    assert keywords(world, "inq-staffing") == ["inquiry"]


async def test_another_message_is_not(world: Wired) -> None:
    world.fake_gateway.answer({"label": "other", "quote": "10 neue Jobs für Sie"})

    assert await run(world, "job-digest") == "done"
    assert keywords(world, "job-digest") == []


async def test_a_label_without_its_quote_is_not_acted_on(world: Wired) -> None:
    world.fake_gateway.answer({"label": "inquiry", "quote": "a great project for you"})

    assert await run(world, "personal") == "decided"
    assert keywords(world, "personal") == []


async def test_the_label_has_an_evaluation_of_its_own(world: Wired) -> None:
    items = load_gold(DATA / "gold-inquiries.jsonl")
    quotes = {
        "inq-staffing": ("inquiry", "für einen Kunden aus der Logistik"),
        "inq-direct": ("inquiry", "wir suchen ab März 2027 Unterstützung"),
        "inq-english": ("inquiry", "we are looking for a Senior Python Engineer"),
        "job-digest": ("other", "10 neue Jobs für Sie"),
        "meeting": ("other", "Termin zum laufenden Projekt"),
        "invoice": ("other", "Anbei Ihre Rechnung"),
        "personal": ("inquiry", "Hast du am Samstag Zeit?"),
    }
    for item in items:
        label, quote = quotes[item.message_id]
        world.fake_gateway.answer({"label": label, "quote": quote})
    the_agent = agent(inquiries_patterns_file=PATTERNS)

    outcomes = await evaluate(
        the_agent,
        items,
        reader=world.mailbox,
        gateway=world.gateway,
        store=world.store,
        now=world.clock,
    )
    report = build(the_agent, "alias", outcomes, world.clock())

    model, rules = report["model"], report["baseline"]
    assert model["labels"]["inquiry"] == {
        "true_positive": 3,
        "false_positive": 1,
        "false_negative": 0,
        "precision": 0.75,
        "recall": 1.0,
    }
    assert rules["labels"]["inquiry"]["recall"] == 1.0
    assert rules["agreed"] == 7
