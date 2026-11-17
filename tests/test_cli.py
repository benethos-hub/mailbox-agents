"""The command line."""

from __future__ import annotations

from importlib.metadata import version

import pytest

from benethos_mailbox_agent import __version__
from benethos_mailbox_agent.cli import PROG, main


def test_version_is_the_distributions() -> None:
    assert __version__ == version("benethos-mailbox-agent")


def test_version_flag_prints_name_and_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--version"])

    assert raised.value.code == 0
    assert capsys.readouterr().out.strip() == f"{PROG} {__version__}"


def test_no_command_prints_the_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert capsys.readouterr().out.startswith(f"usage: {PROG}")
