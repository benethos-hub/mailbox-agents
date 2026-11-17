# Specification — Mailbox Agents

> **Status: draft, 2026-11-17. Nothing is built.** This document records what
> was decided before the first line of code. A statement about another system
> that nobody has checked yet is marked **(to verify)**, and a choice that is
> still open is listed in section 17 rather than written as fact.

## 1. Purpose

A set of small agents that work on a mailbox continuously: each one looks at
mail as it arrives or leaves, decides one narrow question about it, and takes
one reversible action. The first three sort invoices, track sent mail that
is still waiting for a reply, and recognise project inquiries.

The agents reach mail only through the REST API of a mailbox service, with
its Python client `benethos-mailbox-client`. They reach a language model only
through an OpenAI-compatible gateway. Everything else is deterministic code
in this repository.

The project exists for two reasons. Mail that holds customer correspondence
should be processed by code its owner can read, on a machine its owner runs.
And a claim about how well an agent works should be a number measured
against labelled mail, not an impression.

## 2. Scope

**In scope:** reading the change feed of the mailbox service, selecting the
messages an agent cares about, classifying a message with rules and with one
model call, extracting fields from it, setting and removing a keyword, moving
a message to a folder, keeping per-agent state in SQLite, measuring every
agent against a labelled set of mail, and exposing health and metrics.

**Out of scope (non-goals):**

- Sending mail, and deleting mail, to the trash or for good.
- A model that chooses tools. No step in this project hands tools to a
  model. Work of that kind belongs to a separate agent server, which a
  later phase may call over HTTP (section 16).
- An agent framework. One call with a schema needs none (section 6).
- Talking IMAP, SMTP or a provider API. The mailbox service does that.
- Parsing MIME, decoding character sets or turning HTML into text. The
  mailbox service does that too.
- A conversation or session store. Every model call is a single turn
  (section 9).
- A user interface. The mailbox is the interface: a keyword or a folder is
  what a person sees, and taking a keyword off is how a person answers.

**Deliberately gated rather than excluded:** writing a reply as a draft. It
needs a right the first agents do not get, and it comes after the agents
that only read and sort have been measured.

## 3. Naming

| Where | Name |
|---|---|
| Repository | `mailbox-agent` |
| PyPI distribution | `benethos-mailbox-agent` |
| Import package | `benethos_mailbox_agent` |
| Console script | `benethos-mailbox-agent` |
| Container image | `ghcr.io/benethos-hub/benethos-mailbox-agent` |
| Settings prefix | `MAILBOX_AGENT_` |
| Agent names | lowercase letters, digits and `_`: `invoices`, `awaiting_reply`, `inquiries` |

## 4. Architecture

```
                 mail servers
                      ^
                      |
        +----------------------------+
        | mailbox service            |   accounts, change feed,
        | (not part of this project) |   one user per agent, audit
        +-------------^--------------+
                      | REST, benethos-mailbox-client
        +-------------+--------------+
        | mailbox-agent              |   one image,
        |   invoices        + SQLite |   one process per agent,
        |   awaiting_reply  + SQLite |   one state file per agent
        |   inquiries       + SQLite |
        +-------------+--------------+
                      | OpenAI-compatible HTTP, one key per agent
        +-------------v--------------+
        | model gateway              |   aliases, allowlist and
        | (not part of this project) |   budget per key
        +-------------+--------------+
                      |
            model backends, local or hosted
```

How one message passes through one agent:

```
trigger          selection        decision                  effect
---------------------------------------------------------------------------
change feed  ->  code: is    ->   1. baseline (rules)   ->  shadow
tick (clock)     this mine?       2. model, one call,       keyword
                                     schema, no tools       folder
                                  3. check in code:
                                     schema, evidence

             every step is recorded in the agent's state file
```

### Modules

