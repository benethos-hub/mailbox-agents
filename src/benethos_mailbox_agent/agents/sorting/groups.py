"""The list of ``sorting``: groups of senders, each with its folder.

An entry names a group, the folder its mail goes to and the senders that
belong to it. A sender is written in one of three ways:

- an address, ``service@bank-two.example``: that address alone,
- a pattern with ``*`` before the ``@``, ``*@cloudhost.example`` or
  ``mailbox*@telco.example``: every address the ``*`` fits, of that one
  domain,
- a pattern for the subdomains, ``*@*.shop.example``: every address of
  every subdomain of ``shop.example``, not of ``shop.example`` itself
  (decided 2026-11-18). The domain after ``*.`` has two names at least, so
  ``*@*.example`` is refused as too broad.

A domain alone, ``cloudhost.example``, is refused: ``sorting`` sets no
keyword a domain could mark with, and the message says what to write
instead (decided 2026-11-18). Matching ignores case. The most specific rule
wins: an address before a pattern before a pattern for the subdomains. Two
groups whose rules of the same kind both match leave the sender to no
group, so neither is guessed. See docs/specs/agents/sorting.md.

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

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from ...errors import ConfigError, describe_invalid

__all__ = ["READERS", "Group", "Groups", "Kind", "Match", "load_groups"]

_NAME = r"[^\s@*]+"
_DOMAIN = rf"{_NAME}\.{_NAME}"
_ADDRESS = re.compile(rf"^{_NAME}@{_DOMAIN}$")
_PATTERN = re.compile(rf"^[^\s@]*\*[^\s@]*@{_DOMAIN}$")
_SUBDOMAINS = re.compile(rf"^[^\s@]+@\*\.({_DOMAIN})$")
_BARE_DOMAIN = re.compile(rf"^@?{_DOMAIN}$")


class Kind(IntEnum):
    """How specific a sender rule is, the higher the more."""

    SUBDOMAINS = 1
    PATTERN = 2
    ADDRESS = 3


def _kind(rule: str) -> Kind:
    if _ADDRESS.match(rule):
        return Kind.ADDRESS
    if _PATTERN.match(rule):
        return Kind.PATTERN
    if _SUBDOMAINS.match(rule):
        return Kind.SUBDOMAINS
    if _BARE_DOMAIN.match(rule):
        domain = rule.lstrip("@")
        raise ValueError(
            f"{rule!r} is a domain: write *@{domain} for its addresses, "
            f"or *@*.{domain} for those of its subdomains"
        )
    if "@*." in rule:
        raise ValueError(
            f"{rule!r} is too broad: the domain after *. needs two names at least"
        )
    raise ValueError(
        f"{rule!r} is no address and no pattern: a * stands before the @, "
        "or as *. at the start of the domain"
    )


def _matches(rule: str, kind: Kind, address: str) -> bool:
    if kind is Kind.ADDRESS:
        return address == rule
    local, _, domain = rule.rpartition("@")
    found_local, _, found_domain = address.rpartition("@")
    if kind is Kind.SUBDOMAINS:
        parent = domain[2:]  # the domain after "*."
        if not found_domain.endswith("." + parent):
            return False
    elif found_domain != domain:
        return False
    pattern = "^" + ".*".join(re.escape(p) for p in local.split("*")) + "$"
    return re.match(pattern, found_local) is not None


class Group(BaseModel):
    """One group: its name, its folder, its senders, and whether its moves
    are held."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    folder: str = Field(min_length=1, max_length=200)
    senders: tuple[str, ...] = Field(min_length=1)
    hold: StrictBool = False

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
    def folders(self) -> tuple[str, ...]:
        """Its folder and every folder above it, the top first: the folders
        the agent may make for it."""
        parts = self.folder.split("/")
        return tuple("/".join(parts[: i + 1]) for i in range(len(parts)))


@dataclass(frozen=True)
class Match:
    """The groups whose most specific rules match a sender: one, or more
    when the list names the sender alike in several."""

    groups: tuple[Group, ...]
    kind: Kind

    @property
    def group(self) -> Group | None:
        """The one group, None when several match alike."""
        return self.groups[0] if len(self.groups) == 1 else None


class Groups(BaseModel):
    """The whole list."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    groups: tuple[Group, ...] = ()

    @field_validator("groups")
    @classmethod
    def _unique(cls, value: tuple[Group, ...]) -> tuple[Group, ...]:
        for attribute in ("name", "folder"):
            seen: set[str] = set()
            for group in value:
                key = getattr(group, attribute).casefold()
                if key in seen:
                    raise ValueError(f"two groups share the {attribute} {key!r}")
                seen.add(key)
        owners: dict[str, str] = {}
        for group in value:
            for rule in group.senders:
                if rule in owners and owners[rule] != group.name:
                    raise ValueError(
                        f"the sender {rule!r} is named by {owners[rule]!r} "
                        f"and {group.name!r}"
                    )
                owners[rule] = group.name
        return value

    def named(self, name: str) -> Group | None:
        return next((g for g in self.groups if g.name == name), None)

    def match(self, address: str | None) -> Match | None:
        """The groups ``address`` belongs to by their most specific rules,
        or None when no rule matches."""
        if not address:
            return None
        found = address.strip().lower()
        hits = [
            (group, _kind(rule))
            for group in self.groups
            for rule in group.senders
            if _matches(rule, _kind(rule), found)
        ]
        if not hits:
            return None
        best = max(kind for _, kind in hits)
        top = {group.name: group for group, kind in hits if kind == best}
        return Match(groups=tuple(top.values()), kind=best)

    def may_create(self, path: str) -> bool:
        """Whether ``path`` is the folder of a group or one above it."""
        return any(path in group.folders for group in self.groups)


def _read_json(text: str) -> Any:
    return json.loads(text)


# The readers by suffix. JSON, as the other lists of this project.
READERS: dict[str, Callable[[str], Any]] = {".json": _read_json}


def load_groups(path: Path) -> Groups:
    """The list at ``path``, or a :class:`ConfigError` that says what is
    wrong with it."""
    reader = READERS.get(path.suffix.lower())
    if reader is None:
        raise ConfigError(
            f"the sorting list {path.name} is no {', '.join(sorted(READERS))} file"
        )
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(
            f"the sorting list {path.name} cannot be read ({type(exc).__name__})"
        ) from None
    try:
        return Groups.model_validate(reader(text))
    except ValueError as exc:
        raise ConfigError(
            f"the sorting list {path.name}: {describe_invalid(exc)}"
        ) from None
