# Working guidelines for Claude

How to work in this repository. Read this before making changes. See
[docs/CONCEPT.md](docs/CONCEPT.md) for what the project is and does, and
[docs/concept/](docs/concept/) for each topic and each agent.

## Golden rules

1. **Real mailboxes, real consequences.** An agent reads customer mail and
   moves it. Never run anything against a mailbox that has not been named
   as a test account by its owner. The live checks in `live/` bring their
   own mail server with an account made for them and filled with invented
   mail. A new agent, and one whose prompt or model changed, starts in the
   stage `shadow`. A change of stage on a real mailbox is the owner's
   decision, never a default.
2. **Virtual environment only.** Never the global Python or pip. `uv run ...`
   satisfies this rule. Without uv, invoke the project interpreter directly:
   `.venv/Scripts/python.exe` on Windows, `.venv/bin/python` elsewhere.
3. **English in the repo.** All code, comments, docstrings, prompts and
   documentation are English. Conversation with the user may be German.
4. **Secrets never travel.** The service token and the gateway key are never
   logged, never stored in a state file and redacted from error text. No
   real token, key, address, account id or message id in any versioned
   file. Nor does a filesystem path of this machine.
5. **Nothing of a mail in a log line.** A line names ids, states, counts and
   durations. Never a subject, a sender, a text or an attachment name.
6. **One module per upstream.** `sources/mailbox.py` is the only module that
   imports `benethos_mailbox_client`, `llm/gateway.py` the only one that
   talks to the model gateway. `tests/test_layers.py` holds the import order.
7. **A model that reads mail has no tools.** It returns a value in a fixed
   schema. Acting on the value is code, and the code checks the evidence
   first. See docs/concept/safety.md.
8. **The repo stands on its own.** State a convention as this project's
   decision. Do not reference the author's other repositories, local
   filesystem paths or email addresses in versioned files.
9. **Decisions are restated, never quoted.** A decision taken in a
   conversation goes into a versioned file in plain English, with its
   date. No message, prompt or wording of the owner is copied in, in any
   language, not even as a short quote. Who proposed what stays out too:
   the file says what was decided and why.

## Environment

- Windows, PowerShell or Bash, and Linux in the container. Python 3.11 to
  3.15.
- Set up: `uv sync`.
- Run: `uv run benethos-mailbox-agents --help`.
- Settings come from the environment or from a `.env` file, every name with
  the prefix `MAILBOX_AGENTS_`. `config/benethos-mailbox-agents/.env.example`
  lists them all. The test suite needs none of them.

## Project layout

See docs/ARCHITECTURE.md for the full table.

```
src/benethos_mailbox_agents/
  cli/            # the console script, its commands, the wiring of a session
  __main__.py     # enables `python -m benethos_mailbox_agents`
  errors/         # the error hierarchy, one module per error, and redact
  settings/       # settings resolution, secrets from files
  logbook/        # every line on stderr, one activity class per line,
                  # see docs/LOGGING.md
  records/        # the models passed between layers
  contract/       # Agent (ABC), Action, Trigger, Limits, Requires, the
                  # Context protocols, registry, prompt loading
  store/          # SQLite: schema, migrations, one file per agent
  sources/
    mailbox.py    # the only module importing benethos_mailbox_client
  llm/
    gateway.py    # the only module that talks to the model gateway
    evidence.py   # whether a quote is in the text the model was given
  runtime/        # worker loop, step runner, model calls, open items, the
                  # read-only mailbox, action executor, readiness, health,
                  # metrics
  evaluation/     # the gold format, the scoring, the report
  agents/<name>/  # one package per agent: agent.py always, schema.py
                  # and prompts/ for one that asks a model, baseline.py
                  # where its rules need a module, and modules of its own
tests/            # offline: REST and gateway through httpx.MockTransport
live/             # run by hand, outside testpaths: checks against the
                  # test account of containers/live/
containers/       # images/, production/, development/, and live/: a mail
                  # server and a mailbox service of their own for live/
config/           # .env.example and *.example.json versioned, .env local
docs/             # CONCEPT.md, the overview, and concept/, a file per
                  # topic and per agent, ARCHITECTURE.md, LOGGING.md,
                  # ROADMAP.md
data/             # state files and the gold set, never versioned
reports/          # evaluation reports, numbers only, versioned
assets/           # brand/: icon.svg and the PNGs build.py renders from it
.github/          # workflows/: CI, CodeQL, freshness, publish, and
                  # dependabot.yml
.githooks/        # pre-commit: refuses staged secrets, state files and
                  # the gold set
```

