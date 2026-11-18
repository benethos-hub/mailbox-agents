"""The mailbox service: the only module that imports benethos_mailbox_client.

It offers what the agents need of the service and nothing else: the change
feed, the messages of the last days for a backfill, a message, a thread,
the folders, a keyword set or taken off, and a move. There is no way here
to send, delete, trash or create a folder, so the runtime cannot do any of
it whatever an agent asks. Every answer is
turned into a record of :mod:`records`, and every failure into an error of
:mod:`errors`. See SPECS.md section 5.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Iterable
from contextlib import asynccontextmanager
from datetime import date
from types import TracebackType
from typing import TypeVar

import httpx
from benethos_mailbox_client import (
    ApiError,
    ConfigurationError,
    MailboxClient,
    MailboxError,
    ServiceTimeoutError,
    ServiceUnavailableError,
)
from benethos_mailbox_client import models as wire

from ..errors import (
    ChangesExpiredError,
    ConfigError,
    MailboxRefusedError,
    MailboxUnavailableError,
)
from ..records import (
    Address,
    Attachment,
    Event,
    FolderRef,
    MailMessage,
    MessageRef,
    Thread,
)

__all__ = ["Mailbox", "connect"]

T = TypeVar("T")

# The size of one page of the feed and of a message list.
_PAGE = 200


async def _call(pending: Awaitable[T]) -> T:
    """Await a call of the client and translate what it raises."""
    try:
        return await pending
    except ApiError as exc:
        if exc.status == 410 and exc.code == "changes_expired":
            raise ChangesExpiredError("the feed state has expired") from None
        if exc.status >= 500 or exc.status == 429:
            raise MailboxUnavailableError(
                f"the mailbox service answered {exc.status} ({exc.code})"
            ) from None
        raise MailboxRefusedError(
            f"the mailbox service refused: {exc.code}",
            status=exc.status,
            reason=exc.code,
        ) from None
    except (ServiceUnavailableError, ServiceTimeoutError) as exc:
        raise MailboxUnavailableError(
            f"the mailbox service is away ({type(exc).__name__})"
        ) from None
    except ConfigurationError as exc:
        raise ConfigError(f"the mailbox service: {exc}") from None
    except MailboxError as exc:
        raise MailboxUnavailableError(
            f"the mailbox service failed ({type(exc).__name__})"
        ) from None


def _address(found: wire.Address | None) -> Address | None:
    return Address(email=found.email, name=found.name) if found else None


def _addresses(found: Iterable[wire.Address]) -> tuple[Address, ...]:
    return tuple(Address(email=a.email, name=a.name) for a in found)


class Mailbox:
    """One agent's view of the mailbox service, over one client."""

    def __init__(self, client: MailboxClient) -> None:
        self._client = client
        self._folders: dict[str, dict[str, FolderRef]] = {}

    async def __aenter__(self) -> Mailbox:
        return self

    async def __aexit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    # -- the change feed ----------------------------------------------------------

    async def start(self, accounts: list[str] | None = None) -> str:
        """The state to read the feed from, from now on."""
        found = await _call(self._client.list_all_changes(accounts=accounts or None))
        return found.state

    async def changes(
        self, since: str, accounts: list[str] | None = None
    ) -> tuple[list[Event], str]:
        """Every change after ``since``, pages followed, and the new state.
        Raises :class:`ChangesExpiredError` for a state the service no
        longer keeps changes for."""
        events: list[Event] = []
        state = since
        while True:
            found = await _call(
                self._client.list_all_changes(
                    accounts=accounts or None, since=state, limit=_PAGE
                )
            )
            events += [
                Event(
                    type=change.type,
                    ref=MessageRef(account_id=change.account_id, message_id=change.id),
                    at=change.at,
                )
                for change in found.changes
                if change.type.startswith("message.")
            ]
            state = found.state
            if not found.more:
                return events, state

    async def recent(
        self,
        since: date,
        accounts: list[str] | None = None,
        roles: tuple[str, ...] = ("inbox", "sent"),
    ) -> list[MessageRef]:
        """The messages from ``since`` on in the folders of ``roles``,
        received or sent, for a backfill. The service lists the inbox alone when
        no folder is named, so each role is asked for by itself."""
        refs: dict[MessageRef, None] = {}
        for role in roles:
            cursor: str | None = None
            while True:
                page = await _call(
                    self._client.list_all_messages(
                        accounts=accounts or None,
                        folder=role,
                        after=since.isoformat(),
                        limit=_PAGE,
                        cursor=cursor,
                    )
                )
                for item in page.items:
                    if item.account_id:
                        refs[
                            MessageRef(account_id=item.account_id, message_id=item.id)
                        ] = None
                cursor = page.next_cursor
                if not cursor:
                    break
        return list(refs)

    # -- reading ---------------------------------------------------------------------

    async def folders(
        self, account_id: str, *, fresh: bool = False
    ) -> dict[str, FolderRef]:
        """The folders of an account by id, each with its path. Kept until
        ``fresh`` asks for them again."""
        if fresh or account_id not in self._folders:
            found = await _call(self._client.list_folders(account_id))
            self._folders[account_id] = _with_paths(found)
        return self._folders[account_id]

    async def folder_at(self, account_id: str, path: str) -> FolderRef | None:
        """The folder at ``path``, ``/`` between the names, asked once more
        of the service before it counts as missing."""
        for fresh in (False, True):
            for folder in (await self.folders(account_id, fresh=fresh)).values():
                if folder.path == path:
                    return folder
        return None

    async def _refs(self, account_id: str, ids: list[str]) -> tuple[FolderRef, ...]:
        known = await self.folders(account_id)
        if any(i not in known for i in ids):
            known = await self.folders(account_id, fresh=True)
        return tuple(known[i] for i in ids if i in known)

    async def message(self, ref: MessageRef) -> MailMessage:
        found = await _call(self._client.get_message(ref.account_id, ref.message_id))
        return MailMessage(
            ref=ref,
            thread_id=found.thread_id,
            folders=await self._refs(ref.account_id, found.folder_ids),
            subject=found.subject,
            sender=_address(found.sender),
            to=_addresses(found.to),
            cc=_addresses(found.cc),
            date=found.date,
            received=found.received,
            keywords=tuple(found.keywords),
            text=found.text_body or "",
            attachments=tuple(
                Attachment(
                    filename=a.filename,
                    content_type=a.content_type,
                    size=a.size,
                    inline=a.inline,
                )
                for a in found.attachments
            ),
            message_id_header=found.message_id_header,
            in_reply_to=found.in_reply_to,
        )

    async def thread(self, account_id: str, thread_id: str) -> Thread:
        """A thread, its messages oldest first, each without its text."""
        found = await _call(self._client.get_thread(account_id, thread_id))
        messages = []
        for item in found.messages:
            messages.append(
                MailMessage(
                    ref=MessageRef(account_id=account_id, message_id=item.id),
                    thread_id=item.thread_id,
                    folders=await self._refs(account_id, item.folder_ids),
                    subject=item.subject,
                    sender=_address(item.sender),
                    to=_addresses(item.to),
                    date=item.date,
                    received=item.received,
                    keywords=tuple(item.keywords),
                )
            )
        return Thread(id=found.id, messages=tuple(messages))

    # -- the three actions -------------------------------------------------------------

    async def add_keyword(self, ref: MessageRef, keyword: str) -> None:
        await _call(
            self._client.update_message(
                ref.account_id, ref.message_id, add_keywords=[keyword]
            )
        )

    async def remove_keyword(self, ref: MessageRef, keyword: str) -> None:
        await _call(
            self._client.update_message(
                ref.account_id, ref.message_id, remove_keywords=[keyword]
            )
        )

    async def move(self, ref: MessageRef, folder_id: str) -> None:
        """Move a message into the folder ``folder_id``, out of the others."""
        await _call(
            self._client.update_message(
                ref.account_id, ref.message_id, folder_ids=[folder_id]
            )
        )


