# <img src="https://raw.githubusercontent.com/benethos-hub/mailbox-agents/main/assets/brand/icon.svg" alt="" height="36" align="absmiddle"> Mailbox Agents

[![CI](https://github.com/benethos-hub/mailbox-agents/actions/workflows/ci.yml/badge.svg)](https://github.com/benethos-hub/mailbox-agents/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/benethos-hub/mailbox-agents/badges/coverage.json&logo=githubactions&logoColor=white)](https://github.com/benethos-hub/mailbox-agents/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/benethos-hub/mailbox-agents?logo=opensourceinitiative&logoColor=white)](https://github.com/benethos-hub/mailbox-agents/blob/main/LICENSE)
[![Python](https://img.shields.io/pypi/pyversions/benethos-mailbox-agents?logo=python&logoColor=white)](https://pypi.org/project/benethos-mailbox-agents/)

[![PyPI benethos-mailbox-agents](https://img.shields.io/pypi/v/benethos-mailbox-agents?label=PyPI%20benethos-mailbox-agents&logo=pypi&logoColor=white)](https://pypi.org/project/benethos-mailbox-agents/)
[![Container benethos-mailbox-agents](https://img.shields.io/badge/ghcr.io-benethos--mailbox--agents-2496ED?logo=docker&logoColor=white)](https://github.com/benethos-hub/mailbox-agents/pkgs/container/benethos-mailbox-agents)

[![Sponsor](https://raw.githubusercontent.com/benethos-hub/.github/main/profile/badges/sponsor.svg)](https://github.com/sponsors/BeneODev)
[![PayPal](https://raw.githubusercontent.com/benethos-hub/.github/main/profile/badges/paypal.svg)](https://paypal.me/BeneODev)

Small agents that work on a mailbox continuously. Each one looks at mail as
it arrives or leaves, decides one narrow question about it and takes one
reversible action: a keyword, or a move to a folder. The first ones sort
invoices, track sent mail that still waits for a reply, recognise project
inquiries and file the mail of listed senders into folders.

> **Status: alpha.** Built, and run on a test account of invented mail
> only. Names, settings and the state file may still change from one
> version to the next. The design is written down in
> [docs/CONCEPT.md](https://github.com/benethos-hub/mailbox-agents/blob/main/docs/CONCEPT.md),
> and no agent acts on a real mailbox yet. Do not point it at a mailbox you
> care about.

## How it works

- Mail is reached only through the REST API of the
  [mailbox service](https://github.com/benethos-hub/mailbox), with its
  Python client `benethos-mailbox-client`. An agent works only against a
  version of the service it was tested against, today 0.7 from 0.7.5, and
  refuses any other.
- A language model is reached only through an OpenAI-compatible gateway,
  with one call per message, a JSON schema for the answer and no tools.
- Everything else is deterministic code: which messages an agent looks at,
  what a rule says, whether a quote from the model is really in the mail,
  and which action follows.
- Every agent runs in a process of its own, with its own credentials and
  its own SQLite state file. The state file holds ids and decisions, never
  the text of a mail.
- A new agent starts in the stage `shadow`, where it only records what it
  would do. The stages `keyword` and `full` follow after it was measured
  against labelled mail.

## Setup

Needs [uv](https://docs.astral.sh/uv/) and Python 3.11 or newer.

```
uv sync
uv run benethos-mailbox-agents --version
```

## Licence

MIT, see [LICENSE](https://github.com/benethos-hub/mailbox-agents/blob/main/LICENSE).
