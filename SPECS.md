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
  cli/            # the console script: worker, run, backfill, report, eval,
                  # status, paths, health, and the wiring of one session
  __main__.py     # enables `python -m benethos_mailbox_agent`
  errors.py       # the error hierarchy, and redact
  settings/       # settings resolution, secrets from files
  logbook/        # every line on stderr, and what a line may never carry
  contract/       # Agent (ABC), Action, Trigger, Limits, Requires
  records/        # the models passed between layers: MessageRef, Decision,
                  # Evidence, StepResult, and what an agent sees of a
                  # mailbox: Event, MailMessage, Address, FolderRef, Thread
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
  production/     # the published image, one service per agent, each
                  # behind a profile of its name
  development/    # built from the checkout, against the test account
  live/           # a mail server and a mailbox service of their own, with
                  # a test account of invented mail
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
  Another process of the same user, that is: the command line sets the
  umask to 077, so a state file is readable by its owner only (decided
  2026-11-17).

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
| The messages received since a day, for `backfill` | `list_all_messages`, once for the inbox and once for sent mail |

`sources/mailbox.py` offers these and nothing else: no send, no delete, no
trash, no folder creation. A move sets the message's folders to the one
target. A message without a text body is read with an empty text
**(to verify: whether the service always converts an HTML-only message)**.
`list_all_messages` without a folder lists the inbox alone (measured
2026-11-17 against 0.7.5), so a backfill names each folder role it wants.

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
  schema, and validated again with pydantic. The gateway hands the schema
  to a local backend, which builds a grammar from it: measured 2026-11-17
  with LiteLLM v1.108.10 in front of llama.cpp build 12464, a schema
  allowing one value only got that value against a prompt asking for prose.
- **No fallback** from one model to another inside the agent. A fallback at
  the gateway from a local to a hosted model must not be configured for a
  key that reads customer mail.
- **The schema is sent in its strict form:** every object closed, every
  property required, a value that may be empty typed with `null`. A quote
  or a free value longer than 300 characters does not fit, checked after
  parsing so the schema sent stays plain, and no answer copies the mail
  into the state file. No tools
  are sent, and no sampling setting: some hosted models refuse one, so the
  gateway sets it per model, such as a temperature of 0 for a local one.
- **A gateway that is away** (no connection, a timeout, a 5xx, a 408 or a
  429) leaves the message `pending`, and the loop waits twice as long
  before it tries again, up to `BACKOFF_CEILING_SECONDS`. Nothing counts
  against the message.
- **An answer outside the schema, or a request the gateway refuses** with
  another 4xx, counts as an attempt of that message. Its next attempt waits
  twice as long, and after `MAX_ATTEMPTS` it is `failed`.
- **A key or an alias the gateway refuses** (401, 403, 404) is a
  configuration error. The pass stops and nothing is decided.

## 7. The agent contract

Every agent package defines exactly one concrete `Agent` subclass in its
`agent.py`. A package under `agents/` without `agent.py` is not an agent. The class attributes are validated on instantiation.

| Attribute | Meaning |
|---|---|
| `name`, `version`, `description` | identity. `name` equals the package name |
| `triggers` | the feed events it wants, and whether it wants the tick |
| `actions` | the actions it may take, from the list below |
| `limits` | model calls per message and per day |
| `requires` | settings that must be present before it starts |
| `default_keyword` | the keyword it sets when `MAILBOX_AGENT_KEYWORD` is unset |
| `prompt_version` | the version of the prompt its model step runs under |

| Method | Meaning |
|---|---|
| `select(event)` | whether this event concerns the agent, and its route: `decide` or `observe`. Code only |
| `admit(message)` | after the fetch, whether the message is one for the agent, such as one in the inbox. Code only |
| `baseline(message)` | the question answered by rules |
| `decide(message, context)` | the question answered with the model, within the limits |
| `effect(decision, message, context)` | the actions that follow from a decision |
| `observe(message, context)` | for an event routed to `observe`: the actions it calls for, no model |
| `tick(now, context)` | for agents with deadlines: what is due |
| `prepare()` | reads what the agent needs beyond its settings, such as a list in a file |
| `summarize(decided)` | for `report`: lines about the messages shown, given as sender and decision |