```
src/benethos_mailbox_agent/
  cli.py          # the console script: worker, run, backfill, report, eval,
                  # status, paths
  __main__.py     # enables `python -m benethos_mailbox_agent`
  errors.py       # the error hierarchy, and redact
  settings/       # settings resolution, secrets from files
  logbook/        # every line on stderr, and what a line may never carry
  contract/       # Agent (ABC), Action, Trigger, Limits, Requires
  records/        # the models passed between layers: MessageRef, Decision,
                  # Evidence, StepResult
  sources/
    mailbox.py    # the only module importing benethos_mailbox_client
  llm/
    gateway.py    # the only module that talks to the model gateway
  store/          # SQLite: schema, migrations, one file per agent
  runtime/        # registry, worker loop, feed reader, tick, step runner,
                  # action executor, health, metrics
  evaluation/     # the gold format, scoring per label and per field, report
  agents/
    <name>/       # one package per agent
      agent.py    # one Agent subclass, no side effects at import
      schema.py   # what the model must answer
      baseline.py # the same question answered by rules
      prompts/    # system prompts as Markdown, each with a version
tests/            # offline: REST and gateway through httpx.MockTransport
live/             # run by hand, outside testpaths: smoke against a test
                  # account, the evaluation against the gold set
containers/
  images/mailbox-agent/Dockerfile
  production/     # the published image, one service per agent
  development/    # built from the checkout
config/           # .env.example versioned, .env local
data/             # state files and the gold set, never versioned
```

### Design decisions

- **A model that reads foreign text has no tools.** Mail is written by
  strangers. The step that reads it returns a value in a fixed schema and
  nothing else, so an instruction hidden in a mail can at worst produce a
  wrong value. Acting on the value is code.
- **One process per agent, one image for all.** `worker --agent invoices`
  runs one agent. Each has its own credentials, its own state file, its own
  health and its own restart. They share code and nothing else.
- **The mailbox service and the gateway each sit behind one module.**
  `sources/mailbox.py` and `llm/gateway.py` are the only places that know
  them. A test in the suite holds the import order, as in a layered project.
- **Agents are self-contained.** Prompt, schema and baseline belong to one
  agent and are never shared. What several agents need lives in `runtime/`.
- **State stays where it is authoritative.** Mail stays in the mailbox. The
  state file holds ids, decisions and what was done, not copies of mail.
- **A backend that is away is a normal condition.** A model may run on a
  machine that is switched off. A message then waits and is taken up again,
  and nothing is lost or decided without the model.
- **asyncio throughout** (decided 2026-11-17). The async class of the
  mailbox client, an async httpx client for the gateway, one event loop per
  process. Calls to SQLite are short and serialized.
- **A state file can be read by another process.** It runs in WAL mode and
  its schema is part of this document, so a later overview of what every
  agent did (section 16) reads the files without the agents knowing of it.

## 5. Upstream: the mailbox service

The agents use the service's REST API through `benethos-mailbox-client`.
Operation names below are the service's `operationId`s.

| Need | Operation |
|---|---|
| What changed since the last look | `list_all_changes` with a state token |
| A message, its text and attachment list | `get_message` |
| The conversation a message belongs to | `get_thread` |
| Set or remove a keyword, move to a folder | `update_message`, `batch_messages` |
| The folders of an account | `list_folders` |

What the agents rely on:

- The feed names created, updated, deleted and sent messages by id and
  answers with a new state token. A token older than the service keeps
  changes for answers `410 changes_expired`.
- The feed may name a change more than once. Every step is therefore
  idempotent (section 8).
- The text of a message arrives already converted, with hidden HTML content
  dropped.
- A change of flags made in another mail client reaches the feed only where
  the provider reports it, for IMAP with CONDSTORE. `awaiting_reply` depends
  on this (section 10.2).
- Keywords are not available on every provider **(to verify per account
  before an agent is switched to the keyword stage)**.

Rights. Each agent has a user of its own in the service:

| Agent | Rights | Not granted |
|---|---|---|
| `invoices` | `mail.read`, `mail.write` | `drafts`, send, `mail.delete` |
| `awaiting_reply` | `mail.read`, `mail.write` | `drafts`, send, `mail.delete` |
| `inquiries` | `mail.read`, `mail.write` | `drafts`, send, `mail.delete` |

