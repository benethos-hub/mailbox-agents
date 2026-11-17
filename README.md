# benethos-mailbox-agent

Small agents that work on a mailbox continuously. Each one looks at mail as
it arrives or leaves, decides one narrow question about it and takes one
reversible action: a keyword, or a move to a folder. The first three sort
invoices, track sent mail that still waits for a reply and recognise
project inquiries.

> **Status: nothing usable yet.** The design is written down in
> [SPECS.md](https://github.com/benethos-hub/mailbox-agent/blob/main/SPECS.md),
> the code is being built. Do not point it at a mailbox you care about.

## How it works

- Mail is reached only through the REST API of a mailbox service, with its
  Python client `benethos-mailbox-client`.
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
uv run benethos-mailbox-agent --version
```

## Licence

MIT, see [LICENSE](https://github.com/benethos-hub/mailbox-agent/blob/main/LICENSE).
