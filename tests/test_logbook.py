"""The log: stderr, one function per line, nothing of a mail."""

from __future__ import annotations

import ast
import io
import logging
from pathlib import Path

import pytest

import benethos_mailbox_agent
from benethos_mailbox_agent import errors, logbook
from benethos_mailbox_agent.logbook.lines import describe

SOURCE = Path(benethos_mailbox_agent.__file__).parent


@pytest.fixture
def stream() -> io.StringIO:
    found = io.StringIO()
    logbook.configure("DEBUG", stream=found)
    return found


def test_configure_twice_keeps_one_handler(stream: io.StringIO) -> None:
    logbook.configure("DEBUG", stream=stream)
    logbook.started("invoices", "1", "shadow")

    assert stream.getvalue().count("started") == 1


def test_the_libraries_are_held_at_warning(stream: io.StringIO) -> None:
    for name in logbook.LIBRARIES:
        assert logging.getLogger(name).level == logging.WARNING


def test_an_error_is_named_never_quoted(stream: io.StringIO) -> None:
    error = errors.MailboxRefusedError(
        "Subject: secret plans", status=404, reason="not_found"
    )

    logbook.step_failed("invoices", "m1", "fetch", error)

    line = stream.getvalue()
    assert "MailboxRefusedError(mailbox_refused)" in line
    assert "secret plans" not in line


def test_describe_a_foreign_error() -> None:
    assert describe(ValueError("x")) == "ValueError"


def test_every_line_function_writes_one_line(stream: io.StringIO) -> None:
    error = errors.GatewayUnavailableError("away")
    logbook.started("a", "1", "shadow")
    logbook.stopped("a", "signal")
    logbook.metrics_serving("a", 9464)
    logbook.migrated("a", 1, 2, ("schema 2: x",))
    logbook.feed_read("a", 3, 1)
    logbook.feed_expired("a")
    logbook.backfill_done("a", 4, 7)
    logbook.tick_done("a", 2)
    logbook.pass_done("a", 0.5, 0)
    logbook.pass_failed("a", error)
    logbook.upstream_away("a", error, 30)
    logbook.message_state("a", "m1", "done")
    logbook.step_done("a", "m1", "model", 12)
    logbook.step_failed("a", "m1", "model", error)
    logbook.answer_refused("a", "m1", "schema")
    logbook.evidence_missing("a", "m1", "label")
    logbook.action_done("a", "m1", "add_keyword", "shadow", False, "due")
    logbook.action_refused("a", "m1", "move_to_folder", error)

    assert len(stream.getvalue().splitlines()) == 18


def test_no_other_module_imports_logging() -> None:
    importers = []
    for path in SOURCE.rglob("*.py"):
        if "logbook" in path.relative_to(SOURCE).parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            if any(name.split(".")[0] == "logging" for name in names):
                importers.append(path.relative_to(SOURCE).as_posix())

    assert importers == []
