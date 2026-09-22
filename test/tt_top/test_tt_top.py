"""Program the TinyTapeout top through the pin host and run hello_world.pio."""

from __future__ import annotations

from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, ReadOnly

from lib.tt_host import read_word, write_word

TEST_DIR = Path(__file__).resolve().parent
HEX_PATH = TEST_DIR / "generated" / "hello_world.hex"

CTRL = 0x000
IMEM_DATA = 0x024
EXECCTRL = 0x104
PINCTRL = 0x10C
ID = 0xFFC
ID_VALUE = 0x4B52414B


def load_hex(path: Path) -> list[int]:
    words: list[int] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("//"):
            words.append(int(line, 16))
    return words


@cocotb.test()
async def test_tt_hello_world(dut):
    """ID readback, then the pioasm square wave on gpio0."""
    assert HEX_PATH.is_file(), f"missing {HEX_PATH}; run make assemble first"
    words = load_hex(HEX_PATH)
    assert words == [0xE101, 0xE100], [hex(w) for w in words]

    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 4)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    assert await read_word(dut, ID) == ID_VALUE

    for word in words:
        await write_word(dut, IMEM_DATA, word)

    # wrap_bottom=0, wrap_top=1; set_count=1 so SET drives gpio0
    await write_word(dut, EXECCTRL, 0x0000_0020)
    await write_word(dut, PINCTRL, 0x0001_0000)
    await write_word(dut, CTRL, 0x1)

    samples = []
    for _ in range(16):
        await RisingEdge(dut.clk)
        await ReadOnly()
        samples.append(int(dut.uo_out.value) & 1)

    bits = "".join(str(b) for b in samples)
    assert "11001100" in bits or "00110011" in bits, f"gpio0 samples {samples}"
