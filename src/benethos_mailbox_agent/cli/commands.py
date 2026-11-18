"""The commands. Each takes the parsed arguments and the settings and
answers the exit code. What they print names ids, counts and paths, never
anything of a mail, except ``report``, which is for the owner."""

from __future__ import annotations

import argparse
import asyncio
import signal
import tempfile
from contextlib import ExitStack, suppress
from pathlib import Path
from typing import Any

from .. import logbook
from ..contract import Agent, discover, load
from ..errors import ConfigError
from ..evaluation.gold import GoldItem, load_gold
from ..evaluation.report import build, render, write
from ..evaluation.run import evaluate as run_evaluation
from ..runtime.health import check
from ..runtime.readiness import MAILBOX_SETTINGS, readiness, start
from ..settings import DEFAULT_ENV_FILE, Settings
from ..store import STATES, Store, path_for
from .report import report as make_report
from .session import now, session, upstreams

__all__ = [
    "backfill",
    "evaluate",
    "health",
    "paths",
    "report",
    "run",
    "status",
    "worker",
]


def _counts(store: Store) -> str:
    return " ".join(f"{state}={count}" for state, count in store.counts().items())


# -- worker -------------------------------------------------------------------


def worker(args: argparse.Namespace, settings: Settings) -> int:
    asyncio.run(_worker(args.agent, settings))
    return 0


def _stop_on_signals(stop: asyncio.Event) -> None:
    """Set ``stop`` on SIGTERM and SIGINT, where the platform lets a loop
    handle them. Elsewhere Ctrl+C ends the process as usual."""
    loop = asyncio.get_running_loop()
    for name in ("SIGTERM", "SIGINT"):
        number = getattr(signal, name, None)
        if number is not None:
            with suppress(NotImplementedError, RuntimeError):
                loop.add_signal_handler(number, stop.set)


async def _worker(name: str, settings: Settings) -> None:
    async with session(load(name), settings) as found:
        logbook.started(found.agent.name, found.agent.version, settings.stage)
        stop = asyncio.Event()
        _stop_on_signals(stop)
        with ExitStack() as serving:
            if settings.metrics_port:
                serving.enter_context(
                    found.worker.metrics.serving(settings.metrics_port)
                )
                logbook.metrics_serving(found.agent.name, settings.metrics_port)
            await found.worker.run(stop)
        logbook.stopped(found.agent.name, "signal")


# -- run and backfill -------------------------------------------------------------


def run(args: argparse.Namespace, settings: Settings) -> int:
    return asyncio.run(_run(args.agent, settings))


async def _run(name: str, settings: Settings) -> int:
    async with session(load(name), settings) as found:
        await found.worker.run_pass()
        print(f"{found.agent.name}: {_counts(found.store)}")
        return 1 if found.worker.away else 0


def backfill(args: argparse.Namespace, settings: Settings) -> int:
    days = args.days if args.days is not None else settings.backfill_days
    if days < 0:
        raise ConfigError("--days must not be negative")
    return asyncio.run(_backfill(args.agent, days, settings))


async def _backfill(name: str, days: int, settings: Settings) -> int:
    async with session(load(name), settings) as found:
        added = await found.worker.backfill(days, again=True)
        while await found.worker.process_due():
            pass
        print(f"{found.agent.name}: {added} taken up, {_counts(found.store)}")
        return 0


# -- status and paths -------------------------------------------------------------


def status(args: argparse.Namespace, settings: Settings) -> int:
    for cls in discover().values():
        found = readiness(cls, settings)
        if found.ready:
            state = "ready"
        elif found.missing:
            state = "misses " + ", ".join(found.missing)
        else:
            state = f"not ready: {found.problem}"
        print(f"{found.name} {found.version}: {state}")
        path = path_for(settings.data_dir, cls.name)
        if path.is_file():
            with Store.open(path, read_only=True) as store:
                last = store.progress()
                print(f"  {_counts(store)}")
                print(f"  last progress: {last.isoformat() if last else 'none'}")
    return 0


def paths(args: argparse.Namespace, settings: Settings) -> int:
    env = args.env_file or DEFAULT_ENV_FILE
    print(f"settings: {env.resolve()} ({'found' if env.is_file() else 'missing'})")
    print(f"data: {settings.data_dir.resolve()}")
    for name in discover():
        path = path_for(settings.data_dir, name)
        print(
            f"  {name}: {path.resolve()} ({'found' if path.is_file() else 'none yet'})"
        )
    return 0


# -- report -------------------------------------------------------------------------


def report(args: argparse.Namespace, settings: Settings) -> int:
    agent = load(args.agent)(settings)
    name = agent.name
    if args.state is not None and args.state not in STATES:
        raise ConfigError(f"--state is one of {', '.join(STATES)}")
    if args.limit < 1:
        raise ConfigError("--limit must be at least 1")
    missing = settings.missing(MAILBOX_SETTINGS)
    if missing and not args.offline:
        raise ConfigError(
            f"the report fetches subject and sender and misses {', '.join(missing)}"
            ", or ask for it --offline"
        )
    lines = asyncio.run(
        make_report(
            agent, settings, limit=args.limit, state=args.state, offline=args.offline
        )
    )
    print("\n".join(lines) if lines else f"{name}: nothing recorded yet")
    return 0


# -- health ---------------------------------------------------------------------------


def health(args: argparse.Namespace, settings: Settings) -> int:
    """0 while the agent's loop makes progress, 1 when it does not, a
    state file not there yet included: Docker keeps 2 for itself."""
    name = load(args.agent).name
    path = path_for(settings.data_dir, name)
    if not path.is_file():
        print(f"{name}: unhealthy, no pass yet")
        return 1
    with Store.open(path, read_only=True) as store:
        found = check(store, settings, now())
    print(f"{name}: {'healthy' if found.healthy else 'unhealthy'}, {found.reason}")
    return 0 if found.healthy else 1


# -- eval -----------------------------------------------------------------------------


def evaluate(args: argparse.Namespace, settings: Settings) -> int:
    """Run an agent over a gold set, print the scores, write the report."""
    cls = load(args.agent)
    items = load_gold(args.gold)
    report = asyncio.run(_evaluate(cls, items, settings))
    for line in render(report):
        print(line)
    print(f"report: {write(report, args.reports)}")
    return 0


async def _evaluate(
    cls: type[Agent], items: list[GoldItem], settings: Settings
) -> dict[str, Any]:
    agent = start(cls, settings)
    async with upstreams(agent, settings) as (mailbox, gateway):
        with tempfile.TemporaryDirectory() as folder:
            with Store.open(Path(folder) / "evaluation.db") as store:
                outcomes = await run_evaluation(
                    agent, items, reader=mailbox, gateway=gateway, store=store, now=now
                )
    return build(agent, gateway.model, outcomes, now())
