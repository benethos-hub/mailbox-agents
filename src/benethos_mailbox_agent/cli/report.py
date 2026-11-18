"""The report: what an agent decided and did, for its owner to review.

The state file holds ids only, so subject and sender are fetched from the
mailbox service at the moment of the report and are never stored. The
state file is opened read-only, so a report can be made while the agent
runs. It prints to stdout, for the person who asked, and nothing of it
reaches the log. See SPECS.md section 8.2.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..contract import Agent
from ..errors import MailboxRefusedError
from ..records import Decision, MailMessage, MessageRef
from ..settings import Settings
from ..sources.mailbox import Mailbox, connect
from ..store import ActionRow, MessageRow, Store, path_for
from .session import TRANSPORTS

__all__ = ["Entry", "collect", "render", "report", "summary"]


@dataclass
class Entry:
    """One message of the report."""

    row: MessageRow
    message: MailMessage | None
    decision: Decision | None
    model: str
    baseline: Decision | None
    actions: list[ActionRow] = field(default_factory=list)


def _latest(store: Store, ref: MessageRef, step: str) -> tuple[Decision | None, str]:
    found = [s for s in store.steps(ref) if s.step == step]
    if not found:
        return None, ""
    return Decision.model_validate(found[-1].result), found[-1].model


async def collect(
    store: Store,
    mailbox: Mailbox | None,
    *,
    limit: int,
    state: str | None = None,
) -> list[Entry]:
    """The newest ``limit`` messages, in ``state`` if named, each with its
    subject and sender fetched now unless ``mailbox`` is None."""
    entries = []
    for row in store.messages(state)[:limit]:
        message = None
        if mailbox is not None:
            try:
                message = await mailbox.message(row.ref)
            except MailboxRefusedError:
                message = None
        decision, model = _latest(store, row.ref, "decision")
        baseline, _ = _latest(store, row.ref, "baseline")
        entries.append(
            Entry(row, message, decision, model, baseline, store.actions(row.ref))
        )
    return entries


def _sender(message: MailMessage) -> str:
    if message.sender is None:
        return "(no sender)"
    if message.sender.name:
        return f"{message.sender.name} <{message.sender.email}>"
    return message.sender.email


def _decision(decision: Decision, model: str) -> str:
    line = f"  decision: {decision.label} ({decision.source}"
    line += f", {model})" if model else ")"
    if decision.refused:
        line += f" refused: {decision.refused}"
    for name, value in sorted(decision.fields.items()):
        line += f" {name}={value}"
    for name, value in sorted(decision.details.items()):
        line += f" {name}={value}"
    return line


def _action(action: ActionRow) -> str:
    done = "done" if action.executed else "would have been done"
    return f"  action: {action.action} {action.argument} ({action.stage}: {done})"


def render(entries: list[Entry]) -> list[str]:
    """The report as lines."""
    lines: list[str] = []
    for entry in entries:
        ref = entry.row.ref
        lines.append(
            f"{entry.row.created:%Y-%m-%d %H:%M}  {ref.account_id}/{ref.message_id}"
            f"  {entry.row.state}"
        )
        if entry.message is None:
            lines.append("  (not fetched: gone from the mailbox or no service)")
        else:
            lines.append(f"  from: {_sender(entry.message)}")
            lines.append(f"  subject: {entry.message.subject or '(none)'}")
        if entry.decision is not None:
            lines.append(_decision(entry.decision, entry.model))
            for item in entry.decision.evidence:
                found = {True: "found", False: "NOT found", None: "not checked"}
                said = f'"{item.quote}"' if item.quote else "(by a rule)"
                lines.append(f"  evidence: {item.field} {said} {found[item.found]}")
        if entry.baseline is not None:
            lines.append(f"  baseline: {entry.baseline.label}")
        lines.extend(_action(action) for action in entry.actions)
        lines.append("")
    return lines


def summary(agent: Agent, entries: list[Entry]) -> list[str]:
    """What the agent has to say about the messages shown."""
    decided = [
        (
            entry.message.sender.email
            if entry.message is not None and entry.message.sender is not None
            else None,
            entry.decision,
        )
        for entry in entries
        if entry.decision is not None
    ]
    return agent.summarize(decided)


async def report(
    agent: Agent, settings: Settings, *, limit: int, state: str | None, offline: bool
) -> list[str]:
    """The report of ``agent``, read beside the running agent."""
    with Store.open(path_for(settings.data_dir, agent.name), read_only=True) as store:
        if offline:
            entries = await collect(store, None, limit=limit, state=state)
        else:
            async with connect(
                settings.service_url or "",
                settings.secret("service_token"),
                allow_http=settings.service_allow_http,
                transport=TRANSPORTS.get("service"),
            ) as mailbox:
                entries = await collect(store, mailbox, limit=limit, state=state)
    return render(entries) + summary(agent, entries)
