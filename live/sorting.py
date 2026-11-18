"""The live check of the agent sorting, against the test account of
containers/live/. It WRITES to that account and puts the mail back.

    sh containers/live/setup.sh          # once, in a shell with Docker
    uv run python live/sorting.py [--env-file containers/live/secrets/agent.env]

It runs ``sorting`` over the mail of the last weeks with the list
containers/live/sorting.json, each time with a state file in a folder of
its own: first in ``shadow``, which must change nothing in the mailbox,
then in ``full``, which makes the missing folders and moves the mail of
each group not held, with the agent's keyword. Then it moves every
message back to where it was and takes the keyword off. The folders it
made stay: no agent may delete a folder, and a second run finds them
there. Each check says ok or FAILED, and the exit code is 1 if one
failed. Never point it at an account that is not a test account.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from benethos_mailbox_agents.agents.sorting.agent import Sorting
from benethos_mailbox_agents.records import MessageRef
from benethos_mailbox_agents.runtime.loop import Worker
from benethos_mailbox_agents.runtime.model import NoModel
from benethos_mailbox_agents.settings import Settings, load_settings
from benethos_mailbox_agents.sources.mailbox import Mailbox, connect
from benethos_mailbox_agents.store import ActionRow, Store

ROOT = Path(__file__).resolve().parent.parent
LIVE = ROOT / "containers" / "live"
ENV = LIVE / "secrets" / "agent.env"
LIST = LIVE / "sorting.json"

# What the list makes of the invented mail of containers/live/mail.py.
MOVED = {"CloudHost": 3, "Telco": 1}
HELD = {"Paperworks": 2}
FOLDERS = ("Providers", "Providers/CloudHost", "Providers/Telco")
KEYWORD = Sorting.default_keyword


@dataclass
class Live:
    settings: Settings
    mailbox: Mailbox
    before: dict[MessageRef, tuple[tuple[str, ...], tuple[str, ...]]] = field(
        default_factory=dict
    )
    folders_before: set[str] = field(default_factory=set)
    moved: list[ActionRow] = field(default_factory=list)

    @property
    def account(self) -> str:
        return self.settings.accounts[0]


async def snapshot(
    live: Live,
) -> dict[MessageRef, tuple[tuple[str, ...], tuple[str, ...]]]:
    """Each message of the inbox and the folders below: its folders and
    keywords."""
    since = date.today() - timedelta(days=30)
    refs = await live.mailbox.recent(since, live.settings.accounts, roles=("inbox",))
    found = {}
    for ref in refs:
        message = await live.mailbox.message(ref)
        found[ref] = (
            tuple(sorted(f.id for f in message.folders)),
            tuple(sorted(message.keywords)),
        )
    return found


async def sort(
    live: Live, stage: str, folder: Path
) -> tuple[list[ActionRow], Counter[str]]:
    """The agent over the mail of the last weeks in ``stage``: its actions
    and how many messages it decided for each label."""
    settings = live.settings.model_copy(
        update={"stage": stage, "sorting_file": LIST, "data_dir": folder}
    )
    agent = Sorting(settings)
    agent.prepare()
    with Store.open(folder / "sorting.db") as store:
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
        labels: Counter[str] = Counter()
        for row in store.messages(None, 1000):
            steps = [s for s in store.steps(row.ref) if s.step == "decision"]
            if steps:
                labels[str(steps[-1].result["label"])] += 1
        return store.actions(), labels


async def before(live: Live) -> str:
    live.before = await snapshot(live)
    live.folders_before = {
        f.path for f in (await live.mailbox.folders(live.account, fresh=True)).values()
    }
    return f"{len(live.before)} messages in the inbox"


async def shadow(live: Live) -> str:
    with tempfile.TemporaryDirectory() as folder:
        actions, labels = await sort(live, "shadow", Path(folder))
    for name, count in {**MOVED, **HELD}.items():
        if labels[name] != count:
            raise AssertionError(f"{labels[name]} messages of {name}, {count} expected")
    if any(a.executed for a in actions):
        raise AssertionError("an action was carried out in shadow")
    after = await snapshot(live)
    folders = {
        f.path for f in (await live.mailbox.folders(live.account, fresh=True)).values()
    }
    if after != live.before or folders != live.folders_before:
        raise AssertionError("the mailbox changed in shadow")
    moves = sum(a.action == "move_to_folder" for a in actions)
    made = sorted({a.argument for a in actions if a.action == "create_folder"})
    return (
        f"{sum(labels.values())} decided, {moves} moves and the folders "
        f"{made or 'none'} recorded, nothing changed"
    )


async def full(live: Live) -> str:
    with tempfile.TemporaryDirectory() as folder:
        actions, labels = await sort(live, "full", Path(folder))
    live.moved = [a for a in actions if a.action == "move_to_folder" and a.executed]
    folders = {
        f.path for f in (await live.mailbox.folders(live.account, fresh=True)).values()
    }
    missing = [path for path in FOLDERS if path not in folders]
    if missing:
        raise AssertionError(f"the folders {missing} were not made")
    if "Paperworks" in folders - live.folders_before:
        raise AssertionError("the folder of a held group was made")
    by_folder = Counter(a.argument for a in live.moved)
    expected = {f"Providers/{name}": count for name, count in MOVED.items()}
    if dict(by_folder) != expected:
        raise AssertionError(f"moved {dict(by_folder)}, {expected} expected")
    for action in live.moved:
        message = await live.mailbox.message(action.ref)
        if [f.path for f in message.folders] != [action.argument]:
            raise AssertionError("a message is not in the folder it was moved to")
        if KEYWORD not in {k.casefold() for k in message.keywords}:
            raise AssertionError("a moved message lacks the keyword")
    made = sorted((folders - live.folders_before) & set(FOLDERS))
    return (
        f"{sum(by_folder.values())} moved, {sum(HELD.values())} held, folders "
        f"made {made or 'none, there from an earlier run'}"
    )


async def put_back(live: Live) -> str:
    for action in live.moved:
        await live.mailbox.move(action.ref, action.before["folders"][0])
        await live.mailbox.remove_keyword(action.ref, KEYWORD)
    after = await snapshot(live)
    if after != live.before:
        changed = sum(after.get(ref) != was for ref, was in live.before.items())
        raise AssertionError(f"{changed} messages are not as they were")
    return f"{len(live.moved)} messages back in the inbox, keyword off"


CHECKS: list[tuple[str, Callable[[Live], Awaitable[str]]]] = [
    ("the inbox before", before),
    ("sorting in shadow", shadow),
    ("sorting in full", full),
    ("the mail put back", put_back),
]


async def run(settings: Settings) -> int:
    failed = 0
    async with connect(
        settings.service_url or "",
        settings.secret("service_token"),
        allow_http=settings.service_allow_http,
    ) as mailbox:
        live = Live(settings, mailbox)
        for name, check in CHECKS:
            try:
                said = await check(live)
            except Exception as exc:
                failed += 1
                print(f"FAILED   {name}: {type(exc).__name__}: {exc}")
                if check is full and live.moved:
                    print(f"         {await put_back(live)}")
                break
            print(f"ok       {name}: {said}")
    return 1 if failed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="The live check of sorting.")
    parser.add_argument("--env-file", type=Path, default=ENV)
    args = parser.parse_args()
    if not args.env_file.is_file():
        sys.exit(
            f"sorting: no settings at {args.env_file}, run containers/live/setup.sh"
        )
    found = load_settings(args.env_file)
    if not found.accounts:
        sys.exit("sorting: the settings name no account, the check needs the test one")
    sys.exit(asyncio.run(run(found)))
