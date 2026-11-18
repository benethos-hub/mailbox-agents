"""Settings: prefix, .env, secrets from files, and the table of
docs/specs/configuration.md."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from benethos_mailbox_agent import errors
from benethos_mailbox_agent.settings import PREFIX, Settings, load_settings

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """No setting of the machine, and no default .env, reaches a test."""
    import os

    for name in list(os.environ):
        if name.startswith(PREFIX):
            monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)
    errors.forget_secrets()
    yield
    errors.forget_secrets()


def test_the_defaults() -> None:
    found = load_settings()

    assert found.stage == "shadow"
    assert found.accounts == []
    assert found.prompt_retention_days == 0
    assert found.reply_days == 3
    assert found.data_dir == Path("data")


def test_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAILBOX_AGENT_STAGE", "keyword")
    monkeypatch.setenv("MAILBOX_AGENT_ACCOUNTS", "acc1, acc2,")
    monkeypatch.setenv("MAILBOX_AGENT_LOG_LEVEL", "debug")

    found = load_settings()

    assert found.stage == "keyword"
    assert found.accounts == ["acc1", "acc2"]
    assert found.log_level == "DEBUG"


def test_from_a_named_env_file(tmp_path: Path) -> None:
    env = tmp_path / "agent.env"
    env.write_text("MAILBOX_AGENT_MODEL=classifier\n", encoding="utf-8")

    assert load_settings(env).model == "classifier"


def test_the_default_env_file_is_read_when_it_exists(tmp_path: Path) -> None:
    folder = tmp_path / "config" / "benethos-mailbox-agent"
    folder.mkdir(parents=True)
    (folder / ".env").write_text("MAILBOX_AGENT_POLL_SECONDS=5\n", encoding="utf-8")

    assert load_settings().poll_seconds == 5


def test_a_named_env_file_must_exist(tmp_path: Path) -> None:
    with pytest.raises(errors.ConfigError, match="does not exist"):
        load_settings(tmp_path / "missing.env")


def test_a_secret_from_a_file_is_read_and_registered(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    secret = tmp_path / "token"
    secret.write_text("service-token-value\n", encoding="utf-8")
    monkeypatch.setenv("MAILBOX_AGENT_SERVICE_TOKEN_FILE", str(secret))

    found = load_settings()

    assert found.secret("service_token") == "service-token-value"
    assert errors.redact("x service-token-value") == "x [redacted]"


def test_a_secret_given_directly_wins_over_its_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("MAILBOX_AGENT_GATEWAY_KEY", "direct-key-value")
    monkeypatch.setenv("MAILBOX_AGENT_GATEWAY_KEY_FILE", str(tmp_path / "none"))

    assert load_settings().secret("gateway_key") == "direct-key-value"


def test_an_empty_secret_lets_its_file_be_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    secret = tmp_path / "service_token"
    secret.write_text("from-the-file\n", encoding="utf-8")
    monkeypatch.setenv("MAILBOX_AGENT_SERVICE_TOKEN", "")
    monkeypatch.setenv("MAILBOX_AGENT_SERVICE_TOKEN_FILE", str(secret))
    monkeypatch.setenv("MAILBOX_AGENT_GATEWAY_KEY", "")

    found = load_settings(None)

    assert found.secret("service_token") == "from-the-file"
    assert found.gateway_key is None
    assert found.missing(("gateway_key",)) == ["MAILBOX_AGENT_GATEWAY_KEY"]


def test_an_unreadable_secret_file_is_a_config_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("MAILBOX_AGENT_GATEWAY_KEY_FILE", str(tmp_path / "none"))

    with pytest.raises(errors.ConfigError, match="GATEWAY_KEY_FILE"):
        load_settings()


def test_a_missing_secret_is_named() -> None:
    with pytest.raises(errors.ConfigError, match="MAILBOX_AGENT_SERVICE_TOKEN"):
        load_settings().secret("service_token")


def test_a_wrong_value_is_named_never_quoted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAILBOX_AGENT_STAGE", "everything-now")

    with pytest.raises(errors.ConfigError) as raised:
        load_settings()

    assert "MAILBOX_AGENT_STAGE" in str(raised.value)
    assert "everything-now" not in str(raised.value)


@pytest.mark.parametrize("keyword", ["", "two words", "(x)", 'q"'])
def test_a_keyword_is_one_atom(keyword: str) -> None:
    with pytest.raises(errors.ConfigError, match="KEYWORD"):
        load_settings(keyword=keyword)


def test_missing_names_the_unset_settings() -> None:
    found = load_settings(model="m")

    assert found.missing(("model", "service_url")) == ["MAILBOX_AGENT_SERVICE_URL"]


def _configuration_spec() -> str:
    return (ROOT / "docs" / "specs" / "configuration.md").read_text("utf-8")


def test_every_setting_of_the_configuration_spec_exists() -> None:
    """The table of docs/specs/configuration.md against the code."""
    rows = [
        line for line in _configuration_spec().splitlines() if line.startswith("| `")
    ]
    names = {
        name.lower()
        for row in rows
        for name in re.findall(r"`([A-Z_]+)`", row.split("|")[1])
    }

    assert names
    assert names <= set(Settings.model_fields)


def test_the_env_example_names_every_setting() -> None:
    example = ROOT / "config" / "benethos-mailbox-agent" / ".env.example"
    named = set(re.findall(r"MAILBOX_AGENT_([A-Z_]+)=", example.read_text("utf-8")))

    assert {name.lower() for name in named} == set(Settings.model_fields)
