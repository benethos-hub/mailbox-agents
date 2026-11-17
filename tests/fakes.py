"""Stand-ins for the two upstreams, served through ``httpx.MockTransport``.

:class:`FakeService` answers the REST paths of the mailbox service the
package uses, from messages kept in its wire format, and applies the
updates it is sent. :class:`FakeGateway` answers chat completions from a
queue of answers. Both record every request, so a test can say what was
asked. Nothing here reaches a network.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib.parse import unquote

import httpx

ACCOUNT = "acc1"

FOLDERS = [
    {"id": "inbox", "name": "INBOX", "role": "inbox"},
    {"id": "sent", "name": "Sent", "role": "sent"},
    {"id": "trash", "name": "Trash", "role": "trash"},
    {"id": "inv", "name": "Invoices", "role": None},
    {"id": "inv-hosting", "name": "Hosting", "role": None, "parent_id": "inv"},
    {"id": "inv-mo", "name": "mo", "role": None, "parent_id": "inv"},
]


def wire_message(
    message_id: str,
    *,
    account_id: str = ACCOUNT,
    folder_ids: list[str] | None = None,
    subject: str | None = "Hello",
    sender: str | None = "someone@example.test",
    sender_name: str | None = None,
    to: list[str] | None = None,
    text: str | None = "Hello.",
    attachments: list[dict[str, Any]] | None = None,
    thread_id: str | None = None,
    keywords: list[str] | None = None,
    date: str = "2026-11-17T08:00:00+00:00",
) -> dict[str, Any]:
    """A message as the service answers ``get_message``."""
    return {
        "id": message_id,
        "account_id": account_id,
        "thread_id": thread_id,
        "folder_ids": folder_ids if folder_ids is not None else ["inbox"],
        "subject": subject,
        "from": {"email": sender, "name": sender_name} if sender else None,
        "to": [{"email": a} for a in (to or ["me@example.test"])],
        "cc": [],
        "bcc": [],
        "reply_to": [],
        "date": date,
        "received": date,
        "snippet": None,
        "unread": True,
        "starred": False,
        "keywords": list(keywords or []),
        "has_attachments": bool(attachments),
        "message_id_header": f"<{message_id}@example.test>",
        "in_reply_to": None,
        "text_body": text,
        "html_body": None,
        "attachments": [
            {"id": f"att{i}", "size": 1000, "inline": False, **a}
            for i, a in enumerate(attachments or [])
        ],
    }


def _error(status: int, code: str, message: str = "refused") -> httpx.Response:
    return httpx.Response(status, json={"error": {"code": code, "message": message}})


class FakeService:
    """The mailbox service, as far as this package uses it."""

    def __init__(self) -> None:
        self.folders: dict[str, list[dict[str, Any]]] = {
            ACCOUNT: [dict(f) for f in FOLDERS]
        }
        self.messages: dict[tuple[str, str], dict[str, Any]] = {}
        self.feed: list[dict[str, Any]] = []
        self.expired: set[str] = set()
        self.down = False
        # Status and code every request is refused with while set.
        self.refusal: tuple[int, str] | None = None
        self.requests: list[httpx.Request] = []

    # -- filling ---------------------------------------------------------------

    def add(
        self, message: dict[str, Any], change: str | None = "message.created"
    ) -> None:
        """Keep ``message`` and, unless ``change`` is None, put it in the feed."""
        key = (message["account_id"], message["id"])
        self.messages[key] = message
        if change:
            self.change(change, message["id"], message["account_id"])

    def change(self, kind: str, message_id: str, account_id: str = ACCOUNT) -> None:
        self.feed.append(
            {
                "type": kind,
                "id": message_id,
                "account_id": account_id,
                "at": "2026-11-17T08:00:00+00:00",
            }
        )

    @property
    def state(self) -> str:
        return str(len(self.feed))

    def writes(self) -> list[tuple[str, dict[str, Any]]]:
        """The PATCH requests sent, as path and body."""
        return [
            (unquote(r.url.path), json.loads(r.content))
            for r in self.requests
            if r.method == "PATCH"
        ]

    # -- answering ---------------------------------------------------------------

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.down:
            return _error(503, "unavailable")
        if self.refusal:
            return _error(*self.refusal)
        parts = [unquote(p) for p in request.url.path.split("/")[2:]]
        route: Callable[[httpx.Request, list[str]], httpx.Response] | None = {
            ("GET", "changes"): self._changes,
            ("GET", "messages"): self._list,
            ("GET", "folders"): self._folders,
            ("GET", "message"): self._message,
            ("GET", "thread"): self._thread,
            ("PATCH", "message"): self._update,
        }.get((request.method, _kind(parts)))
        if route is None:
            return _error(404, "not_found", "no such path")
        return route(request, parts)

    def _changes(self, request: httpx.Request, parts: list[str]) -> httpx.Response:
        since = request.url.params.get("since")
        if since is None:
            return httpx.Response(200, json={"changes": [], "state": self.state})
        if since in self.expired:
            return _error(410, "changes_expired", "too old")
        start = int(since)
        limit = int(request.url.params.get("limit", "200"))
        chunk = self.feed[start : start + limit]
        end = start + len(chunk)
        return httpx.Response(
            200,
            json={"changes": chunk, "state": str(end), "more": end < len(self.feed)},
        )

    def _list(self, request: httpx.Request, parts: list[str]) -> httpx.Response:
        items = sorted(self.messages.values(), key=lambda m: m["id"])
        cursor = int(request.url.params.get("cursor", "0"))
        limit = int(request.url.params.get("limit", "200"))
        page = items[cursor : cursor + limit]
        more = cursor + limit < len(items)
        return httpx.Response(
            200,
            json={
                "items": page,
                "next_cursor": str(cursor + limit) if more else None,
            },
        )

    def _folders(self, request: httpx.Request, parts: list[str]) -> httpx.Response:
        return httpx.Response(200, json=self.folders.get(parts[1], []))

    def _message(self, request: httpx.Request, parts: list[str]) -> httpx.Response:
        found = self.messages.get((parts[1], parts[3]))
        if found is None:
            return _error(404, "not_found", "no such message")
        return httpx.Response(200, json=found)

    def _thread(self, request: httpx.Request, parts: list[str]) -> httpx.Response:
        account, thread = parts[1], parts[3]
        members = sorted(
            (
                m
                for (a, _), m in self.messages.items()
                if a == account and m.get("thread_id") == thread
            ),
            key=lambda m: m["date"],
        )
        if not members:
            return _error(404, "not_found", "no such thread")
        return httpx.Response(
            200,
            json={
                "id": thread,
                "account_id": account,
                "subject": members[-1]["subject"],
                "participants": [],
                "message_count": len(members),
                "unread_count": 0,
                "date": members[-1]["date"],
                "snippet": None,
                "folder_ids": [],
                "truncated": False,
                "messages": members,
            },
        )

    def _update(self, request: httpx.Request, parts: list[str]) -> httpx.Response:
        found = self.messages.get((parts[1], parts[3]))
        if found is None:
            return _error(404, "not_found", "no such message")
        body = json.loads(request.content)
        keywords = [
            k for k in found["keywords"] if k not in body.get("remove_keywords", [])
        ]
        keywords += [k for k in body.get("add_keywords", []) if k not in keywords]
        found["keywords"] = keywords
        if "folder_ids" in body:
            found["folder_ids"] = list(body["folder_ids"])
        return httpx.Response(200, json=found)


def _kind(parts: list[str]) -> str:
    """Which route ``parts``, the path below /v1, names."""
    if parts == ["changes"]:
        return "changes"
    if parts == ["messages"]:
        return "messages"
    if len(parts) == 3 and parts[0] == "accounts" and parts[2] == "folders":
        return "folders"
    if len(parts) == 4 and parts[0] == "accounts" and parts[2] == "messages":
        return "message"
    if len(parts) == 4 and parts[0] == "accounts" and parts[2] == "threads":
        return "thread"
    return ""


class FakeGateway:
    """An OpenAI-compatible chat completions endpoint with queued answers.

    An answer is a dict, sent as the JSON content of the message, a string,
    sent as the content as it is, or an ``httpx.Response``, sent whole.
    """

    def __init__(self, model: str = "reported-model") -> None:
        self.model = model
        self.answers: list[dict[str, Any] | str | httpx.Response] = []
        self.requests: list[httpx.Request] = []

    def answer(self, *answers: dict[str, Any] | str | httpx.Response) -> None:
        self.answers.extend(answers)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def bodies(self) -> list[dict[str, Any]]:
        return [json.loads(r.content) for r in self.requests]

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404, json={"error": {"message": "no such path"}})
        if not self.answers:
            return httpx.Response(503, json={"error": {"message": "no answer queued"}})
        found = self.answers.pop(0)
        if isinstance(found, httpx.Response):
            return found
        content = found if isinstance(found, str) else json.dumps(found)
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-1",
                "model": self.model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 120, "completion_tokens": 15},
            },
        )
