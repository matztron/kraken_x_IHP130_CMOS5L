"""Assemble hello_world.pio with pioasm and check the binary."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

TEST_DIR = Path(__file__).resolve().parent
ROOT = TEST_DIR.parents[1]
PIO_SRC = TEST_DIR / "hello_world.pio"
GEN_DIR = TEST_DIR / "generated"

# Golden words from pioasm 2.3.0 (SET pins,1 [1] / SET pins,0 [1])
EXPECTED_WORDS = (0xE101, 0xE100)


def _find_pioasm() -> str:
    env = os.environ.get("PIOASM")
    if env:
        return env
    found = shutil.which("pioasm")
    if found:
        return found
    mac_default = Path("/Applications/pico-sdk-tools/pioasm/pioasm")
    if mac_default.is_file():
        return str(mac_default)
    pytest.skip("pioasm not found (set PATH or PIOASM)")


def _parse_hex(path: Path) -> list[int]:
    words: list[int] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        words.append(int(line, 16))
    return words


def test_hello_world_assembles_with_pioasm(tmp_path: Path) -> None:
    pioasm = _find_pioasm()
    assert PIO_SRC.is_file(), f"missing {PIO_SRC}"

    out_hex = tmp_path / "hello_world.hex"
    result = subprocess.run(
        [pioasm, "-o", "hex", str(PIO_SRC), str(out_hex)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"pioasm failed ({result.returncode}):\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert out_hex.is_file()

    words = _parse_hex(out_hex)
    assert words == list(EXPECTED_WORDS), f"got {[hex(w) for w in words]}"


def test_hello_world_makefile_assemble() -> None:
    pioasm = _find_pioasm()
    result = subprocess.run(
        ["make", "-C", str(TEST_DIR), f"PIOASM={pioasm}", "assemble"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"make assemble failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    hex_path = GEN_DIR / "hello_world.hex"
    assert hex_path.is_file()
    assert _parse_hex(hex_path) == list(EXPECTED_WORDS)
