"""The step runner: one pending message through fetch, baseline, model,
check and effect.

Each step writes its result before the next begins. The baseline is stored
once per agent version, the decision once per prompt version and model
alias, so a message run again, after a crash or a repeated feed entry,
reuses what was decided and asks the model nothing. See SPECS.md section 8.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import TypeVar

from pydantic import BaseModel

from .. import logbook
from ..contract import ActionRequest, Agent, Context, Reader
from ..errors import (
    AnswerRefusedError,
    GatewayUnavailableError,
    LimitReachedError,
    MailboxRefusedError,
)
from ..llm.evidence import check
from ..llm.gateway import Reply
from ..records import Decision, MailMessage, MessageRef, StepResult
from ..settings import Settings
from ..store import Store
from .items import StoredItems
from .metrics import Metrics
from .model import Asker, Calls, start_of_day

__all__ = ["Effects", "StepRunner", "backoff"]

T = TypeVar("T", bound=BaseModel)

# What carries out the actions of an effect: the action executor.
Effects = Callable[[list[ActionRequest]], Awaitable[None]]


def backoff(settings: Settings, attempts: int) -> float:
    """Seconds to wait after ``attempts`` failed tries: twice as long each
    time, from the poll interval up to the ceiling."""
    return float(
        min(
            settings.poll_seconds * 2 ** max(attempts, 0),
            settings.backoff_ceiling_seconds,
        )
    )


class _Away:
    """A gateway known to be away for the rest of a pass: every call fails
    at once, without a request."""

    def __init__(self, gateway: Asker, error: GatewayUnavailableError) -> None:
        self.model = gateway.model
        self._error = error

    async def ask(self, *, system: str, content: str, schema: type[T]) -> Reply[T]:
        raise self._error


class StepRunner:
    """Runs the steps of one agent's pending messages."""

    def __init__(
        self,
        *,
        agent: Agent,
        store: Store,
        reader: Reader,
        gateway: Asker,
        effects: Effects,
        now: Callable[[], datetime],
        metrics: Metrics | None = None,
    ) -> None:
        self.metrics = metrics or Metrics(
            agent.name, agent.version, agent.settings.stage
        )
        self.agent = agent
        self.settings = agent.settings
        self._store = store
        self._reader = reader
        self._gateway = gateway
        self._effects = effects
        self._now = now
        self.items = StoredItems(store, now)
        # Set by the loop when the gateway was found away in this pass.
        self.gateway_away: GatewayUnavailableError | None = None

    @property
    def model_alias(self) -> str:
        return self._gateway.model

    def calls(self, ref: MessageRef) -> Calls:
        gateway: Asker = self._gateway
        if self.gateway_away is not None:
            gateway = _Away(gateway, self.gateway_away)
        return Calls(
            gateway=gateway,
            store=self._store,
            ref=ref,
            limits=self.agent.limits,
            prompt_version=self.agent.prompt_version,
            retention_days=self.settings.prompt_retention_days,
            now=self._now,
            metrics=self.metrics,
        )

    def context(self, calls: Calls) -> Context:
        return Context(
            settings=self.settings,
            model=calls,
            reader=self._reader,
            items=self.items,
            now=self._now,
        )

    def _state(
        self,
        ref: MessageRef,
        state: str,
        *,
        attempts: int | None = None,
        next_attempt: datetime | None = None,
    ) -> str:
        self._store.set_state(
            ref, state, self._now(), attempts=attempts, next_attempt=next_attempt
        )
        logbook.message_state(self.agent.name, ref.message_id, state)
        return state

    def _retry(self, ref: MessageRef, attempts: int) -> str:
        tried = attempts + 1
        if tried >= self.settings.max_attempts:
            return self._state(ref, "failed", attempts=tried)
        wait = timedelta(seconds=backoff(self.settings, tried))
        return self._state(
            ref, "pending", attempts=tried, next_attempt=self._now() + wait
        )

    async def process(self, ref: MessageRef, attempts: int = 0) -> str:
        """Run the steps of one message. Answers the state it is left in.

        A mailbox service or a gateway that is away, and a configuration
        error, are raised to the loop and leave the message as it was.
        """
        try:
            message = await self._reader.message(ref)
        except MailboxRefusedError as exc:
            logbook.step_failed(self.agent.name, ref.message_id, "fetch", exc)
            self.metrics.step_failed(exc.code)
            if exc.status == 404:
                return self._state(ref, "skipped")
            return self._retry(ref, attempts)
        if not self.agent.admit(message):
            return self._state(ref, "skipped")
        self._baseline(message)
        calls = self.calls(ref)
        try:
            decision = await self._decision(message, calls)
        except AnswerRefusedError as exc:
            logbook.answer_refused(self.agent.name, ref.message_id, exc.reason)
            return self._retry(ref, attempts)
        except LimitReachedError as exc:
            logbook.step_failed(self.agent.name, ref.message_id, "model", exc)
            self.metrics.step_failed(exc.code)
            if not exc.per_day:
                return self._state(ref, "failed", attempts=attempts + 1)
            tomorrow = start_of_day(self._now()) + timedelta(days=1)
            return self._state(ref, "pending", next_attempt=tomorrow)
        except MailboxRefusedError as exc:
            logbook.step_failed(self.agent.name, ref.message_id, "decide", exc)
            self.metrics.step_failed(exc.code)
            return self._retry(ref, attempts)
        if not decision.actionable:
            self.metrics.answer_refused(decision.refused or "")
            return self._state(ref, "decided")
        return await self._act(decision, message, calls, attempts)

    async def _act(
        self, decision: Decision, message: MailMessage, calls: Calls, attempts: int
    ) -> str:
        """Ask the agent what to do and have it done. A refusal of what the
        agent read for it, such as an earlier message of the thread deleted
        since, ends the message as skipped when it is gone, and counts as
        an attempt otherwise."""
        ref = message.ref
        try:
            requests = await self.agent.effect(decision, message, self.context(calls))
            await self._effects(requests)
        except MailboxRefusedError as exc:
            logbook.step_failed(self.agent.name, ref.message_id, "effect", exc)
            self.metrics.step_failed(exc.code)
            if exc.status == 404:
                return self._state(ref, "skipped")
            return self._retry(ref, attempts)
        return self._state(ref, "done")

    def _baseline(self, message: MailMessage) -> None:
        ref = message.ref
        if self._store.step(ref, "baseline", self.agent.version, "") is not None:
            return
        started = time.monotonic()
        decided = self.agent.baseline(message)
        self._store.add_step(
            ref,
            StepResult(
                step="baseline",
                prompt_version=self.agent.version,
                result=decided.model_dump(mode="json"),
                duration_ms=_since(started),
                at=self._now(),
            ),
            "",
        )

    async def _decision(self, message: MailMessage, calls: Calls) -> Decision:
        """The decision of the model with its evidence checked, stored once
        per prompt version and model alias."""
        ref = message.ref
        stored = self._store.step(
            ref, "decision", self.agent.prompt_version, self.model_alias
        )
        if stored is not None:
            return Decision.model_validate(stored.result)
        started = time.monotonic()
        decided = await self.agent.decide(message, self.context(calls))
        if decided.source == "model":
            decided = check(decided, calls.evidence)
            for item in decided.evidence:
                if not item.found:
                    logbook.evidence_missing(
                        self.agent.name, ref.message_id, item.field
                    )
        duration = _since(started)
        self._store.add_step(
            ref,
            StepResult(
                step="decision",
                prompt_version=self.agent.prompt_version,
                model=",".join(dict.fromkeys(calls.models)),
                result=decided.model_dump(mode="json"),
                tokens_in=calls.tokens_in,
                tokens_out=calls.tokens_out,
                duration_ms=duration,
                at=self._now(),
            ),
            self.model_alias,
        )
        logbook.step_done(self.agent.name, ref.message_id, "decision", duration)
        return decided


def _since(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