An event routed to `decide` makes the message `pending` and runs the steps
of section 8 once per message, prompt version and model. An event routed to
`observe` is one that may come many times for one message, such as an
update of its flags. It is fetched and handed to `observe` at once.

The `context` is all an agent reaches while it works: the model, as one call
with a schema that the runtime counts, records and keeps the content of for
the evidence check, the mailbox read-only, and its open items. An agent never
holds the mailbox client, the gateway client or the state file.

The actions that exist:

| Action | Reversible by |
|---|---|
| `add_keyword` | `remove_keyword` |
| `remove_keyword` | `add_keyword` |
| `move_to_folder` | a move back, the previous folder is recorded |

An agent declares which of them it uses, and the runtime carries out no
other. A new action is added here first, with how it is taken back.

The runtime carries out an action only on these terms: it is declared, a
keyword is the agent's own, a move goes into a folder that exists and is
neither the trash or junk nor below them, the message itself is not in
the trash or junk, and the account is one the agent works on. An
action whose result is already there is not taken again. What the stage
does not allow is recorded as what would have been done.

`status` reports for each agent whether it is ready and which required
setting is missing, without starting it.

## 8. Runtime

One loop per process:

1. Read the feed from the stored cursor. On the first pass, start from the
   state of now. On `410` take a new state and run `backfill` over
   `BACKFILL_DAYS`.
2. For each event the agent routes to `decide`, record the message as
   `pending`. Hand each one routed to `observe` to the agent at once.
3. For each `pending` message whose next attempt has come, at most 50 a
   pass, run the steps: fetch, baseline, model, check, effect. Each step
   writes its result before the next begins.
4. On the tick, ask the agent what is due and run the effects.
5. Store the cursor and the time of the pass, then sleep `POLL_SECONDS`.

A mailbox service or gateway that is away while the feed is read stops the
pass before the cursor moves. One that is away while pending messages run
leaves them `pending`, the cursor moves, and the next pass waits twice as
long as the last, up to `BACKOFF_CEILING_SECONDS`.

Message states: `pending`, `skipped` (not admitted, or gone from the
mailbox), `decided` (recorded and not acted on, such as a label whose quote
was not found), `done` (its effect carried out, in whatever stage),
`failed` (given up after `MAX_ATTEMPTS`, or more model calls asked for
than the limit per message allows).

The steps of one message: fetch, `admit`, baseline, decision, effect. The
baseline is stored once per agent version. The decision, with the model
calls it made and its evidence checked, is stored once per prompt version
and model alias. A message that reached its daily limit of model calls
waits for the next day.

Rules:

- **Idempotent steps.** A step whose result is stored for the same message,
  prompt version and model is not run again. A repeated feed entry is
  harmless.
- **The cursor moves last.** A crash repeats work, it does not skip mail.
- **One writer.** A process is the only writer of its state file. It holds
  an exclusive lock on `<agent>.db.lock` beside it while the file is open,
  so `run` or `backfill` beside a running `worker` is refused. Readers
  such as `status` and `report` stay free (decided 2026-11-17).
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

### 8.1 Commands

| Command | What it does |
|---|---|
| `worker --agent <name>` | runs one agent pass after pass until SIGTERM or SIGINT |
| `run --agent <name>` | one pass, then the counts per state |
| `backfill --agent <name> [--days N]` | takes the messages of the last days up anew and runs them |
| `report --agent <name> [--limit N] [--state S] [--offline]` | section 8.2 |
| `eval --agent <name> --gold <file> [--reports DIR]` | section 12 |
| `health --agent <name>` | exit 0 while the loop makes progress, section 14 |
| `status` | for each agent whether it is ready, which setting it misses, its counts and its last pass |
| `paths` | the settings file, the data folder and each state file |

