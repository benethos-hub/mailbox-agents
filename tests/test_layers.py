"""Which part of the package may import which, read from the source.

The package is layered, see SPECS.md section 4: the foundation, the
records, the contract and the state file, the two modules that talk to
the upstreams, the runtime, the agents, and the command line on top.
Every import statement counts, one inside a function or under
``TYPE_CHECKING`` included, since a deferred import is still a dependency.

A new module or subpackage fails :func:`test_every_layer_has_a_row` until
it is given a row in :data:`MAY_IMPORT`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import benethos_mailbox_agent

PACKAGE = "benethos_mailbox_agent"
SOURCE = Path(benethos_mailbox_agent.__file__).parent

# Which layers a layer may import, besides itself and the package root,
# which every module may read ``__version__`` from. Each row allows what the
# layer uses and no more. A change that needs another layer adds it here on
# purpose.
MAY_IMPORT: dict[str, frozenset[str]] = {
    "errors": frozenset(),
    "logbook": frozenset(),
    "settings": frozenset({"errors"}),
    "records": frozenset(),
    "contract": frozenset({"errors", "records", "settings"}),
    "store": frozenset({"errors", "records"}),
    # The mailbox service, behind one module.
    "sources": frozenset({"errors", "records"}),
    # The model gateway, behind one module, and the evidence check.
    "llm": frozenset({"errors", "records"}),
    # An agent sees the contract and the records, never the client, the
    # gateway, the state file or the runtime that holds them.
    "agents": frozenset({"errors", "records", "settings", "contract"}),
    "cli": frozenset(),
    "__main__": frozenset({"cli"}),
}

# A dependency some modules may import and no other: the modules that are
# its interface to the rest of the package.
CONFINED: dict[str, frozenset[str]] = {
    "logging": frozenset({"logbook/output.py"}),
    "sqlite3": frozenset({"store/store.py"}),
    "benethos_mailbox_client": frozenset({"sources/mailbox.py"}),
    "httpx": frozenset({"sources/mailbox.py", "llm/gateway.py"}),
}


def _layer(module: str) -> str:
    """``benethos_mailbox_agent.store.store`` is in the layer ``store``."""
    parts = module.split(".")
    return parts[1] if len(parts) > 1 else ""


def _imports(path: Path) -> list[tuple[str, int]]:
    """Every module of this package that ``path`` imports, with its line."""
    relative = path.relative_to(SOURCE).with_suffix("").parts
    base = [PACKAGE, *relative][:-1]
    found: list[tuple[str, int]] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                anchor = base[: len(base) - (node.level - 1)]
                module = ".".join([*anchor, *([node.module] if node.module else [])])
            else:
                module = node.module or ""
            if module != PACKAGE and not module.startswith(f"{PACKAGE}."):
                continue
            if module == PACKAGE:
                found += [
                    (f"{module}.{alias.name}", node.lineno) for alias in node.names
                ]
            else:
                found.append((module, node.lineno))
        elif isinstance(node, ast.Import):
            found += [
                (alias.name, node.lineno)
                for alias in node.names
                if alias.name.startswith(f"{PACKAGE}.")
            ]
    return found


def _modules() -> list[Path]:
    return sorted(SOURCE.rglob("*.py"))


def _layer_of(path: Path) -> str:
    return path.relative_to(SOURCE).parts[0].removesuffix(".py")


@pytest.mark.parametrize(
    "path", _modules(), ids=[p.relative_to(SOURCE).as_posix() for p in _modules()]
)
def test_a_module_imports_only_the_layers_it_may(path: Path) -> None:
    layer = _layer_of(path)
    if layer == "__init__":
        return  # the package root, which holds the version and nothing else
    allowed = MAY_IMPORT[layer]
    wrong = [
        f"line {line}: {module}"
        for module, line in _imports(path)
        if (target := _layer(module)) not in ("", "__version__", layer)
        and target not in allowed
    ]
    assert wrong == [], f"{layer} may import {sorted(allowed)}"


def test_every_layer_has_a_row() -> None:
    """A module or subpackage added without deciding where it sits fails here."""
    layers = {_layer_of(path) for path in _modules()} - {"__init__"}
    assert layers == set(MAY_IMPORT)


def _third_party(path: Path) -> set[str]:
    """The top-level names of what ``path`` imports from outside the package."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and not node.level and node.module:
            found.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            found |= {alias.name.split(".")[0] for alias in node.names}
    return found


@pytest.mark.parametrize(("dependency", "homes"), CONFINED.items())
def test_a_confined_dependency_is_imported_in_its_homes_alone(
    dependency: str, homes: frozenset[str]
) -> None:
    importers = {
        path.relative_to(SOURCE).as_posix()
        for path in _modules()
        if dependency in _third_party(path)
    }
    assert importers == homes


def test_the_check_finds_a_relative_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The check itself, on a package of its own: a record that imports the
    state file is found, and the table forbids it."""
    (tmp_path / "records").mkdir()
    probe = tmp_path / "records" / "probe.py"
    probe.write_text("from ..store import Store\n", encoding="utf-8")
    monkeypatch.setitem(globals(), "SOURCE", tmp_path)

    found = [module for module, _ in _imports(probe)]

    assert found == ["benethos_mailbox_agent.store"]
    assert _layer(found[0]) not in MAY_IMPORT["records"]
