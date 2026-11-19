"""What never belongs in a versioned file, checked over every tracked file.

The pre-commit hook in .githooks/ looks at staged lines, and only where it
is enabled. This test reads the files git tracks, on every run of the
suite and so in CI, and fails on:

- an e-mail address or a sender pattern on a domain that is not reserved
  for examples, as a real supplier's or the owner's would be,
- a path of a machine or of a user, also in the form Git Bash and WSL
  write it,
- an id of the mailbox service as a real account or message carries it,
- a credential in the forms the pre-commit hook knows: a token by its
  prefix, and a value given to a name such as ``*_TOKEN`` or ``password``.

It holds no list of names: a list of the owner's real suppliers would
publish what it is meant to keep out (decided 2026-11-19). A line that
must show such a form ends with ``pragma: allowlist secret``, as for the
hook. See CLAUDE.md, golden rules 4 and 8.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from functools import cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ALLOW = "pragma: allowlist secret"

# Domains reserved for examples and tests (RFC 2606, RFC 6761), and the
# addresses a commit trailer or a package names on purpose.
RESERVED_SUFFIXES = (".example", ".test", ".invalid", ".localhost")
RESERVED_DOMAINS = frozenset({"example.com", "example.org", "example.net"})
ALLOWED_ADDRESSES = frozenset({"noreply@anthropic.com"})
# The domain of GitHub's private commit addresses, as a whole.
NOREPLY_DOMAINS = frozenset({"users.noreply.github.com"})

# Something before the @, so a decorator such as @pytest.fixture is no
# address, and * for a sender pattern such as *@*.example. A domain may
# hold letters beyond ASCII.
ADDRESS = re.compile(
    r"(?<![A-Za-z0-9._%+*-])([A-Za-z0-9._%+*-]+)@"
    r"((?:(?:[^\W_]|[*-])+\.)+[^\W\d_]{2,})\b"
)
# A user's folder on Windows, macOS and Linux, a drive as WSL and Git Bash
# mount it, and any drive path but the programs' folders, which a script
# may name on purpose. A letter after a backslash is a regular expression,
# as \d:\d.
PATH = re.compile(
    r"[A-Za-z]:[\\/]+Users[\\/]|(?<![\w.])/Users/\w|(?<![\w.])/home/\w"
    r"|(?<![\w.])/mnt/[a-z]/"
    r"|(?<![\w.])/[A-Za-z]/(?:Users|home|projects)/\w"
    r"|(?<![\w\\])[A-Za-z]:[\\/]+(?!Program Files|Windows\b)\w"
)
SERVICE_ID = re.compile(r"\b(?:acc|msg|usr|tok|thr|fld)_[0-9a-f]{16,}\b")
CREDENTIAL = re.compile(
    r"sk-ant-[A-Za-z0-9_-]{16,}|\bsk-[A-Za-z0-9_-]{20,}|mbx_[A-Za-z0-9_-]{16,}"
    r"|Bearer [A-Za-z0-9._-]{16,}|\bgh[pousr]_[A-Za-z0-9]{16,}"
    r"|glpat-[A-Za-z0-9_-]{16,}|\bAKIA[0-9A-Z]{16}\b"
    r"|BEGIN (?:RSA |OPENSSH |EC |DSA |PGP )?PRIVATE KEY"
    # A name that ends in TOKEN, SECRET, PASSWORD or _KEY, maybe with more
    # parts such as _FILE, then the value. _KEYWORD is no such name. A
    # value that starts with / is a path.
    r"|(?:TOKEN|SECRET|PASSWORD|_KEY)(?:_[A-Z]+)*\s*[:=]\s*[\"']?"
    r"[A-Za-z0-9+_-][A-Za-z0-9+/_.-]{11,}"
)
# The same in any case, as JSON and YAML write it: a quoted value, or a
# bare one that ends the line or a word. A bare value with a dot or a
# bracket is code, such as token = base64.b64encode(raw).
NAMED = re.compile(
    r"(?:^|[^a-z0-9])[\"']?[a-z0-9_]*(?:token|secret|password|passwd|_key)[\"']?"
    r"\s*[:=]\s*"
    r"(?:[\"'][A-Za-z0-9+_-][A-Za-z0-9+/_.-]{11,}"
    r"|[A-Za-z0-9+_-][A-Za-z0-9+/_-]{11,}(?:\s|$))",
    re.IGNORECASE,
)
# CREDENTIAL and NAMED follow the patterns of .githooks/pre-commit. A
# change to one changes the other.


def _reserved(domain: str) -> bool:
    """Whether ``domain`` is reserved for examples, or names no domain of
    anyone: a placeholder such as ``*.domain`` or a whole top-level
    domain such as ``*.de``, one label after the wildcards."""
    domain = domain.lower()
    labels = [label for label in domain.split(".") if label != "*"]
    return (
        len(labels) < 2
        or domain in RESERVED_DOMAINS
        or domain.endswith(RESERVED_SUFFIXES)
    )


def addresses(line: str) -> list[str]:
    """The addresses and sender patterns of ``line`` on a domain that is
    not reserved for examples."""
    return [
        found.group(0)
        for found in ADDRESS.finditer(line)
        if not _reserved(found.group(2))
        and found.group(0).lower() not in ALLOWED_ADDRESSES
        and found.group(2).lower() not in NOREPLY_DOMAINS
    ]


def problems(line: str) -> list[str]:
    """What is wrong with one line, each named by its rule."""
    if ALLOW in line:
        return []
    found = [f"address {a}" for a in addresses(line)]
    found += [f"path {m.group(0)}" for m in PATH.finditer(line)]
    found += [f"service id {m.group(0)[:8]}..." for m in SERVICE_ID.finditer(line)]
    found += [f"credential {m.group(0)[:12]}..." for m in CREDENTIAL.finditer(line)]
    found += [f"credential {m.group(0)[:12]}..." for m in NAMED.finditer(line)]
    return found


@cache
def tracked() -> tuple[Path, ...]:
    """The files git tracks, as text. A binary file is left out."""
    git = shutil.which("git")
    if git is None:
        pytest.fail("the repository content is read through git, which is missing")
    listed = subprocess.run(
        [git, "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout.decode()
    found = []
    for name in filter(None, listed.split("\0")):
        path = ROOT / name
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" in data:
            continue
        found.append(path)
    return tuple(found)


def test_the_repository_holds_none_of_it() -> None:
    files = tracked()
    assert len(files) > 100, "git listed too few files to be this repository"
    hits = []
    for path in files:
        text = path.read_bytes().decode("utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), 1):
            hits += [
                f"{path.relative_to(ROOT).as_posix()}:{number}: {problem}"
                for problem in problems(line)
            ]
    assert hits == [], "\n".join(hits)


# -- the rules themselves, on lines put together here so the scan above
# -- does not find them in this file.

AT = "@"


@pytest.mark.parametrize(
    "line",
    [
        "billing" + AT + "real-host.com",
        '"senders": ["*' + AT + 'real-host.com"]',
        "rechnung" + AT + "mail.provider.de",
        "Owner <someone" + AT + "provider.net>",
        "rechnung" + AT + "müller.de",
    ],
)
def test_an_address_on_a_real_domain_is_found(line: str) -> None:
    assert problems(line)


@pytest.mark.parametrize(
    "line",
    [
        "billing" + AT + "hosting.example",
        "*" + AT + "*.shop.example",
        "agents" + AT + "agents.test",
        "a" + AT + "example.com",
        "someone" + AT + "nowhere.invalid",
        "Co-Authored-By: Claude <noreply" + AT + "anthropic.com>",
        "1+someone" + AT + "users.noreply.github.com",
        AT + "pytest.mark.parametrize",
        "uses: actions/checkout" + AT + "v4.2.2",
        "write `*" + AT + "domain` or `*" + AT + "*.domain`",
        "*" + AT + "*.de is refused as too broad",
    ],
)
def test_an_address_for_examples_passes(line: str) -> None:
    assert problems(line) == []


@pytest.mark.parametrize(
    "line",
    [
        "C:" + "\\Users\\someone\\project",
        "D:/" + "Users/someone/x",
        "/" + "Users/someone/project",
        "/" + "home/someone/.local",
        "sh /" + "mnt/d/projects/x/setup.sh",
        "/" + "c/Users/someone/project",
        "cd /" + "d/projects/mailbox-agent",
        "D:" + "\\projects\\mailbox-agent\\data",
        "d:" + "/projects/mailbox-agent",
    ],
)
def test_a_path_of_a_machine_is_found(line: str) -> None:
    assert problems(line)


def test_a_path_inside_the_project_passes() -> None:
    assert problems("containers/live/secrets/agent.env") == []
    assert problems(r"C:\Program Files\Google\Chrome\Application\chrome.exe") == []


def test_an_id_of_the_service_is_found() -> None:
    assert problems("account " + "acc" + "_" + "3f9a" * 8)
    assert problems("message " + "msg" + "_" + "0b1c" * 16)
    assert problems("account acc1, message m1") == []


@pytest.mark.parametrize(
    "line",
    [
        "token = " + "mbx" + "_" + "A1b2C3d4E5f6G7h8I9",
        "key " + "sk-ant-" + "api03-abcdefghijklmnop",
        "-----" + "BEGIN " + "OPENSSH PRIVATE KEY-----",
        "Authorization: " + "Bearer " + "abcdefghijklmnopqrstu",
        "POSTGRES_PASSWORD" + "=hunter2hunter2hunter2",
        "MAILBOX_AGENTS_SERVICE_TOKEN" + "=abcdefghijklmnop",
        "GATEWAY_KEY_FILE" + "=Zq7xW2pL9mN4vB8k",
        "pass" + 'word: "Sup3rS3cretValue99"',
    ],
)
def test_a_credential_is_found(line: str) -> None:
    assert problems(line)


@pytest.mark.parametrize(
    "line",
    [
        "MAILBOX_AGENTS_GATEWAY_KEY_FILE=/run/secrets/gateway_key",
        "token = base64.b64encode(raw)",
    ],
)
def test_a_name_that_is_no_credential_passes(line: str) -> None:
    assert problems(line) == []


def test_an_allowlisted_line_passes() -> None:
    assert problems("billing" + AT + "real-host.com  # " + ALLOW) == []