`mail.write` also allows moving a message to the trash and creating a
folder. The service cannot refuse those to an agent that may move mail, so
the runtime does (section 11). Narrowing a grant to chosen folders is
possible in the service. Whether a move between two granted folders works
under such a grant is **(to verify)**.

## 6. The model gateway

The agents speak the OpenAI chat completions and embeddings API to a
gateway, with httpx. No model SDK and no agent framework is a dependency:
a call with a schema, a validation and a retry are little code, and every
request stays visible, storable and mockable.

- **One key per agent.** The key names the models the agent may use and a
  budget. An agent whose key lists only local models cannot send mail
  content to a hosted one through a configuration mistake.
- **A model is named by an alias.** The setting `MAILBOX_AGENT_MODEL` holds
  an alias the gateway resolves. Changing the model behind it is a change at
  the gateway followed by an evaluation run. The model the gateway reports
  in its answer is stored with every step.
- **The answer is forced into a schema** with `response_format` and a JSON
  schema, and validated again with pydantic. That the gateway hands the
  schema to a local backend unchanged is **(to verify)**.
- **No fallback** from one model to another inside the agent. A fallback at
  the gateway from a local to a hosted model must not be configured for a
  key that reads customer mail.
- **A failed or missing answer** leaves the message `pending`. The next
  attempt waits twice as long, up to a ceiling.

## 7. The agent contract

Every agent package defines exactly one concrete `Agent` subclass in its
`agent.py`. The class attributes are validated on instantiation.

| Attribute | Meaning |
|---|---|
| `name`, `version`, `description` | identity. `name` equals the package name |
| `triggers` | the feed events it wants, and whether it wants the tick |
| `actions` | the actions it may take, from the list below |
| `limits` | model calls per message and per day |
| `requires` | settings that must be present before it starts |

| Method | Meaning |
|---|---|
| `select(event)` | whether this event concerns the agent. Code only |
| `baseline(message)` | the question answered by rules |
| `decide(message)` | the question answered with one model call |
| `effect(decision)` | the actions that follow from a decision |
| `tick(now)` | for agents with deadlines: what is due |

The actions that exist:

| Action | Reversible by |
|---|---|
| `add_keyword` | `remove_keyword` |
| `remove_keyword` | `add_keyword` |
| `move_to_folder` | a move back, the previous folder is recorded |

An agent declares which of them it uses, and the runtime carries out no
other. A new action is added here first, with how it is taken back.

`status` reports for each agent whether it is ready and which required
setting is missing, without starting it.

## 8. Runtime

One loop per process:

1. Read the feed from the stored cursor. On `410` take a new state and run
   `backfill` over the window the setting names.
2. For each event the agent selects, record the message as `pending`.
3. For each `pending` message run the steps: fetch, baseline, model, check,
   effect. Each step writes its result before the next begins.
4. On the tick, ask the agent what is due and run the effects.
5. Store the cursor, then sleep.

Message states: `pending`, `skipped` (not selected or ruled out), `decided`,
`done`, `failed` (given up after the configured attempts).

Rules:

- **Idempotent steps.** A step whose result is stored for the same message,
  prompt version and model is not run again. A repeated feed entry is
  harmless.
- **The cursor moves last.** A crash repeats work, it does not skip mail.
- **One writer.** A process is the only writer of its state file.
- **A new prompt or model does not rewrite history.** `backfill` runs old
  messages again under the new version and keeps both results.

Rollout stage, per agent, in `MAILBOX_AGENT_STAGE`:

| Stage | What the agent does |
|---|---|
| `shadow` | records what it would do, changes nothing |
| `keyword` | sets its keyword, moves nothing |
| `full` | every action it declares |

A new agent starts in `shadow`, and so does one whose prompt or model
changed until the evaluation was run again.

### 8.1 Report

