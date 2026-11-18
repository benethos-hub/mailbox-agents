"""The worker loop: one pass after another, for one agent.

A pass reads the feed from the stored cursor, records each message the
agent selects for a decision as ``pending``, hands each event routed to
``observe`` to the agent at once, runs the steps of the pending messages
that are due, asks the agent on the tick what is due, and stores the
cursor last. A crash repeats work and skips no mail. A mailbox service or
gateway that is away leaves every message where it is, and the next pass
waits twice as long, up to the ceiling. See SPECS.md section 8.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Protocol

from .. import logbook
from ..contract import Action, ActionRequest, Agent, Context, Limits, Reader, Route
from ..errors import (
    ChangesExpiredError,
    GatewayUnavailableError,
    MailboxAgentError,
    MailboxRefusedError,
    UnavailableError,
)
from ..records import Event, MessageRef
from ..store import Store
from .actions import Executor, Outcome, Writer
from .metrics import Metrics
from .model import Asker
from .reader import ReadOnlyMailbox
from .steps import StepRunner, backoff, make_calls

__all__ = ["BATCH", "Upstream", "Worker"]

# Pending messages one pass takes up at most, so a long queue still lets
# the cursor move and the health check see progress.
BATCH = 50


class Upstream(Reader, Writer, Protocol):
    """What the loop needs of the mailbox service."""

    async def start(self, accounts: list[str] | None = None) -> str: ...

    async def changes(
        self, since: str, accounts: list[str] | None = None
    ) -> tuple[list[Event], str]: ...

    async def recent(
        self, since: date, accounts: list[str] | None = None
    ) -> list[MessageRef]: ...


class Worker:
    """The loop of one agent over one state file."""

    def __init__(
        self,
        *,
        agent: Agent,
        store: Store,
        mailbox: Upstream,
        gateway: Asker,
        now: Callable[[], datetime],
    ) -> None:
        self.agent = agent
        self.settings = agent.settings
        self.store = store
        self._mailbox = mailbox
        self._now = now
        self.metrics = Metrics(agent.name, agent.version, agent.settings.stage)
        self.executor = Executor(
            agent=agent, store=store, mailbox=mailbox, now=now, metrics=self.metrics
        )
        self.runner = StepRunner(
            agent=agent,
            store=store,
            reader=ReadOnlyMailbox(mailbox),
            gateway=gateway,
            effects=self.executor,
            now=now,
            metrics=self.metrics,
        )
        self._gateway = gateway
        self._away = 0
        self._last_tick: datetime | None = None
        self._waiting: set[MessageRef] = set()

    @property
    def away(self) -> bool:
        """Whether the last pass found the mailbox service or the gateway
        away."""
        return self._away > 0

    @property
    def accounts(self) -> list[str] | None:
        return self.settings.accounts or None

    def context(self) -> Context:
        """A context without the model, for observe and tick."""
        calls = make_calls(
            self.agent,
            gateway=self._gateway,
            store=self.store,
            ref=MessageRef(account_id="", message_id=""),
            now=self._now,
            limits=Limits(model_calls_per_message=0, model_calls_per_day=0),
        )
        return self.runner.context(calls)

    # -- one pass ---------------------------------------------------------------

    async def run_pass(self) -> float:
        """One pass. Answers the seconds to wait before the next."""
        started = time.monotonic()
        state, events = await self._read_feed()
        observe = self._record(events)
        for ref in observe:
            await self._observe(ref)
        away: UnavailableError | None = None
        try:
            await self.process_due()
            if self.runner.gateway_away is None or self._only_gateway_waits():
                await self._tick()
        except UnavailableError as exc:
            away = exc
        if away is None:
            away = self.runner.gateway_away
        now = self._now()
        self.store.set_cursor(state, now)
        self.store.set_last_pass(now)
        self._purge(now)
        self.metrics.state(self.store, now)
        logbook.pass_done(
            self.agent.name, time.monotonic() - started, self.store.counts()["pending"]
        )
        if away is not None:
            return self._wait_after(away)
        self._away = 0
        return self.settings.poll_seconds

    async def _read_feed(self) -> tuple[str, list[Event]]:
        state = self.store.cursor()
        if state is None:
            return await self._mailbox.start(self.accounts), []
        try:
            events, fresh = await self._mailbox.changes(state, self.accounts)
        except ChangesExpiredError:
            logbook.feed_expired(self.agent.name)
            fresh = await self._mailbox.start(self.accounts)
            await self.backfill(self.settings.backfill_days)
            return fresh, []
        return fresh, events

    def _record(self, events: list[Event]) -> list[MessageRef]:
        """Record what the agent decides on, answer what it observes."""
        now = self._now()
        observe: list[MessageRef] = []
        selected = 0
        for event in events:
            route = self.agent.select(event)
            if route is Route.DECIDE:
                self.store.enqueue(event.ref, now)
                selected += 1
            elif route is Route.OBSERVE and event.ref not in observe:
                observe.append(event.ref)
                selected += 1
        logbook.feed_read(self.agent.name, len(events), selected)
        return observe

    async def _observe(self, ref: MessageRef) -> None:
        try:
            message = await self._mailbox.message(ref)
        except MailboxRefusedError as exc:
            logbook.step_failed(self.agent.name, ref.message_id, "observe", exc)
            return
        await self.executor(await self.agent.observe(message, self.context()))

    async def process_due(self) -> int:
        """Run the steps of the pending messages that are due. Answers how
        many were taken up.

        A gateway that is away leaves each message that needs it pending,
        no attempt counted, and is not asked again in this pass, while the
        messages that need no model go on."""
        self.runner.gateway_away = None
        self._waiting = set()
        rows = self.store.due(self._now(), BATCH)
        for row in rows:
            try:
                await self.runner.process(row.ref, row.attempts)
            except GatewayUnavailableError as exc:
                self.runner.gateway_away = exc
                self._waiting.add(row.ref)
            self.store.set_last_pass(self._now())
        return len(rows)

    def _only_gateway_waits(self) -> bool:
        """Whether every message still due waits for the gateway alone. Only
        then may the tick run without it: a reply still in the queue must
        close its item before a deadline marks it."""
        due = self.store.due(self._now(), len(self._waiting) + 1)
        return {row.ref for row in due} <= self._waiting

    async def _tick(self) -> None:
        if not self.agent.triggers.tick:
            return
        now = self._now()
        if self._last_tick is not None and now - self._last_tick < timedelta(
            seconds=self.settings.tick_seconds
        ):
            return
        requests: list[ActionRequest] = await self.agent.tick(now, self.context())
        for request in requests:
            self._note(request, await self.executor.run(request))
        self._last_tick = now
        logbook.tick_done(self.agent.name, len(requests))

    def _note(self, request: ActionRequest, outcome: Outcome) -> None:
        """Keep on an open item what became of its keyword: set when it is on
        the message, recorded in this stage when the stage did not allow it.
        A refused keyword leaves the item due."""
        if request.action is not Action.ADD_KEYWORD:
            return
        if outcome in (Outcome.DONE, Outcome.PRESENT):
            self.store.mark_keyword(request.ref, True)
        elif outcome is Outcome.RECORDED:
            self.store.record_keyword_stage(request.ref, self.settings.stage)

    def _purge(self, now: datetime) -> None:
        days = self.settings.prompt_retention_days
        self.store.purge_calls(now - timedelta(days=days))

    def _wait_after(self, error: BaseException) -> float:
        self._away += 1
        self.metrics.step_failed(getattr(error, "code", type(error).__name__))
        wait = backoff(self.settings, self._away)
        logbook.upstream_away(self.agent.name, error, wait)
        return wait

    # -- backfill ---------------------------------------------------------------

    async def backfill(self, days: int, *, again: bool = False) -> int:
        """Record the messages of the last ``days`` days the agent selects,
        as if each had just been created. With ``again`` a message decided
        before is taken up anew, for a new prompt or model. Answers how
        many are pending because of it."""
        since = (self._now() - timedelta(days=days)).date()
        now = self._now()
        added = 0
        for ref in await self._mailbox.recent(since, self.accounts):
            event = Event(type="message.created", ref=ref, at=now)
            if self.agent.select(event) is Route.DECIDE:
                added += self.store.enqueue(ref, now, again=again)
        logbook.backfill_done(self.agent.name, added, days)
        return added

    # -- the loop ---------------------------------------------------------------

    async def run(self, stop: asyncio.Event) -> None:
        """Pass after pass until ``stop`` is set."""
        while not stop.is_set():
            try:
                wait = await self.run_pass()
            except UnavailableError as exc:
                wait = self._wait_after(exc)
            except MailboxAgentError as exc:
                logbook.pass_failed(self.agent.name, exc)
                wait = self._wait_after(exc)
            await self._sleep(wait, stop)

    async def _sleep(self, wait: float, stop: asyncio.Event) -> None:
        """Wait ``wait`` seconds or until ``stop``, in slices of at most one
        poll interval, writing progress after each. A loop that waits long
        for its gateway is alive, and the health check must see it so."""
        left = wait
        while left > 0 and not stop.is_set():
            step = min(left, self.settings.poll_seconds)
            try:
                await asyncio.wait_for(stop.wait(), timeout=step)
            except TimeoutError:
                self.store.set_last_pass(self._now())
            left -= step