Which layer may import which is a table in `tests/test_layers.py`. A new
top-level module or subpackage needs a row there, an import against the
order fails the suite, and so does an import that closes a circle.

## Verifying

All of these must be green before a commit:

```
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv lock --check
```

- The suite is offline. The mailbox service and the gateway are mocked
  with `httpx.MockTransport`. Never write a test that reaches a network,
  and never one that skips itself when a credential is missing.
- The coverage floor of 80 % is part of the pytest run.
- `tests/test_repo_content.py` reads every tracked file and fails on an
  address or a sender pattern on a real domain, a path of a machine, an
  id of the mailbox service or a credential. Example data uses domains
  reserved for examples (`*.example`, `*.test`) and invented names, never
  a real supplier, company or person from a mailbox. The test holds no
  list of such names, as it would publish them.
- Async tests run with pytest-asyncio in `auto` mode.
- **The gates do not cover the upstreams changing.** Verify a new
  assumption about the mailbox service or the gateway with a live check
  before building on it, and mark it **(to verify)** in its file under
  `docs/concept/` until then.
- A live check is a manual run, never a gate: `containers/live/README.md`
  says how to start the mail server of its own, and `live/smoke.py` checks
  the package against it, read-only.
- An evaluation run is manual too, against a gold set under `data/`. Its
  report goes into `reports/` and holds numbers only.

## Conventions

- **asyncio throughout.** One event loop per process, an async httpx client
  for the gateway, the async class of the mailbox client.
- **A dependency** is added to `pyproject.toml` in the commit that first
  imports it, as `~=X.Y.Z` at the version tested. Dev tools go into
  `[dependency-groups]`.
- **Agents are self-contained.** Prompt, schema and baseline belong to one
  agent and are never shared. What several agents need lives in `runtime/`,
  or in `contract/` and `records/` where an agent needs it.
- **A prompt has a version.** Changing a prompt changes its version, and
  the step runner treats it as new work.
- **A migration is never changed once released.** A change of the schema is
  a new migration: a class `VNNNN<Subject>` of `Migration` in a module
  `vNNNN_<subject>.py` in `store/migrations/versions/` with the next
  number, added to `MIGRATIONS` in `store/migrations/__init__.py`. Its
  docstring says what it does and why. Each statement stands alone, a step
  in Python is the method `before`. A release freezes its new migrations:
  the fingerprint of each goes into `RELEASED` in `tests/test_store.py`.
- **The concept moves with the code.** `docs/CONCEPT.md` is the overview,
  and `docs/concept/` holds one file per topic and one per agent. A change
  that departs from them changes them in the same commit. Every
  user-facing change gets an entry under `[Unreleased]` in `CHANGELOG.md`
  in the same commit.
- **A document is named for its subject.** One that stands directly in
  `docs/` is written in capitals: `CONCEPT.md`, `ARCHITECTURE.md`. One
  that grows too long becomes an overview, and its parts go into a folder
  of the same name in lowercase beside it: `CONCEPT.md` and `concept/`. A
  part is named in lowercase with hyphens, an agent's as `agent-<name>.md`
  with the `_` of its name as a hyphen. It starts with the name of its
  document, as in `# Concept: runtime`, and a line that leads back to the
  overview. The overview lists every part in a table.
- No semicolons in prose: README, docstrings, docs and commit messages.

## Git

- Commit only when the user asks. Push, remote and pull request likewise.
- One commit per change, with all the gates green.
- The pre-commit hook in `.githooks/` refuses staged secrets and state
  files. It is enabled once per clone with
  `git config core.hooksPath .githooks`.
