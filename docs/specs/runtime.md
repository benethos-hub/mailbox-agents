# Runtime

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

Rollout stage, per agent, in `MAILBOX_AGENTS_STAGE`:

| Stage | What the agent does |
|---|---|
| `shadow` | records what it would do, changes nothing |
| `keyword` | sets its keyword, moves nothing |
| `full` | every action it declares |

A new agent starts in `shadow`, and so does one whose prompt or model
changed until the evaluation was run again.

## Commands

| Command | What it does |
|---|---|
| `worker --agent <name>` | runs one agent pass after pass until SIGTERM or SIGINT |
| `run --agent <name>` | one pass, then the counts per state |
| `backfill --agent <name> [--days N]` | takes the messages of the last days up anew and runs them: those of the inbox and of sent mail, and those of the folders the agent wants besides, such as the folders `invoices` looks in |
| `report --agent <name> [--limit N] [--state S] [--offline]` | [runtime](runtime.md) |
| `eval --agent <name> --gold <file> [--reports DIR]` | [evaluation](evaluation.md) |
| `health --agent <name>` | exit 0 while the loop makes progress, [operation](operation.md) |
| `status` | for each agent whether it is ready, which setting it misses, a folder it expects that is missing, its counts and its last pass |
| `paths` | the settings file, the data folder and each state file |

`--env-file` names the settings file for every command. An error to
correct ends with exit code 2, an upstream that is away with 1. `status`
and `paths` start no agent and change nothing.

## Report

`benethos-mailbox-agents report --agent <name>` shows what an agent decided
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
`invoices`, the senders of invoices it marked and did not move, with how
many each sent, as candidates for a group of `sorting`. For `sorting`, per group
how many messages were moved, recorded, held or not moved, the senders in
no group that wrote most often, and those two groups name alike. It opens the state file
read-only, so it runs beside the agent.
`--offline` reads the state file alone, without subject and sender. What
it prints goes to stdout for the person who asked and never to the log.
