"""Make the PNG files of ``brand/`` from ``brand/icon.svg``, and those of
``architecture/`` from ``architecture/architecture.html``.

    uv run python assets/build.py            all of them
    uv run python assets/build.py --icon     brand/icon.png, 512 by 512
    uv run python assets/build.py --social   brand/social-preview.png
    uv run python assets/build.py --diagram  architecture/architecture.png
                                             and architecture-dark.png

All are rendered with a headless Chromium browser (Chrome, Edge or
Chromium). Export them again whenever ``icon.svg`` changes, and the
diagram whenever its page changes as well, and commit them with it. The
social preview goes up by hand as well, under Settings, General, Social
preview, as GitHub does not read it from the repository.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

ASSETS = Path(__file__).resolve().parent
ICON_SOURCE = ASSETS / "brand/icon.svg"
ICON = ASSETS / "brand/icon.png"
ICON_SIZE = (512, 512)
SOCIAL = ASSETS / "brand/social-preview.png"
# GitHub's size. It may crop the edges, so the content keeps 96 pixels
# away from them.
SOCIAL_SIZE = (1280, 640)
DIAGRAM_SOURCE = ASSETS / "architecture/architecture.html"
# The size of the page in CSS pixels, drawn at twice that.
DIAGRAM_SIZE = (1430, 776)
DIAGRAM_SCALE = 2
# Each image and the fragment that picks its colours on the page.
DIAGRAMS = {
    ASSETS / "architecture/architecture.png": "",
    ASSETS / "architecture/architecture-dark.png": "#dark",
}

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


def _capture(
    address: str,
    target: Path,
    size: tuple[int, int],
    transparent: bool = False,
    scale: int = 1,
) -> None:
    """Render the page at an address as a PNG with a headless browser, of
    ``scale`` pixels for each of its own. A transparent page keeps its
    alpha channel instead of the browser's white."""
    width, height = size
    background = ["--default-background-color=00000000"] if transparent else []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
        subprocess.run(
            [
                _browser(),
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                *background,
                f"--force-device-scale-factor={scale}",
                f"--user-data-dir={profile}",
                f"--window-size={width},{height}",
                f"--screenshot={target}",
                address,
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )


def _screenshot(
    page: str, name: str, target: Path, size: tuple[int, int], transparent: bool
) -> None:
    """Render a page given as text, from a file of that name."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        source = Path(folder) / name
        source.write_text(page, "utf-8")
        _capture(source.as_uri(), target, size, transparent)


def stamped(png: bytes, svg: str) -> bytes:
    """``png`` with a text chunk after its header that names the hash of
    the SVG it was rendered from, any such chunk before replaced. So a
    change of the SVG that leaves the pixels as they were, such as its
    title, still changes the PNG, and the PNG is never older than the SVG,
    as the brand check of the organisation asks."""
    signature, header_end = b"\x89PNG\r\n\x1a\n", 8 + 4 + 4 + 13 + 4
    if not png.startswith(signature) or png[12:16] != b"IHDR":
        raise ValueError("not a PNG file")
    digest = hashlib.sha256(svg.encode("utf-8")).hexdigest()
    data = b"Source\0" + f"{ICON_SOURCE.name} sha256:{digest}".encode("ascii")
    chunk = (
        struct.pack(">I", len(data))
        + b"tEXt"
        + data
        + struct.pack(">I", zlib.crc32(b"tEXt" + data))
    )
    rest, position = png[header_end:], 0
    kept: list[bytes] = []
    while position < len(rest):
        end = position + 12
        if end <= len(rest):
            (length,) = struct.unpack(">I", rest[position : position + 4])
            end += length
        if end > len(rest):
            raise ValueError("a chunk of the PNG is cut short")
        piece = rest[position:end]
        if not (piece[4:8] == b"tEXt" and piece[8:].startswith(b"Source\0")):
            kept.append(piece)
        position = end
        if piece[4:8] == b"IEND":
            break
    if position != len(rest) or not kept or kept[-1][4:8] != b"IEND":
        raise ValueError("the PNG does not end with its IEND chunk")
    return png[:header_end] + chunk + b"".join(kept)


def render_icon() -> None:
    svg = ICON_SOURCE.read_text("utf-8")
    _screenshot(placed(svg, ICON_SIZE[0]), "icon.svg", ICON, ICON_SIZE, True)
    ICON.write_bytes(stamped(ICON.read_bytes(), svg))


def render_social() -> None:
    svg = ICON_SOURCE.read_text("utf-8")
    _screenshot(social(svg), "social.html", SOCIAL, SOCIAL_SIZE, False)
    SOCIAL.write_bytes(stamped(SOCIAL.read_bytes(), svg))


def render_diagram() -> None:
    """The architecture diagram, light and dark. The page stays where it
    is, as it takes the icon from beside it."""
    for target, fragment in DIAGRAMS.items():
        _capture(
            DIAGRAM_SOURCE.as_uri() + fragment,
            target,
            DIAGRAM_SIZE,
            scale=DIAGRAM_SCALE,
        )


def main(arguments: list[str]) -> int:
    if arguments not in ([], ["--icon"], ["--social"], ["--diagram"]):
        print("usage: build.py [--icon | --social | --diagram]", file=sys.stderr)
        return 2
    if arguments in ([], ["--icon"]):
        render_icon()
    if arguments in ([], ["--social"]):
        render_social()
    if arguments in ([], ["--diagram"]):
        render_diagram()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
