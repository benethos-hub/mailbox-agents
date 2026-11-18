"""The list of sorting: format, loading, validation, matching."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from benethos_mailbox_agents.agents.sorting.groups import Groups, Kind, load_groups
from benethos_mailbox_agents.errors import ConfigError


def groups(*entries: dict[str, Any]) -> Groups:
    return Groups.model_validate({"groups": list(entries)})


@pytest.fixture
def listed() -> Groups:
    return groups(
        {
            "name": "Bank",
            "folder": "Providers/Bank",
            "senders": ["service@bank-two.example", "*@bank-one.example"],
            "hold": True,
        },
        {
            "name": "CloudHost",
            "folder": "Providers/CloudHost",
            "senders": ["*@cloudhost.example", "mailbox*@telco.example"],
        },
        {
            "name": "Shop",
            "folder": "Shop",
            "senders": ["*@*.shop.example", "Orders@Shop.Example"],
        },
    )


@pytest.mark.parametrize(
    ("address", "group", "kind"),
    [
        ("service@bank-two.example", "Bank", Kind.ADDRESS),
        ("anyone@bank-one.example", "Bank", Kind.PATTERN),
        ("mailbox7@telco.example", "CloudHost", Kind.PATTERN),
        ("billing@cloudhost.example", "CloudHost", Kind.PATTERN),
        ("news@eu.shop.example", "Shop", Kind.SUBDOMAINS),
        ("news@a.b.shop.example", "Shop", Kind.SUBDOMAINS),
        ("ORDERS@shop.example", "Shop", Kind.ADDRESS),
    ],
)
def test_a_sender_finds_its_group(
    listed: Groups, address: str, group: str, kind: Kind
) -> None:
    found = listed.match(address)

    assert found is not None and found.group is not None
    assert (found.group.name, found.kind) == (group, kind)


@pytest.mark.parametrize(
    "address",
    [
        "billing@eu.cloudhost.example",  # a pattern covers one domain
        "news@shop.example",  # a pattern for subdomains not the domain
        "info@telco.example",
        "someone@elsewhere.example",
        "",
        None,
    ],
)
def test_a_sender_in_no_group(listed: Groups, address: str | None) -> None:
    assert listed.match(address) is None


def test_an_address_wins_over_a_pattern() -> None:
    found = groups(
        {"name": "A", "folder": "A", "senders": ["*@telco.example"]},
        {"name": "B", "folder": "B", "senders": ["billing@telco.example"]},
    ).match("billing@telco.example")

    assert found is not None and found.group is not None
    assert found.group.name == "B"


def test_a_pattern_wins_over_one_for_subdomains() -> None:
    found = groups(
        {"name": "A", "folder": "A", "senders": ["*@*.shop.example"]},
        {"name": "B", "folder": "B", "senders": ["*@eu.shop.example"]},
    ).match("news@eu.shop.example")

    assert found is not None and found.group is not None
    assert found.group.name == "B"


def test_two_groups_alike_leave_the_sender_to_none() -> None:
    found = groups(
        {"name": "A", "folder": "A", "senders": ["*@telco.example"]},
        {"name": "B", "folder": "B", "senders": ["bill*@telco.example"]},
    ).match("billing@telco.example")

    assert found is not None
    assert found.group is None
    assert [g.name for g in found.groups] == ["A", "B"]


def test_the_folders_a_group_may_have_made(listed: Groups) -> None:
    assert listed.may_create("Providers")
    assert listed.may_create("Providers/Bank")
    assert listed.may_create("Shop")
    assert not listed.may_create("Providers/Other")
    assert not listed.may_create("providers")
    assert not listed.may_create("Elsewhere")


def test_a_group_is_moved_unless_it_is_held(listed: Groups) -> None:
    assert [g.hold for g in listed.groups] == [True, False, False]


@pytest.mark.parametrize(
    ("entries", "says"),
    [
        ([{"name": "", "folder": "A", "senders": ["a@b.example"]}], "name"),
        ([{"name": " A", "folder": "A", "senders": ["a@b.example"]}], "space"),
        (
            [
                {"name": "A", "folder": "A", "senders": ["a@b.example"]},
                {"name": "a", "folder": "B", "senders": ["c@b.example"]},
            ],
            "share the name",
        ),
        (
            [
                {"name": "A", "folder": "Same", "senders": ["a@b.example"]},
                {"name": "B", "folder": "same", "senders": ["c@b.example"]},
            ],
            "share the folder",
        ),
        ([{"name": "A", "folder": "A//B", "senders": ["a@b.example"]}], "none empty"),
        ([{"name": "A", "folder": "A/..", "senders": ["a@b.example"]}], "none empty"),
        ([{"name": "A", "folder": "A/ B", "senders": ["a@b.example"]}], "none empty"),
        ([{"name": "A", "folder": "A", "senders": []}], "senders"),
        (
            [
                {"name": "A", "folder": "A", "senders": ["a@b.example"]},
                {"name": "B", "folder": "B", "senders": ["A@b.example"]},
            ],
            "named by",
        ),
        ([{"name": "A", "folder": "A", "senders": ["b.example"]}], "*@b.example"),
        ([{"name": "A", "folder": "A", "senders": ["@b.example"]}], "*@*.b.example"),
        ([{"name": "A", "folder": "A", "senders": ["*@*.example"]}], "too broad"),
        ([{"name": "A", "folder": "A", "senders": ["*@b*.example"]}], "no address"),
        ([{"name": "A", "folder": "A", "senders": ["nobody"]}], "no address"),
        (
            [{"name": "A", "folder": "A", "senders": ["a@b.example"], "hold": "yes"}],
            "hold",
        ),
        (
            [{"name": "A", "folder": "A", "senders": ["a@b.example"], "color": 1}],
            "color",
        ),
    ],
)
def test_a_wrong_list_says_what_is_wrong(
    tmp_path: Path, entries: list[dict[str, Any]], says: str
) -> None:
    path = tmp_path / "sorting.json"
    path.write_text(json.dumps({"groups": entries}), encoding="utf-8")

    with pytest.raises(ConfigError, match="sorting.json") as raised:
        load_groups(path)

    assert says in raised.value.message


def test_a_list_is_read_from_its_file(tmp_path: Path) -> None:
    path = tmp_path / "sorting.json"
    entry = {"name": "Bank", "folder": "Bank", "senders": ["*@bank-one.example"]}
    path.write_text(json.dumps({"groups": [entry]}), encoding="utf-8")

    assert [g.name for g in load_groups(path).groups] == ["Bank"]


def test_a_list_that_is_no_json_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "sorting.json"
    path.write_text("{groups: [", encoding="utf-8")

    with pytest.raises(ConfigError, match="sorting.json"):
        load_groups(path)


def test_a_list_of_another_format_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "sorting.yaml"
    path.write_text("groups: []", encoding="utf-8")

    with pytest.raises(ConfigError, match="no .json file"):
        load_groups(path)


def test_a_list_that_cannot_be_read_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot be read"):
        load_groups(tmp_path / "missing.json")
