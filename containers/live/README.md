# The live setup

A mail server and a mailbox service of their own, for the live checks in
`live/`. Nothing here reaches a real mailbox: [Stalwart](https://stalw.art)
holds one account made for the agents, `agents@agents.test`, filled with
invented mail, and the mailbox service is the published image
`ghcr.io/benethos-hub/benethos-mailbox-service`. It is a manual aid, never
part of `uv run pytest`.

## Set it up

Needs Docker with compose, `openssl` and `python3`, on Linux, macOS or in
WSL. From the repository:

```
sh containers/live/setup.sh
```

The script makes everything anew each time. It removes the volumes of an
earlier run, then:

1. makes a test CA and a certificate for `mail.agents.test`,
2. starts Stalwart in its bootstrap mode, sets host name and domain
   without ACME and DKIM, restarts it out of that mode, installs the
   certificate and creates the account,
3. appends the invented mail of `mail.py` over IMAP: invoices of listed
   and unlisted suppliers, an invoice notice without a file, near misses,
   sent mail that waits for a reply and some that does not, a reply, an
   automatic answer and a project inquiry,
4. makes the mailbox service's keys and administrator, signs in to its UI
   once for the first token, connects the account, and creates the user
   `agents` with `mail.read` and `mail.write` on it and that user's token.

What it makes stays in `secrets/` beside it, never versioned:

| File | Holds |
|---|---|
| `agent.env` | the settings the agents and `live/smoke.py` read |
| `service-token` | the token of the user `agents` |
| `service-admin`, `stalwart-admin` | the administrators' passwords |
| `master_key` | the service's master key, a test key readable by all |
| `tls/` | the test CA, and the mail server's certificate and key |

## Ports

On `127.0.0.1` only:

| Port | What |
|---|---|
| 38081 | the mailbox service, its API and UI |
| 38080 | Stalwart's HTTP: JMAP and its management |
| 38993 | Stalwart's IMAP over TLS |
| 38465 | Stalwart's SMTP submission over TLS |

## Use it

```
uv run python live/smoke.py
uv run benethos-mailbox-agent --env-file containers/live/secrets/agent.env status
uv run benethos-mailbox-agent --env-file containers/live/secrets/agent.env run --agent counting
```

`agent.env` sets the stage `shadow`. An agent that may change a message
does so only in this account.

## Take it down

```
docker compose -f containers/live/compose.yaml down --volumes
```
