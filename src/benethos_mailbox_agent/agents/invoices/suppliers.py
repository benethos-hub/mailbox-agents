"""The supplier list of ``invoices``: who a supplier is, and its folder.

An entry names a supplier, the senders it writes from, and its folder
under the parent folder of MAILBOX_AGENT_INVOICES_FOLDER. A sender is
written in one of three ways:

- an address, ``billing@cloudhost.example``: that address alone,
- a pattern with ``*`` for a part that changes,
  ``mailbox*@telco.example``,
- a domain, ``telco.example`` or ``@telco.example``: every address of it
  and of its subdomains.

Matching ignores case. The most specific rule wins, an address before a
pattern before a domain. Two suppliers whose rules of the same kind both
match leave the sender unmatched, so neither is guessed. See SPECS.md
section 10.1.

The file is JSON. A reader is chosen by the file's suffix, so another
format is one entry in :data:`READERS`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ...errors import ConfigError

__all__ = ["READERS", "Kind", "Match", "Supplier", "Suppliers", "load_suppliers"]

_ADDRESS = re.compile(r"^[^\s@*]+@[^\s@*]+\.[^\s@*]+$")
_PATTERN = re.compile(r"^[^\s@]*\*[^\s@]*@[^\s@*]+\.[^\s@*]+$")
_DOMAIN = re.compile(r"^@?[^\s@*/]+\.[^\s@*/]+$")


class Kind(IntEnum):
    """How specific a sender rule is, the higher the more."""

    DOMAIN = 1
    PATTERN = 2
    ADDRESS = 3


def _kind(rule: str) -> Kind:
    if _ADDRESS.match(rule):
        return Kind.ADDRESS
    if _PATTERN.match(rule):
        return Kind.PATTERN
    if _DOMAIN.match(rule):
        return Kind.DOMAIN
    raise ValueError(f"{rule!r} is no address, no pattern with * and no domain")


class Supplier(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    folder: str = Field(min_length=1, max_length=200)
    senders: tuple[str, ...] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("a name has no space at its ends")
        return value

    @field_validator("folder")
    @classmethod
    def _folder(cls, value: str) -> str:
        parts = value.split("/")
        if any(not p.strip() or p in (".", "..") or p != p.strip() for p in parts):
            raise ValueError("a folder is names between /, none empty, . or ..")
        return value

    @field_validator("senders")
    @classmethod
    def _senders(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        found = tuple(rule.strip().lower() for rule in value)
        for rule in found:
            _kind(rule)
        return found

    @property
    def domains(self) -> tuple[str, ...]:
        """The domains its sender rules name, each once."""
        return tuple(dict.fromkeys(rule.rpartition("@")[2] for rule in self.senders))


@dataclass(frozen=True)
class Match:
    supplier: Supplier
    kind: Kind
    rule: str


def _matches(rule: str, kind: Kind, address: str) -> bool:
    if kind is Kind.ADDRESS:
        return address == rule
    if kind is Kind.PATTERN:
        pattern = "^" + ".*".join(re.escape(p) for p in rule.split("*")) + "$"
        return re.match(pattern, address) is not None
    domain = rule.lstrip("@")
    found = address.rpartition("@")[2]
    return found == domain or found.endswith("." + domain)


class Suppliers(BaseModel):
    """The whole list."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    suppliers: tuple[Supplier, ...] = ()

    @field_validator("suppliers")
    @classmethod
    def _unique(cls, value: tuple[Supplier, ...]) -> tuple[Supplier, ...]:
        for attribute in ("name", "folder"):
            seen: set[str] = set()
            for supplier in value:
                key = getattr(supplier, attribute).casefold()
                if key in seen:
                    raise ValueError(f"two suppliers share the {attribute} {key!r}")
                seen.add(key)
        owners: dict[str, str] = {}
        for supplier in value:
            for rule in supplier.senders:
                if rule in owners and owners[rule] != supplier.name:
                    raise ValueError(
                        f"the sender {rule!r} is named by {owners[rule]!r} "
                        f"and {supplier.name!r}"
                    )
                owners[rule] = supplier.name
        return value

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(s.name for s in self.suppliers)

    def named(self, name: str) -> Supplier | None:
        return next((s for s in self.suppliers if s.name == name), None)

    def match(self, address: str | None) -> Match | None:
        """The supplier ``address`` belongs to by the rules, or None when
        no rule matches or the most specific ones name two suppliers."""
        if not address:
            return None
        found = address.strip().lower()
        hits = [
            Match(supplier, _kind(rule), rule)
            for supplier in self.suppliers
            for rule in supplier.senders
            if _matches(rule, _kind(rule), found)
        ]
        if not hits:
            return None
        best = max(hit.kind for hit in hits)
        top = [hit for hit in hits if hit.kind == best]
        if len({hit.supplier.name for hit in top}) > 1:
            return None
        return top[0]


def _read_json(text: str) -> Any:
    return json.loads(text)


# The readers by suffix. JSON for now, decided 2026-11-17.
READERS: dict[str, Callable[[str], Any]] = {".json": _read_json}


def load_suppliers(path: Path) -> Suppliers:
    """The supplier list at ``path``, or a :class:`ConfigError` that says
    what is wrong with it."""
    reader = READERS.get(path.suffix.lower())
    if reader is None:
        raise ConfigError(
            f"the supplier list {path.name} is no {', '.join(sorted(READERS))} file"
        )
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(
            f"the supplier list {path.name} cannot be read ({type(exc).__name__})"
        ) from None
    try:
        return Suppliers.model_validate(reader(text))
    except ValueError as exc:
        if isinstance(exc, ValidationError):
            reason = ", ".join(
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                for e in exc.errors(include_input=False, include_url=False)
            )
        else:
            reason = type(exc).__name__
        raise ConfigError(f"the supplier list {path.name}: {reason}") from None
