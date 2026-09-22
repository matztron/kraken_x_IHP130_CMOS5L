"""Byte host on the TinyTapeout pins of kraken_tt_host."""

from __future__ import annotations

from cocotb.triggers import RisingEdge, ClockCycles

OP_ADDR_LO = 1
OP_ADDR_HI = 2
OP_DATA = 3
OP_WRITE = 4
OP_READ = 5
OP_SHIFT = 6


async def commit(dut, op: int, data: int = 0, gpio_in: int = 0) -> None:
    """Pulse host_stb for one cycle with opcode and data, then wait out the AXI transfer."""
    dut.ui_in.value = data & 0xFF
    dut.uio_in.value = ((gpio_in & 0xF) << 4) | ((op & 0x7) << 1) | 1
    await RisingEdge(dut.clk)
    dut.uio_in.value = (gpio_in & 0xF) << 4
    await ClockCycles(dut.clk, 16 if op in (OP_WRITE, OP_READ) else 2)


async def write_word(dut, addr: int, value: int) -> None:
    await commit(dut, OP_ADDR_LO, addr & 0xFF)
    await commit(dut, OP_ADDR_HI, (addr >> 8) & 0xF)
    for lane in range(4):
        await commit(dut, OP_DATA, (value >> (8 * lane)) & 0xFF)
    await commit(dut, OP_WRITE, 0)


async def read_word(dut, addr: int) -> int:
    await commit(dut, OP_ADDR_LO, addr & 0xFF)
    await commit(dut, OP_ADDR_HI, (addr >> 8) & 0xF)
    await commit(dut, OP_READ, 0)
    word = int(dut.uio_out.value) & 0xFF
    for lane in range(1, 4):
        await commit(dut, OP_SHIFT, 0)
        word |= (int(dut.uio_out.value) & 0xFF) << (8 * lane)
    return word
