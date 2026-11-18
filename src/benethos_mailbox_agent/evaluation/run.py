"""The run: every gold message through the rules and through the model.

Each message is fetched by its id, answered by the agent's baseline and by
its decision with the model, the evidence checked as in operation, and
the model calls counted on a state file of the run's own, so the agent's
own state file is never touched. A gateway that is away ends the run: a
score over the messages it happened to answer would mislead.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from ..contract import Agent, Context, Reader
from ..errors import AnswerRefusedError, LimitReachedError, MailboxRefusedError
from ..llm.evidence import check
from ..runtime.items import StoredItems
from ..runtime.model import Asker, Calls
from ..runtime.reader import ReadOnlyMailbox
from ..store import Store
from .gold import GoldItem
from .scoring import Outcome

__all__ = ["evaluate"]


async def evaluate(
    agent: Agent,
    items: list[GoldItem],
    *,
    reader: Reader,
    gateway: Asker,
    store: Store,
    now: Callable[[], datetime],
) -> list[Outcome]:
    reader = ReadOnlyMailbox(reader)
    outcomes = []
    for item in items:
        try:
            message = await reader.message(item.ref)
        except MailboxRefusedError as exc:
            outcomes.append(Outcome(item, None, None, failure=f"fetch:{exc.reason}"))
            continue
        baseline = agent.baseline(message)
        calls = Calls(
            gateway=gateway,
            store=store,
            ref=item.ref,
            limits=agent.limits,
            prompt_version=agent.prompt_version,
            retention_days=0,
            now=now,
        )
        context = Context(
            settings=agent.settings,
            model=calls,
            reader=reader,
            items=StoredItems(store, now),
            now=now,
        )
        failure = None
        try:
            decision = await agent.decide(message, context)
            if decision.source == "model":
                decision = check(decision, calls.evidence)
        except AnswerRefusedError as exc:
            decision, failure = None, f"answer:{exc.reason}"
        except LimitReachedError:
            decision, failure = None, "limit"
        outcomes.append(
            Outcome(
                item,
                baseline,
                decision,
                tokens_in=calls.tokens_in,
                tokens_out=calls.tokens_out,
                duration_ms=calls.duration_ms,
                failure=failure,
                models=tuple(calls.models),
            )
        )
    return outcomes
