# Specification — Mailbox Agents

> **Status: 2026-11-18. The runtime and the agents `counting`, `invoices`,
> `awaiting_reply`, `inquiries` and `sorting` are built and run against a
> test account of invented mail. `invoices` version 3 ran in `shadow` on its
> owner's real account, read-only, and changed nothing. Version 4, which
> works beside `sorting`, and `sorting` itself have not run on a real
> mailbox. None acts on a real mailbox yet.** This
> file is the table of contents of the specification: what the project is,
> the decisions that matter most, and where the details are. The details
> live in [docs/specs/](docs/specs/) and move with the code. A statement
> about another system that nobody has checked yet is marked
> **(to verify)**, and a choice that is still open is listed in
> [roadmap.md](docs/specs/roadmap.md) rather than written as fact.

## Purpose

A set of small agents that work on a mailbox continuously: each one looks at
mail as it arrives or leaves, decides one narrow question about it, and takes
one reversible action. The first ones sort invoices, track sent mail that
is still waiting for a reply, recognise project inquiries and file the mail
of listed senders into folders.

The agents reach mail only through the REST API of a mailbox service, with
its Python client `benethos-mailbox-client`. They reach a language model only
through an OpenAI-compatible gateway. Everything else is deterministic code
in this repository.

The project exists for two reasons. Mail that holds customer correspondence
should be processed by code its owner can read, on a machine its owner runs.
And a claim about how well an agent works should be a number measured
against labelled mail, not an impression.

## Scope

**In scope:** reading the change feed of the mailbox service, selecting the
messages an agent cares about, classifying a message with rules and with one
model call, extracting fields from it, setting and removing a keyword, moving
a message to a folder, keeping per-agent state in SQLite, measuring every
agent against a labelled set of mail, and exposing health and metrics.

**Out of scope (non-goals):**

- Sending mail, and deleting mail, to the trash or for good.
- A model that chooses tools. No step in this project hands tools to a
  model. Work of that kind belongs to a separate agent server, which a
  later phase may call over HTTP ([roadmap](docs/specs/roadmap.md)).
- An agent framework. One call with a schema needs none
  ([model gateway](docs/specs/model-gateway.md)).
- Talking IMAP, SMTP or a provider API. The mailbox service does that.
- Parsing MIME, decoding character sets or turning HTML into text. The
  mailbox service does that too.
- A conversation or session store. Every model call is a single turn
  ([state](docs/specs/state.md)).
- A user interface. The mailbox is the interface: a keyword or a folder is
  what a person sees, and taking a keyword off is how a person answers.

**Deliberately gated rather than excluded:** writing a reply as a draft. It
needs a right the first agents do not get, and it comes after the agents
that only read and sort have been measured.

## Naming

The name is plural (decided 2026-11-18): the project holds several agents
on one runtime, and each process runs one of them.

| Where | Name |
|---|---|
| Display name, in the README and the brand | Mailbox Agents |
| Repository | `mailbox-agents` |
| PyPI distribution | `benethos-mailbox-agents` |
| Import package | `benethos_mailbox_agents` |
| Console script | `benethos-mailbox-agents` |
| Container image | `ghcr.io/benethos-hub/benethos-mailbox-agents` |
| Settings prefix | `MAILBOX_AGENTS_` |
| Agent names | lowercase letters, digits and `_`: `invoices`, `awaiting_reply`, `inquiries` |

## What matters most

- **Shadow first.** A new agent, and one whose prompt or model changed,
  starts in the stage `shadow`: it records what it would do and changes
  nothing. `keyword` sets keywords, `full` also moves. A change of stage on
  a real mailbox is the owner's decision ([runtime](docs/specs/runtime.md)).
- **A model that reads mail has no tools.** It answers in a fixed schema,
  code acts on the answer ([agent contract](docs/specs/agent-contract.md)).
- **A value needs evidence.** Every label and field carries a quote that
  code finds in the mail, word for word, before anything is done with it
  ([safety](docs/specs/safety.md)).
- **The sender is not proof.** Only a rule naming an address or a pattern
  moves a message. A domain rule and a model's choice mark only, with one
  exception since 2026-11-18: `invoices` moves a message its model takes
  for an invoice, into the subfolder of a folder it looks in, and out of
  the inbox only into the inbox folder the owner set. The model names no
  folder ([invoices](docs/specs/agents/invoices.md)).
- **Reversible only.** Every action records what was there before.
- **Nothing of a mail in a log line, secrets never travel**
  ([safety](docs/specs/safety.md), [docs/LOGGING.md](docs/LOGGING.md)).
- **Measured, not believed.** Every agent is scored against labelled mail
  beside its rules without a model ([evaluation](docs/specs/evaluation.md)).

## The specification in detail

| File | What it holds |
|---|---|
| [architecture.md](docs/specs/architecture.md) | the layers, the modules and the design decisions behind them |
| [mailbox-service.md](docs/specs/mailbox-service.md) | the upstream: rights, the change feed, what the service exposes and what is still to verify |
| [model-gateway.md](docs/specs/model-gateway.md) | the OpenAI-compatible gateway, structured output, local and hosted models |
| [agent-contract.md](docs/specs/agent-contract.md) | `Agent`, its triggers, actions and limits, the context it is handed |
| [runtime.md](docs/specs/runtime.md) | the worker loop, the steps of a message, stages, the commands and `report` |
| [state.md](docs/specs/state.md) | the SQLite state file, its tables and migrations |
| [safety.md](docs/specs/safety.md) | untrusted mail, evidence, sender rules, reversibility, secrets |
| [evaluation.md](docs/specs/evaluation.md) | gold sets, scoring, reports of numbers only |
| [configuration.md](docs/specs/configuration.md) | every setting |
| [operation.md](docs/specs/operation.md) | containers, health, metrics, cost, logs |
| [testing.md](docs/specs/testing.md) | the offline suite and the live checks |
| [roadmap.md](docs/specs/roadmap.md) | the phases, ideas and the open questions |

## The agents

| Agent | Question | Status | Spec |
|---|---|---|---|
| `counting` | none: counts what arrives and is sent, changes nothing | built | [counting.md](docs/specs/agents/counting.md) |
| `invoices` | is this an invoice? It moves one into the subfolder of the folder it lies in | built, version 4, prompt `v4` | [invoices.md](docs/specs/agents/invoices.md) |
| `awaiting_reply` | does this sent message wait for an answer? | built | [awaiting_reply.md](docs/specs/agents/awaiting_reply.md) |
| `inquiries` | is this a project inquiry, and what does it say? | built, prompt `v3` | [inquiries.md](docs/specs/agents/inquiries.md) |
| `sorting` | is the sender one of a listed group, and which folder is the group's? | built, no model. `invoices` then files an invoice within the folder `sorting` put it in | [sorting.md](docs/specs/agents/sorting.md) |
