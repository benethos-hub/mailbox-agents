# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

Every user-facing change gets an entry under `[Unreleased]` in the same
commit that makes the change. Design decisions live in
[docs/CONCEPT.md](docs/CONCEPT.md).

## [Unreleased]

### Added

- The README shows the architecture as a diagram, light and dark: the
  mailbox service, the four steps of a message in an agent, and the model
  gateway. `assets/build.py --diagram` renders it from its page.

### Changed

- The package page on PyPI links the repository, the README, the issues
  and the changelog. The package states its licence as the expression
  `MIT` with its licence file, and its description, keywords and
  classifiers say what it is: self-hosted agents for a mailbox, typed and
  asyncio.
- An answer of `inquiries` holds at most 2000 characters in all its
  quotes and values, beside the 300 of each. A longer one is refused as
  not fitting the schema.
- The contract refuses an agent whose `default_keyword` is not lower
  case letters, digits and dashes, the form `MAILBOX_AGENTS_KEYWORD` must
  have. Before, it checked a shorter list of characters only.
- `counting` needs `mail.read` alone in the mailbox service, as the
  production README and the rights table now say. It was named with
  `mail.write` like the other agents before.

### Fixed

- An answer of the model whose quote holds the JSON escape of a lone
  surrogate is refused and tried again like any other answer outside the
  schema. Before, storing it ended the worker after the paid call, and the
  message ended it again after each restart.
- A lone surrogate in what the mailbox service answers, in a subject, a
  text, a name, an address, a file name or a folder, becomes U+FFFD.
  Before, it ended the worker when the message was sent to the gateway.
- A message whose subject, text or thread the mailbox service answers as
  another type is refused and tried again. Before, the worker ended with a
  traceback that quoted the value.
- JSON nested too deep for the parser, from the gateway or the mailbox
  service, is a refused answer or an upstream away. Before, its
  `RecursionError` ended the worker.
- A token count of the gateway beyond what SQLite stores is capped.
  Before, storing the step ended the worker after the paid call.
- A body of the gateway that cannot be decoded, such as one that says
  gzip and is none, is a refused answer. Before, it ended the worker.
- `invoices` and `inquiries` cut the sender's address at 320 characters
  for the model, as they cut the name. `sorting` matches no rule against
  a longer address, where a pattern of several `*` held up the worker.
- The error line a command ends with writes a control or direction
  character escaped, as `status` and `report` do. Before, a code the
  mailbox service answered reached the terminal raw.
- A lone surrogate in a line of the log, of `status` or of `report` is
  written as its escape. Before, writing it to a terminal raised an
  error.

## [0.1.0] - 2026-11-19

The first release. Nothing was released before it, so each entry says
what the release holds, not how it came about.

### Added

#### The command line

- The console script `benethos-mailbox-agents` with the commands `worker`,
  `run`, `backfill`, `status`, `paths`, `report`, `eval` and `health`, and
  `--env-file`. An error to correct ends with exit code 2, a mailbox
  service or gateway that is away or a state file that cannot be read
  with 1, each in one line.
- The agents work only against the versions of the mailbox service they
  were tested against: 0.8 from 0.8.0 in this release. The worker asks the
  service for its version before every pass and every backfill. One
  outside the tested lines ends `worker`, `run` and `backfill` with exit
  code 2 before anything is read or changed, in every stage. `status`
  names the version of the service and whether it is tested.
  `docs/COMPATIBILITY.md` lists which releases of the service each
  release works with.
- `worker` runs one agent, pass after pass, and `run` one pass.
  `backfill` takes up the messages of the last days anew, those of the
  inbox, of sent mail and of the folders the agent looks in besides, in
  every account its user is granted unless `MAILBOX_AGENTS_ACCOUNTS` names
  some. It ends with exit code 1 when the gateway is away, after asking
  it once.
- `status`: for each agent whether it is ready and which setting it
  misses, per account the folders that matter to it and each folder it
  expects that is missing or there in another case only, its counts and
  its last progress. An account whose folders are refused and a state file
  that cannot be read get a line of their own, the rest is still listed.
  It warns when `MAILBOX_AGENTS_KEYWORD` is set for every agent of the
  settings. Every line is written escaped.
- `report`: what an agent decided and did, or in `shadow` would have done,
  with subject and sender fetched at the moment of the report. A control
  character, a line separator or a mark of direction from a mail or a
  model is written as its escape.
- `eval`: an agent over a gold set of labelled mail, the model beside the
  rules, precision and recall per label, each field right, wrong, missing,
  invented or rightly empty, and a report file of numbers only. A report
  names only the labels and fields the agent declares as its own. Any
  other, such as the name of a group of `sorting`, becomes `label-<n>` or
  `field-<n>`.
- `health`: exit code 0 while the loop makes progress, 1 when it does not,
  also before the state file exists. Metrics in the Prometheus text format
  on `MAILBOX_AGENTS_METRICS_PORT` while `worker` runs, named
  `mailbox_agents_*`.

#### The agents

Each sets a keyword of its own, of the form `agent-<word>`.

