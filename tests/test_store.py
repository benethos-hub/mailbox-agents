"""The state file: migrations, the tables, and a reader beside the writer."""

from __future__ import annotations

import re
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from benethos_mailbox_agent.errors import ConfigError
from benethos_mailbox_agent.records import MessageRef, StepResult
from benethos_mailbox_agent.store import MIGRATIONS, Store, path_for

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 17, 9, 0, tzinfo=UTC)
REF = MessageRef(account_id="acc", message_id="m1")
OTHER = MessageRef(account_id="acc", message_id="m2")


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return path_for(tmp_path / "data", "invoices")


@pytest.fixture
def store(path: Path) -> Iterator[Store]:
    with Store.open(path) as opened:
        yield opened


def test_the_file_is_named_after_the_agent(tmp_path: Path) -> None:
    assert path_for(tmp_path, "invoices").name == "invoices.db"


def test_a_new_file_runs_every_migration_in_wal_mode(store: Store) -> None:
    assert store.version == len(MIGRATIONS)
    assert store._one("PRAGMA journal_mode")[0] == "wal"


def test_opening_again_runs_nothing_twice(path: Path, store: Store) -> None:
    store.set_cursor("s1", NOW)
    store.close()
    with Store.open(path) as again:
        assert again.migrate() == len(MIGRATIONS)
        assert again.cursor() == "s1"


def test_one_writer_per_state_file(path: Path, store: Store) -> None:
    with pytest.raises(ConfigError, match="already running: one writer"):
        Store.open(path)
    with Store.open(path, read_only=True) as reader:
        assert reader.cursor() is None

    store.close()
    with Store.open(path) as again:
        again.set_cursor("s2", NOW)


def test_the_tables_are_those_of_specs_section_9(store: Store) -> None:
    text = (ROOT / "SPECS.md").read_text(encoding="utf-8")
    section = text[text.index("\n## 9. ") : text.index("\n## 10. ")]
    named = set(re.findall(r"^\| `([a-z_]+)` \|", section, flags=re.MULTILINE))
    tables = {
        row[0]
        for row in store._all(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%'"
        )
    }

    assert named == tables


def test_a_reader_needs_the_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="no state file"):
        Store.open(tmp_path / "none.db", read_only=True)


def test_a_reader_refuses_a_newer_schema(path: Path, store: Store) -> None:
    store._write(f"PRAGMA user_version = {len(MIGRATIONS) + 1}")

    with pytest.raises(ConfigError, match="schema version"):
        Store.open(path, read_only=True)


def test_a_reader_sees_the_writer_and_cannot_write(path: Path, store: Store) -> None:
    store.set_cursor("s2", NOW)

    with Store.open(path, read_only=True) as reader:
        assert reader.cursor() == "s2"
        with pytest.raises(sqlite3.OperationalError):
            reader.set_cursor("s3", NOW)


def test_another_process_reads_while_the_writer_holds_the_file(
    path: Path, store: Store
) -> None:
    store.enqueue(REF, NOW)
    script = (
        "import sqlite3,sys;"
        "c=sqlite3.connect(sys.argv[1]+'?mode=ro',uri=True);"
        "print(c.execute('SELECT COUNT(*) FROM messages').fetchone()[0]);"
        "c.close()"
    )

    found = subprocess.run(
        [sys.executable, "-c", script, path.resolve().as_uri()],
        capture_output=True,
        text=True,
        check=True,
    )

    assert found.stdout.strip() == "1"


def test_a_message_is_enqueued_once(store: Store) -> None:
    assert store.enqueue(REF, NOW)
    assert not store.enqueue(REF, NOW + timedelta(minutes=1))

    row = store.message(REF)
    assert row is not None
    assert (row.state, row.attempts, row.created) == ("pending", 0, NOW)


def test_again_makes_a_finished_message_pending_anew(store: Store) -> None:
    store.enqueue(REF, NOW)
    store.set_state(REF, "done", NOW, attempts=2)

    assert store.enqueue(REF, NOW, again=True)
    row = store.message(REF)
    assert row is not None
    assert (row.state, row.attempts) == ("pending", 0)
    assert not store.enqueue(REF, NOW, again=True)


def test_due_waits_for_the_next_attempt(store: Store) -> None:
    store.enqueue(REF, NOW)
    store.enqueue(OTHER, NOW + timedelta(seconds=1))
    store.set_state(
        REF, "pending", NOW, attempts=1, next_attempt=NOW + timedelta(hours=1)
    )

    assert [row.ref for row in store.due(NOW + timedelta(minutes=1))] == [OTHER]
    assert len(store.due(NOW + timedelta(hours=2))) == 2