`--env-file` names the settings file for every command. An error to
correct ends with exit code 2, an upstream that is away with 1. `status`
and `paths` start no agent and change nothing.

### 8.2 Report

`benethos-mailbox-agent report --agent <name>` shows what an agent decided
and did, or in `shadow` would have done: per message the subject and sender,
the decision, the evidence and the action (decided 2026-11-17). The state
file holds ids only, so subject and sender are fetched from the mailbox
service at the moment of the report and are never stored. Without it the
stage `shadow` could not be reviewed.

The report lists the newest messages first, 50 unless `--limit` says
otherwise, and with `--state` those in one state. Per message it prints
sender and subject, the decision with its source, model, fields and
details, each quote and whether it was found, the label of the baseline,
and each action with its stage and whether it was carried out or would
have been. It ends with what the agent has to say about the messages shown: for
`invoices`, the senders of invoices no supplier was found for, with how many
each sent, as candidates for the supplier list. It opens the state file
read-only, so it runs beside the agent.
`--offline` reads the state file alone, without subject and sender. What
it prints goes to stdout for the person who asked and never to the log.

## 9. State

One SQLite file per agent, with numbered migrations that are never changed
once released.

| Table | Holds |
|---|---|
| `cursor` | the feed state token |
| `passes` | when the last complete pass of the loop finished, for the health check |
| `messages` | message id, account id, state, attempts, next attempt |
| `steps` | message, step, prompt version, model alias and the model reported, result, tokens, duration |
| `actions` | message, action, what it was before, when, stage, whether it was carried out |
| `open_items` | for agents with deadlines: message, thread, due, whether the keyword is on the message, the stage its keyword was recorded in without being set, closed and why |
| `calls` | the full request and answer of a model call, only while `PROMPT_RETENTION_DAYS` keeps them |

The schema version is the file's `user_version`. A reader opens the file
read-only and refuses one newer than it knows.

What is stored: ids, decisions, evidence quotes, counts and times. What is
not: the text of a mail, its subject, its sender or an attachment. A message
is fetched again by its id when it is needed.

One exception, off by default: `MAILBOX_AGENT_PROMPT_RETENTION_DAYS` above
zero keeps the full request and answer of each model call for that many
days, for finding an error. They are deleted after it.

There is no session store. No step carries a conversation from one call to
the next. Context a decision needs, such as the thread, is fetched fresh.

## 10. Agents

### 10.0 `counting`

Counts every message created or sent, asks no model and declares no
action. Each ends `done` with the label `counted`. It checks a deployment
end to end, feed, state file, steps, report and health, before any agent
may change a message, and the runtime's tests run on it.

### 10.1 `invoices`

**Question:** is this incoming message an invoice, and is its sender a
supplier with a folder of its own?

| | |
|---|---|
| Triggers | `message.created` in the inbox |
| Baseline | a sender on the supplier list, a PDF or XML attachment, invoice words in subject and attachment names |
| Model | label `invoice` or `other`, for `other` the near miss it is: reminder, quotation, order confirmation, payment receipt, none, and for an invoice a supplier of the list or none |
| Supplier | a sender rule of the list first, the model's choice from the list only when no rule matches (decided 2026-11-17) |
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

The list is JSON (decided 2026-11-17), read by the file's suffix so another
format is one reader more. `suppliers.example.json` shows it:

```json
{"suppliers": [
  {"name": "CloudHost", "folder": "CloudHost",
   "senders": ["billing@cloudhost.example", "cloudhost.example"]},
  {"name": "Telco", "folder": "Telco",
   "senders": ["rechnung@telco.example", "mailbox*@telco.example"]}
]}
```

