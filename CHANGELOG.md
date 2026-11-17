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
- The agent `counting`, which counts what arrives and is sent and changes
  nothing, for checking a deployment end to end.
