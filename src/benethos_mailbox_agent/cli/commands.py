"""The commands. Each takes the parsed arguments and the settings and
answers the exit code. What they print names ids, counts and paths, never
anything of a mail, except ``report``, which is for the owner."""

from __future__ import annotations

import argparse
import asyncio
import signal
from contextlib import suppress

from .. import logbook
from ..contract import discover, load
from ..errors import ConfigError
from ..runtime.readiness import readiness
from ..settings import DEFAULT_ENV_FILE, Settings
from ..store import Store, path_for
from .session import session

__all__ = ["backfill", "paths", "run", "status", "worker"]


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
        await found.worker.run(stop)
        logbook.stopped(found.agent.name, "signal")


# -- run and backfill -------------------------------------------------------------


def run(args: argparse.Namespace, settings: Settings) -> int:
    return asyncio.run(_run(args.agent, settings))


async def _run(name: str, settings: Settings) -> int:
    async with session(load(name), settings) as found:
        wait = await found.worker.run_pass()
        print(f"{found.agent.name}: {_counts(found.store)}")
        return 0 if wait <= settings.poll_seconds else 1


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
                last = store.last_pass()
                print(f"  {_counts(store)}")
                print(f"  last pass: {last.isoformat() if last else 'none'}")
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