def _with_paths(found: list[wire.Folder]) -> dict[str, FolderRef]:
    by_id = {folder.id: folder for folder in found}

    def path(folder: wire.Folder) -> str:
        names = [folder.name]
        seen = {folder.id}
        parent = by_id.get(folder.parent_id) if folder.parent_id else None
        while parent is not None and parent.id not in seen:
            names.append(parent.name)
            seen.add(parent.id)
            parent = by_id.get(parent.parent_id) if parent.parent_id else None
        return "/".join(reversed(names))

    return {
        folder.id: FolderRef(
            id=folder.id, name=folder.name, role=folder.role, path=path(folder)
        )
        for folder in found
    }


@asynccontextmanager
async def connect(
    base_url: str,
    token: str,
    *,
    allow_http: bool = False,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AsyncIterator[Mailbox]:
    """A :class:`Mailbox` over a client of its own, closed on the way out.

    Without a transport of a test, the client gets one that reads no proxy
    and no certificate setting from the environment, as the gateway does.
    """
    if transport is None:
        transport = httpx.AsyncHTTPTransport(trust_env=False)
    try:
        client = MailboxClient(
            base_url=base_url, token=token, transport=transport, allow_http=allow_http
        )
    except ConfigurationError as exc:
        raise ConfigError(f"the mailbox service: {exc}") from None
    async with Mailbox(client) as mailbox:
        yield mailbox
