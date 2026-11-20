"""The stamp assets/build.py writes into the PNG files: the hash of the SVG,
so a change of the SVG always changes them, as the brand check asks."""

from __future__ import annotations

import struct
import subprocess
import zlib
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

from helpers import ROOT, load_script

BUILD = ROOT / "assets" / "build.py"


@pytest.fixture(scope="module")
def build() -> Iterator[ModuleType]:
    with load_script(BUILD, "assets_build") as module:
        yield module


def _chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data))
    )


PNG = (
    b"\x89PNG\r\n\x1a\n"
    + _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
    + _chunk(b"IDAT", zlib.compress(b"\0\0\0\0\0"))
    + _chunk(b"IEND", b"")
)


def _texts(png: bytes) -> list[bytes]:
    position, found = 8, []
    while position < len(png):
        (length,) = struct.unpack(">I", png[position : position + 4])
        if png[position + 4 : position + 8] == b"tEXt":
            found.append(png[position + 8 : position + 8 + length])
        position += 12 + length
    return found


def test_the_stamp_names_the_hash_of_the_svg(build: ModuleType) -> None:
    stamped = build.stamped(PNG, "<svg/>")

    (text,) = _texts(stamped)
    assert text.startswith(b"Source\0icon.svg sha256:")
    assert stamped.endswith(PNG[33:])


def test_another_svg_gives_another_png_and_one_stamp_only(build: ModuleType) -> None:
    first = build.stamped(PNG, "<svg><title>a</title></svg>")
    second = build.stamped(first, "<svg><title>b</title></svg>")

    assert first != second
    assert len(_texts(second)) == 1
    assert build.stamped(second, "<svg><title>b</title></svg>") == second


@pytest.mark.parametrize(
    "png",
    [PNG[:35], PNG[:60], PNG + b"\0\1", PNG[:-12]],
    ids=["length-cut", "chunk-cut", "after-iend", "no-iend"],
)
def test_a_png_cut_short_or_with_bytes_after_its_end_is_refused(
    build: ModuleType, png: bytes
) -> None:
    with pytest.raises(ValueError, match="PNG"):
        build.stamped(png, "<svg/>")


def test_a_browser_that_writes_no_screenshot_leaves_the_png_as_it_was(
    build: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    icon = tmp_path / "icon.png"
    icon.write_bytes(PNG)
    monkeypatch.setattr(build, "ICON", icon)
    monkeypatch.setattr(build, "_browser", lambda: "chromium")
    monkeypatch.setattr(
        build.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, b"", b""),
    )

    with pytest.raises(RuntimeError, match="no screenshot for icon.png"):
        build.render_icon()

    assert icon.read_bytes() == PNG


def test_a_file_that_is_no_png_is_refused(build: ModuleType) -> None:
    with pytest.raises(ValueError):
        build.stamped(b"GIF89a", "<svg/>")
