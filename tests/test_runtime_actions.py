"""The action executor: declared actions only, the stage, what was before."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping
from pathlib import Path

import httpx
import pytest

from benethos_mailbox_agents.contract import Action, ActionRequest
from benethos_mailbox_agents.errors import MailboxUnavailableError, MessageGoneError
from benethos_mailbox_agents.records import FolderRef, MessageRef
from benethos_mailbox_agents.runtime.actions import Executor, Outcome
from fakes import ACCOUNT, wire_message
from helpers import Echo, Wired, settings, wired

REF = MessageRef(account_id=ACCOUNT, message_id="m1")
PATH = f"/v1/accounts/{ACCOUNT}/messages/m1"

ADD = ActionRequest(Action.ADD_KEYWORD, REF, keyword="echo")
REMOVE = ActionRequest(Action.REMOVE_KEYWORD, REF, keyword="echo")
MOVE = ActionRequest(Action.MOVE_TO_FOLDER, REF, folder="Invoices/Hosting")


@pytest.fixture
async def world(tmp_path: Path) -> AsyncIterator[Wired]:
    async with wired(tmp_path) as found:
        found.service.add(wire_message("m1", keywords=["$seen"]))
        yield found


class Every(Echo):
    actions = frozenset(Action)


def executor(world: Wired, stage: str = "full", **values: object) -> Executor:
    return Executor(
        agent=Every(settings(stage=stage, **values)),
        store=world.store,
        mailbox=world.mailbox,
        now=world.clock,
    )


async def test_full_takes_every_declared_action(world: Wired) -> None:
    await executor(world)([ADD, MOVE])

    assert world.service.writes() == [
        (PATH, {"add_keywords": ["echo"]}),
        (PATH, {"folder_ids": ["inv-hosting"]}),
    ]
    keyword, move = world.store.actions(REF)
    assert (keyword.argument, keyword.before, keyword.executed) == (
        "echo",
        {"keywords": ["$seen"]},
        True,
    )
    assert (move.argument, move.before, move.stage) == (
        "Invoices/Hosting",
        {"folders": ["inbox"]},
        "full",
    )


async def test_shadow_records_and_changes_nothing(world: Wired) -> None:
    await executor(world, "shadow")([ADD, MOVE])

    assert world.service.writes() == []
    assert [(a.action, a.executed) for a in world.store.actions(REF)] == [
        ("add_keyword", False),
        ("move_to_folder", False),
    ]


async def test_keyword_sets_the_keyword_and_moves_nothing(world: Wired) -> None:
    await executor(world, "keyword")([ADD, MOVE])

    assert world.service.writes() == [(PATH, {"add_keywords": ["echo"]})]
    assert [a.executed for a in world.store.actions(REF)] == [True, False]


async def test_an_action_already_done_is_not_taken_again(world: Wired) -> None:
    run = executor(world)
    await run([ADD, MOVE])
    await run([ADD, MOVE])

    assert len(world.service.writes()) == 2
    assert len(world.store.actions(REF)) == 2


async def test_an_action_recorded_before_is_not_recorded_again(
    world: Wired, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    asked = [make("Providers"), make("Providers/CloudHost"), ADD]

    for _ in range(3):
        assert await maker(world, "shadow")(asked) == [Outcome.RECORDED] * 3

    assert world.service.writes() == []
    assert [(a.action, a.argument) for a in world.store.actions(REF)] == [
        ("create_folder", "Providers"),
        ("create_folder", "Providers/CloudHost"),
        ("add_keyword", "echo"),
    ]
    lines = [r.getMessage() for r in caplog.records if ".actions." in r.name]
    assert len(lines) == 3


async def test_an_action_recorded_in_another_stage_is_recorded_again(
    world: Wired,
) -> None:
    await executor(world, "shadow")([MOVE])
    await executor(world, "keyword")([MOVE])

    assert [a.stage for a in world.store.actions(REF)] == ["shadow", "keyword"]


async def test_removing_a_keyword_that_is_not_there_does_nothing(world: Wired) -> None:
    assert await executor(world)([REMOVE]) == [Outcome.PRESENT]

    await executor(world)([ADD])
    assert await executor(world)([REMOVE]) == [Outcome.DONE]
    assert world.service.writes()[-1] == (PATH, {"remove_keywords": ["echo"]})


@pytest.mark.parametrize(
    "request_",
    [
        ActionRequest(Action.REMOVE_KEYWORD, REF, keyword="echo"),
        ActionRequest(Action.ADD_KEYWORD, REF, keyword="someone-elses"),
        ActionRequest(Action.MOVE_TO_FOLDER, REF, folder="Missing"),
        ActionRequest(Action.MOVE_TO_FOLDER, REF, folder="Trash"),
        ActionRequest(Action.MOVE_TO_FOLDER, REF, folder="Trash/Sub"),
        ActionRequest(Action.MOVE_TO_FOLDER, REF, folder=None),
        ActionRequest(
            Action.ADD_KEYWORD,
            MessageRef(account_id=ACCOUNT, message_id="gone"),
            keyword="echo",
        ),
    ],
    ids=[
        "undeclared",
        "foreign-keyword",
        "missing-folder",
        "trash",
        "below-trash",
        "no-folder",
        "gone",
    ],
)
async def test_a_refused_action_is_neither_taken_nor_recorded(
    world: Wired, request_: ActionRequest
) -> None:
    class Narrow(Echo):
        actions = frozenset({Action.ADD_KEYWORD, Action.MOVE_TO_FOLDER})

    run = Executor(
        agent=Narrow(settings(stage="full")),
        store=world.store,
        mailbox=world.mailbox,
        now=world.clock,
    )

    if request_.ref.message_id == "gone":
        with pytest.raises(MessageGoneError):
            await run([request_])
    else:
        assert await run([request_]) == [Outcome.REFUSED]
    assert world.service.writes() == []
    assert world.store.actions() == []


@pytest.mark.parametrize("folder", ["trash", "junk", "trash-sub"])
@pytest.mark.parametrize("request_", [ADD, MOVE], ids=["keyword", "move"])
async def test_a_message_in_the_trash_or_junk_is_left_alone(
    tmp_path: Path, folder: str, request_: ActionRequest
) -> None:
    async with wired(tmp_path) as found:
        found.service.add(wire_message("m1", folder_ids=[folder]))

        assert await executor(found)([request_]) == [Outcome.REFUSED]
        assert found.service.writes() == []
        assert found.store.actions() == []


async def test_an_account_the_agent_does_not_work_on_is_refused(world: Wired) -> None:
    assert await executor(world, accounts=["other"])([ADD]) == [Outcome.REFUSED]
    assert world.service.writes() == []


async def test_what_was_before_is_recorded_before_the_action(
    world: Wired, monkeypatch: pytest.MonkeyPatch
) -> None:
    def crash(action_id: int) -> None:
        raise RuntimeError("the process ends here")

    monkeypatch.setattr(world.store, "mark_action_executed", crash)

    with pytest.raises(RuntimeError):
        await executor(world)([MOVE])

    assert world.service.writes() == [(PATH, {"folder_ids": ["inv-hosting"]})]
    (move,) = world.store.actions(REF)
    assert (move.action, move.before) == ("move_to_folder", {"folders": ["inbox"]})


async def test_a_write_the_service_refuses_is_not_recorded(world: Wired) -> None:
    world.service.write_refusal = (422, "keyword_refused")

    assert await executor(world)([ADD]) == [Outcome.REFUSED]
    assert world.store.actions() == []


async def test_the_log_line_names_why(
    world: Wired, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    request = ActionRequest(Action.ADD_KEYWORD, REF, keyword="echo", why="due")

    await executor(world)([request])
    await executor(world)([MOVE])

    lines = [r.getMessage() for r in caplog.records if ".actions." in r.name]
    assert lines[0].endswith("carried out add_keyword on message m1 in stage full: due")
    assert lines[1].endswith("in stage full")


async def test_a_service_that_is_away_is_raised(world: Wired) -> None:
    world.service.down = True

    with pytest.raises(MailboxUnavailableError):
        await executor(world)([ADD])


def taken_then_away(
    world: Wired, monkeypatch: pytest.MonkeyPatch, *, down: bool = False
) -> None:
    """The service takes each write and then answers 503, and with
    ``down`` answers 503 to everything after."""
    for name in ("_update", "_create_folder"):
        write = getattr(world.service, name)

        def away(
            request: httpx.Request,
            parts: list[str],
            write: Callable[[httpx.Request, list[str]], httpx.Response] = write,
        ) -> httpx.Response:
            write(request, parts)
            world.service.down = down
            return httpx.Response(503, json={"error": {"code": "unavailable"}})

        monkeypatch.setattr(world.service, name, away)


@pytest.mark.parametrize(
    "request_",
    [MOVE, ADD, ActionRequest(Action.CREATE_FOLDER, REF, folder="Providers")],
    ids=["move", "keyword", "folder"],
)
async def test_an_action_taken_while_the_answer_failed_counts_as_taken(
    world: Wired, monkeypatch: pytest.MonkeyPatch, request_: ActionRequest
) -> None:
    taken_then_away(world, monkeypatch)

    with pytest.raises(MailboxUnavailableError):
        await maker(world)([request_])

    (taken,) = world.store.actions(REF)
    assert (taken.action, taken.executed) == (request_.action.value, True)


async def test_an_action_the_service_cannot_tell_of_stays_not_taken(
    world: Wired, monkeypatch: pytest.MonkeyPatch
) -> None:
    taken_then_away(world, monkeypatch, down=True)

    with pytest.raises(MailboxUnavailableError):
        await executor(world)([MOVE])

    (move,) = world.store.actions(REF)
    assert (move.action, move.executed) == ("move_to_folder", False)


async def test_a_move_not_taken_while_the_service_was_away_is_dropped(
    world: Wired,
) -> None:
    world.service.write_refusal = (503, "unavailable")

    with pytest.raises(MailboxUnavailableError):
        await executor(world)([MOVE])

    assert world.store.actions() == []


# -- folders an agent makes -----------------------------------------------------

MAY_MAKE = frozenset(
    {
        "Providers",
        "Providers/CloudHost",
        "Trash/New",
        "Junk/New",
        "invoices",
        "Invoices/Hosting",
        "Missing/Below",
    }
)


class Maker(Every):
    def may_create(self, path: str, folders: Mapping[str, FolderRef]) -> bool:
        # The executor hands over the account's folders by path.
        return path in MAY_MAKE and folders["INBOX"].role == "inbox"


def maker(world: Wired, stage: str = "full") -> Executor:
    return Executor(
        agent=Maker(settings(stage=stage)),
        store=world.store,
        mailbox=world.mailbox,
        now=world.clock,
    )


def make(path: str) -> ActionRequest:
    return ActionRequest(Action.CREATE_FOLDER, REF, folder=path, why="group")


async def test_a_folder_the_agent_may_make_is_made_from_the_top(world: Wired) -> None:
    run = maker(world)

    outcomes = await run([make(p) for p in ("Providers", "Providers/CloudHost")])

    assert outcomes == [Outcome.DONE, Outcome.DONE]
    assert world.service.made() == [
        {"name": "Providers"},
        {"name": "CloudHost", "parent_id": "Providers"},
    ]
    made = world.store.actions(REF)
    assert [(a.action, a.argument, a.before, a.executed) for a in made] == [
        ("create_folder", "Providers", {}, True),
        ("create_folder", "Providers/CloudHost", {}, True),
    ]


@pytest.mark.parametrize(
    "path",
    ["Elsewhere", "Trash/New", "Junk/New", "invoices", "Missing/Below"],
    ids=["not-declared", "below-trash", "below-junk", "other-case", "parent-missing"],
)
async def test_a_folder_is_refused(world: Wired, path: str) -> None:
    assert await maker(world)([make(path)]) == [Outcome.REFUSED]
    assert world.service.made() == []
    assert world.store.actions() == []


async def test_a_folder_that_exists_is_not_made_again(world: Wired) -> None:
    assert await maker(world)([make("Invoices/Hosting")]) == [Outcome.PRESENT]
    assert world.service.made() == []


async def test_an_agent_makes_no_folder_unless_it_says_so(world: Wired) -> None:
    assert await executor(world)([make("Providers")]) == [Outcome.REFUSED]
    assert world.service.made() == []


@pytest.mark.parametrize("stage", ["shadow", "keyword"])
async def test_a_folder_is_recorded_only_below_full(world: Wired, stage: str) -> None:
    assert await maker(world, stage)([make("Providers")]) == [Outcome.RECORDED]
    assert world.service.made() == []
    (made,) = world.store.actions(REF)
    assert (made.action, made.argument, made.executed) == (
        "create_folder",
        "Providers",
        False,
    )


async def test_a_move_below_a_held_folder_is_recorded_only(world: Wired) -> None:
    held = ActionRequest(Action.CREATE_FOLDER, REF, folder="Providers", held=True)
    move = ActionRequest(Action.MOVE_TO_FOLDER, REF, folder="Providers")

    await maker(world)([held, move])

    assert world.service.writes() == []
    assert world.service.made() == []
    assert [(a.action, a.executed) for a in world.store.actions(REF)] == [
        ("create_folder", False),
        ("move_to_folder", False),
    ]


async def test_a_folder_below_a_held_folder_is_recorded_only(world: Wired) -> None:
    held = ActionRequest(Action.CREATE_FOLDER, REF, folder="Providers", held=True)

    await maker(world)([held, make("Providers/CloudHost")])

    assert world.service.made() == []
    assert [(a.argument, a.executed) for a in world.store.actions(REF)] == [
        ("Providers", False),
        ("Providers/CloudHost", False),
    ]


# -- a message is moved once ----------------------------------------------------


async def test_a_message_the_owner_moved_back_is_not_moved_again(
    world: Wired,
) -> None:
    run = executor(world)
    assert await run([MOVE]) == [Outcome.DONE]
    world.service.messages[(ACCOUNT, "m1")]["folder_ids"] = ["inbox"]

    assert await run([MOVE]) == [Outcome.REFUSED]
    assert world.service.writes() == [(PATH, {"folder_ids": ["inv-hosting"]})]
    assert world.service.messages[(ACCOUNT, "m1")]["folder_ids"] == ["inbox"]


async def test_no_folder_is_made_for_a_message_moved_before(world: Wired) -> None:
    run = maker(world)
    await run([MOVE])
    world.service.messages[(ACCOUNT, "m1")]["folder_ids"] = ["inbox"]

    outcomes = await run([make("Providers"), MOVE])

    assert outcomes == [Outcome.SKIPPED, Outcome.REFUSED]
    assert world.service.made() == []
    assert [a.action for a in world.store.actions(REF)] == ["move_to_folder"]
    assert world.service.messages[(ACCOUNT, "m1")]["folder_ids"] == ["inbox"]


async def test_a_move_only_recorded_does_not_count(world: Wired) -> None:
    assert await executor(world, "shadow")([MOVE]) == [Outcome.RECORDED]

    assert await executor(world)([MOVE]) == [Outcome.DONE]


async def test_after_a_refused_move_the_rest_is_not_taken(world: Wired) -> None:
    missing = ActionRequest(Action.MOVE_TO_FOLDER, REF, folder="Missing")

    assert await executor(world)([missing, ADD]) == [Outcome.REFUSED]

    assert world.service.writes() == []
    assert world.store.actions() == []


async def test_after_a_refused_folder_the_rest_is_not_taken(world: Wired) -> None:
    await maker(world)([make("Elsewhere"), MOVE, ADD])

    assert world.service.writes() == []


async def test_a_refused_keyword_does_not_stop_a_move(world: Wired) -> None:
    other = ActionRequest(Action.ADD_KEYWORD, REF, keyword="other")

    await executor(world)([other, MOVE])

    assert world.service.writes() == [(PATH, {"folder_ids": ["inv-hosting"]})]
