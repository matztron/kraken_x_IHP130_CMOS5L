"""UART RX over AXI: bit-bang 8N1 on gpio_in, read byte from RXF0."""

from __future__ import annotations

from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles
from cocotbext.axi import AxiLiteBus, AxiLiteMaster

from lib.sm_cfg import pack_clkdiv, pack_execctrl, pack_pinctrl, pack_shiftctrl

TEST_DIR = Path(__file__).resolve().parent
HEX_PATH = TEST_DIR / "generated" / "uart_rx.hex"

CTRL = 0x000
FSTAT = 0x004
RXF0 = 0x014
IMEM_ADDR = 0x020
IMEM_DATA = 0x024
CLKDIV = 0x100
EXECCTRL = 0x104
SHIFTCTRL = 0x108
PINCTRL = 0x10C

# Match uart_rx_mini: 8 SM cycles per bit (CLKDIV=1 → 8 sysclk/bit)
BIT_CYCLES = 8


def load_hex(path: Path) -> list[int]:
    words: list[int] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            words.append(int(line, 16))
    return words


async def reset(dut) -> None:
    dut.rst_n.value = 0
    dut.gpio_in.value = 1  # UART idle high
    await ClockCycles(dut.clk, 4)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


def make_axil(dut) -> AxiLiteMaster:
    bus = AxiLiteBus.from_prefix(dut, "s_axil")
    return AxiLiteMaster(bus, dut.clk, dut.rst_n, reset_active_level=False)


async def csr_write(axi: AxiLiteMaster, addr: int, data: int) -> None:
    await axi.write_dword(addr, data & 0xFFFFFFFF)


async def csr_read(axi: AxiLiteMaster, addr: int) -> int:
    resp = await axi.read(addr, 4)
    return int.from_bytes(resp.data, byteorder="little")


async def load_program(axi: AxiLiteMaster, words: list[int]) -> None:
    await csr_write(axi, IMEM_ADDR, 0)
    for w in words:
        await csr_write(axi, IMEM_DATA, w)


async def configure_uart_rx(axi: AxiLiteMaster, wrap_top: int) -> None:
    await csr_write(axi, CLKDIV, pack_clkdiv(1))
    await csr_write(axi, EXECCTRL, pack_execctrl(wrap_bottom=0, wrap_top=wrap_top))
    # shift right, autopush @ 8 (Pico uart_rx_mini); FJOIN_RX for deeper FIFO optional
    await csr_write(
        axi,
        SHIFTCTRL,
        pack_shiftctrl(
            in_shiftdir=1,
            out_shiftdir=1,
            autopush=1,
            push_thresh=8,
            fjoin_rx=1,
        ),
    )
    await csr_write(axi, PINCTRL, pack_pinctrl(in_base=0))


async def drive_uart_byte(dut, byte: int, bit_cycles: int = BIT_CYCLES) -> None:
    """Drive one 8N1 frame on gpio0 (LSB first), idle high before/after."""
    # Start bit
    dut.gpio_in.value = 0
    await ClockCycles(dut.clk, bit_cycles)
    # Data bits
    for i in range(8):
        dut.gpio_in.value = (byte >> i) & 1
        await ClockCycles(dut.clk, bit_cycles)
    # Stop bit
    dut.gpio_in.value = 1
    await ClockCycles(dut.clk, bit_cycles)


@cocotb.test()
async def test_uart_rx_byte_over_axi(dut):
    """Bit-bang 0x55 on gpio_in; SM pushes to RXF0 (byte in bits [31:24])."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    axi = make_axil(dut)

    words = load_hex(HEX_PATH)
    assert len(words) >= 4
    await load_program(axi, words)
    await configure_uart_rx(axi, wrap_top=len(words) - 1)
    await csr_write(axi, CTRL, 0x1)

    # Idle a few cycles while SM sits in WAIT
    dut.gpio_in.value = 1
    await ClockCycles(dut.clk, 4)

    payload = 0x55
    await drive_uart_byte(dut, payload)

    # Allow autopush / wrap settle
    await ClockCycles(dut.clk, 16)

    fstat = await csr_read(axi, FSTAT)
    assert (fstat & 0x100) == 0, f"RX still empty after frame, FSTAT={fstat:#x}"

    word = await csr_read(axi, RXF0)
    got = (word >> 24) & 0xFF
    assert got == payload, f"RX mismatch: got 0x{got:02X} from word=0x{word:08X}, expected 0x{payload:02X}"


@cocotb.test()
async def test_uart_rx_two_bytes_over_axi(dut):
    """Two frames 0x41 and 0x0A appear in RX FIFO in order."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    axi = make_axil(dut)

    words = load_hex(HEX_PATH)
    await load_program(axi, words)
    await configure_uart_rx(axi, wrap_top=len(words) - 1)
    await csr_write(axi, CTRL, 0x1)

    dut.gpio_in.value = 1
    await ClockCycles(dut.clk, 4)

    payloads = [0x41, 0x0A]
    for b in payloads:
        await drive_uart_byte(dut, b)
        await ClockCycles(dut.clk, 4)  # inter-frame idle

    await ClockCycles(dut.clk, 16)

    for expected in payloads:
        fstat = await csr_read(axi, FSTAT)
        assert (fstat & 0x100) == 0, f"RX empty before reading 0x{expected:02X}"
        word = await csr_read(axi, RXF0)
        got = (word >> 24) & 0xFF
        assert got == expected, f"got 0x{got:02X} expected 0x{expected:02X} (word={word:#010x})"
