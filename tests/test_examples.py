"""Every example list in the repository parses with the loader it is for."""

from __future__ import annotations

from pathlib import Path

import pytest

from benethos_mailbox_agent.agents.inquiries.patterns import load_patterns
from benethos_mailbox_agent.agents.invoices.suppliers import load_suppliers

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = sorted(
    [
        *(ROOT / "config").rglob("*.example.json"),
        *(ROOT / "containers").rglob("*.example.json"),
        ROOT / "containers" / "live" / "suppliers.json",
    ]
)
LOADERS = {"suppliers": load_suppliers, "inquiries": load_patterns}


@pytest.mark.parametrize(
    "path", EXAMPLES, ids=[p.relative_to(ROOT).as_posix() for p in EXAMPLES]
)
def test_an_example_parses(path: Path) -> None:
    loader = LOADERS[path.name.split(".")[0]]

    assert loader(path) is not None


def test_every_example_is_found() -> None:
    assert len(EXAMPLES) >= 5
