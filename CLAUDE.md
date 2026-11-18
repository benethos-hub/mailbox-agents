# Working guidelines for Claude

How to work in this repository. Read this before making changes. See
[SPECS.md](SPECS.md) for what the project is and does.

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
   first. See SPECS.md section 11.
8. **The repo stands on its own.** State a convention as this project's
   decision. Do not reference the author's other repositories, local
   filesystem paths or email addresses in versioned files.

## Environment

- Windows, PowerShell or Bash, and Linux in the container. Python 3.11 to
  3.15.
- Set up: `uv sync`.
- Run: `uv run benethos-mailbox-agent --help`.
- Settings come from the environment or from a `.env` file, every name with
  the prefix `MAILBOX_AGENT_`. `config/benethos-mailbox-agent/.env.example`
  lists them all. The test suite needs none of them.

## Project layout

See SPECS.md section 4 for the full table.

```
src/benethos_mailbox_agent/
  cli/            # the console script, its commands, the wiring of a session
  __main__.py     # enables `python -m benethos_mailbox_agent`
  errors.py       # the error hierarchy, and redact
  settings/       # settings resolution, secrets from files
  logbook/        # every line on stderr, one function per line
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
  agents/<name>/  # one package per agent: agent.py always, schema.py,
                  # baseline.py and prompts/ for one that asks a model,
                  # and modules of its own
tests/            # offline: REST and gateway through httpx.MockTransport
live/             # run by hand, outside testpaths: a mail server of its own
containers/       # images/, production/, development/, and live/: a mail
                  # server and a mailbox service of their own for live/
config/           # .env.example and *.example.json versioned, .env local
data/             # state files and the gold set, never versioned
reports/          # evaluation reports, numbers only, versioned
```

Which layer may import which is a table in `tests/test_layers.py`. A new
module or subpackage needs a row there, and an import against the order
fails the suite.

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
- Async tests run with pytest-asyncio in `auto` mode.
- **The gates do not cover the upstreams changing.** Verify a new
  assumption about the mailbox service or the gateway with a live check
  before building on it, and mark it **(to verify)** in SPECS.md until then.
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
  agent and are never shared. What several agents need lives in `runtime/`.
- **A prompt has a version.** Changing a prompt changes its version, and
  the step runner treats it as new work.
- **A migration is never changed once released.** A change of the schema is
  a new numbered migration.
- **SPECS.md moves with the code.** A change that departs from it changes
  it in the same commit. Every user-facing change gets an entry under
  `[Unreleased]` in `CHANGELOG.md` in the same commit.
- No semicolons in prose: README, docstrings, docs and commit messages.

## Git

- Commit only when the user asks. Push, remote and pull request likewise.
- One commit per change, with all the gates green.
- The pre-commit hook in `.githooks/` refuses staged secrets and state
  files. It is enabled once per clone with
  `git config core.hooksPath .githooks`.
