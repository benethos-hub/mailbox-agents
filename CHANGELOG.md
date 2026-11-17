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
- The agent `counting`, which counts what arrives and is sent and changes
  nothing, for checking a deployment end to end.
