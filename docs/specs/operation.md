# Operation

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
  2026-11-17), one registry per process: `mailbox_agents_info` with agent,
  version and stage, `mailbox_agents_messages` per state,
  `mailbox_agents_oldest_pending_age_seconds`,
  `mailbox_agents_last_pass_timestamp_seconds`,
  `mailbox_agents_step_failures_total` by kind,
  `mailbox_agents_answers_refused_total` by reason (schema, request,
  evidence), `mailbox_agents_model_calls_total`,
  `mailbox_agents_model_tokens_total` by direction,
  `mailbox_agents_model_call_seconds` and `mailbox_agents_actions_total` by
  action and whether it was carried out.
- **Cost:** read at the gateway, per key.
- **Logs:** stderr, through `logbook/` only. [docs/LOGGING.md](docs/LOGGING.md)
  holds the levels, the shape of a line, what never goes into one and the
  catalogue of every activity. A line is one sentence, such as
  `invoices set message m1 to done`, after an ISO time with the offset,
  the level and the source `activity.<area>.<name>`.
