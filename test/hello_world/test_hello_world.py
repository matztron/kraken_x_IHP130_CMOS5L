"""Cocotb: run hello_world.pio on kraken_io and check SET pin square wave."""

from __future__ import annotations

from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, ReadOnly

TEST_DIR = Path(__file__).resolve().parent
HEX_PATH = TEST_DIR / "generated" / "hello_world.hex"


def load_hex(path: Path) -> list[int]:
    words: list[int] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        words.append(int(line, 16))
    return words


async def reset(dut, cycles: int = 4) -> None:
    dut.rst_n.value = 0
    dut.imem_wr_en.value = 0
    dut.sm_enable.value = 0
    dut.clk_en.value = 1
    dut.sm_restart.value = 0
    dut.host_exec_stb.value = 0
    dut.host_exec_instr.value = 0
    dut.wrap_bottom.value = 0
    dut.wrap_top.value = 1
    dut.set_base.value = 0
    dut.set_count.value = 1
    dut.out_base.value = 0
    dut.out_count.value = 0
    dut.in_base.value = 0
    dut.jmp_pin.value = 0
    dut.in_shiftdir.value = 1
    dut.out_shiftdir.value = 1
    dut.push_thresh.value = 0
    dut.pull_thresh.value = 0
    dut.autopush.value = 0
    dut.autopull.value = 0
    dut.fjoin_tx.value = 0
    dut.fjoin_rx.value = 0
    dut.sideset_base.value = 0
    dut.sideset_count.value = 0
    dut.side_en.value = 0
    dut.side_pindir.value = 0
    dut.status_sel.value = 0
    dut.status_n.value = 0
    dut.gpio_in.value = 0
    dut.tx_push.value = 0
    dut.tx_data.value = 0
    dut.rx_pop.value = 0
    dut.imem_wr_addr.value = 0
    dut.imem_wr_data.value = 0
    await ClockCycles(dut.clk, cycles)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def load_program(dut, words: list[int]) -> None:
    for addr, word in enumerate(words):
        dut.imem_wr_en.value = 1
        dut.imem_wr_addr.value = addr
        dut.imem_wr_data.value = word
        await RisingEdge(dut.clk)
    dut.imem_wr_en.value = 0
    await RisingEdge(dut.clk)


@cocotb.test()
async def test_hello_world_square_wave(dut):
    """Pin0 should toggle 1,1,0,0,1,1,0,0... (exec+delay per SET)."""
    assert HEX_PATH.is_file(), f"missing {HEX_PATH}; run make assemble first"
    words = load_hex(HEX_PATH)
    assert words == [0xE101, 0xE100], [hex(w) for w in words]

    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    await load_program(dut, words)

    dut.sm_enable.value = 1

    samples = []
    for _ in range(8):
        await RisingEdge(dut.clk)
        await ReadOnly()
        samples.append(int(dut.gpio_out.value) & 1)

    expected = [1, 1, 0, 0, 1, 1, 0, 0]
    assert samples == expected, f"got {samples}, expected {expected}"