- `invoices`, version 5 with the prompt `v4`: marks invoices with
  `agent-invoice`, notices that an invoice waits at the supplier, a
  receipt that carries its invoice and a credit note included. It looks in
  the inbox and in the folders `MAILBOX_AGENTS_INVOICES_FOLDERS` names,
  `Parent/*` for the folders directly below one and `*` for every folder at
  the top without a role. It moves an invoice into the subfolder
  `MAILBOX_AGENTS_INVOICES_SUBFOLDER` names below the folder it lies in,
  such as `{folder}/Rechnungen`, made when missing, and never looks in that
  subfolder. An invoice in the inbox is marked and stays, or moves to the
  folder `MAILBOX_AGENTS_INVOICES_INBOX_FOLDER` names. That folder is an
  end station: looked in when the folders setting takes it in, an invoice
  there is marked and stays, and nothing is made below it. A message that
  carries the keyword and that the state file does not know is skipped
  before the rules and the model, until the keyword is taken off. `report`
  names the senders of invoices marked and not moved, as candidates for a
  group of `sorting`.
- `awaiting_reply`: opens an item for each sent message the model finds
  asking for an answer, unless its thread already holds a later answer. It
  closes the item on a reply in its thread, when the keyword is taken off
  or the message is deleted, and sets `agent-awaiting-reply` on the sent
  message after `MAILBOX_AGENTS_REPLY_DAYS` working days.
- `inquiries`, prompt `v3`: marks project inquiries with `agent-inquiry`
  and records what an inquiry says, role, start, end, duration, workload,
  location, remote share, contract form, intermediary, end client, rate,
  skills and deadline, each with a quote from the mail. Its rules read
  phrases, dates and rates, and the sender domains and phrases of
  `MAILBOX_AGENTS_INQUIRIES_PATTERNS_FILE`.
- `sorting`: moves mail of listed senders from the inbox into the folder of
  their group, makes a missing folder first, and sets `agent-sorted` with
  the move. No model. The groups are a JSON file in
  `MAILBOX_AGENTS_SORTING_FILE`. A sender rule is an address, a pattern of
  one domain or `*@*.domain` for its subdomains, and a group with
  `"hold": true` has its moves recorded only. A list that could never work
  is refused at the start, and a changed list decides each message anew.
- `counting`: counts what arrives and is sent and changes nothing, for
  checking a deployment end to end.

#### What keeps the agents safe

- Three stages, `shadow`, `keyword` and `full`, `shadow` when unset. An
  action the stage does not allow is recorded, once per message and stage.
- An agent acts only through the actions it declares: `add_keyword`,
  `remove_keyword`, `move_to_folder` and `create_folder`. A folder is made
  only where the agent's configuration names it, below one that exists. A
  message in or below the trash, junk or spam is left alone, and nothing
  moves there.
- An agent moves a message at most once. A folder the owner chose after it
  stands, logged as `actions.kept`. After a refused move the rest of the
  message's actions are not taken, and after one recorded only they are
  recorded only.
- A model that reads mail has no tools and answers in a fixed schema.
  Every label and field carries a quote, which the code looks up in the
  parts of the mail the model was given, word for word and by whole words,
  case and punctuation aside. A quote not found keeps the field or the
  decision from being acted on.
- What the model is given is cut: the text, and the subject and the
  sender's name at 300 characters each. `invoices` lists at most 20
  attachments within 1000 characters.
- The mailbox service and the gateway are reached over https, or over http
  to this machine, and over http to another machine only with
  `MAILBOX_AGENTS_SERVICE_ALLOW_HTTP` or
  `MAILBOX_AGENTS_GATEWAY_ALLOW_HTTP`. `MAILBOX_AGENTS_CA_FILE` names the
  certificates of an own CA in place of the public roots. Proxy variables
  and `SSL_CERT_FILE` are never read.
- `MAILBOX_AGENTS_KEYWORD` takes lower case letters, digits and dashes,
  and an agent whose keyword setting is another agent's keyword does not
  start. Keywords are compared without case.
- The service token and the gateway key are never logged and redacted
  from every error text, also when given as files through `*_FILE`.

#### The runtime

- The context an agent is handed holds the model, the read-only mailbox,
  its open items and the clock. Its settings it has as `self.settings`.
- One SQLite state file per agent, readable by its owner only, with its
  schema brought forward on opening and a second writer refused. A state
  file that cannot be read or written ends the worker.
- A gateway that is away holds up only the messages that need it. A worker
  that waits for an upstream waits in slices of one poll interval and
  stays healthy. A write the service refuses, or a message deleted in the
  meantime, is logged and does not stop the cursor. A garbled token count
  of the gateway counts no tokens.
- Every log line is one sentence in the past tense, such as
  `invoices set message m1 to done`, with the time in ISO 8601, the level
  and the source `benethos_mailbox_agents.activity.<area>.<name>`, and
  names ids, states, counts and codes, never anything of a mail.
  `docs/LOGGING.md` holds the catalogue of every line.

#### Operation and development

- The container image, one for all agents, and compose files for
  operation, one service per agent behind a profile of its name, and for
  development.
- `containers/live/`: a mail server of its own with a test account of
  invented mail, the published mailbox service in front of it, and a model
  gateway with Claude and local models. The agents get a key of the
  gateway for their aliases only, within a budget. The scripts in `live/`
  check the package against it and put the mail back.
- A pre-commit hook in `.githooks/` and a test over every tracked file,
  which refuse a credential, an address on a real domain, a path of a
  machine or an id of the mailbox service.
- The concept: `docs/CONCEPT.md` as its overview, and in `docs/concept/`
  one file per topic and one per agent.

[Unreleased]: https://github.com/benethos-hub/mailbox-agents/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/benethos-hub/mailbox-agents/releases/tag/v0.1.0
