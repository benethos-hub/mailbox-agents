"""The report: decision, evidence and action, with subject and sender."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from benethos_mailbox_agent.cli import main
from benethos_mailbox_agent.cli.report import Entry, render
from benethos_mailbox_agent.records import (
    LABEL,
    Address,
    Decision,
    Evidence,
    MailMessage,
    MessageRef,
)
from benethos_mailbox_agent.store import ActionRow, MessageRow
from fakes import ACCOUNT, FakeService, wire_message
from test_cli import configure, service  # noqa: F401 - the fixture

NOW = datetime(2026, 11, 17, 9, 0, tzinfo=UTC)
REF = MessageRef(account_id=ACCOUNT, message_id="m1")


def test_render_one_entry() -> None:
    entry = Entry(
        row=MessageRow(REF, "done", 0, NOW, NOW, NOW),
        message=MailMessage(
            ref=REF,
            subject="Ihre Rechnung",
            sender=Address(email="billing@supplier.test", name="Billing"),
        ),
        decision=Decision(
            label="invoice",
            source="model",
            fields={"supplier": "Hosting"},
            details={"supplier_source": "rule"},
            evidence=(
                Evidence(
                    field=LABEL, value="invoice", quote="Ihre Rechnung", found=True
                ),
                Evidence(field="x", value="y", quote="nowhere", found=False),
            ),
        ),
        model="local-small",
        baseline=Decision(label="invoice", source="baseline"),
        actions=[
            ActionRow(REF, "add_keyword", "invoice", {}, "shadow", False, NOW),
            ActionRow(REF, "move_to_folder", "Invoices/Hosting", {}, "full", True, NOW),
        ],
    )

    assert render([entry]) == [
        f"2026-11-17 09:00  {ACCOUNT}/m1  done",
        "  from: Billing <billing@supplier.test>",
        "  subject: Ihre Rechnung",
        "  decision: invoice (model, local-small) supplier=Hosting"
        " supplier_source=rule",
        '  evidence: label "Ihre Rechnung" found',
        '  evidence: x "nowhere" NOT found',
        "  baseline: invoice",
        "  action: add_keyword invoice (shadow: would have been done)",
        "  action: move_to_folder Invoices/Hosting (full: done)",
        "",
    ]


def test_render_a_refused_decision_and_a_message_gone() -> None:
    entry = Entry(
        row=MessageRow(REF, "decided", 0, NOW, NOW, NOW),
        message=MailMessage(ref=REF),
        decision=Decision(label="invoice", source="model", refused="evidence"),
        model="",
        baseline=None,
    )
    gone = Entry(MessageRow(REF, "skipped", 0, NOW, NOW, NOW), None, None, "", None)

    lines = render([entry, gone])

    assert "  from: (no sender)" in lines
    assert "  subject: (none)" in lines
    assert "  decision: invoice (model) refused: evidence" in lines
    assert "  (not fetched: gone from the mailbox or no service)" in lines


def test_report_after_a_run(
    service: FakeService,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure(monkeypatch)
    main(["run", "--agent", "counting"])
    service.add(wire_message("m1", subject="Quarterly numbers", sender="a@b.test"))
    service.add(wire_message("m2", subject="Gone soon"))
    main(["run", "--agent", "counting"])
    del service.messages[(ACCOUNT, "m2")]
    capsys.readouterr()

    assert main(["report", "--agent", "counting"]) == 0

    out = capsys.readouterr().out
    assert "subject: Quarterly numbers" in out
    assert "from: a@b.test" in out
    assert "decision: counted (baseline) roles=inbox" in out
    assert "(not fetched" in out

    assert main(["report", "--agent", "counting", "--state", "failed"]) == 0
    assert "nothing recorded yet" in capsys.readouterr().out


def test_report_offline_needs_no_service(
    service: FakeService,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure(monkeypatch)
    main(["run", "--agent", "counting"])
    service.add(wire_message("m1"))
    main(["run", "--agent", "counting"])
    monkeypatch.delenv("MAILBOX_AGENT_SERVICE_TOKEN")
    capsys.readouterr()

    assert main(["report", "--agent", "counting", "--offline", "--limit", "1"]) == 0
    assert "(not fetched" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("argv", "said"),
    [
        (["report", "--agent", "counting"], "misses MAILBOX_AGENT_SERVICE_URL"),
        (["report", "--agent", "counting", "--offline"], "no state file"),
        (["report", "--agent", "counting", "--state", "lost"], "--state is one of"),
        (["report", "--agent", "counting", "--limit", "0"], "--limit"),
    ],
)
def test_report_refusals(
    service: FakeService,  # noqa: F811
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    said: str,
) -> None:
    assert main(argv) == 2
    assert said in capsys.readouterr().err
