"""Where invoices looks, and where an invoice goes: the three settings."""

from __future__ import annotations

import pytest

from benethos_mailbox_agent.agents.invoices.folders import Places
from benethos_mailbox_agent.errors import ConfigError
from benethos_mailbox_agent.records import FolderRef
from benethos_mailbox_agent.settings import Settings


def folder(path: str, role: str | None = None) -> FolderRef:
    return FolderRef(id=path, name=path.rpartition("/")[2], role=role, path=path)


INBOX = folder("INBOX", "inbox")


def places(
    *folders: str, subfolder: str | None = None, inbox: str | None = None
) -> Places:
    return Places.read(list(folders), subfolder, inbox)


def test_unset_it_looks_in_the_inbox_alone() -> None:
    found = places()

    assert found.looks_in(INBOX)
    assert not found.looks_in(folder("Providers"))
    assert found.target(INBOX) is None
    assert found.needed() == ()


def test_a_named_folder_and_none_below_it() -> None:
    found = places("Providers/CloudHost")

    assert found.looks_in(folder("Providers/CloudHost"))
    assert not found.looks_in(folder("Providers/CloudHost/Rechnungen"))
    assert not found.looks_in(folder("Providers"))
    assert not found.looks_in(folder("providers/cloudhost"))


def test_parent_star_is_every_folder_directly_below() -> None:
    found = places("Providers/*")

    assert found.looks_in(folder("Providers/CloudHost"))
    assert found.looks_in(folder("Providers/Made-later"))
    assert not found.looks_in(folder("Providers"))
    assert not found.looks_in(folder("Providers/CloudHost/Rechnungen"))
    assert not found.looks_in(folder("Other/CloudHost"))
    assert found.needed() == ("Providers",)


def test_star_is_every_folder_at_the_top_without_a_role() -> None:
    found = places("*")

    assert found.looks_in(folder("Hosting"))
    assert found.looks_in(folder("My own"))
    assert not found.looks_in(folder("Hosting/Rechnungen"))
    for role in ("sent", "drafts", "trash", "junk", "archive", "all"):
        assert not found.looks_in(folder("Something", role))


def test_a_named_folder_with_a_role_is_looked_in_unless_it_is_the_trash() -> None:
    found = places("Archive", "Trash")

    assert found.looks_in(folder("Archive", "archive"))
    assert not found.looks_in(folder("Trash", "trash"))


def test_the_subfolder_below_the_folder_a_message_lies_in() -> None:
    found = places("Providers/*", subfolder="{folder}/Rechnungen/Eingang")

    assert found.target(folder("Providers/Hosting")) == (
        "Providers/Hosting/Rechnungen/Eingang"
    )
    assert found.target(INBOX) is None
    assert found.may_create("Providers/Hosting/Rechnungen")
    assert found.may_create("Providers/Hosting/Rechnungen/Eingang")
    assert not found.may_create("Providers/Hosting")
    assert not found.may_create("Other/Hosting/Rechnungen")
    assert not found.may_create("INBOX/Rechnungen")
    assert not found.may_create("Providers/Hosting/Other")


def test_without_a_subfolder_nothing_is_made() -> None:
    found = places("*")

    assert found.target(folder("Hosting")) is None
    assert not found.may_create("Hosting/Rechnungen")


def test_the_inbox_folder_is_needed_and_not_made() -> None:
    found = places("Providers/CloudHost", inbox="Rechnungen/Eingang")

    assert found.target(INBOX) == "Rechnungen/Eingang"
    assert found.needed() == ("Providers/CloudHost", "Rechnungen/Eingang")
    assert not found.may_create("Rechnungen/Eingang")


@pytest.mark.parametrize(
    ("folders", "subfolder", "inbox", "says"),
    [
        (["Providers//CloudHost"], None, None, "INVOICES_FOLDERS"),
        (["Providers/*/x"], None, None, "INVOICES_FOLDERS"),
        (["../x"], None, None, "INVOICES_FOLDERS"),
        ([], "Rechnungen", None, "does not start with {folder}/"),
        ([], "{folder}/", None, "INVOICES_SUBFOLDER"),
        ([], "{folder}/a/{folder}", None, "INVOICES_SUBFOLDER"),
        ([], None, "a/ b", "INVOICES_INBOX_FOLDER"),
    ],
)
def test_a_wrong_setting_says_what_is_wrong(
    folders: list[str], subfolder: str | None, inbox: str | None, says: str
) -> None:
    with pytest.raises(ConfigError) as raised:
        Places.read(folders, subfolder, inbox)

    assert says in raised.value.message


def test_the_folders_come_comma_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAILBOX_AGENT_INVOICES_FOLDERS", "Providers/*, *,Archive")

    assert Settings().invoices_folders == ["Providers/*", "*", "Archive"]
