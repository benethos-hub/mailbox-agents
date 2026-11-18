# Architecture

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

## Modules

```
src/benethos_mailbox_agent/
  cli/            # the console script: worker, run, backfill, report, eval,
                  # status, paths, health, and the wiring of one session
  __main__.py     # enables `python -m benethos_mailbox_agent`
  errors.py       # the error hierarchy, and redact
  settings/       # settings resolution, secrets from files
  logbook/        # every line on stderr as an activity of its catalogue,
                  # and what a line may never carry (docs/LOGGING.md)
  contract/       # Agent (ABC), Action, Trigger, Limits, Requires, the
                  # Context an agent is handed with its protocols Model,
                  # Reader and Items, the registry of agents, prompt loading
  records/        # the models passed between layers: MessageRef, Decision,
                  # Evidence, StepResult, OpenItem, and what an agent sees of
                  # a mailbox: Event, MailMessage, Address, Attachment,
                  # FolderRef, Thread
  sources/
    mailbox.py    # the only module importing benethos_mailbox_client
  llm/
    gateway.py    # the only module that talks to the model gateway
    evidence.py   # whether a quote is in the mail the model was given
  store/          # SQLite: schema, migrations, one file per agent
  runtime/        # worker loop, feed reader, tick, step runner, the model
                  # calls of one message, open items over the state file,
                  # the read-only mailbox, action executor, readiness,
                  # health, metrics
  evaluation/     # the gold format, scoring per label and per field, report
  agents/
    <name>/       # one package per agent
      agent.py    # one Agent subclass, no side effects at import, always
      schema.py   # for an agent that asks a model: what it must answer
      baseline.py # for an agent that asks a model: the question by rules
      prompts/    # for an agent that asks a model: its system prompts as
                  # Markdown, each with a version
      ...         # modules of its own, such as invoices/suppliers.py,
                  # inquiries/patterns.py, awaiting_reply/text.py
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
config/           # .env.example and the example lists *.example.json
                  # versioned, .env local
data/             # state files and the gold set, never versioned
reports/          # evaluation reports, numbers only, versioned
```

## Design decisions

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
  agent did ([roadmap](roadmap.md)) reads the files without the agents knowing of it.
  Another process of the same user, that is: the command line sets the
  umask to 077, so a state file is readable by its owner only (decided
  2026-11-17).
