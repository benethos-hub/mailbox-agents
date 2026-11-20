"""The settings of the live checks: from their file alone, on this machine."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

from benethos_mailbox_agents.records import MessageRef
from benethos_mailbox_agents.sources.mailbox import connect
from fakes import ACCOUNT, FakeService, wire_message
from helpers import ROOT, load_script

# live/ is no package and lies outside testpaths: the module is loaded by
# its path, as a script would find it beside itself.
COMMON = ROOT / "live" / "common.py"


@pytest.fixture(scope="module")
def common() -> Iterator[ModuleType]:
    with load_script(COMMON, "live_common") as module:
        yield module


def test_loading_a_script_leaves_the_path_as_it_was() -> None:
    before = list(sys.path)

    with load_script(COMMON, "live_common_again") as module:
        assert str(ROOT / "containers" / "live") in sys.path
        assert module.mail.local("<x@y.example>") == "x"

    assert sys.path == before
    assert "live_common_again" not in sys.modules


def env_file(tmp_path: Path, url: str) -> Path:
    path = tmp_path / "agent.env"
    path.write_text(
        f"MAILBOX_AGENTS_SERVICE_URL={url}\nMAILBOX_AGENTS_ACCOUNTS=test-account\n",
        encoding="utf-8",
    )
    return path


def test_the_file_wins_over_the_environment(
    common: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MAILBOX_AGENTS_SERVICE_URL", "https://real.example")
    monkeypatch.setenv("MAILBOX_AGENTS_ACCOUNTS", "real-account")
    monkeypatch.setenv("MAILBOX_AGENTS_STAGE", "full")

    found = common.live_settings(env_file(tmp_path, "http://127.0.0.1:38081"), "x")

    assert found.service_url == "http://127.0.0.1:38081"
    assert found.accounts == ["test-account"]
    assert found.stage == "shadow"
    assert "live: account test-account at http://127.0.0.1:38081" in (
        capsys.readouterr().out
    )


def test_the_environment_is_left_as_it_was(
    common: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAILBOX_AGENTS_STAGE", "full")

    common.live_settings(env_file(tmp_path, "http://127.0.0.1:38081"), "x")

    assert os.environ["MAILBOX_AGENTS_STAGE"] == "full"


@pytest.mark.parametrize("url", ["http://localhost:38081", "http://[::1]:38081"])
def test_a_service_on_this_machine_is_taken(
    common: ModuleType, tmp_path: Path, url: str
) -> None:
    assert common.live_settings(env_file(tmp_path, url), "x").service_url == url


@pytest.mark.parametrize(
    "url",
    [
        "https://real.example",
        "https://real.example:38081",
        "http://127.0.0.1:8080",
        "http://127.0.0.1",
        "http://localhost:99999",
    ],
)
def test_a_service_elsewhere_stops_the_check(
    common: ModuleType, tmp_path: Path, url: str
) -> None:
    with pytest.raises(SystemExit) as raised:
        common.live_settings(env_file(tmp_path, url), "x")

    assert raised.value.code == 2


def test_the_live_port_is_the_one_of_the_compose_file(common: ModuleType) -> None:
    compose = (ROOT / "containers" / "live" / "compose.yaml").read_text("utf-8")
    setup = (ROOT / "containers" / "live" / "setup.sh").read_text("utf-8")

    assert f'"127.0.0.1:{common.LIVE_PORT}:8080"' in compose
    assert f"SERVICE_URL=http://127.0.0.1:{common.LIVE_PORT} " in setup


async def test_put_back_takes_off_each_keyword_and_moves_back_once(
    common: ModuleType,
) -> None:
    service = FakeService()
    service.add(wire_message("m1", folder_ids=["inbox"]), change=None)
    service.add(wire_message("m2", folder_ids=["inbox"]), change=None)
    service.messages[(ACCOUNT, "m2")]["keywords"] = ["mine"]
    async with connect(
        "https://mailbox.example.test", "t", transport=service.transport()
    ) as mailbox:
        refs = [MessageRef(account_id=ACCOUNT, message_id=m) for m in ("m1", "m2")]
        before = await common.snapshot(mailbox, refs)
        service.messages[(ACCOUNT, "m1")]["folder_ids"] = ["inv-hosting"]
        service.messages[(ACCOUNT, "m1")]["keywords"] = ["agent-sorted"]
        service.messages[(ACCOUNT, "m2")]["keywords"] = [
            "mine",
            "agent-sorted",
            "agent-invoice",
        ]

        moved = await common.put_back(mailbox, before, "agent-sorted", "agent-invoice")

    assert moved == 1
    assert service.messages[(ACCOUNT, "m1")]["folder_ids"] == ["inbox"]
    assert service.messages[(ACCOUNT, "m1")]["keywords"] == []
    assert service.messages[(ACCOUNT, "m2")]["keywords"] == ["mine"]
