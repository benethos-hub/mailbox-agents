"""The mailbox service behind sources/mailbox.py, mocked."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date

import httpx
import pytest

from benethos_mailbox_agents.errors import (
    ChangesExpiredError,
    ConfigError,
    MailboxRefusedError,
    MailboxUnavailableError,
)
from benethos_mailbox_agents.records import MessageRef
from benethos_mailbox_agents.sources.mailbox import Mailbox, connect
from fakes import ACCOUNT, FakeService, wire_message

REF = MessageRef(account_id=ACCOUNT, message_id="m1")


@pytest.fixture
def service() -> FakeService:
    return FakeService()


@pytest.fixture
async def mailbox(service: FakeService) -> AsyncIterator[Mailbox]:
    async with connect(
        "https://mailbox.example.test", "token-value", transport=service.transport()
    ) as opened:
        yield opened


async def test_the_feed_from_a_state_with_pages_followed(
    service: FakeService, mailbox: Mailbox
) -> None:
    start = await mailbox.start()
    for number in range(450):
        service.change("message.created", f"m{number}")
    service.feed.append(
        {
            "type": "account.updated",
            "id": "x",
            "account_id": ACCOUNT,
            "at": "2026-11-17T08:00:00+00:00",
        }
    )

    events, state = await mailbox.changes(start)

    assert start == "0"
    assert len(events) == 450
    assert events[0].ref == MessageRef(account_id=ACCOUNT, message_id="m0")
    assert events[0].type == "message.created"
    assert state == "451"


async def test_an_expired_state_is_its_own_error(
    service: FakeService, mailbox: Mailbox
) -> None:
    service.expired.add("7")

    with pytest.raises(ChangesExpiredError):
        await mailbox.changes("7")


async def test_a_message_with_its_folders_by_path(
    service: FakeService, mailbox: Mailbox
) -> None:
    service.add(
        wire_message(
            "m1",
            folder_ids=["inv-hosting"],
            sender="billing@hosting.example.test",
            sender_name="Billing",
            attachments=[{"filename": "R-1.pdf", "content_type": "application/pdf"}],
            keywords=["$seen"],
        )
    )

    found = await mailbox.message(REF)

    assert found.folders[0].path == "Invoices/Hosting"
    assert found.sender is not None
    assert found.sender.domain == "hosting.example.test"
    assert found.attachments[0].filename == "R-1.pdf"
    assert found.keywords == ("$seen",)
    assert found.text == "Hello."


async def test_a_message_without_text_has_an_empty_one(
    service: FakeService, mailbox: Mailbox
) -> None:
    service.add(wire_message("m1", text=None, sender=None))

    found = await mailbox.message(REF)

    assert (found.text, found.sender) == ("", None)


async def test_a_new_folder_is_asked_for_again(
    service: FakeService, mailbox: Mailbox
) -> None:
    await mailbox.folders(ACCOUNT)
    service.folders[ACCOUNT].append({"id": "new", "name": "New", "role": None})

    found = await mailbox.folder_at(ACCOUNT, "New")

    assert found is not None and found.id == "new"
    assert await mailbox.folder_at(ACCOUNT, "Missing") is None


async def test_a_thread_oldest_first(service: FakeService, mailbox: Mailbox) -> None:
    service.add(wire_message("m2", thread_id="t", date="2026-11-18T08:00:00+00:00"))
    service.add(wire_message("m1", thread_id="t", folder_ids=["sent"]))

    found = await mailbox.thread(ACCOUNT, "t")

    assert [m.ref.message_id for m in found.messages] == ["m1", "m2"]
    assert found.messages[0].in_role("sent")


async def test_recent_follows_the_pages(service: FakeService, mailbox: Mailbox) -> None:
    for number in range(250):
        service.add(wire_message(f"m{number:03d}"), change=None)
    service.add(wire_message("s1", folder_ids=["sent"]), change=None)
    service.add(wire_message("x1", folder_ids=["inv"]), change=None)

    found = await mailbox.recent(date(2026, 11, 10), roles=("inbox", "sent"))

    assert len(found) == 251
    assert MessageRef(account_id=ACCOUNT, message_id="s1") in found
    asked = [r.url.params for r in service.requests if r.url.path == "/v1/messages"]
    assert [(p["folder"], p.get("cursor")) for p in asked] == [
        ("inbox", None),
        ("inbox", "200"),
        ("sent", None),
    ]
    assert asked[0]["after"] == "2026-11-10"


async def test_the_three_actions(service: FakeService, mailbox: Mailbox) -> None:
    service.add(wire_message("m1"))

    await mailbox.add_keyword(REF, "invoice")
    await mailbox.remove_keyword(REF, "old")
    await mailbox.move(REF, "inv-mo")

    assert service.writes() == [
        (f"/v1/accounts/{ACCOUNT}/messages/m1", {"add_keywords": ["invoice"]}),
        (f"/v1/accounts/{ACCOUNT}/messages/m1", {"remove_keywords": ["old"]}),
        (f"/v1/accounts/{ACCOUNT}/messages/m1", {"folder_ids": ["inv-mo"]}),
    ]
    assert service.messages[(ACCOUNT, "m1")]["folder_ids"] == ["inv-mo"]


async def test_a_folder_is_made_at_the_top_and_below_another(
    service: FakeService, mailbox: Mailbox
) -> None:
    top = await mailbox.create_folder(ACCOUNT, "Providers")
    below = await mailbox.create_folder(ACCOUNT, "Providers/CloudHost")

    assert service.made() == [
        {"name": "Providers"},
        {"name": "CloudHost", "parent_id": top.id},
    ]
    assert (top.path, below.path) == ("Providers", "Providers/CloudHost")
    found = await mailbox.folder_at(ACCOUNT, "Providers/CloudHost")
    assert found is not None and found.id == below.id


async def test_a_folder_below_a_missing_one_is_refused(
    service: FakeService, mailbox: Mailbox
) -> None:
    with pytest.raises(MailboxRefusedError) as raised:
        await mailbox.create_folder(ACCOUNT, "Missing/CloudHost")

    assert raised.value.reason == "parent_missing"
    assert raised.value.status is None
    assert service.made() == []


async def test_a_folder_that_exists_is_refused_by_the_service(
    mailbox: Mailbox,
) -> None:
    with pytest.raises(MailboxRefusedError) as raised:
        await mailbox.create_folder(ACCOUNT, "Invoices")

    assert (raised.value.status, raised.value.reason) == (409, "conflict")


async def test_a_refusal_carries_status_and_code(mailbox: Mailbox) -> None:
    with pytest.raises(MailboxRefusedError) as raised:
        await mailbox.message(REF)

    assert (raised.value.status, raised.value.reason) == (404, "not_found")


async def test_a_service_that_is_down_is_unavailable(
    service: FakeService, mailbox: Mailbox
) -> None:
    service.down = True

    with pytest.raises(MailboxUnavailableError):
        await mailbox.start()


@pytest.mark.parametrize(
    "failure",
    [httpx.ConnectError("refused"), httpx.ReadTimeout("slow")],
)
async def test_a_service_that_cannot_be_reached_is_unavailable(
    failure: httpx.TransportError,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise failure

    async with connect(
        "https://mailbox.example.test",
        "token-value",
        transport=httpx.MockTransport(handler),
    ) as mailbox:
        with pytest.raises(MailboxUnavailableError):
            await mailbox.start()


async def test_an_answer_of_the_wrong_shape_is_a_refusal() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    async with connect(
        "https://mailbox.example.test", "token-value", transport=transport
    ) as mailbox:
        with pytest.raises(MailboxRefusedError):
            await mailbox.start()


async def test_the_environment_sets_no_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example.test:3128")
    monkeypatch.setenv("ALL_PROXY", "http://proxy.example.test:3128")

    async with connect("https://mailbox.example.test", "token-value") as mailbox:
        http = mailbox._client._http

    assert http._mounts == {}
    assert isinstance(http._transport, httpx.AsyncHTTPTransport)


async def test_http_to_another_machine_needs_allowing() -> None:
    with pytest.raises(ConfigError, match="mailbox service"):
        async with connect("http://mailbox.example.test", "token-value"):
            pass

    async with connect(
        "http://mailbox.example.test", "token-value", allow_http=True
    ) as mailbox:
        assert isinstance(mailbox, Mailbox)


async def test_accounts_are_the_ids_the_user_is_granted(
    service: FakeService, mailbox: Mailbox
) -> None:
    service.folders["acc2"] = []

    assert await mailbox.accounts() == (ACCOUNT, "acc2")


async def test_recent_in_lists_one_folder_of_one_account(
    service: FakeService, mailbox: Mailbox
) -> None:
    service.add(wire_message("h1", folder_ids=["inv-hosting"]), change=None)
    service.add(wire_message("i1"), change=None)

    found = await mailbox.recent_in(ACCOUNT, "inv-hosting", date(2026, 11, 10))

    assert found == [MessageRef(account_id=ACCOUNT, message_id="h1")]
    (asked,) = [r for r in service.requests if r.url.path.endswith("/messages")]
    assert asked.url.path == f"/v1/accounts/{ACCOUNT}/messages"
    assert (asked.url.params["folder"], asked.url.params["after"]) == (
        "inv-hosting",
        "2026-11-10",
    )