A sender is an address, a pattern with `*` for a part that changes, or a
domain, which covers its subdomains too. Case is ignored. The most specific
rule wins: an address before a pattern before a domain. Two suppliers whose
rules of the same kind both match leave the sender unmatched. Names and
folders are unique, a sender rule belongs to one supplier, and a folder is
names between `/`, none empty, `.` or `..`. A wrong list stops the agent at
its start and `status` names what is wrong.

From is not authenticated, and a domain rule covers every address and
subdomain of it. So only an address or a pattern rule moves an invoice
into a supplier's folder. A domain rule and the model's choice mark only
(decided 2026-11-17).

The sender rule is applied again when the agent acts, against the list
as it is then. A supplier added to the list reaches an invoice decided
before once `backfill --again` takes it up, without a new model call.
The decision keeps who chose the supplier at the time (decided
2026-11-17).

| The message is | What happens |
|---|---|
| an invoice from a listed supplier, by an address or pattern rule | the keyword, and in stage `full` a move to the supplier's folder |
| an invoice from a listed supplier, by a domain rule or the model's choice | the keyword. It stays in the inbox |
| an invoice from a sender not listed | the keyword. It stays in the inbox, and `report` names the sender as a candidate for the list |
| not an invoice | nothing |

**The supplier (decided 2026-11-17).** When a sender rule of the list
matches, it decides the supplier and the model cannot overrule it: what the
model named instead is recorded as `model_supplier` and not used. When no
rule matches, the model may name a supplier of the list, as an enum in the
schema, with a quote that the code finds in the mail and that names the
supplier or a domain of its sender rules, case aside (decided
2026-11-17). Without that quote the supplier is dropped, its name kept as
`model_supplier`, and the invoice gets the keyword only. The
decision records the source of its supplier as `supplier_source`: `rule`,
`model` or `none`, and `report` and the evaluation tell them apart. So the
content of a mail can at worst give an invoice of an unlisted sender the
name of a listed supplier. It moves nothing, since only an address or a
pattern rule moves.

The prompt is `prompts/system.v1.md`, version `v1`. The model is given the
sender, the subject, the names and types of the attachments and the first
6000 characters of the text.

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
| Deadline | `MAILBOX_AGENT_REPLY_DAYS` working days, Monday to Friday, 3 by default (decided 2026-11-17, public holidays kept as a later option) |

A sent message that expects a reply becomes an open item. It closes when:

- a later message from another sender appears in its thread, automatic
  answers not counted. The service exposes no header, so an automatic
  answer is told by a sender such as `noreply` or `mailer-daemon` and a
  subject such as "Automatische Antwort" or "Out of Office" (decided
  2026-11-17),
- a person takes the keyword off, which the agent learns from the feed where
  the provider reports flag changes (`message.updated`, routed to
  `observe`). Its own keyword set or taken off closes nothing,
- the sender writes again in the same thread. That restarts the deadline and
  does not count as a reply: when the new message expects a reply itself,
  the earlier item closes as `followed_up` and the new one opens, otherwise
  the earlier item starts again from the new message.

A sent message whose thread already holds a later answer from someone
else opens no item. So a reply taken up before the message it answers,
by a backfill or a backoff, is not missed.

An item past its deadline gets the keyword on the tick. The message stays
where it is. The item counts the keyword as set only once it is on the
message, so in `shadow` a star or another flag closes nothing. A stage
that does not allow the keyword records it once, and a later stage that
does sets it. A keyword the service refused is offered again on the next
tick. The deadline counts from the date of the sent message, and a
date on a weekend counts from the Monday after.

The model is given the recipients, the subject and the text the sender
wrote, without what it quotes, the last 4000 characters of it. The prompt is
`prompts/system.v1.md`, version `v1`. A received message asks no model:
what it closes is a rule. The agent works on messages in sent mail, and on
messages in the inbox that belong to a thread.

Known misses, to be counted in the evaluation rather than argued away: an
answer that comes as a new mail outside the thread, an answer by telephone,
and several recipients of whom one answers.