`benethos-mailbox-agent report --agent <name>` shows what an agent decided
and did, or in `shadow` would have done: per message the subject and sender,
the decision, the evidence and the action (decided 2026-11-17). The state
file holds ids only, so subject and sender are fetched from the mailbox
service at the moment of the report and are never stored. Without it the
stage `shadow` could not be reviewed.

## 9. State

One SQLite file per agent, with numbered migrations that are never changed
once released.

| Table | Holds |
|---|---|
| `cursor` | the feed state token |
| `messages` | message id, account id, state, attempts, next attempt |
| `steps` | message, step, prompt version, model, result, tokens, duration |
| `actions` | message, action, what it was before, when, stage |
| `open_items` | for agents with deadlines: message, thread, due, closed and why |

What is stored: ids, decisions, evidence quotes, counts and times. What is
not: the text of a mail, its subject, its sender or an attachment. A message
is fetched again by its id when it is needed.

One exception, off by default: `MAILBOX_AGENT_PROMPT_RETENTION_DAYS` above
zero keeps the full request and answer of each model call for that many
days, for finding an error. They are deleted after it.

There is no session store. No step carries a conversation from one call to
the next. Context a decision needs, such as the thread, is fetched fresh.

## 10. Agents

### 10.1 `invoices`

**Question:** is this incoming message an invoice, and is its sender a
supplier with a folder of its own?

| | |
|---|---|
| Triggers | `message.created` in the inbox |
| Baseline | a sender on the supplier list, a PDF or XML attachment, invoice words in subject and attachment names |
| Model | label `invoice` or `other`, and for `other` the near miss it is: reminder, quotation, order confirmation, payment receipt, none |
| Supplier | from the sender and the supplier list, never from the model |
| Actions | `add_keyword`, `move_to_folder` |

**What counts (decided 2026-11-17).** An invoice is a message that carries
an invoice a supplier sent, or that tells one is ready to be fetched. The
second kind matters: many suppliers send a notice and no file.

**One folder per supplier, under one parent (decided 2026-11-17).** The
parent is named in `MAILBOX_AGENT_INVOICES_FOLDER`. The supplier list is a
file named in `MAILBOX_AGENT_INVOICES_SUPPLIERS_FILE`. It is not versioned,
an example of it is. An entry names a supplier, the sender addresses or
domains it writes from, and its folder under the parent. Every folder must
exist. The agent creates none.

| The message is | What happens |
|---|---|
| an invoice from a listed supplier | the keyword, and in stage `full` a move to the supplier's folder |
| an invoice from a sender not listed | the keyword. It stays in the inbox, and `report` names the sender as a candidate for the list |
| not an invoice | nothing |

The folder a message goes to follows from its sender and the list alone.
The model decides only whether the message is an invoice, so the content of
a mail cannot choose where it is moved.

Recognising an electronic invoice by its embedded data needs the attachment
read and is not part of the first version.

### 10.2 `awaiting_reply`

**Question:** does this sent message expect an answer, and has one come?

| | |
|---|---|
| Triggers | `message.sent`, `message.created`, `message.updated`, the tick |
| Baseline | a question mark or a request phrase in the last paragraph written |
| Model | whether the message expects a reply, yes or no |
| Actions | `add_keyword`, `remove_keyword`, both on the sent message |
| Deadline | `MAILBOX_AGENT_REPLY_DAYS` working days, 3 by default |

A sent message that expects a reply becomes an open item. It closes when:

- a later message from another sender appears in its thread, automatic
  answers not counted **(that the service exposes what marks an automatic
  answer is to verify)**,
- a person takes the keyword off, which the agent learns from the feed where
  the provider reports flag changes,
- the sender writes again in the same thread. That restarts the deadline and
  does not count as a reply.

An item past its deadline gets the keyword. The message stays where it is.

Known misses, to be counted in the evaluation rather than argued away: an
answer that comes as a new mail outside the thread, an answer by telephone,
and several recipients of whom one answers.

### 10.3 `inquiries`

**Question:** is this a project inquiry, and what does it say?

