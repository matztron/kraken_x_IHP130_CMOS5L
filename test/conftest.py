"""Shared pytest helpers for Kraken IO testcases."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_pio_hex(path: Path) -> list[int]:
    """Load a pioasm -o hex file into a list of 16-bit instruction words."""
    words: list[int] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        words.append(int(line, 16))
    return words
