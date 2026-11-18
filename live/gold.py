"""The gold files of the test account of containers/live/.

    uv run python live/gold.py [--env-file containers/live/secrets/agent.env]

The invented mail of containers/live/mail.py comes with its labels. This
fetches the messages of the test account, finds each by its Message-ID and
writes containers/live/secrets/gold-<agent>.jsonl, so an agent can be
evaluated against it:

    uv run benethos-mailbox-agents --env-file containers/live/secrets/agent.env \
        eval --agent invoices --gold containers/live/secrets/gold-invoices.jsonl \
        --reports containers/live/secrets/reports

It only reads. Never point it at an account that is not a test account.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from common import live_settings  # beside this script, not a package

from benethos_mailbox_agents.settings import Settings
from benethos_mailbox_agents.sources.mailbox import connect

ROOT = Path(__file__).resolve().parent.parent
LIVE = ROOT / "containers" / "live"
sys.path.insert(0, str(LIVE))

from mail import GOLD  # noqa: E402 - beside the setup, not a package


async def write(settings: Settings) -> list[Path]:
    lines: dict[str, list[str]] = {}
    async with connect(
        settings.service_url or "",
        settings.secret("service_token"),
        allow_http=settings.service_allow_http,
    ) as mailbox:
        refs = await mailbox.recent(
            date.today() - timedelta(days=30),
            settings.accounts,
            roles=("inbox", "sent"),
        )
        for ref in refs:
            message = await mailbox.message(ref)
            local = (message.message_id_header or "").strip("<>").partition("@")[0]
            for agent, (label, fields) in GOLD.get(local, {}).items():
                item = {
                    "account_id": ref.account_id,
                    "message_id": ref.message_id,
                    "label": label,
                    "fields": fields,
                    "note": local,
                }
                lines.setdefault(agent, []).append(json.dumps(item))
    written = []
    for agent, found in sorted(lines.items()):
        path = LIVE / "secrets" / f"gold-{agent}.jsonl"
        path.write_bytes(("\n".join(found) + "\n").encode("utf-8"))
        written.append(path)
    return written


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="The gold files of the test account.")
    parser.add_argument("--env-file", type=Path, default=LIVE / "secrets" / "agent.env")
    args = parser.parse_args()
    for path in asyncio.run(write(live_settings(args.env_file, "gold"))):
        count = len(path.read_text(encoding="utf-8").splitlines())
        print(f"gold: {path.relative_to(ROOT)} ({count} messages)")
