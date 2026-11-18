# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

Every user-facing change gets an entry under `[Unreleased]` in the same
commit that makes the change. Design decisions live in
[SPECS.md](SPECS.md).

## [Unreleased]

### Added

- The console script `benethos-mailbox-agent` with the commands `worker`,
  `run`, `backfill`, `status` and `paths`, and `--env-file`.
- The command `report`: what an agent decided and did, or in `shadow` would
  have done, with subject and sender fetched at the moment of the report.
- The command `eval`: an agent over a gold set of labelled mail, the model
  beside the rules, precision and recall per label, each field right,
  wrong, missing or invented, and a report file of numbers only.
- The command `health`, and metrics in the Prometheus text format on
  `MAILBOX_AGENT_METRICS_PORT` while `worker` runs.
- The container image, one for every agent, and compose files for
  operation, one service per agent behind a profile of its name, and for
  development against a test account of invented mail.
- The agent `invoices`: marks invoices and invoice notices from suppliers
  with the keyword `invoice`, and moves those of a listed supplier into
  its folder under `MAILBOX_AGENT_INVOICES_FOLDER`. The supplier comes from
  a sender rule of the JSON list in `MAILBOX_AGENT_INVOICES_SUPPLIERS_FILE`,
  or from the model's choice among the listed suppliers when no rule
  matches.
- The agent `awaiting_reply`: opens an item for each sent message the
  model finds asking for an answer, closes it on a reply in its thread or
  when the keyword is taken off, and sets the keyword `awaiting-reply` on
  the sent message after `MAILBOX_AGENT_REPLY_DAYS` working days.
- The agent `inquiries`: marks project inquiries with the keyword
  `inquiry` and records what an inquiry says, role, start, end, duration,
  workload, location, remote share, contract form, intermediary, end
  client, rate, skills and deadline, each with a quote from the mail. Its rules read phrases, dates and rates, and the sender
  domains and phrases of `MAILBOX_AGENT_INQUIRIES_PATTERNS_FILE`.
- The agent `counting`, which counts what arrives and is sent and changes
  nothing, for checking a deployment end to end.
- The setting `MAILBOX_AGENT_GATEWAY_ALLOW_HTTP`, for a gateway reached
  over http between two containers.

### Changed

- The runtime leaves a message in the trash or junk alone, and moves no
  message into a folder below the trash or junk.
- The evidence check looks for a quote only in the parts of the mail, not
  in the frame around them, brings both sides to Unicode NFC, and finds no
  quote of fewer than eight characters besides whitespace.
- The agent `invoices` moves an invoice only when an address or a pattern
  rule of the supplier list matched its sender. A domain rule and the
  model's choice of a supplier set the keyword only.
- The agent `invoices` takes the model's choice of a supplier only with a
  quote that names the supplier or a domain of its sender rules.
- `report` writes a control character or line separator from a mail or a
  model as its escape, so a subject cannot move the cursor or fake a line.
- The gateway is reached over https, or over http to this machine. http to
  another machine needs `MAILBOX_AGENT_GATEWAY_ALLOW_HTTP`.
- A second writer of a state file, such as `run` beside a running
  `worker`, is refused with a message naming the agent.
- The state file and the secrets of the live setup are written readable
  by their owner only.

### Fixed

- A write the mailbox service refuses, such as a keyword the provider
  does not take, and a message an agent reads for its actions that was
  deleted since, no longer stop the agent before its cursor. The refusal
  is logged and the next messages are taken up.
- A worker that waits long for its gateway or mailbox service stays
  healthy: it waits in slices of one poll interval and writes its progress
  after each.
- A gateway that is away holds up only the messages that need it: the
  others are taken up, and the tick marks what is due, unless a message
  still due waits for another reason.
- `health` answers 1 for an agent without a state file yet, not 2, which
  Docker keeps for itself.
- `run` answers 1 whenever the pass found the mailbox service or the
  gateway away, also with a backoff ceiling below the poll interval.
- `awaiting_reply` counts its keyword as set only once it is on the
  message. In `shadow` a star on a sent message no longer closes its item,
  an item is recorded once per stage, a refused keyword is offered again,
  and after `shadow` the stage `keyword` sets it. The state file gets
  migration 2.
- `invoices` applies the sender rules again when it acts, so a supplier
  added to the list reaches an invoice decided before on
  `backfill --again`, without a new model call.
- `awaiting_reply` opens no item for a sent message whose thread already
  holds a later answer, as after a backfill that took up the reply first.
