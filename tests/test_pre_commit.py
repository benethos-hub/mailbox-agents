"""The pre-commit hook, run in a repository of its own in a temporary folder."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / ".githooks" / "pre-commit"

SH = shutil.which("sh")
GIT = shutil.which("git")

pytestmark = pytest.mark.skipif(
    SH is None or GIT is None, reason="the hook needs sh and git"
)


def _git(repo: Path, *args: str) -> None:
    assert GIT is not None
    subprocess.run([GIT, *args], cwd=repo, check=True, capture_output=True)


def _hook(repo: Path) -> subprocess.CompletedProcess[str]:
    assert SH is not None
    return subprocess.run(
        [SH, str(HOOK)], cwd=repo, capture_output=True, text=True, check=False
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    return tmp_path


def _stage(repo: Path, name: str, content: str = "x\n") -> None:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git(repo, "add", "-f", name)


@pytest.mark.parametrize(
    "name",
    [
        ".env",
        "config/benethos-mailbox-agents/.env",
        ".env.local",
        "data/invoices.db",
        "data/gold/invoices.jsonl",
        "state.db-wal",
        "somewhere/agent.sqlite",
        "containers/live/secrets/x",
        "secrets/agent.env.json",
    ],
)
def test_refuses_files_that_never_belong(repo: Path, name: str) -> None:
    _stage(repo, name)

    answer = _hook(repo)

    assert answer.returncode == 1
    assert name in answer.stderr


@pytest.mark.parametrize(
    "name",
    [
        "config/benethos-mailbox-agents/.env.example",
        "data/.gitkeep",
        "data/gold/.gitkeep",
        "src/module.py",
    ],
)
def test_lets_the_rest_pass(repo: Path, name: str) -> None:
    _stage(repo, name)

    assert _hook(repo).returncode == 0


def test_refuses_a_line_that_looks_like_a_credential(repo: Path) -> None:
    # Split, so this file does not look like a credential to the hook.
    line = "MAILBOX_AGENTS_GATEWAY_KEY=" + "abcdefghijklmnop1234\n"
    _stage(repo, "notes.txt", line)

    answer = _hook(repo)

    assert answer.returncode == 1
    assert "credential" in answer.stderr


# Each split, so this file does not look like a credential to the hook.
@pytest.mark.parametrize(
    "line",
    [
        '{"token": "' + "mbx_" + 'abcdefghijklmnop1234"}',
        "Authorization: " + "Bearer " + "abcdefghijklmnop1234",
        "GATEWAY_KEY: " + "sk-" + "live-abcdefghijklmnop1234",
        "MAILBOX_AGENTS_GATEWAY_KEY = " + '"' + "abcdefghijklmnop1234" + '"',
        "SERVICE_TOKEN: " + "'" + "abcdefghijklmnop1234" + "'",
        '{"password": "' + 'Tr0ub4dor3xyzabc"}',
        "token: " + "abcdefghijklmnopq",
        "Gateway_Key = " + "abcdefghijklmnopq",
        "GATEWAY_KEY=" + "Zq7xW2pL9mN4vB8k",
    ],
    ids=[
        "json-token",
        "bearer",
        "sk-with-dash",
        "spaced-quoted",
        "yaml-quoted",
        "json-lower-case",
        "yaml-lower-case",
        "mixed-case",
        "bare-key",
    ],
)
def test_refuses_a_credential_in_another_form(repo: Path, line: str) -> None:
    _stage(repo, "notes.txt", line + "\n")

    answer = _hook(repo)

    assert answer.returncode == 1
    assert "credential" in answer.stderr


@pytest.mark.parametrize(
    "line",
    [
        "MAILBOX_AGENTS_GATEWAY_KEY_FILE: /run/secrets/gateway_key",
        "GATEWAY_KEY: ${GATEWAY_KEY}",
        'headers={"Authorization": f"Bearer {key}"}',
        "api_key: os.environ/ANTHROPIC_API_KEY",
        "token = base64.b64encode(raw).decode()",
        "tokens_in=calls.tokens_in",
        'default_keyword = "agent-awaiting-reply"',
        '"secret": mailbox_password}',
        'ADD_KEYWORD = "add_keyword_long_value"',
        'REMOVE_KEYWORD = "remove_keyword"',
    ],
)
def test_a_reference_to_a_secret_passes(repo: Path, line: str) -> None:
    _stage(repo, "notes.txt", line + "\n")

    assert _hook(repo).returncode == 0


def test_an_allowlisted_line_passes(repo: Path) -> None:
    line = "TOKEN=abcdefghijklmnop1234  # pragma: allowlist secret\n"
    _stage(repo, "notes.txt", line)

    assert _hook(repo).returncode == 0


def test_nothing_staged_passes(repo: Path) -> None:
    assert _hook(repo).returncode == 0


def test_a_secret_given_as_a_file_passes(repo: Path) -> None:
    _stage(repo, "app.env.example", "SERVICE_TOKEN_FILE=/run/secrets/token\n")

    assert _hook(repo).returncode == 0
