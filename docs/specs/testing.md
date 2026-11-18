# Testing

- The suite is offline. The mailbox service and the gateway are mocked with
  `httpx.MockTransport`. No test reaches a network, and none skips itself
  when a credential is missing.
- Coverage floor 80 %.
- `ruff`, `mypy`, `uv lock --check`.
- A test holds the layer order of [architecture](architecture.md), and one holds the tables of
  this document to the code where they can be compared.
- Async tests run with pytest-asyncio.
- Live checks are scripts in `live/`, run by hand against a test account.
  `containers/live/` holds it (decided 2026-11-17): a mail server of our
  own, Stalwart, in a local container, with an account made for the agents
  and filled with invented mail, and the published image of the mailbox
  service in front of it. `setup.sh` makes it in one run, and
  `live/smoke.py` reads it through the package without writing to it.
  The model gateway belongs to it (decided 2026-11-17): LiteLLM with Claude
  through the owner's API key, and local models under llama.cpp, one
  service on the graphics card and one on the CPU. `live/gold.py` turns
  the labels of the invented mail into gold files, so `eval` can compare
  models on them.
