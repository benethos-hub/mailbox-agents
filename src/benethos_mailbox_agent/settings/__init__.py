"""Settings resolution, secrets from files.

Every setting carries the prefix ``MAILBOX_AGENT_`` and comes from the
environment or from one ``.env`` file, read with pydantic-settings. A
process runs one agent, so one environment describes one agent. The
service token and the gateway key may be given as a file instead, named
in the same setting with the suffix ``_FILE``. See SPECS.md section 13.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from ..errors import ConfigError, describe_invalid, register_secret

__all__ = [
    "DEFAULT_ENV_FILE",
    "KEYWORD_FORBIDDEN",
    "PREFIX",
    "STAGES",
    "Settings",
    "Stage",
    "load_settings",
]

# Characters an IMAP keyword may not carry: it is one atom.
KEYWORD_FORBIDDEN = frozenset(' \t()[]{}"\\%*')

PREFIX = "MAILBOX_AGENT_"

# Where the .env file is looked for when none is named, relative to the
# working directory. The example beside it lists every setting.
DEFAULT_ENV_FILE = Path("config/benethos-mailbox-agent/.env")

Stage = Literal["shadow", "keyword", "full"]
STAGES: tuple[Stage, ...] = ("shadow", "keyword", "full")


class Settings(BaseSettings):
    """The settings of one process, which runs one agent."""

    model_config = SettingsConfigDict(
        env_prefix=PREFIX,
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # --- upstreams ---------------------------------------------------------
    service_url: str | None = None
    service_token: SecretStr | None = None
    service_token_file: Path | None = None
    # The client refuses http to another machine, since the token would
    # travel unencrypted. Between two containers on one network that is
    # the deployment's decision.
    service_allow_http: bool = False
    gateway_url: str | None = None
    gateway_allow_http: bool = False
    gateway_key: SecretStr | None = None
    gateway_key_file: Path | None = None
    gateway_timeout_seconds: float = Field(default=120.0, gt=0)
    model: str | None = None

    # --- what the agent works on and how far it may go ----------------------
    accounts: Annotated[list[str], NoDecode] = Field(default_factory=list)
    stage: Stage = "shadow"
    keyword: str | None = None

    # --- the loop ------------------------------------------------------------
    poll_seconds: float = Field(default=60.0, gt=0)
    tick_seconds: float = Field(default=900.0, gt=0)
    max_attempts: int = Field(default=5, ge=1)
    backoff_ceiling_seconds: float = Field(default=3600.0, gt=0)
    backfill_days: int = Field(default=7, ge=0)

    # --- state, metrics, log ---------------------------------------------------
    data_dir: Path = Path("data")
    prompt_retention_days: int = Field(default=0, ge=0)
    metrics_port: int = Field(default=0, ge=0, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # --- invoices, SPECS.md section 10.1 -----------------------------------------
    invoices_folder: str | None = None
    invoices_suppliers_file: Path | None = None

    # --- awaiting_reply, SPECS.md section 10.2 -------------------------------
    reply_days: int = Field(default=3, ge=1)

    # --- inquiries, SPECS.md section 10.3 ----------------------------------------
    inquiries_patterns_file: Path | None = None

    @field_validator("accounts", mode="before")
    @classmethod
    def _split_accounts(cls, value: Any) -> Any:
        """``a,b`` in the environment, a list when built in code."""
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper(cls, value: Any) -> Any:
        return value.upper() if isinstance(value, str) else value

    @field_validator("keyword")
    @classmethod
    def _one_word(cls, value: str | None) -> str | None:
        """A keyword is one IMAP atom: no space, no bracket, no quote."""
        if value is not None and (not value or KEYWORD_FORBIDDEN & set(value)):
            raise ValueError("a keyword is one word without brackets or quotes")
        return value

    @model_validator(mode="after")
    def _secrets_from_files(self) -> Settings:
        """Read a secret named by its ``_FILE`` setting, and register both
        secrets so no error text carries them. An empty value counts as not
        set, as the empty line ``.env.example`` holds."""
        for name in ("service_token", "gateway_key"):
            given: SecretStr | None = getattr(self, name)
            if given is not None and not given.get_secret_value():
                object.__setattr__(self, name, None)
            path: Path | None = getattr(self, f"{name}_file")
            if getattr(self, name) is None and path is not None:
                try:
                    text = path.read_text(encoding="utf-8").strip()
                except OSError as exc:
                    raise ValueError(
                        f"{PREFIX}{name.upper()}_FILE cannot be read "
                        f"({type(exc).__name__})"
                    ) from None
                object.__setattr__(self, name, SecretStr(text) if text else None)
            secret: SecretStr | None = getattr(self, name)
            if secret is not None:
                register_secret(secret.get_secret_value())
        return self

    def missing(self, names: tuple[str, ...]) -> list[str]:
        """The settings among ``names`` that are not set, as their full
        environment names."""
        return [f"{PREFIX}{name.upper()}" for name in names if not getattr(self, name)]

    def secret(self, name: Literal["service_token", "gateway_key"]) -> str:
        """The value of a secret, or a :class:`ConfigError` naming it."""
        found: SecretStr | None = getattr(self, name)
        if found is None:
            raise ConfigError(f"{PREFIX}{name.upper()} is not set")
        return found.get_secret_value()


def load_settings(env_file: Path | None = None, **overrides: Any) -> Settings:
    """The settings from the environment and ``env_file``, the default
    file when none is named and it exists.

    A wrong setting becomes a :class:`ConfigError` that names the setting
    and the rule, never the value, which may be a secret.
    """
    path = env_file if env_file is not None else DEFAULT_ENV_FILE
    if env_file is not None and not path.is_file():
        raise ConfigError(f"the settings file {path.name} does not exist")
    try:
        return Settings(_env_file=path if path.is_file() else None, **overrides)  # type: ignore[call-arg]
    except ValidationError as exc:
        problems = describe_invalid(
            exc, lambda place: f"{PREFIX}{place.upper() or 'SETTINGS'}"
        )
        raise ConfigError(f"wrong settings: {problems}") from None