| | |
|---|---|
| Triggers | `message.created` in the inbox |
| Baseline | sender domains and phrases known from the gold set, patterns for dates and rates |
| Model | label `inquiry` or `other`, then the fields below |
| Actions | `add_keyword` |

Fields, each optional: role, start, end, duration, workload, location,
remote share, contract form, intermediary, end client, rate, required
skills, desired skills, deadline to apply.

Every field comes with a quote from the message (section 11). What a
message does not say stays empty.

Recognising an inquiry seen before, and anything that writes a reply, come
later (section 16).

## 11. Safety

Three locks, in three places, none of which the model can reach:

| Where | What it stops |
|---|---|
| The mailbox service | sending, deleting for good, drafts: the agent's user has no right to them |
| The model gateway | a model outside the agent's list, spending past its budget |
| The runtime | every action the agent did not declare, the trash and folder creation among them |

Further rules:

- **Mail content is data.** The request names it as the content of a mail
  and never as an instruction, and the step that reads it has no tools.
- **A value needs evidence.** A label and every extracted field carry a
  quote. The code looks for the quote in the text the model was given, with
  whitespace made uniform. A field whose quote is not found is dropped, and
  a label whose quote is not found is recorded and not acted on. A
  confidence the model reports about itself is not used.
- **Reversible only.** Every action records what was there before.
- **Secrets never travel.** The service token and the gateway key are never
  logged, never stored in the state file and redacted from error text.
- **Nothing of a mail in a log line.** A line names ids, states, counts and
  durations.

## 12. Evaluation

A **gold set** is mail a person labelled by hand: for a classifying agent
the right label, for an extracting agent the right value of each field. The
agent runs over it and the scoring counts where it agrees.

- **Format:** one JSON object per line: account id, message id, expected
  label, expected fields. The mail itself is fetched by id at run time.
- **Where it lives:** under `data/`, never versioned, because it points at
  real mail. The repository holds the format, the scoring and a small set of
  invented messages the tests use.
- **What is reported:** for a label, precision and recall. For each field,
  how often the value is right, wrong, missing or invented. Tokens and time
  per message.
- **Always against the baseline.** Every report shows the rules alone
  beside the model, so what the model adds is a number.
- **A run is manual.** `benethos-mailbox-agent eval --agent <name>` needs a
  mailbox service and a model, which a public CI has not. It is a live
  check, outside `testpaths`, and never a gate.
- **A report is versioned.** Each run writes one file naming the agent
  version, prompt version, model and date, with numbers only and no content
  of any mail. A change to a prompt or a model is merged with its report.

Size to start with: about 200 labelled messages for `invoices`, about 150
sent messages for `awaiting_reply`, 80 to 150 inquiries for `inquiries`.

## 13. Configuration

All settings carry the prefix `MAILBOX_AGENT_` and come from the environment
or from one `.env` file, read with pydantic-settings (decided 2026-11-17).
A process runs one agent, so one environment describes one agent. A secret
may be given as a file with the suffix `_FILE`.

