"""Side-set, FIFO join, STATUS, multi-SM host FIFOs (NUM_SM=2)."""

from __future__ import annotations

from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, ReadOnly

from lib.sm_cfg import bcast

TEST_DIR = Path(__file__).resolve().parent
GEN = TEST_DIR / "generated"
NUM_SM = 2


def load_hex(name: str) -> list[int]:
    words = []
    for line in (GEN / name).read_text().splitlines():
        line = line.strip()
        if line:
            words.append(int(line, 16))
    return words


def pack_tx(*words: int) -> int:
    v = 0
    for i, w in enumerate(words):
        v |= (w & 0xFFFFFFFF) << (32 * i)
    return v


def B(val: int, width: int) -> int:
    return bcast(val, width, NUM_SM)


async def idle_inputs(dut) -> None:
    dut.imem_wr_en.value = 0
    dut.sm_enable.value = 0
    dut.clk_en.value = (1 << NUM_SM) - 1
    dut.sm_restart.value = 0
    dut.host_exec_stb.value = 0
    dut.host_exec_instr.value = 0
    dut.wrap_bottom.value = B(0, 5)
    dut.wrap_top.value = B(31, 5)
    dut.set_base.value = B(0, 5)
    dut.set_count.value = B(5, 3)
    dut.out_base.value = B(0, 5)
    dut.out_count.value = B(32, 6)
    dut.in_base.value = B(0, 5)
    dut.jmp_pin.value = B(0, 5)
    dut.sideset_base.value = B(0, 5)
    dut.sideset_count.value = B(0, 3)
    dut.side_en.value = 0
    dut.side_pindir.value = 0
    dut.in_shiftdir.value = 0
    dut.out_shiftdir.value = (1 << NUM_SM) - 1
    dut.push_thresh.value = B(0, 5)
    dut.pull_thresh.value = B(0, 5)
    dut.autopush.value = 0
    dut.autopull.value = 0
    dut.fjoin_tx.value = 0
    dut.fjoin_rx.value = 0
    dut.status_sel.value = 0
    dut.status_n.value = B(0, 4)
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
    wt = wrap_top if wrap_top is not None else max(len(words) - 1, 0)
    dut.wrap_top.value = B(wt, 5)
    await RisingEdge(dut.clk)


@cocotb.test()
async def test_side_toggle(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    await load_program(dut, load_hex("side_toggle.hex"), wrap_top=1)
    dut.sideset_count.value = B(1, 3)
    dut.sideset_base.value = B(0, 5)
    dut.sm_enable.value = 1
    seen_hi = seen_lo = False
    for _ in range(16):
        await RisingEdge(dut.clk)
        await ReadOnly()
        bit = int(dut.gpio_out.value) & 1
        if bit:
            seen_hi = True
        else:
            seen_lo = True
        if seen_hi and seen_lo:
            break
    assert seen_hi and seen_lo


@cocotb.test()
async def test_side_over_set(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    await load_program(dut, load_hex("side_over_set.hex"))
    dut.sideset_count.value = B(1, 3)
    dut.sideset_base.value = B(0, 5)
    dut.set_base.value = B(0, 5)
    dut.set_count.value = B(1, 3)
    dut.sm_enable.value = 1
    await ClockCycles(dut.clk, 4)
    await RisingEdge(dut.clk)
    # SET wants 1, side-set forces 0 on the same pin
    assert (int(dut.gpio_out.value) & 1) == 0


@cocotb.test()
async def test_status_txlevel(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    await load_program(dut, load_hex("mov_status.hex"))
    dut.status_sel.value = 0  # TXLEVEL SM0
    dut.status_n.value = B(1, 4)
    dut.out_count.value = B(32, 6)
    dut.sm_enable.value = 1
    await ClockCycles(dut.clk, 4)
    await RisingEdge(dut.clk)
    # empty TX: level 0 < 1 → all ones
    assert int(dut.gpio_out.value) == 0xFFFFFFFF

    # reload with a word in TX → level 1 < 1 false → zeros
    await reset(dut)
    await load_program(dut, load_hex("mov_status.hex"))
    dut.status_sel.value = 0
    dut.status_n.value = B(1, 4)
    dut.tx_data.value = pack_tx(0xDEAD, 0)
    dut.tx_push.value = 0b01
    await RisingEdge(dut.clk)
    dut.tx_push.value = 0
    dut.sm_enable.value = 1
    await ClockCycles(dut.clk, 4)
    await RisingEdge(dut.clk)
    assert int(dut.gpio_out.value) == 0


@cocotb.test()
async def test_fjoin_tx(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    dut.fjoin_tx.value = 0b01  # SM0 only
    await RisingEdge(dut.clk)
    for i in range(8):
        assert (int(dut.tx_full.value) & 1) == 0
        dut.tx_data.value = pack_tx(i, 0)
        dut.tx_push.value = 0b01
        await RisingEdge(dut.clk)
    dut.tx_push.value = 0
    await RisingEdge(dut.clk)
    assert (int(dut.tx_full.value) & 1) == 1
    # joined RX direction unusable: empty
    assert (int(dut.rx_empty.value) & 1) == 1


@cocotb.test()
async def test_fjoin_rx(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    await load_program(dut, load_hex("push_null.hex"), wrap_top=0)
    dut.fjoin_rx.value = 0b01
    await RisingEdge(dut.clk)
    # TX unusable when RX joined
    assert (int(dut.tx_full.value) & 1) == 1
    dut.sm_enable.value = 1
    # Enough cycles to fill 8-deep joined RX (then SM stalls on block)
    await ClockCycles(dut.clk, 12)
    dut.sm_enable.value = 0
    await RisingEdge(dut.clk)
    got = []
    while (int(dut.rx_empty.value) & 1) == 0:
        got.append(int(dut.rx_data.value) & 0xFFFFFFFF)
        dut.rx_pop.value = 0b01
        await RisingEdge(dut.clk)
        dut.rx_pop.value = 0
        await RisingEdge(dut.clk)
        if len(got) > 8:
            break
    assert len(got) == 8


@cocotb.test()
async def test_multi_sm_host_fifos(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    # Fill each SM's TX independently (depth 4)
    for i in range(4):
        dut.tx_data.value = pack_tx(0xA0 + i, 0xB0 + i)
        dut.tx_push.value = 0b11
        await RisingEdge(dut.clk)
    dut.tx_push.value = 0
    await RisingEdge(dut.clk)
    assert int(dut.tx_full.value) == 0b11

    # SM0 consumes one word; SM1 TX stays full
    await load_program(dut, load_hex("pull_out32.hex"))
    dut.out_count.value = B(32, 6)
    dut.sm_enable.value = 0b01
    await ClockCycles(dut.clk, 2)
    await RisingEdge(dut.clk)
    assert (int(dut.gpio_out.value) & 0xFF) == 0xA0
    dut.sm_enable.value = 0
    await RisingEdge(dut.clk)
    assert (int(dut.tx_full.value) & 0b10) == 0b10

    # Enable SM1; it should OUT its first word
    dut.sm_enable.value = 0b10
    await ClockCycles(dut.clk, 2)
    await RisingEdge(dut.clk)
    assert (int(dut.gpio_out.value) & 0xFF) == 0xB0
    dut.sm_enable.value = 0
