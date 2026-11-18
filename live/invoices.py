"""The live check of invoices beside sorting, against the test account of
containers/live/. sorting WRITES to that account, and the mail is put back.

    sh containers/live/setup.sh          # once, in a shell with Docker
    uv run python live/invoices.py [--env-file containers/live/secrets/agent.env]

``invoices`` runs in ``shadow`` with the folders ``Providers/*`` and the
subfolder ``{folder}/Rechnungen``, beside ``sorting`` in ``full`` with the
list containers/live/sorting.json, in both orders:

1. ``invoices`` first: it marks the invoices in the inbox and opens an
   item for each. ``sorting`` then moves the mail of its groups, and the
   updates reach ``invoices`` through the feed, which records the move of
   each invoice into its subfolder, with no model call.
2. ``sorting`` first: the mail lies in the folders of the groups, and
   ``invoices`` finds it there through ``backfill``.

Then every message goes back to where it was. ``invoices`` asks the model
of the settings, so the check costs one call per message and order. Each
check says ok or FAILED, and the exit code is 1 if one failed. Never point
it at an account that is not a test account.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
import time
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from email.utils import parseaddr
from pathlib import Path

from common import (  # beside this script, not a package
    DAYS,
    LIST,
    Snapshot,
    connect_mailbox,
    inbox_snapshot,
    labels,
    mail,
    open_gateway,
    parse_settings,
    put_back,
    run_checks,
    snapshot,
    sort_test_account,
    worker,
)

from benethos_mailbox_agents.agents.invoices.agent import Invoices
from benethos_mailbox_agents.agents.sorting.agent import Sorting
from benethos_mailbox_agents.agents.sorting.groups import load_groups
from benethos_mailbox_agents.llm.gateway import Gateway
from benethos_mailbox_agents.runtime.loop import Worker
from benethos_mailbox_agents.settings import Settings
from benethos_mailbox_agents.sources.mailbox import Mailbox
from benethos_mailbox_agents.store import Store

SUBFOLDER = "Rechnungen"
WAIT = 120


def _invoices() -> tuple[int, set[str]]:
    """What the list and the labels make of the invented mail of mail.py:
    how many invoices lie in the inbox, and the subfolders of those that
    sorting moves. The invoice of a held group or of a sender in no group
    stays in the inbox."""
    groups = load_groups(LIST)
    count, filed = 0, set()
    for folder, _, message in mail.messages("me@invented.example"):
        local = str(message["Message-ID"]).strip("<>").partition("@")[0]
        label = mail.GOLD.get(local, {}).get("invoices", ("", {}))[0]
        if folder != "inbox" or label != "invoice":
            continue
        count += 1
        match = groups.match(parseaddr(str(message["From"]))[1])
        group = match.group if match else None
        if group is not None and not group.hold:
            filed.add(f"{group.folder}/{SUBFOLDER}")
    return count, filed


INVOICES, FILED = _invoices()


@dataclass
class Live:
    settings: Settings
    mailbox: Mailbox
    gateway: Gateway
    folder: Path
    before: Snapshot = field(default_factory=dict)
    putting_back: bool = False

    @property
    def keyword(self) -> str:
        """The keyword sorting sets with these settings."""
        return Sorting(self.settings).keyword

    def invoices(self, name: str) -> tuple[Worker, Store]:
        settings = self.settings.model_copy(
            update={
                "stage": "shadow",
                "invoices_folders": ["Providers/*"],
                "invoices_subfolder": "{folder}/" + SUBFOLDER,
                "data_dir": self.folder,
            }
        )
        agent = Invoices(settings)
        agent.prepare()
        store = Store.open(self.folder / f"invoices-{name}.db")
        return worker(agent, store, self.mailbox, self.gateway), store

    async def sort(self) -> None:
        await sort_test_account(self.settings, self.mailbox, "full", self.folder)


def recorded_moves(store: Store) -> set[str]:
    return {
        a.argument
        for a in store.actions()
        if a.action == "move_to_folder" and not a.executed
    }


async def before(live: Live) -> str:
    live.before = await inbox_snapshot(live.mailbox, live.settings)
    return f"{len(live.before)} messages in the inbox"


async def invoices_first(live: Live) -> str:
    marking, store = live.invoices("first")
    with store:
        await marking.run_pass()
        await marking.backfill(DAYS)
        await marking.drain()
        decided = labels(store)["invoice"]
        if decided != INVOICES:
            raise AssertionError(f"{decided} invoices decided")
        opened = [i for i in (store.item(r) for r in live.before) if i and i.is_open]
        if len(opened) != INVOICES:
            raise AssertionError(f"{len(opened)} open items, {INVOICES} expected")
        steps = len(store.actions())
        await live.sort()
        started = time.monotonic()
        while recorded_moves(store) != FILED and time.monotonic() - started < WAIT:
            await asyncio.sleep(5)
            await marking.run_pass()
        found = recorded_moves(store)
        if found != FILED:
            raise AssertionError(
                f"recorded moves {sorted(found)}, {sorted(FILED)} expected"
            )
        filed = [
            i for i in (store.item(r) for r in live.before) if i and i.reason == "filed"
        ]
        calls = len(
            [s for r in live.before for s in store.steps(r) if s.step == "decision"]
        )
        if any(a.executed for a in store.actions()):
            raise AssertionError("invoices carried an action out in shadow")
        later = len(store.actions()) - steps
    return (
        f"{INVOICES} invoices marked, {len(filed)} filed after sorting moved them "
        f"({time.monotonic() - started:.0f} s through the feed), "
        f"{later} actions recorded then, {calls} decisions"
    )


async def sorting_first(live: Live) -> str:
    marking, store = live.invoices("second")
    with store:
        taken = await marking.backfill(DAYS)
        await marking.drain()
        found = recorded_moves(store)
        if found != FILED:
            raise AssertionError(
                f"recorded moves {sorted(found)}, {sorted(FILED)} expected"
            )
        decided = labels(store)["invoice"]
        made = sorted(
            {a.argument for a in store.actions() if a.action == "create_folder"}
        )
    return f"{taken} taken up, {decided} invoices, folders recorded {made}"


async def put_back_check(live: Live) -> str:
    live.putting_back = True
    moved = await put_back(live.mailbox, live.before, live.keyword)
    after = await snapshot(live.mailbox, live.before)
    if {r: f for r, (f, _) in after.items()} != {
        r: f for r, (f, _) in live.before.items()
    }:
        raise AssertionError("the inbox is not as it was")
    return f"{moved} messages back in the inbox"


CHECKS: list[tuple[str, Callable[[Live], Awaitable[str]]]] = [
    ("the inbox before", before),
    ("invoices first, then sorting", invoices_first),
    ("sorting first, then invoices", sorting_first),
    ("the mail put back", put_back_check),
]


async def run(settings: Settings) -> int:
    async with AsyncExitStack() as stack:
        mailbox = await stack.enter_async_context(connect_mailbox(settings))
        gateway = await stack.enter_async_context(open_gateway(settings))
        folder = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        live = Live(settings, mailbox, gateway, folder)
        try:
            failed = await run_checks(live, CHECKS, stop=True)
        finally:
            # A check that failed or a run cut short leaves no mail moved.
            if not live.putting_back:
                moved = await put_back(live.mailbox, live.before, live.keyword)
                if moved:
                    print(f"         {moved} messages back in the inbox")
    return 1 if failed else 0


if __name__ == "__main__":
    found = parse_settings("invoices", "The live check of invoices.")
    sys.exit(asyncio.run(run(found)))
