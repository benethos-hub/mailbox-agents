"""Which part of the package may import which, read from the source.

The package is layered, see docs/specs/architecture.md: the foundation, the
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

import benethos_mailbox_agents

PACKAGE = "benethos_mailbox_agents"
SOURCE = Path(benethos_mailbox_agents.__file__).parent

# Which layers a layer may import, besides itself and the package root,
# which every module may read ``__version__`` from. Each row allows what the
# layer uses and no more. A change that needs another layer adds it here on
# purpose.
MAY_IMPORT: dict[str, frozenset[str]] = {
    "errors": frozenset(),
    # errors for redact, which every line passes before it is written.
    "logbook": frozenset({"errors"}),
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
    # The runtime holds every piece below it and hands an agent its context.
    "runtime": frozenset(
        {"errors", "logbook", "settings", "records", "contract", "store", "llm"}
    ),
    # settings for PREFIX alone, which an agent's messages name settings by.
    "agents": frozenset({"errors", "records", "settings", "contract"}),
    # Scores an agent the way the runtime runs it, on a state file of its own.
    "evaluation": frozenset({"errors", "records", "contract", "store", "runtime"}),
    # The top: it wires the upstreams, the state file and the runtime.
    "cli": frozenset(
        {
            "errors",
            "logbook",
            "settings",
            "records",
            "contract",
            "store",
            "sources",
            "llm",
            "runtime",
            "evaluation",
        }
    ),
    "__main__": frozenset({"cli"}),
}

# A dependency some modules may import and no other: the modules that are
# its interface to the rest of the package.
CONFINED: dict[str, frozenset[str]] = {
    # The output, the recorder, and the areas of the catalogue that set a
    # level of their own.
    "logging": frozenset(
        {
            "logbook/output.py",
            "logbook/activity.py",
            "logbook/catalogue/worker.py",
            "logbook/catalogue/feed.py",
            "logbook/catalogue/messages.py",
        }
    ),
    # A step of the schema is handed the connection to run its statements on.
    "sqlite3": frozenset({"store/store.py", "store/migrations/migration.py"}),
    "benethos_mailbox_client": frozenset({"sources/mailbox.py"}),
    "httpx": frozenset({"sources/mailbox.py", "llm/gateway.py"}),
    "prometheus_client": frozenset({"runtime/metrics.py"}),
    "pydantic_settings": frozenset({"settings/__init__.py"}),
}

# contract/registry.py is the one module that reaches into the package by
# name, through importlib, to find the agents: no import statement shows it,
# so no row of MAY_IMPORT can.


def _layer(module: str) -> str:
    """``benethos_mailbox_agents.store.store`` is in the layer ``store``."""
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


@pytest.mark.parametrize(
    "path",
    [p for p in _modules() if _layer_of(p) == "agents"],
    ids=[
        p.relative_to(SOURCE).as_posix() for p in _modules() if _layer_of(p) == "agents"
    ],
)
def test_an_agent_imports_no_other_agent(path: Path) -> None:
    """Agents stand on their own: prompt, schema and rules are never shared."""
    parts = path.relative_to(SOURCE).parts
    own = f"{PACKAGE}.agents.{parts[1]}" if len(parts) > 2 else None
    for module, line in _imports(path):
        if module.startswith(f"{PACKAGE}.agents."):
            assert own is not None and (
                module == own or module.startswith(f"{own}.")
            ), f"line {line}: {module}"


def test_every_layer_has_a_row() -> None:
    """A module or subpackage added without deciding where it sits fails here."""
    layers = {_layer_of(path) for path in _modules()} - {"__init__"}
    assert layers == set(MAY_IMPORT)


LIVE = SOURCE.parent.parent / "live"


@pytest.mark.parametrize("path", sorted(LIVE.glob("*.py")), ids=lambda p: p.name)
def test_a_live_script_imports_nothing_of_the_command_line(path: Path) -> None:
    """A live script works with the runtime, as the command line does, not
    through it."""
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith("benethos_mailbox_agents.cli"), (
                f"{path.name} imports {node.module}"
            )


# Where an HTTP status may be read: the modules of the upstreams, and the
# error that carries it.
HTTP_HOMES = frozenset({"sources", "llm", "errors"})


@pytest.mark.parametrize(
    "path",
    [p for p in _modules() if _layer_of(p) not in HTTP_HOMES],
    ids=[
        p.relative_to(SOURCE).as_posix()
        for p in _modules()
        if _layer_of(p) not in HTTP_HOMES
    ],
)
def test_no_http_status_beyond_the_upstreams(path: Path) -> None:
    """A status code or a comparison with one stays where the upstream is
    spoken to, so a change of client touches nothing else."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    caught = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler) and node.name
    }
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "status"
            and isinstance(node.value, ast.Name)
        ):
            assert node.value.id not in caught, f"{path.name} reads an error's .status"
        if isinstance(node, ast.Compare):
            for side in (node.left, *node.comparators):
                code = side.value if isinstance(side, ast.Constant) else None
                assert not (isinstance(code, int) and 100 <= code <= 599), (
                    f"{path.name} compares with {code}"
                )


AGENT_MODULES = [p for p in _modules() if _layer_of(p) == "agents"]


@pytest.mark.parametrize(
    "path", AGENT_MODULES, ids=[p.relative_to(SOURCE).as_posix() for p in AGENT_MODULES]
)
def test_no_agent_compares_the_stage(path: Path) -> None:
    """What a stage carries out is the executor's table alone: an agent
    asks for its actions whatever the stage."""
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Compare):
            for side in (node.left, *node.comparators):
                assert not (isinstance(side, ast.Attribute) and side.attr == "stage"), (
                    f"{path.name} compares the stage on line {node.lineno}"
                )


@pytest.mark.parametrize(
    "path",
    [p for p in _modules() if p != SOURCE / "records" / "mail.py"],
    ids=lambda p: p.relative_to(SOURCE).as_posix(),
)
def test_the_discard_roles_are_spelt_once(path: Path) -> None:
    """The trash, junk and spam are named in records/mail.py alone, so the
    executor and an agent cannot come to differ on them."""
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Set):
            values = {e.value for e in node.elts if isinstance(e, ast.Constant)}
            assert "trash" not in values, (
                f"{path.name} names the roles on line {node.lineno}"
            )


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

    assert found == ["benethos_mailbox_agents.store"]
    assert _layer(found[0]) not in MAY_IMPORT["records"]


TESTS = Path(__file__).resolve().parent


@pytest.mark.parametrize("path", sorted(TESTS.glob("test_*.py")), ids=lambda p: p.name)
def test_a_test_module_imports_no_other(path: Path) -> None:
    """What test modules share lives in conftest.py, helpers.py and fakes.py."""
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith("test_"), f"imports {node.module}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("test_"), f"imports {alias.name}"
