"""The console script ``benethos-mailbox-agent``.

Only the version is built. The commands SPECS.md section 4 names (worker,
run, backfill, eval, status, paths) arrive with the modules behind them.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from . import __version__

PROG = "benethos-mailbox-agent"


def build_parser() -> argparse.ArgumentParser:
    """The argument parser, apart from ``main`` so a test can read it."""
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Agents that read and sort a mailbox.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{PROG} {__version__}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line and answer with the exit code."""
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0
