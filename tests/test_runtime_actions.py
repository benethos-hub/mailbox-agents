"""The action executor: declared actions only, the stage, what was before."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from benethos_mailbox_agent.contract import Action, ActionRequest
from benethos_mailbox_agent.errors import MailboxUnavailableError
from benethos_mailbox_agent.records import MessageRef
from benethos_mailbox_agent.runtime.actions import Executor, Outcome
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


async def test_removing_a_keyword_that_is_not_there_does_nothing(world: Wired) -> None:
    assert await executor(world).run(REMOVE) is Outcome.PRESENT

    await executor(world).run(ADD)
    assert await executor(world).run(REMOVE) is Outcome.DONE
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

    gone = request_.ref.message_id == "gone"
    expected = Outcome.GONE if gone else Outcome.REFUSED
    assert await run.run(request_) is expected
    assert world.service.writes() == []
    assert world.store.actions() == []


@pytest.mark.parametrize("folder", ["trash", "junk"])
@pytest.mark.parametrize("request_", [ADD, MOVE], ids=["keyword", "move"])
async def test_a_message_in_the_trash_or_junk_is_left_alone(
    tmp_path: Path, folder: str, request_: ActionRequest
) -> None:
    async with wired(tmp_path) as found:
        found.service.add(wire_message("m1", folder_ids=[folder]))

        assert await executor(found).run(request_) is Outcome.REFUSED
        assert found.service.writes() == []
        assert found.store.actions() == []


async def test_an_account_the_agent_does_not_work_on_is_refused(world: Wired) -> None:
    assert await executor(world, accounts=["other"]).run(ADD) is Outcome.REFUSED
    assert world.service.writes() == []


async def test_what_was_before_is_recorded_before_the_action(
    world: Wired, monkeypatch: pytest.MonkeyPatch
) -> None:
    def crash(action_id: int) -> None:
        raise RuntimeError("the process ends here")

    monkeypatch.setattr(world.store, "mark_action_executed", crash)

    with pytest.raises(RuntimeError):
        await executor(world).run(MOVE)

    assert world.service.writes() == [(PATH, {"folder_ids": ["inv-hosting"]})]
    (move,) = world.store.actions(REF)
    assert (move.action, move.before) == ("move_to_folder", {"folders": ["inbox"]})


async def test_a_write_the_service_refuses_is_not_recorded(world: Wired) -> None:
    world.service.write_refusal = (422, "keyword_refused")

    assert await executor(world).run(ADD) is Outcome.REFUSED
    assert world.store.actions() == []


async def test_the_log_line_names_why(
    world: Wired, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    request = ActionRequest(Action.ADD_KEYWORD, REF, keyword="echo", why="due")

    await executor(world).run(request)
    await executor(world).run(MOVE)

    lines = [r.getMessage() for r in caplog.records if ".actions." in r.name]
    assert lines[0].endswith("carried out add_keyword on message m1 in stage full: due")
    assert lines[1].endswith("in stage full")


async def test_a_service_that_is_away_is_raised(world: Wired) -> None:
    world.service.down = True

    with pytest.raises(MailboxUnavailableError):
        await executor(world).run(ADD)