| Setting | Meaning |
|---|---|
| `SERVICE_URL`, `SERVICE_TOKEN` | the mailbox service and this agent's token |
| `GATEWAY_URL`, `GATEWAY_KEY` | the model gateway and this agent's key |
| `GATEWAY_TIMEOUT_SECONDS` | how long one model call may take, `120` when unset |
| `MODEL` | the alias the gateway resolves |
| `ACCOUNTS` | the accounts to work on, comma separated, all the user may read when unset |
| `STAGE` | `shadow`, `keyword` or `full`, `shadow` when unset |
| `KEYWORD` | the keyword the agent sets, the agent's own default when unset |
| `POLL_SECONDS`, `TICK_SECONDS` | how often the feed is read and the clock asked |
| `MAX_ATTEMPTS` | refused answers before a message is `failed`, `5` when unset |
| `BACKOFF_CEILING_SECONDS` | the longest wait between two attempts, `3600` when unset |
| `BACKFILL_DAYS` | the window `backfill` runs over after an expired feed state, `7` when unset |
| `DATA_DIR` | where the state file lives |
| `PROMPT_RETENTION_DAYS` | section 9, `0` when unset |
| `METRICS_PORT` | section 14, `0` serves no endpoint |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING` or `ERROR`, `INFO` when unset |

`SERVICE_TOKEN_FILE` and `GATEWAY_KEY_FILE` name the file a secret is read
from. A secret given directly wins over its file.

Settings of one agent, such as `INVOICES_FOLDER`, `INVOICES_SUPPLIERS_FILE`,
`REPLY_DAYS` and `INQUIRIES_PATTERNS_FILE`, are named in its section. The
`.env` file is `config/benethos-mailbox-agent/.env` below the working
directory unless the command line names another.

## 14. Operation

- **Container:** non-root, read-only root file system, no capabilities, one
  volume for the state file. One Compose service per agent from the same
  image, `restart: unless-stopped`.
- **Health:** the check passes when the last complete pass of the loop is
  younger than a few poll intervals. A process that is alive and stuck is
  unhealthy.
- **Metrics:** an HTTP endpoint in the Prometheus text format, served with
  the `prometheus-client` package (decided 2026-11-17): messages per
  state, age of the oldest `pending` message, step failures by kind, answers
  the schema or the evidence check refused, model calls, tokens and duration.
- **Cost:** read at the gateway, per key.
- **Logs:** stderr, through `logbook/` only.

## 15. Testing

- The suite is offline. The mailbox service and the gateway are mocked with
  `httpx.MockTransport`. No test reaches a network, and none skips itself
  when a credential is missing.
- Coverage floor 80 %.
- `ruff`, `mypy`, `uv lock --check`.
- A test holds the layer order of section 4, and one holds the tables of
  this document to the code where they can be compared.
- Async tests run with pytest-asyncio.
- Live checks are scripts in `live/`, run by hand against a test account.
  The direction (2026-11-17): a mail server of our own in a local container,
  with an account made for the agents and filled with invented mail. How it
  is set up is settled with the first live check.

## 16. Roadmap

| Phase | Content |
|---|---|
| 0 | Package, CI, settings, contract, store with migrations |
| 1 | Runtime: feed, tick, steps, actions, health, metrics, with an agent that only counts |
| 2 | `invoices`: gold set, baseline, model, first report, then `keyword`, then `full` |
| 3 | `awaiting_reply` |
| 4 | `inquiries`: label, then fields |
| 5 | Recognising a repeated inquiry by embeddings, stored in the state file |
| 6 | Handing a message to an external agent server over HTTP, and reply drafts |
| 7 | A daily overview of what every agent did, read from the state files by a process of its own, with no model involved |

Ideas not scheduled: newsletters to a folder by the `List-Unsubscribe`
header, a keyword for mail that names a deadline, a mark for mail from
authorities.

## 17. Open questions

1. **How the daily overview reaches the owner.** A mail to the owner's own
   address, from a user that may send there and nowhere else, or a draft.
   Not decided, the overview is phase 7.
2. **The test setup for live checks.** Section 15 names the direction.
3. **Schema through the gateway.** Section 6, to verify with the first
   local model.
4. **Keywords per provider.** Section 5, to verify per account.
5. **Folder-narrowed grants and moves.** Section 5, to verify. It decides
   whether the grant of `invoices` can be narrowed to the inbox and the
   parent folder of section 10.1.
6. **Automatic answers.** Section 10.2, to verify.

Answered, all on 2026-11-17:

- **Licence.** MIT.
- **What `invoices` covers.** Section 10.1: invoices and invoice notices
  from suppliers, one folder per listed supplier, others marked only.
- **Order of the agents.** `invoices`, `awaiting_reply`, `inquiries`.
- **Metrics.** The `prometheus-client` package.
- **Settings.** pydantic-settings.
- **Sync or async.** asyncio.
- **A report command.** Yes, section 8.1.
