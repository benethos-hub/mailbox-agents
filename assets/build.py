"""Make the PNG files of ``brand/`` from ``brand/icon.svg``.

    uv run python assets/build.py           both
    uv run python assets/build.py --icon    brand/icon.png, 512 by 512
    uv run python assets/build.py --social  brand/social-preview.png

Both are rendered with a headless Chromium browser (Chrome, Edge or
Chromium). Export them again whenever ``icon.svg`` changes and commit
them with it. The social preview goes up by hand as well, under
Settings, General, Social preview, as GitHub does not read it from the
repository.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ASSETS = Path(__file__).resolve().parent
ICON_SOURCE = ASSETS / "brand/icon.svg"
ICON = ASSETS / "brand/icon.png"
ICON_SIZE = (512, 512)
SOCIAL = ASSETS / "brand/social-preview.png"
# GitHub's size. It may crop the edges, so the content keeps 96 pixels
# away from them.
SOCIAL_SIZE = (1280, 640)

_ROOT_SIZE = re.compile(r'^(<svg [^>]*?)width="([\d.]+)" height="([\d.]+)"')

NAME = "Mailbox Agents"
CLAIM = "Small agents that sort your mailbox"
ADDRESS = "github.com/benethos-hub/mailbox-agents"
# What sets the project apart, each with a sign of 24 by 24.
PROMISES = (
    (
        "Shadow first: records, changes nothing",
        '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/>'
        '<circle cx="12" cy="12" r="3"/>',
    ),
    (
        "One narrow question, one reversible action",
        '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>',
    ),
    (
        "Measured against labelled mail",
        '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    ),
)
# The cards at the right: three agents, each with what it does to one
# message of invented mail.
CARDS = (
    (
        "sorting",
        "Your invoice 0815",
        "billing@cloudhost.example",
        "move_to_folder",
        "CloudHost",
    ),
    (
        "invoices",
        "Your invoice 0815",
        "in CloudHost",
        "move_to_folder",
        "CloudHost/Invoices",
    ),
    (
        "awaiting_reply",
        "Quote for the new site",
        "sent to a customer",
        "add_keyword",
        "agent-awaiting-reply",
    ),
)

_STYLE = """
  html, body { margin: 0; width: 1280px; height: 640px; overflow: hidden; }
  body {
    font-family: "Segoe UI", "Inter", "Helvetica Neue", Arial, sans-serif;
    background:
      radial-gradient(circle at 12% 10%, rgba(255,165,82,.22) 0,
        rgba(255,165,82,0) 40%),
      radial-gradient(circle at 92% 95%, rgba(242,100,48,.28) 0,
        rgba(242,100,48,0) 45%),
      linear-gradient(150deg, #2B120A 0%, #1E0C07 55%, #160805 100%);
    position: relative; color: #FCE7DA;
  }
  .grid {
    position: absolute; inset: 0;
    background-image:
      linear-gradient(rgba(255,190,150,.05) 1px, transparent 1px),
      linear-gradient(90deg, rgba(255,190,150,.05) 1px, transparent 1px);
    background-size: 40px 40px;
    -webkit-mask-image: radial-gradient(circle at 75% 50%, #000 0%,
      transparent 70%);
  }
  .left {
    position: absolute; left: 96px; top: 76px; bottom: 60px; width: 560px;
    display: flex; flex-direction: column;
  }
  .logo { width: 132px; }
  .logo svg { width: 100%; height: auto; display: block; }
  .name {
    margin-top: 22px; font-size: 70px; font-weight: 700;
    letter-spacing: -1.5px; line-height: 1.15; padding-bottom: 10px;
    background: linear-gradient(100deg, #FFE3CC 0%, #FFA552 55%, #F26430 100%);
    -webkit-background-clip: text; color: transparent;
  }
  .claim { font-size: 25px; font-weight: 600; color: #FCE7DA; margin-top: 8px; }
  .promises {
    margin-top: 28px; display: flex; flex-direction: column; gap: 12px;
    font-size: 19px; color: #F3CDB6;
  }
  .promises span { display: inline-flex; align-items: center; gap: 12px; }
  .promises svg { color: #FFA552; flex: none; }
  .foot {
    margin-top: auto; font-size: 19px; color: #B98A73; letter-spacing: .2px;
  }
  .cards {
    position: absolute; right: 96px; top: 50%; width: 440px;
    transform: translateY(-50%); display: flex; flex-direction: column;
    gap: 16px;
  }
  .card {
    background: rgba(255,248,242,.97); border-radius: 18px;
    padding: 14px 18px; color: #2B120A;
    box-shadow: 0 18px 40px rgba(0,0,0,.35), 0 0 0 1px rgba(255,165,82,.25);
  }
  .card:nth-child(2) { margin-left: -36px; margin-right: 36px; }
  .top { display: flex; align-items: center; justify-content: space-between; }
  .agent {
    font-family: "Cascadia Code", Consolas, monospace; font-size: 14px;
    font-weight: 700; color: #fff; background: #F26430;
    border-radius: 999px; padding: 3px 11px;
  }
  .stage {
    font-size: 12px; font-weight: 700; color: #C23A1A;
    text-transform: uppercase; letter-spacing: 1px;
  }
  .subject { margin-top: 8px; font-size: 17px; font-weight: 600; }
  .from { font-size: 14px; color: #8A5A44; }
  .action {
    margin-top: 8px; font-family: "Cascadia Code", Consolas, monospace;
    font-size: 14px; color: #C23A1A;
  }
  .action b { color: #2B120A; }
"""


def placed(svg: str, size: int) -> str:
    """The icon in the middle of a square of ``size``, as high as it."""
    found = _ROOT_SIZE.match(svg)
    if not found:
        raise ValueError("the icon names no width and height")
    width = size * float(found[2]) / float(found[3])
    inner = (
        f'{found[1]}x="{(size - width) / 2:g}" y="0" width="{width:g}" '
        f'height="{size}"' + svg[found.end() :]
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" '
        f'height="{size}" viewBox="0 0 {size} {size}">\n{inner}</svg>\n'
    )


def social(svg: str) -> str:
    """The page of the social preview: on a dark warm ground the icon, the
    name, the claim and what the project promises at the left, and at the
    right three agents, each with what it records for one message."""
    promises = "".join(
        '<span><svg width="24" height="24" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        f'stroke-linejoin="round">{sign}</svg>{text}</span>'
        for text, sign in PROMISES
    )
    cards = "".join(
        f'<div class="card"><div class="top"><span class="agent">{agent}</span>'
        '<span class="stage">shadow &middot; recorded</span></div>'
        f'<div class="subject">{subject}</div><div class="from">{origin}</div>'
        f'<div class="action"><b>{verb}</b> {target}</div></div>'
        for agent, subject, origin, verb, target in CARDS
    )
    return (
        '<!doctype html>\n<html><head><meta charset="utf-8">'
        f"<style>{_STYLE}</style></head>\n<body>\n"
        '<div class="grid"></div>\n'
        '<div class="left">\n'
        f'<div class="logo">{svg}</div>\n'
        f'<div class="name">{NAME}</div><div class="claim">{CLAIM}</div>\n'
        f'<div class="promises">{promises}</div>\n'
        f'<div class="foot">{ADDRESS}</div>\n</div>\n'
        f'<div class="cards">{cards}</div>\n</body></html>\n'
    )


_BROWSERS = (
    "chromium",
    "chromium-browser",
    "google-chrome",
    "chrome",
    "msedge",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)


def _browser() -> str:
    for name in _BROWSERS:
        found = shutil.which(name) or (name if Path(name).is_file() else None)
        if found:
            return found
    raise RuntimeError("no Chromium browser found: Chrome, Edge or Chromium")


def _screenshot(
    page: str, name: str, target: Path, size: tuple[int, int], transparent: bool
) -> None:
    """Render a page as a PNG with a headless browser. A transparent page
    keeps its alpha channel instead of the browser's white."""
    width, height = size
    background = ["--default-background-color=00000000"] if transparent else []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        source = Path(folder) / name
        source.write_text(page, "utf-8")
        subprocess.run(
            [
                _browser(),
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                *background,
                "--force-device-scale-factor=1",
                f"--user-data-dir={Path(folder) / 'profile'}",
                f"--window-size={width},{height}",
                f"--screenshot={target}",
                source.as_uri(),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )


def render_icon() -> None:
    svg = ICON_SOURCE.read_text("utf-8")
    _screenshot(placed(svg, ICON_SIZE[0]), "icon.svg", ICON, ICON_SIZE, True)


def render_social() -> None:
    svg = ICON_SOURCE.read_text("utf-8")
    _screenshot(social(svg), "social.html", SOCIAL, SOCIAL_SIZE, False)


def main(arguments: list[str]) -> int:
    if arguments not in ([], ["--icon"], ["--social"]):
        print("usage: build.py [--icon | --social]", file=sys.stderr)
        return 2
    if arguments != ["--social"]:
        render_icon()
    if arguments != ["--icon"]:
        render_social()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
