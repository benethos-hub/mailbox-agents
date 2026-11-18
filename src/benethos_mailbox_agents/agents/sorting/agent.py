"""``sorting``: is the sender of this message in the inbox one of a listed
group, and which folder is the group's?

The sender rules of the list are the whole agent: no model is asked. A
message of a group is moved from the inbox into the group's folder, which
is made first when it is missing, each folder above it as an action of its
own. A message already in another folder is the owner's choice and stays.
A group that is held has its moves recorded only, whatever the stage. With
the move the agent sets its keyword, so a message it sorted is known as
such also to a person and to a state file made anew (decided 2026-11-18).
The group is looked up again when the agent acts, against the list as it
is then, so a sender added since reaches older mail through
``backfill``. See docs/specs/agents/sorting.md.
"""

from __future__ import annotations

from collections import Counter
from functools import cached_property

from ...contract import (
    Action,
    ActionRequest,
    Agent,
    Context,
    Limits,
    Requires,
    Route,
    Shown,
    Trigger,
)
from ...errors import ConfigError
from ...records import Decision, Event, MailMessage
from ...settings import PREFIX
from .groups import Group, Groups, load_groups

__all__ = ["NONE", "Sorting"]

# The label of a message whose sender is in no group, or in two alike.
NONE = "none"

# The senders in no group a report names at most, as candidates.
CANDIDATES = 10


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def _fate(item: Shown) -> str:
    """What became of a message of a group: moved, held, recorded, or not
    moved, when its move was refused or not asked for."""
    moves = [done for action, done in item.actions if action == "move_to_folder"]
    if not moves:
        return "not moved"
    if any(moves):
        return "moved"
    return "held" if item.decision.details.get("hold") == "yes" else "recorded"


class Sorting(Agent):
    name = "sorting"
    version = "1"
    description = (
        "Moves mail of listed senders from the inbox into the folder of their "
        "group. No model."
    )
    triggers = Trigger(events=frozenset({"message.created"}))
    actions = frozenset(
        {Action.CREATE_FOLDER, Action.MOVE_TO_FOLDER, Action.ADD_KEYWORD}
    )
    limits = Limits(model_calls_per_message=0, model_calls_per_day=0)
    requires = Requires(settings=("sorting_file",))
    # No $ in front: IMAP registers such keywords with meanings, as $Junk.
    default_keyword = "agent-sorted"

    # -- what it reads besides its settings -----------------------------------

    def prepare(self) -> None:
        """Read the list now, so a wrong one stops the start."""
        _ = self.groups

    @cached_property
    def groups(self) -> Groups:
        path = self.settings.sorting_file
        if path is None:
            raise ConfigError(f"{PREFIX}SORTING_FILE is not set")
        return load_groups(path)

    def may_create(self, path: str) -> bool:
        return self.groups.may_create(path)

    # -- the contract -------------------------------------------------------------

    def select(self, event: Event) -> Route | None:
        return Route.DECIDE if event.type == "message.created" else None

    def admit(self, message: MailMessage) -> bool:
        """A message in the inbox the agent has not sorted before: one that
        carries its keyword was put back there by a person."""
        if not message.in_role("inbox"):
            return False
        own = self.keyword.casefold()
        return all(k.casefold() != own for k in message.keywords)

    def baseline(self, message: MailMessage) -> Decision:
        sender = message.sender.email if message.sender else None
        found = self.groups.match(sender)
        if found is None:
            return Decision(label=NONE, source="baseline", details={"match": "none"})
        group = found.group
        if group is None:
            return Decision(
                label=NONE,
                source="baseline",
                details={
                    "match": "ambiguous",
                    "groups": ",".join(g.name for g in found.groups),
                },
            )
        details = {"match": "group", "rule": found.kind.name.lower()}
        if group.hold:
            details["hold"] = "yes"
        return Decision(label=group.name, source="baseline", details=details)

    async def decide(self, message: MailMessage, context: Context) -> Decision:
        return self.baseline(message)

    async def effect(
        self, decision: Decision, message: MailMessage, context: Context
    ) -> list[ActionRequest]:
        # The group as the list says now, not as it said at the decision.
        sender = message.sender.email if message.sender else None
        found = self.groups.match(sender)
        group = found.group if found is not None else None
        if group is None:
            return []
        return self._move(group, message)

    def summarize(self, shown: list[Shown]) -> list[str]:
        """Per group what became of its messages, the senders in no group
        that wrote most often, as candidates for the list, and the senders
        left alone because two groups name them alike."""
        lines: list[str] = []
        fates: dict[str, Counter[str]] = {}
        for item in shown:
            if item.decision.label != NONE:
                fates.setdefault(item.decision.label, Counter())[_fate(item)] += 1
        if fates:
            lines.append("groups:")
            for name in sorted(fates):
                counted = fates[name]
                said = ", ".join(
                    f"{counted[fate]} {fate}"
                    for fate in ("moved", "recorded", "held", "not moved")
                    if counted[fate]
                )
                lines.append(f"  {name}: {said}")
        unknown = Counter(
            item.sender.lower()
            for item in shown
            if item.sender and item.decision.details.get("match") == "none"
        )
        if unknown:
            lines.append("senders in no group, candidates for the list:")
            lines += [
                f"  {sender} ({_plural(count, 'message')})"
                for sender, count in unknown.most_common(CANDIDATES)
            ]
        alike = Counter(
            (item.sender.lower(), item.decision.details.get("groups", ""))
            for item in shown
            if item.sender and item.decision.details.get("match") == "ambiguous"
        )
        if alike:
            lines.append("left alone, two groups name the sender alike:")
            lines += [
                f"  {sender}: {groups} ({_plural(count, 'message')})"
                for (sender, groups), count in alike.most_common()
            ]
        return lines

    def _move(self, group: Group, message: MailMessage) -> list[ActionRequest]:
        """The folders from the top, the move, and with it the keyword. A
        held group asks for all of it to be recorded only."""
        held = group.hold
        requests = [
            ActionRequest(
                Action.CREATE_FOLDER,
                message.ref,
                folder=path,
                why=group.name,
                held=held,
            )
            for path in group.folders
        ]
        requests.append(
            ActionRequest(
                Action.MOVE_TO_FOLDER,
                message.ref,
                folder=group.folder,
                why=group.name,
                held=held,
            )
        )
        # The keyword says the message was moved. It is asked for only
        # where the move is taken: in full and for a group not held. The
        # executor takes nothing after a refused move.
        if self.settings.stage == "full" and not held:
            requests.append(
                ActionRequest(
                    Action.ADD_KEYWORD, message.ref, keyword=self.keyword, why="sorted"
                )
            )
        return requests
