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

import argparse
import asyncio
import sys
import tempfile
import time
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from benethos_mailbox_agent.agents.invoices.agent import Invoices
from benethos_mailbox_agent.agents.sorting.agent import Sorting
from benethos_mailbox_agent.llm.gateway import Gateway
from benethos_mailbox_agent.records import MessageRef
from benethos_mailbox_agent.runtime.loop import Worker
from benethos_mailbox_agent.runtime.model import NoModel
from benethos_mailbox_agent.settings import Settings, load_settings
from benethos_mailbox_agent.sources.mailbox import Mailbox, connect
from benethos_mailbox_agent.store import ActionRow, Store

ROOT = Path(__file__).resolve().parent.parent
LIVE = ROOT / "containers" / "live"
ENV = LIVE / "secrets" / "agent.env"
LIST = LIVE / "sorting.json"

# What the list and the labels make of the invented mail of mail.py: the
# invoices of CloudHost and Telco are sorted, the one of Paperworks, a held
# group, stays in the inbox.
FILED = {"Providers/CloudHost/Rechnungen", "Providers/Telco/Rechnungen"}
INVOICES = 3
WAIT = 120


@dataclass
class Live:
    settings: Settings
    mailbox: Mailbox
    gateway: Gateway
    folder: Path
    before: dict[MessageRef, tuple[str, ...]] = field(default_factory=dict)
    sorted_moves: list[ActionRow] = field(default_factory=list)

    @property
    def account(self) -> str:
        return self.settings.accounts[0]

    def invoices(self, name: str) -> tuple[Worker, Store]:
        settings = self.settings.model_copy(
            update={
                "stage": "shadow",
                "invoices_folders": ["Providers/*"],
                "invoices_subfolder": "{folder}/Rechnungen",
                "data_dir": self.folder,
            }
        )
        agent = Invoices(settings)
        agent.prepare()
        store = Store.open(self.folder / f"invoices-{name}.db")
        worker = Worker(
            agent=agent,
            store=store,
            mailbox=self.mailbox,
            gateway=self.gateway,
            now=lambda: datetime.now(UTC),
        )
        return worker, store


async def inbox(live: Live) -> dict[MessageRef, tuple[str, ...]]:
    since = date.today() - timedelta(days=30)
    refs = await live.mailbox.recent(since, live.settings.accounts, roles=("inbox",))
    return {
        ref: tuple(sorted(f.id for f in (await live.mailbox.message(ref)).folders))
        for ref in refs
    }


async def sort(live: Live) -> None:
    settings = live.settings.model_copy(
        update={"stage": "full", "sorting_file": LIST, "data_dir": live.folder}
    )
    agent = Sorting(settings)
    agent.prepare()
    with Store.open(live.folder / "sorting.db") as store:
        worker = Worker(
            agent=agent,
            store=store,
            mailbox=live.mailbox,
            gateway=NoModel(),
            now=lambda: datetime.now(UTC),
        )
        await worker.backfill(30)
        while await worker.process_due():
            pass
        live.sorted_moves = [
            a for a in store.actions() if a.action == "move_to_folder" and a.executed
        ]


def recorded_moves(store: Store) -> set[str]:
    return {
        a.argument
        for a in store.actions()
        if a.action == "move_to_folder" and not a.executed
    }


def invoices_decided(store: Store) -> int:
    count = 0
    for row in store.messages(None, 1000):
        steps = [s for s in store.steps(row.ref) if s.step == "decision"]
        if steps and steps[-1].result["label"] == "invoice":
            count += 1
    return count


async def before(live: Live) -> str:
    live.before = await inbox(live)
    return f"{len(live.before)} messages in the inbox"


async def invoices_first(live: Live) -> str:
    worker, store = live.invoices("first")
    with store:
        await worker.run_pass()
        await worker.backfill(30)
        while await worker.process_due():
            pass
        if invoices_decided(store) != INVOICES:
            raise AssertionError(f"{invoices_decided(store)} invoices decided")
        opened = [i for i in (store.item(r) for r in live.before) if i and i.is_open]
        if len(opened) != INVOICES:
            raise AssertionError(f"{len(opened)} open items, {INVOICES} expected")
        steps = len(store.actions())
        await sort(live)
        started = time.monotonic()
        while recorded_moves(store) != FILED and time.monotonic() - started < WAIT:
            await asyncio.sleep(5)
            await worker.run_pass()
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
    worker, store = live.invoices("second")
    with store:
        taken = await worker.backfill(30)
        while await worker.process_due():
            pass
        found = recorded_moves(store)
        if found != FILED:
            raise AssertionError(
                f"recorded moves {sorted(found)}, {sorted(FILED)} expected"
            )
        decided = invoices_decided(store)
        made = sorted(
            {a.argument for a in store.actions() if a.action == "create_folder"}
        )
    return f"{taken} taken up, {decided} invoices, folders recorded {made}"


async def put_back(live: Live) -> str:
    for action in live.sorted_moves:
        await live.mailbox.move(action.ref, action.before["folders"][0])
        await live.mailbox.remove_keyword(action.ref, Sorting.default_keyword)
    after = await inbox(live)
    if after != live.before:
        raise AssertionError("the inbox is not as it was")
    return f"{len(live.sorted_moves)} messages back in the inbox"


CHECKS: list[tuple[str, Callable[[Live], Awaitable[str]]]] = [
    ("the inbox before", before),
    ("invoices first, then sorting", invoices_first),
    ("sorting first, then invoices", sorting_first),
    ("the mail put back", put_back),
]


async def run(settings: Settings) -> int:
    failed = 0
    async with AsyncExitStack() as stack:
        mailbox = await stack.enter_async_context(
            connect(
                settings.service_url or "",
                settings.secret("service_token"),
                allow_http=settings.service_allow_http,
            )
        )
        gateway = await stack.enter_async_context(
            Gateway(
                settings.gateway_url or "",
                settings.secret("gateway_key"),
                settings.model or "",
                timeout=settings.gateway_timeout_seconds,
                allow_http=settings.gateway_allow_http,
            )
        )
        folder = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        live = Live(settings, mailbox, gateway, folder)
        for name, check in CHECKS:
            try:
                said = await check(live)
            except Exception as exc:
                failed += 1
                print(f"FAILED   {name}: {type(exc).__name__}: {exc}")
                if live.sorted_moves:
                    print(f"         {await put_back(live)}")
                break
            print(f"ok       {name}: {said}")
    return 1 if failed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="The live check of invoices.")
    parser.add_argument("--env-file", type=Path, default=ENV)
    args = parser.parse_args()
    if not args.env_file.is_file():
        sys.exit(
            f"invoices: no settings at {args.env_file}, run containers/live/setup.sh"
        )
    found = load_settings(args.env_file)
    if not found.accounts:
        sys.exit("invoices: the settings name no account, the check needs the test one")
    sys.exit(asyncio.run(run(found)))