def test_counts_name_every_state(store: Store) -> None:
    store.enqueue(REF, NOW)
    store.enqueue(OTHER, NOW)
    store.set_state(OTHER, "skipped", NOW)

    assert store.counts() == {
        "pending": 1,
        "skipped": 1,
        "decided": 0,
        "done": 0,
        "failed": 0,
    }
    assert store.oldest_pending() == NOW
    assert [row.ref for row in store.messages("skipped")] == [OTHER]
    assert len(store.messages()) == 2


def test_an_unknown_state_is_refused(store: Store) -> None:
    with pytest.raises(ValueError, match="no message state"):
        store.set_state(REF, "lost", NOW)


def test_a_naive_time_is_refused(store: Store) -> None:
    with pytest.raises(ValueError, match="zone"):
        store.set_cursor("s", datetime(2026, 1, 1))  # noqa: DTZ001


def test_a_step_is_found_by_prompt_version_and_model(store: Store) -> None:
    step = StepResult(
        step="model",
        prompt_version="v1",
        model="reported-model",
        result={"label": "invoice"},
        tokens_in=10,
        tokens_out=2,
        duration_ms=5,
        at=NOW,
    )
    store.add_step(REF, step, "alias")

    assert store.step(REF, "model", "v1", "alias") == step
    assert store.step(REF, "model", "v2", "alias") is None
    assert store.step(REF, "model", "v1", "other") is None
    assert store.steps(REF) == [step]
    assert store.model_calls_since(NOW) == 1
    assert store.model_calls_since(NOW + timedelta(seconds=1)) == 0


def test_an_action_keeps_what_was_before(store: Store) -> None:
    store.add_action(
        REF,
        action="move_to_folder",
        argument="f2",
        before={"folders": ["f1"]},
        stage="full",
        executed=True,
        now=NOW,
    )

    (row,) = store.actions(REF)
    assert (row.argument, row.before, row.executed) == ("f2", {"folders": ["f1"]}, True)
    assert store.actions() == [row]
    assert store.actions(OTHER) == []


def test_an_open_item_from_opening_to_closing(store: Store) -> None:
    due = NOW + timedelta(days=3)
    store.open_item(REF, "t1", due, NOW)

    assert store.due_items(NOW) == []
    (item,) = store.due_items(due)
    assert (item.thread_id, item.is_open, item.keyword_set) == ("t1", True, False)
    assert store.items_in_thread("acc", "t1") == [item]

    store.mark_keyword(REF, True)
    assert store.due_items(due) == []
    assert store.close_item(REF, "replied", due)
    assert not store.close_item(REF, "replied", due)
    closed = store.item(REF)
    assert closed is not None
    assert (closed.is_open, closed.reason) == (False, "replied")
    assert store.items_in_thread("acc", "t1") == []


def test_opening_an_item_again_restarts_it(store: Store) -> None:
    store.open_item(REF, "t1", NOW, NOW)
    store.mark_keyword(REF, True)
    store.close_item(REF, "replied", NOW)

    store.open_item(REF, "t1", NOW + timedelta(days=5), NOW)

    item = store.item(REF)
    assert item is not None
    assert (item.is_open, item.keyword_set) == (True, False)


def test_kept_calls_are_purged(store: Store) -> None:
    store.add_call(REF, {"messages": []}, {"choices": []}, NOW)
    store.add_call(REF, {}, {}, NOW + timedelta(days=2))

    assert store.purge_calls(NOW + timedelta(days=1)) == 1
    assert store.count_calls() == 1


def test_last_pass(store: Store) -> None:
    assert store.last_pass() is None
    store.set_last_pass(NOW)
    store.set_last_pass(NOW + timedelta(seconds=5))

    assert store.last_pass() == NOW + timedelta(seconds=5)


def test_a_failed_migration_leaves_the_file_as_it_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import benethos_mailbox_agent.store.store as module

    monkeypatch.setattr(module, "MIGRATIONS", (*MIGRATIONS, "CREATE TABLE broken ("))
    with pytest.raises(sqlite3.OperationalError):
        Store.open(tmp_path / "x.db")

    with closing(sqlite3.connect(tmp_path / "x.db")) as raw:
        assert raw.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