### 10.3 `inquiries`

**Question:** is this a project inquiry, and what does it say?

| | |
|---|---|
| Triggers | `message.created` in the inbox |
| Baseline | phrases of an inquiry, patterns for dates and rates, and the sender domains and phrases of `INQUIRIES_PATTERNS_FILE` (JSON, optional) taken from the gold set |
| Model | label `inquiry` or `other`, then the fields below |
| Actions | `add_keyword` |

The label comes first (built 2026-11-17, prompt `system.v1.md`): an
inquiry gets the keyword `inquiry`. The rules call a message an inquiry
when its sender's domain is known, when it carries two phrases of an
inquiry, or one together with a date or a rate.

Fields, each optional: role, start, end, duration, workload, location,
remote share, contract form, intermediary, end client, rate, required
skills, desired skills, deadline to apply.

Every field comes with a quote from the message (section 11). What a
message does not say stays empty. The fields come in the same call as the
label (built 2026-11-17, prompt `system.v2.md`, version `v2`), each as a
value and a quote, in the schema as `role`, `start`, `end`, `duration`,
`workload`, `location`, `remote_share`, `contract_form`, `intermediary`,
`end_client`, `rate`, `required_skills`, `desired_skills` and `deadline`.
A message labelled `other` keeps none. The evaluation counts each field
right, wrong, missing, invented or rightly empty.

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
- **The sender is not proof.** From is not authenticated. A move that
  rests on the sender needs a rule naming the address or its pattern. A
  domain rule and the model's choice mark only (decided 2026-11-17).
- **A value needs evidence.** A label and every extracted field carry a
  quote. The code looks for the quote in the parts of the mail the model
  was given, each on its own: sender, subject, attachment names, text.
  The frame the code writes around them, such as `Subject:`, is no part.
  Both sides are brought to Unicode NFC and their whitespace made uniform:
  every run of spaces, tabs, line breaks and non-breaking spaces counts as
  one space. Nothing else is forgiven, not case and not a changed
  character. A quote of fewer than eight characters besides whitespace
  counts as not found (decided 2026-11-17). A value code found by a rule,
  such as the supplier of a sender rule, carries no quote, so nothing of
  the mail is stored for it. A field whose quote is not found is dropped, and
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

- **Format:** one JSON object per line: `account_id`, `message_id`, the
  expected `label`, the expected `fields` with `null` for a field the
  message does not fill, and an optional `note`. A line starting with `#`
  is a comment. A message named twice is refused. The mail itself is
  fetched by id at run time.
- **Where it lives:** under `data/`, never versioned, because it points at
  real mail. The repository holds the format, the scoring and a small set of
  invented messages the tests use.
- **What is reported:** for a label, precision and recall. For each field,
  how often the value is right, wrong, missing or invented, and how often
  it is rightly empty. Values are compared with case and whitespace made
  uniform. A decision the evidence check refused counts as no answer.
  Where an agent records who chose a field, as `<field>_source` in its
  details, the field is counted once more per source: for `invoices`, the
  supplier a rule chose apart from the supplier the model chose (decided
  2026-11-17). Tokens and time per message.
- **Always against the baseline.** Every report shows the rules alone
  beside the model, so what the model adds is a number.
- **A run is manual.** `benethos-mailbox-agent eval --agent <name>` needs a
  mailbox service and a model, which a public CI has not. It is a live
  check, outside `testpaths`, and never a gate.
- **A report is versioned.** Each run writes one file,
  `reports/<agent>/<date>-v<agent version>-<prompt version>-<model alias>.json`,
  naming the agent version, prompt version, model alias, the models the
  gateway reported and the date, with numbers only: no id, no label of a
  single message and no content of any mail. A change to a prompt or a
  model is merged with its report.
