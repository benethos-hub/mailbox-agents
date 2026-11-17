"""Where the lines go: one handler on stderr."""

from __future__ import annotations

import logging
import sys
from typing import TextIO

__all__ = ["LIBRARIES", "LOGGER", "PACKAGE", "configure"]

PACKAGE = __name__.split(".")[0]
LOGGER = logging.getLogger(PACKAGE)

# Held at WARNING whatever the level says. httpx names every request with
# its whole URL at INFO, and a URL of the mailbox service carries ids and
# query parameters this package writes down only through its own lines.
LIBRARIES = ("httpx", "httpcore")

FORMAT = "%(asctime)s %(levelname)-7s %(message)s"

# Marks the handler this module installed, so configuring twice replaces it
# rather than printing every line twice.
_MARK = "_mailbox_agent_logbook"


def configure(level: str = "INFO", stream: TextIO | None = None) -> None:
    """Send the package's lines to ``stream``, stderr by default, at ``level``."""
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(logging.Formatter(FORMAT))
    setattr(handler, _MARK, True)
    for old in [h for h in LOGGER.handlers if getattr(h, _MARK, False)]:
        LOGGER.removeHandler(old)
    LOGGER.addHandler(handler)
    LOGGER.setLevel(level.upper())
    LOGGER.propagate = False
    for name in LIBRARIES:
        logging.getLogger(name).setLevel(logging.WARNING)
