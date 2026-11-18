# Configuration

All settings carry the prefix `MAILBOX_AGENTS_` and come from the environment
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
| `POLL_SECONDS`, `TICK_SECONDS` | how often the feed is read and the clock asked, `60` and `900` when unset |
| `MAX_ATTEMPTS` | refused answers before a message is `failed`, `5` when unset |
| `BACKOFF_CEILING_SECONDS` | the longest wait between two attempts, `3600` when unset |
| `BACKFILL_DAYS` | the window `backfill` runs over after an expired feed state, `7` when unset |
| `DATA_DIR` | where the state file lives |
| `PROMPT_RETENTION_DAYS` | [state](state.md), `0` when unset |
| `METRICS_PORT` | [operation](operation.md), `0` serves no endpoint |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING` or `ERROR`, `INFO` when unset |

`SERVICE_TOKEN_FILE` and `GATEWAY_KEY_FILE` name the file a secret is read
from. A secret given directly wins over its file.

Settings of one agent, such as `INVOICES_FOLDERS`, `INVOICES_SUBFOLDER`,
`REPLY_DAYS`, `INQUIRIES_PATTERNS_FILE` and `SORTING_FILE`, are named in
the agent's spec under [agents/](agents/). The `.env` file is `config/benethos-mailbox-agents/.env` below the working
directory unless the command line names another.
