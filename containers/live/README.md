# The live setup

A mail server, a mailbox service and a model gateway of their own, for the
live checks in `live/`. Nothing here reaches a real mailbox:
[Stalwart](https://stalw.art) holds one account made for the agents,
`agents@agents.test`, filled with invented mail, and the mailbox service is
the published image `ghcr.io/benethos-hub/benethos-mailbox-service`. The
gateway is [LiteLLM](https://docs.litellm.ai) in front of Claude and of
local models under [llama.cpp](https://github.com/ggml-org/llama.cpp). It
is a manual aid, never part of `uv run pytest`.

## Set it up

Needs Docker with compose, `openssl`, `curl` and `python3`, on Linux, macOS
or in WSL. From the repository:

```
sh containers/live/setup.sh
```

The script makes everything anew each time. It removes the volumes of an
earlier run, then, not in this order:

- makes a test CA and a certificate for `mail.agents.test`,
- starts Stalwart in its bootstrap mode, sets host name and domain
   without ACME and DKIM, restarts it out of that mode, installs the
  certificate and creates the account,
- appends the invented mail of `mail.py` over IMAP: invoices with and
  without a PDF, a receipt that carries its invoice, near misses (a
  reminder, a quotation, an order confirmation, a payment receipt), a
  project inquiry, a newsletter, sent mail that waits for a reply and some
  that does not, a reply and an automatic answer,
- makes the mailbox service's keys and administrator, signs in to its UI
   once for the first token, connects the account, and creates the user
   `agents` with `mail.read` and `mail.write` on it and that user's token,
- starts the gateway with a master key of its own, and a local model when
   the agents are to use one (below).

### Which model the agents use

| Situation | Model | Alias in `agent.env` |
|---|---|---|
| a Claude API key is there | Claude Haiku 5.5 | `mail-classifier` |
| no key, or `LIVE_LOCAL=gpu`, and NVIDIA's CDI spec on the host | local, on the graphics card | `mail-classifier-gpu` |
| no key and no CDI spec, or `LIVE_LOCAL=cpu` | local, on the CPU | `mail-classifier-cpu` |

The Claude API key goes into `secrets/anthropic_api_key` or the variable
`ANTHROPIC_API_KEY`. The script keeps the file across runs.

What it makes stays in `secrets/` beside it, never versioned:

| File | Holds |
|---|---|
| `agent.env` | the settings the agents and `live/smoke.py` read |
| `service-token` | the token of the user `agents` |
| `service-admin`, `stalwart-admin` | the administrators' passwords |
| `gateway.env` | the gateway's master key, the address of its database, and the Claude API key if any |
| `gateway-db.env` | the password of the gateway's database |
| `anthropic_api_key` | the Claude API key, when given |
| `master_key` | the service's master key, a test key readable by all |
| `tls/` | the test CA, and the mail server's certificate and key |

The script writes them readable by their owner only, except the CA
certificate and the service's master key, which a container reads as
another user. On a Windows drive mounted under WSL, the file system
keeps no Unix rights, and every file shows as readable by all.
Keep the checkout on the Linux file system where that matters.

## Local models

Two llama.cpp services serve the local models, each as a router that loads
one model at a time on its first request:

| Service | Profile | Image | Models in |
|---|---|---|---|
| `llama-gpu` | `gpu` | `server-cuda` | `llama/presets-gpu.ini` |
| `llama-cpu` | `cpu` | `server` | `llama/presets-cpu.ini` |

A preset section names a model and its options, the options of
`llama-server` without their dashes. The gateway reaches each model as
`gpu/<name>` or `cpu/<name>` (`litellm.yaml`). Neither service has a port
or a way out of the network `models`, which they share with the gateway
alone.

The files are fetched by a script into `models/`, which is not versioned
and survives a new setup. Each comes from a fixed revision of its
repository and is checked against the sha256 the script names:

```
sh containers/live/fetch-models.sh list        # the models it knows
sh containers/live/fetch-models.sh qwen3.5-9b  # one of them
sh containers/live/fetch-models.sh all
```

The graphics card needs the NVIDIA Container Toolkit on the host and its
CDI spec, which the service asks for as the device `nvidia.com/gpu=all`.
On Debian or Ubuntu, or in a WSL distribution of them, a script installs
both, as root and with the driver in place:

```
sudo sh containers/live/nvidia-toolkit.sh
```

It restarts neither Docker nor a container: Docker reads the spec when it
creates one. The service names the device rather than `gpus: all`, which
a Docker without the toolkit's runtime setting cannot resolve.

Start a service by hand with its profile:

```
docker compose -f containers/live/compose.yaml --profile gpu up -d llama-gpu
```

### Comparing models

`live/gold.py` writes the labels of the invented mail as gold files, and
`eval` runs an agent against them with any alias of the gateway:

```
uv run python live/gold.py
MAILBOX_AGENTS_MODEL=claude/haiku-5-5 uv run benethos-mailbox-agents \
    --env-file containers/live/secrets/agent.env \
    eval --agent invoices --gold containers/live/secrets/gold-invoices.jsonl \
    --reports containers/live/secrets/reports
```

The local models were measured with llama.cpp build 12464, an RTX 4070
with 12 GB and a 12th generation Core i9 with 24 threads: `invoices` and
`awaiting_reply` on 2026-11-17, `inquiries` with its prompt `v3` on
2026-11-18. Claude was measured on 2026-11-18 through the Claude API, its
seconds include the way over the internet. The labels agreed with the
gold set, out of 11 messages for `invoices` and `inquiries` and 3 for
`awaiting_reply`. The fields are the right values of `invoices` against
all it should have filled or did fill. The `invoices` column and the
fields are of its prompt `v1`, which still asked for the supplier. Prompt
`v4` was measured on 2026-11-18 with `mail-classifier` and
`mail-classifier-gpu` alone, 11 of 11 each, see
[docs/specs/agents/invoices.md](../../docs/specs/agents/invoices.md). The
test account has had a twelfth message for `invoices` and `inquiries`
since, a receipt that carries its invoice. The seconds are per message,
the first message of a run waiting for a local model to load:

| Model | Size | invoices | inquiries | awaiting_reply | Fields | Seconds, invoices / inquiries |
|---|---|---|---|---|---|---|
| `cpu/qwen3-4b-2507` | 2.5 GB | 10 | 11 | 3 | 5 of 9 | 4.0 / 8.9 |
| `cpu/qwen3.5-4b` | 2.7 GB | 11 | 11 | 3 | 6 of 9 | 4.5 / 11.8 |
| `cpu/gemma-4-e4b` | 5.0 GB | 11 | 11 | 3 | 6 of 9 | 4.9 / 13.5 |
| `cpu/qwen3.6-35b-a3b` | 22.1 GB | 11 | 10 | 3 | 6 of 7 | 4.7 / 22.6 |
| `gpu/ministral-3-8b` | 5.2 GB | 11 | 2 | 3 | 6 of 7 | 0.8 / 3.9 |
| `gpu/qwen3.5-9b` | 5.7 GB | 11 | 11 | 3 | 6 of 8 | 1.0 / 4.2 |
| `gpu/gemma-4-12b` | 7.0 GB | 11 | 11 | 3 | 6 of 7 | 1.4 / 6.0 |
| `gpu/qwen3.6-35b-a3b` | 22.1 GB | 11 | 10 | 3 | 6 of 7 | 1.7 / 11.0 |
| `claude/haiku-5-5` | hosted | 11 | 11 | 3 | 6 of 7 | 1.1 / 2.4 |
| `claude/opus-5-5` | hosted | 11 | 11 | 3 | 6 of 7 | 1.8 / 2.3 |

What decided:

- `ministral-3-8b` words its quotes anew, so the evidence check refuses
  nine answers of `inquiries` out of eleven.
- `gemma-4-e4b` named a supplier where the gold set had none, with
  prompt `v1` of `invoices`, which still filed mail by its supplier.
- On the card, `qwen3.5-9b` agrees on every label, and llama.cpp worked
  2.4 s on an inquiry with it, for about half the electricity of the
  largest model, `qwen3.6-35b-a3b`. That one took 4.1 s and fills the card,
  `--fit` keeps the rest of its experts in main memory. With the prompt
  `v3` of `inquiries` it gave one quote the mail does not hold, on the
  card and on the CPU alike, and the evidence check refused that answer.
  So `mail-classifier-gpu` is `qwen3.5-9b` since 2026-11-18. It was the
  35B model before `v3`.
- On the CPU, `qwen3.5-4b` agrees on every label of `inquiries` and
  `invoices`, in an eighth of the 35B model's memory. The 35B model stays
  at hand as `cpu/qwen3.6-35b-a3b`, for a server with 32 GB or more.
- Haiku and Opus agree on every label and field. Haiku answers as fast
  and costs a fortieth of Opus. So `mail-classifier` is Haiku.

### What a model costs

The gateway counts what each call cost, by the price per token set for
its alias in `litellm.yaml`, and its web interface shows the sum per key
and per model. For Claude the price is the list price of the Claude API
on 2026-11-18. For a local model it is an estimate of the electricity the
call burns, without the hardware:

- the time llama.cpp spent reading and writing tokens in the runs of
  `inquiries` above, from its own timing lines,
- times the power: on the card what `nvidia-smi` read each second while
  the card worked, plus 100 W for the rest of the machine, and 220 W for
  the CPU at full load where it computes, the CPU models and the 35B
  model's experts,
- at $0.40 a kWh, about 0.35 euro.

A local model reads its system prompt from the cache of llama.cpp after
the first message, so most of what it is counted as reading costs next to
nothing. The tokens of Claude and of a local model are not the same
size: Claude counted about 3,800 tokens for an inquiry, the local models
about 570.

| Model | Dollars per million tokens in | Dollars per million tokens out | Dollars per 1,000 inquiries |
|---|---|---|---|
| `cpu/qwen3-4b-2507` | 0.042 | 1.30 | 0.19 |
| `cpu/qwen3.5-4b` | 0.044 | 1.40 | 0.27 |
| `cpu/gemma-4-e4b` | 0.029 | 1.50 | 0.30 |
| `cpu/qwen3.6-35b-a3b` | 0.057 | 1.40 | 0.26 |
| `gpu/ministral-3-8b` | 0.002 | 0.39 | 0.06 |
| `gpu/qwen3.5-9b` | 0.007 | 0.40 | 0.07 |
| `gpu/gemma-4-12b` | 0.010 | 0.50 | 0.10 |
| `gpu/qwen3.6-35b-a3b` | 0.036 | 0.64 | 0.13 |
| `claude/haiku-5-5` | 0.10 | 0.50 | 0.50 |
| `claude/opus-5-5` | 4.00 | 20.00 | 18.64 |

A dozen invented messages show a model that fails outright, not which of
the good ones is best. That takes the evaluation on real mail of
[docs/specs/evaluation.md](../../docs/specs/evaluation.md).

## Ports

On `127.0.0.1` only:

| Port | What |
|---|---|
| 38081 | the mailbox service, its API and UI |
| 38080 | Stalwart's HTTP: JMAP and its management |
| 38993 | Stalwart's IMAP over TLS |
| 38465 | Stalwart's SMTP submission over TLS |
| 38400 | the model gateway, with the master key in `secrets/gateway.env`, and its web interface at `/ui/`: the user `admin`, the master key its password |

The gateway keeps its keys and what each spent in a database of its
own, `gateway-db`, which the web interface needs to sign in. It keeps no
prompt and no answer.

## Use it

```
uv run python live/smoke.py
uv run python live/sorting.py
uv run python live/invoices.py
uv run benethos-mailbox-agents --env-file containers/live/secrets/agent.env status
uv run benethos-mailbox-agents --env-file containers/live/secrets/agent.env run --agent counting
```

`agent.env` sets the stage `shadow`. An agent that may change a message
does so only in this account.

`live/sorting.py` writes to the account: it runs `sorting` with
`sorting.json` beside this file in `shadow`, then in `full`, and puts every
message back where it was. The folders it made, `Providers` and two below
it, stay, as no agent may delete a folder. `setup.sh` makes the account
anew without them. `live/invoices.py` runs `invoices` in `shadow` beside
`sorting` in `full`, in both orders, and puts the mail back. It asks the
model of `agent.env`, one call per message and order.

## Take it down

```
docker compose -f containers/live/compose.yaml --profile gpu --profile cpu down --volumes
```
