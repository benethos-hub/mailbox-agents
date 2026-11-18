"""Where ``invoices`` looks for invoices, and where it puts one.

The folders it looks in are a setting, read at its start, so it works with
``sorting`` and without it (decided 2026-11-18): it knows nothing of
groups. ``MAILBOX_AGENTS_INVOICES_FOLDERS`` names them, separated by
commas, each written in one of three ways:

- a path, ``Providers/CloudHost``: that folder,
- ``Parent/*``: every folder directly below ``Parent``,
- ``*``: every folder at the top that has no role, the owner's own included
  (decided 2026-11-18). The inbox, sent mail, drafts, the trash, junk, the
  archive and the like have a role.

The inbox is always looked in. A message in a folder below one looked in,
such as the subfolder an invoice was put in, is not looked at, so an
invoice is not asked about twice. Neither the subfolder nor the inbox
folder is looked in even where the settings would take it in, as
``Invoices`` and ``Invoices/*`` take in ``Invoices/Rechnungen``, and ``*``
an inbox folder at the top. ``Parent/*`` and ``*`` are matched
against the path of the folder a message lies in, so a folder made after
the start, by ``sorting`` say, is looked in too.

``MAILBOX_AGENTS_INVOICES_SUBFOLDER`` is where an invoice goes, as
``{folder}/Rechnungen``: below the folder the message lies in.
``MAILBOX_AGENTS_INVOICES_INBOX_FOLDER`` is where an invoice found in the
inbox goes. Unset, it is marked and stays. See docs/specs/agents/invoices.md.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ...errors import ConfigError
from ...records import FolderRef
from ...settings import PREFIX

__all__ = ["ALL_AT_TOP", "FOLDER", "Places"]

# Every folder at the top without a role.
ALL_AT_TOP = "*"

# What the subfolder's pattern starts with: the folder a message lies in.
FOLDER = "{folder}"

# Roles a named folder is never looked in: a message there is not the
# owner's to file, and the runtime refuses to touch it.
_NEVER = frozenset({"trash", "junk", "spam"})


def _path(value: str, setting: str) -> str:
    """``value`` as a path of names between ``/``, or a ConfigError."""
    parts = value.split("/")
    if any(
        not p.strip()
        or p in (".", "..")
        or p != p.strip()
        or any(c in p for c in "*{}")
        for p in parts
    ):
        raise ConfigError(
            f"{PREFIX}{setting}: {value!r} is no folder, names between / are "
            "neither empty, . nor .., and hold no *, { or }"
        )
    return value


@dataclass(frozen=True)
class Places:
    """The folders ``invoices`` looks in, and where an invoice goes."""

    named: tuple[str, ...] = ()
    parents: tuple[str, ...] = ()
    top: bool = False
    subfolder: tuple[str, ...] = ()
    inbox_folder: str | None = None

    @classmethod
    def read(
        cls,
        folders: list[str],
        subfolder: str | None,
        inbox_folder: str | None,
    ) -> Places:
        """The places as the settings name them, or a ConfigError that says
        what is wrong."""
        named: list[str] = []
        parents: list[str] = []
        top = False
        for entry in (f.strip() for f in folders):
            if entry == ALL_AT_TOP:
                top = True
            elif entry.endswith("/" + ALL_AT_TOP):
                parents.append(_path(entry[: -len(ALL_AT_TOP) - 1], "INVOICES_FOLDERS"))
            else:
                named.append(_path(entry, "INVOICES_FOLDERS"))
        below: tuple[str, ...] = ()
        if subfolder:
            if not subfolder.startswith(FOLDER + "/"):
                raise ConfigError(
                    f"{PREFIX}INVOICES_SUBFOLDER: {subfolder!r} does not start with "
                    f"{FOLDER}/, the folder the message lies in"
                )
            rest = _path(subfolder[len(FOLDER) + 1 :], "INVOICES_SUBFOLDER")
            below = tuple(rest.split("/"))
        inbox = _path(inbox_folder, "INVOICES_INBOX_FOLDER") if inbox_folder else None
        return cls(
            named=tuple(dict.fromkeys(named)),
            parents=tuple(dict.fromkeys(parents)),
            top=top,
            subfolder=below,
            inbox_folder=inbox,
        )

    # -- where it looks -------------------------------------------------------------

    def _by_path(self, path: str, role: str | None) -> bool:
        """Whether the folder at ``path`` is one it looks in, the inbox
        aside. Never the inbox folder, nor the subfolder of a folder it
        looks in or a folder between the two, whatever the settings
        match: an invoice put there is not filed again."""
        if path == self.inbox_folder or self._below_one(path):
            return False
        return self._matches(path, role)

    def _matches(self, path: str, role: str | None) -> bool:
        """Whether the settings take in the folder at ``path``."""
        if role in _NEVER:
            return False
        if path in self.named:
            return True
        if role is not None:
            return False
        parent = path.rpartition("/")[0]
        if parent:
            return parent in self.parents
        return self.top

    def _below_one(self, path: str) -> bool:
        """Whether ``path`` is the subfolder of a folder the settings take
        in, or a folder between the two. The folder above is judged by
        its path alone, its role unknown here."""
        for count in range(1, len(self.subfolder) + 1):
            suffix = "/".join(self.subfolder[:count])
            if path.endswith("/" + suffix) and self._matches(
                path[: -len(suffix) - 1], None
            ):
                return True
        return False

    def looks_in(self, folder: FolderRef) -> bool:
        """Whether a message in ``folder`` is one to ask about."""
        return folder.role == "inbox" or self._by_path(folder.path, folder.role)

    # -- where an invoice goes ------------------------------------------------------

    def target(self, folder: FolderRef) -> str | None:
        """Where an invoice in ``folder`` goes: the subfolder below it, the
        inbox folder for the inbox. None when it stays."""
        if folder.role == "inbox":
            return self.inbox_folder
        if not self.subfolder:
            return None
        return "/".join((folder.path, *self.subfolder))

    def steps(self, folder: FolderRef) -> tuple[str, ...]:
        """The folders from the one below ``folder`` down to its subfolder,
        the top first: those made when missing."""
        return tuple(
            "/".join((folder.path, *self.subfolder[:count]))
            for count in range(1, len(self.subfolder) + 1)
        )

    def may_create(self, path: str, folders: Mapping[str, FolderRef]) -> bool:
        """Whether ``path`` is the subfolder of a folder it looks in, or a
        folder between the two: what the runtime may make for it.
        ``folders`` are the account's folders by path: the folder it looks
        in must be one of them, and is judged with its role, so ``*``
        makes nothing below sent mail or drafts. The inbox folder is not
        made."""
        for count in range(1, len(self.subfolder) + 1):
            suffix = "/".join(self.subfolder[:count])
            if path.endswith("/" + suffix):
                base = folders.get(path[: -len(suffix) - 1])
                if base is not None and self._by_path(base.path, base.role):
                    return True
        return False

    def needed(self) -> tuple[str, ...]:
        """The folders that should be there: those named, the parents of
        ``Parent/*``, and the inbox folder."""
        found = (*self.named, *self.parents)
        if self.inbox_folder:
            found = (*found, self.inbox_folder)
        return tuple(dict.fromkeys(found))