- **A run never touches the agent's state file.** It counts its model
  calls on a state file of its own and applies the evidence check as in
  operation. A gateway that is away ends the run.

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
| `SERVICE_ALLOW_HTTP` | allow http to another machine, as between two containers, `false` when unset |
| `GATEWAY_URL`, `GATEWAY_KEY` | the model gateway and this agent's key |
| `GATEWAY_ALLOW_HTTP` | allow http to another machine for the gateway, as between two containers, `false` when unset. https or http to this machine otherwise |
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

- **Container:** non-root (uid 10001), read-only root file system, no
  capabilities, `no-new-privileges`, one volume for the state file, the
  token and the key mounted as files and named in `*_FILE` settings, at
  most five log files of 10 MB. One Compose service per agent from the same
  image, each behind a profile of its own name, `restart: unless-stopped`,
  its health check `health --agent <name>`.
- **Health:** `health --agent <name>` exits 0 while the loop's last sign
  of progress, written to the state file after each message and at the end
  of each pass, is younger than three poll intervals plus one model call
  (`3 * POLL_SECONDS + GATEWAY_TIMEOUT_SECONDS`), and 1 otherwise. It reads
  the state file beside the running agent. A process that is alive and
  stuck is unhealthy. One whose gateway is away is not, its loop goes on.
- **Metrics:** an HTTP endpoint in the Prometheus text format on
  `METRICS_PORT`, served with the `prometheus-client` package (decided
  2026-11-17), one registry per process: `mailbox_agent_info` with agent,
  version and stage, `mailbox_agent_messages` per state,
  `mailbox_agent_oldest_pending_age_seconds`,
  `mailbox_agent_last_pass_timestamp_seconds`,
  `mailbox_agent_step_failures_total` by kind,
  `mailbox_agent_answers_refused_total` by reason (schema, request,
  evidence), `mailbox_agent_model_calls_total`,
  `mailbox_agent_model_tokens_total` by direction,
  `mailbox_agent_model_call_seconds` and `mailbox_agent_actions_total` by
  action and whether it was carried out.
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
  `containers/live/` holds it (decided 2026-11-17): a mail server of our
  own, Stalwart, in a local container, with an account made for the agents
  and filled with invented mail, and the published image of the mailbox
  service in front of it. `setup.sh` makes it in one run, and
  `live/smoke.py` reads it through the package without writing to it.
  The model gateway belongs to it (decided 2026-11-17): LiteLLM with Claude
  through the owner's API key, and local models under llama.cpp, one
  service on the graphics card and one on the CPU. `live/gold.py` turns
  the labels of the invented mail into gold files, so `eval` can compare
  models on them.

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
2. **Keywords per provider.** Section 5, to verify per account. Measured
   2026-11-17 for IMAP at Stalwart through the service 0.7.5: a keyword is
   set and taken off, and a move to another folder keeps the message's id
   and is taken back by a move to the folder before. Other providers are
   still to verify.
3. **Folder-narrowed grants and moves.** Section 5, to verify. It decides
   whether the grant of `invoices` can be narrowed to the inbox and the
   parent folder of section 10.1.
4. **Automatic answers.** The service exposes no header of a message
   (measured 2026-11-17 against 0.7.5), so `Auto-Submitted` cannot be read.
   `awaiting_reply` uses a heuristic on sender and subject (decided
   2026-11-17) and the evaluation counts what it misses.

Answered, all on 2026-11-17:

- **Licence.** MIT.
- **What `invoices` covers.** Section 10.1: invoices and invoice notices
  from suppliers, one folder per listed supplier, others marked only.
- **Order of the agents.** `invoices`, `awaiting_reply`, `inquiries`.
- **Metrics.** The `prometheus-client` package.
- **Settings.** pydantic-settings.
- **Sync or async.** asyncio.
- **A report command.** Yes, section 8.2.
- **The test setup for live checks.** `containers/live/`, section 15.
- **Schema through the gateway.** It reaches a local backend, section 6.
