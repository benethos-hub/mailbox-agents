"""The evidence check of SPECS.md section 11."""

from __future__ import annotations

import pytest

from benethos_mailbox_agent.llm.evidence import check, contains, normalize
from benethos_mailbox_agent.records import LABEL, Decision, Evidence

NBSP = chr(0xA0)

CONTENT = (
    "Subject: Ihre Rechnung\n\n"
    "Sehr geehrte Damen und Herren,\n\n"
    f"anbei  die\tRechnung{NBSP}Nr. 4711 vom 01.11.2026."
)


def test_whitespace_is_made_uniform() -> None:
    assert normalize(f"  a\n\n b\t{NBSP}c  ") == "a b c"


@pytest.mark.parametrize(
    ("quote", "found"),
    [
        ("anbei die Rechnung Nr. 4711", True),
        ("anbei\ndie   Rechnung", True),
        ("  Ihre Rechnung  ", True),
        ("ihre rechnung", False),
        ("Rechnung Nr. 4712", False),
        ("", False),
        ("   ", False),
    ],
)
def test_a_quote_is_looked_up(quote: str, found: bool) -> None:
    assert contains(CONTENT, quote) is found


def _decision(*evidence: Evidence, **fields: str) -> Decision:
    return Decision(label="invoice", source="model", fields=fields, evidence=evidence)


def test_a_found_label_and_field_stay() -> None:
    decided = check(
        _decision(
            Evidence(field=LABEL, value="invoice", quote="Ihre Rechnung"),
            Evidence(field="number", value="4711", quote="Nr. 4711"),
            number="4711",
        ),
        CONTENT,
    )

    assert decided.actionable
    assert decided.fields == {"number": "4711"}
    assert all(item.found for item in decided.evidence)


def test_a_field_whose_quote_is_not_found_is_dropped() -> None:
    decided = check(
        _decision(
            Evidence(field=LABEL, value="invoice", quote="Ihre Rechnung"),
            Evidence(field="number", value="9999", quote="Nr. 9999"),
            number="9999",
        ),
        CONTENT,
    )

    assert decided.actionable
    assert decided.fields == {}
    assert [item.found for item in decided.evidence] == [True, False]


def test_a_field_without_a_quote_is_dropped() -> None:
    label = Evidence(field=LABEL, value="invoice", quote="Ihre Rechnung")

    decided = check(_decision(label, date="x"), CONTENT)

    assert decided.fields == {}


def test_a_label_whose_quote_is_not_found_is_refused() -> None:
    decided = check(
        _decision(Evidence(field=LABEL, value="invoice", quote="Your invoice")),
        CONTENT,
    )

    assert decided.refused == "evidence"
    assert not decided.actionable


def test_a_label_without_any_quote_is_refused() -> None:
    assert check(_decision(), CONTENT).refused == "evidence"


def test_an_earlier_refusal_is_kept() -> None:
    decided = _decision(
        Evidence(field=LABEL, value="invoice", quote="Ihre Rechnung")
    ).model_copy(update={"refused": "limit"})

    assert check(decided, CONTENT).refused == "limit"
