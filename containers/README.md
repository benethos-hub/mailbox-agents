# Containers

The image, and the places it runs in, each in a folder of its own.

```
containers/
  images/
    mailbox-agents/
      Dockerfile          # the one image of every agent, built with the
                          # repository root as context
  production/             # in operation, the published image:
    compose.yaml          #   one service per agent, each behind a profile
    .env.example          #   the version and the metrics ports
    agents/<name>/        #   each agent's .env, and its lists
    README.md             #   how to set it up and update it
  development/            # for development, built from this checkout:
    compose.yaml          #   against the test account of live/
  live/                   # a mail server, a mailbox service and a model
                          # gateway of their own,
                          # with a test account of invented mail: the place
                          # the live checks and development run against
```

| Folder | For | Image | Ports | Compose project |
|---|---|---|---|---|
| `production/` | running the agents, without a clone of the repository | from the GitHub container registry, the version named in `.env` | metrics on 9470 to 9474, 127.0.0.1 | `benethos-mailbox-agents` |
| `development/` | trying a change in a container | built from this checkout | metrics on 9480 to 9482, 127.0.0.1 | `benethos-mailbox-agents-dev` |
| `live/` | the test account | Stalwart, the published mailbox service, LiteLLM with its database, llama.cpp | 38080, 38081, 38400, 38465, 38993, 127.0.0.1 | `mailbox-agents-live` |

Each folder has its own volumes, so a trial in `development/` never
reaches the state of an installation in `production/`, and nothing in
`development/` reaches a real mailbox.

## For development

```sh
sh containers/live/setup.sh                 # once: the test account
cd containers/development
docker compose up -d --build                # the agent counting
docker compose exec counting benethos-mailbox-agents report --agent counting
docker compose down -v                      # stop, and forget the volumes
```

An agent that asks a model reaches the gateway by its name on the live
network: `MAILBOX_AGENTS_GATEWAY_URL=http://gateway:4000/v1` in an `.env`
beside `development/compose.yaml`, which is not versioned. The key and the
model come from `agent.env`, and the `.env` may override them.

## The image

`ghcr.io/benethos-hub/benethos-mailbox-agents`, built from the repository
root:

```sh
docker build -f containers/images/mailbox-agents/Dockerfile -t benethos-mailbox-agents:local .
docker run --rm benethos-mailbox-agents:local --version
```

It runs as uid 10001, keeps the state file in the volume `/data`, serves
metrics on 9464 and holds no secret. A container runs one agent, named in
its command: `worker --agent <name>`. Its health check is
`benethos-mailbox-agents health --agent <name>`, set per service in
compose. A release publishes it for linux/amd64 and linux/arm64 under its
version, see [docs/RELEASING.md](../docs/RELEASING.md).
