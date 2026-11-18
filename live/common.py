"""What the live checks share: their settings, from their file alone.

A live check runs against the test account of containers/live/ and no
other. So its settings come from its file and from nothing else: a
setting exported in the shell, of a real deployment say, is not read, and
cannot point a check at a real account. A mailbox service that is not on
this machine stops the check with exit code 2 (decided 2026-11-18). The
account and the service are printed before the check reads or writes.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

from benethos_mailbox_agents.settings import PREFIX, Settings, load_settings

__all__ = ["LOOPBACK", "live_settings"]

# The hosts of a mailbox service on this machine, as containers/live has it.
LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})


def live_settings(path: Path, script: str) -> Settings:
    """The settings in the file at ``path``, every ``MAILBOX_AGENTS_``
    variable of the environment aside. Exits when the file is missing or
    names no account, and with code 2 when the mailbox service is not on
    this machine. ``script`` names the check in what it says."""
    if not path.is_file():
        sys.exit(f"{script}: no settings at {path}, run containers/live/setup.sh")
    aside = {
        name: os.environ.pop(name)
        for name in list(os.environ)
        if name.upper().startswith(PREFIX)  # read without regard to case
    }
    try:
        found = load_settings(path)
    finally:
        os.environ.update(aside)
    if urlsplit(found.service_url or "").hostname not in LOOPBACK:
        print(
            f"{script}: the mailbox service is not on this machine, a live check "
            "runs against the test account of containers/live only",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if not found.accounts:
        sys.exit(
            f"{script}: the settings name no account, the check needs the test one"
        )
    for account in found.accounts:
        print(f"live: account {account} at {found.service_url}")
    return found
