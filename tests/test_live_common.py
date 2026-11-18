"""The settings of the live checks: from their file alone, on this machine."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import ModuleType

import pytest

# live/ is no package and lies outside testpaths: the module is loaded by
# its path, as a script would find it beside itself.
COMMON = Path(__file__).resolve().parent.parent / "live" / "common.py"


@pytest.fixture(scope="module")
def common() -> ModuleType:
    spec = importlib.util.spec_from_file_location("live_common", COMMON)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def test_a_service_elsewhere_stops_the_check(
    common: ModuleType, tmp_path: Path
) -> None:
    with pytest.raises(SystemExit) as raised:
        common.live_settings(env_file(tmp_path, "https://real.example"), "x")

    assert raised.value.code == 2
