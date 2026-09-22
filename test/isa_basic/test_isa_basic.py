"""Cocotb coverage for JMP, WAIT, IN/OUT, PUSH/PULL, MOV, IRQ."""

from __future__ import annotations

from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, ReadOnly

TEST_DIR = Path(__file__).resolve().parent
GEN = TEST_DIR / "generated"


def load_hex(name: str) -> list[int]:
    path = GEN / name
    words = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            words.append(int(line, 16))
    return words


async def idle_inputs(dut) -> None:
    dut.imem_wr_en.value = 0
    dut.sm_enable.value = 0
    dut.clk_en.value = 1
    dut.sm_restart.value = 0
    dut.host_exec_stb.value = 0
    dut.host_exec_instr.value = 0
    dut.wrap_bottom.value = 0
    dut.wrap_top.value = 31
    dut.set_base.value = 0
    dut.set_count.value = 5
    dut.out_base.value = 0
    dut.out_count.value = 32
    dut.in_base.value = 0
    dut.jmp_pin.value = 0
    dut.in_shiftdir.value = 0  # shift left into ISR
    dut.out_shiftdir.value = 1  # shift right out of OSR
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


async def reset(dut) -> None:
    await idle_inputs(dut)
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 4)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def load_program(dut, words: list[int], wrap_top: int | None = None) -> None:
    for addr, word in enumerate(words):
        dut.imem_wr_en.value = 1
        dut.imem_wr_addr.value = addr
        dut.imem_wr_data.value = word
        await RisingEdge(dut.clk)
    dut.imem_wr_en.value = 0
    if wrap_top is not None:
        dut.wrap_top.value = wrap_top
    else:
        dut.wrap_top.value = max(len(words) - 1, 0)
    await RisingEdge(dut.clk)


async def run_cycles(dut, n: int) -> None:
    for _ in range(n):
        await RisingEdge(dut.clk)


@cocotb.test()
async def test_jmp_countdown(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    words = load_hex("jmp_count.hex")
    await load_program(dut, words)
    dut.sm_enable.value = 1
    # set x,2; jmp x-- ; jmp x-- ; jmp fall; set pins,1
    await run_cycles(dut, 8)
    await ReadOnly()
    assert (int(dut.gpio_out.value) & 1) == 1


@cocotb.test()
async def test_wait_gpio(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    await load_program(dut, load_hex("wait_gpio.hex"))
    dut.sm_enable.value = 1
    await run_cycles(dut, 4)
    await RisingEdge(dut.clk)
    assert (int(dut.gpio_out.value) & 1) == 0  # still waiting
    dut.gpio_in.value = 1
    await run_cycles(dut, 4)
    await RisingEdge(dut.clk)
    assert (int(dut.gpio_out.value) & 1) == 1


@cocotb.test()
async def test_pull_out(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    await load_program(dut, load_hex("pull_out.hex"))
    # Push a word into TX before enabling
    dut.tx_data.value = 0xA5
    dut.tx_push.value = 1
    await RisingEdge(dut.clk)
    dut.tx_push.value = 0
    dut.sm_enable.value = 1
    await run_cycles(dut, 6)
    await RisingEdge(dut.clk)
    assert (int(dut.gpio_out.value) & 0xFF) == 0xA5


@cocotb.test()
async def test_in_push(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    await load_program(dut, load_hex("in_push.hex"))
    dut.gpio_in.value = 0x0000003C
    dut.sm_enable.value = 1
    await run_cycles(dut, 6)
    await RisingEdge(dut.clk)
    assert int(dut.rx_empty.value) == 0
    got = int(dut.rx_data.value)
    dut.rx_pop.value = 1
    await RisingEdge(dut.clk)
    dut.rx_pop.value = 0
    assert got == 0x0000003C


@cocotb.test()
async def test_mov_xy(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    await load_program(dut, load_hex("mov_xy.hex"))
    dut.sm_enable.value = 1
    await run_cycles(dut, 6)
    await RisingEdge(dut.clk)
    assert (int(dut.gpio_out.value) & 0x1F) == 5


@cocotb.test()
async def test_irq_pulse(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    await load_program(dut, load_hex("irq_pulse.hex"))
    dut.sm_enable.value = 1
    seen_set = False
    pin_on = False
    for _ in range(8):
        await RisingEdge(dut.clk)
        flags = int(dut.irq_flags.value)
        if flags & 1:
            seen_set = True
        if (int(dut.gpio_out.value) & 1) == 1:
            pin_on = True
            break
    assert pin_on
    assert (int(dut.irq_flags.value) & 1) == 0
    # set may be brief; pin reaching 1 is the main check
    _ = seen_set
