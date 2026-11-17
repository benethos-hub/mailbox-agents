"""The supplier list of invoices: format, loading, validation, matching."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benethos_mailbox_agent.agents.invoices.suppliers import (
    Kind,
    Suppliers,
    load_suppliers,
)
from benethos_mailbox_agent.errors import ConfigError

ROOT = Path(__file__).resolve().parent.parent

EXAMPLES = [
    ROOT / "config" / "benethos-mailbox-agent" / "suppliers.example.json",
    ROOT
    / "containers"
    / "production"
    / "agents"
    / "invoices"
    / "suppliers.example.json",
    ROOT / "containers" / "live" / "suppliers.json",
]


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.parent.name)
def test_every_versioned_example_loads(path: Path) -> None:
    assert load_suppliers(path).names == ("CloudHost", "Telco")


@pytest.fixture
def suppliers() -> Suppliers:
    return Suppliers.model_validate(
        {
            "suppliers": [
                {
                    "name": "CloudHost",
                    "folder": "CloudHost",
                    "senders": ["billing@cloudhost.example", "cloudhost.example"],
                },
                {
                    "name": "Telco",
                    "folder": "Phone/Telco",
                    "senders": ["mailbox*@telco.example", "@telco.example"],
                },
                {
                    "name": "Platform",
                    "folder": "Platform",
                    "senders": ["billing@platform.example"],
                },
                {
                    "name": "Shared",
                    "folder": "Shared",
                    "senders": ["shared.example"],
                },
                {
                    "name": "Shared too",
                    "folder": "Shared too",
                    "senders": ["@shared.example"],
                },
            ]
        }
    )


@pytest.mark.parametrize(
    ("address", "supplier", "kind"),
    [
        ("billing@cloudhost.example", "CloudHost", Kind.ADDRESS),
        ("Billing@CloudHost.Example", "CloudHost", Kind.ADDRESS),
        ("noreply@cloudhost.example", "CloudHost", Kind.DOMAIN),
        ("noreply@eu.cloudhost.example", "CloudHost", Kind.DOMAIN),
        ("mailbox7f3a9@telco.example", "Telco", Kind.PATTERN),
        ("service@telco.example", "Telco", Kind.DOMAIN),
    ],
)
def test_a_sender_is_matched_by_its_most_specific_rule(
    suppliers: Suppliers, address: str, supplier: str, kind: Kind
) -> None:
    found = suppliers.match(address)

    assert found is not None
    assert (found.supplier.name, found.kind) == (supplier, kind)


@pytest.mark.parametrize(
    "address",
    [
        "billing@notcloudhost.example",
        "cloudhost.example@evil.example",
        "someone@shared.example",
        "",
        None,
    ],
    ids=["other-domain", "domain-in-local-part", "two-suppliers", "empty", "none"],
)
def test_no_match_is_guessed(suppliers: Suppliers, address: str | None) -> None:
    assert suppliers.match(address) is None


def test_names_and_lookup(suppliers: Suppliers) -> None:
    assert suppliers.names[:2] == ("CloudHost", "Telco")
    supplier = suppliers.named("Telco")
    assert supplier is not None and supplier.folder == "Phone/Telco"
    assert suppliers.named("Nobody") is None


def _write(tmp_path: Path, content: object, name: str = "suppliers.json") -> Path:
    path = tmp_path / name
    text = content if isinstance(content, str) else json.dumps(content)
    path.write_text(text, encoding="utf-8")
    return path


def _entry(**changes: object) -> dict[str, object]:
    return {"name": "A", "folder": "A", "senders": ["a@a.example"], **changes}


@pytest.mark.parametrize(
    ("content", "said"),
    [
        ("{not json", "JSONDecodeError"),
        ({"suppliers": [_entry(senders=[])]}, "senders"),
        ({"suppliers": [_entry(senders=["not a sender"])]}, "no address"),
        ({"suppliers": [_entry(folder="../escape")]}, "folder"),
        ({"suppliers": [_entry(folder="A//B")]}, "folder"),
        ({"suppliers": [_entry(name=" A")]}, "space"),
        ({"suppliers": [_entry(), _entry(folder="B")]}, "share the name"),
        ({"suppliers": [_entry(), _entry(name="B")]}, "share the folder"),
        (
            {"suppliers": [_entry(), _entry(name="B", folder="B")]},
            "is named by 'A' and 'B'",
        ),
        ({"suppliers": [], "extra": 1}, "extra"),
    ],
)
def test_a_wrong_list_is_named(tmp_path: Path, content: object, said: str) -> None:
    with pytest.raises(ConfigError, match=said):
        load_suppliers(_write(tmp_path, content))


def test_another_format_is_refused_by_name(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="is no .json file"):
        load_suppliers(_write(tmp_path, "suppliers = []", "suppliers.toml"))


def test_a_missing_list_is_named(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot be read"):
        load_suppliers(tmp_path / "none.json")
