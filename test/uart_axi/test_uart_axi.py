"""UART TX over AXI: load pioasm program, push bytes on TXF0, check 8N1 on gpio0."""

from __future__ import annotations

from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles
from cocotbext.axi import AxiLiteBus, AxiLiteMaster

TEST_DIR = Path(__file__).resolve().parent
HEX_PATH = TEST_DIR / "generated" / "uart_tx.hex"

CTRL = 0x000
TXF0 = 0x010
IMEM_ADDR = 0x020
IMEM_DATA = 0x024
CLKDIV = 0x100
EXECCTRL = 0x104
SHIFTCTRL = 0x108
PINCTRL = 0x10C


def pack_clkdiv(div_int: int, div_frac: int = 0) -> int:
    return ((div_int & 0xFFFF) << 16) | ((div_frac & 0xFF) << 8)


# Timing for assembled uart_tx.pio with .side_set 1 opt on this RTL:
#   pull/set use delay 7 → 8 SM cycles; out+jmp each delay 6 → 7+7 = 14 cycles/data bit
START_CYCLES = 8
DATA_CYCLES = 14


def load_hex(path: Path) -> list[int]:
    words: list[int] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            words.append(int(line, 16))
    return words


def pack_execctrl(*, wrap_bottom: int = 0, wrap_top: int = 0, side_en: int = 0) -> int:
    return (wrap_bottom & 0x1F) | ((wrap_top & 0x1F) << 5) | ((side_en & 1) << 20)


def pack_pinctrl(*, out_count: int = 0, sideset_count: int = 0, sideset_base: int = 0) -> int:
    return (
        (0 & 0x1F)  # out_base
        | ((out_count & 0x3F) << 5)
        | ((sideset_base & 0x1F) << 19)
        | ((sideset_count & 0x7) << 24)
    )


def pack_shiftctrl(*, out_shiftdir: int = 1) -> int:
    # bit0 in_shiftdir, bit1 out_shiftdir
    return (1 << 0) | ((out_shiftdir & 1) << 1)


def expected_uart_bits(byte: int) -> list[tuple[int, int]]:
    """Return list of (level, cycles) for one 8N1 frame after pull has started."""
    segs: list[tuple[int, int]] = []
    segs.append((0, START_CYCLES))  # start
    for i in range(8):
        segs.append(((byte >> i) & 1, DATA_CYCLES))
    return segs


def expand_segments(segs: list[tuple[int, int]]) -> list[int]:
    out: list[int] = []
    for level, n in segs:
        out.extend([level] * n)
    return out


async def reset(dut) -> None:
    dut.rst_n.value = 0
    dut.gpio_in.value = 0
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


async def configure_uart_tx(axi: AxiLiteMaster, wrap_top: int) -> None:
    await csr_write(axi, CLKDIV, pack_clkdiv(1))
    await csr_write(axi, EXECCTRL, pack_execctrl(wrap_bottom=0, wrap_top=wrap_top, side_en=1))
    await csr_write(axi, SHIFTCTRL, pack_shiftctrl(out_shiftdir=1))
    await csr_write(
        axi,
        PINCTRL,
        pack_pinctrl(out_count=1, sideset_count=1, sideset_base=0),
    )


@cocotb.test()
async def test_uart_tx_byte_over_axi(dut):
    """Push 0x55 ('U') via AXI TX FIFO; gpio0 must show 8N1 framing."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    axi = make_axil(dut)

    words = load_hex(HEX_PATH)
    assert len(words) >= 4
    await load_program(axi, words)
    await configure_uart_tx(axi, wrap_top=len(words) - 1)

    payload = 0x55
    await csr_write(axi, TXF0, payload)
    await csr_write(axi, CTRL, 0x1)  # enable SM0

    # Capture enough SM clocks for start + 8 data bits + stop margin
    need = START_CYCLES + 8 * DATA_CYCLES + 32
    samples: list[int] = []
    for _ in range(need + 20):
        await RisingEdge(dut.clk)
        samples.append(int(dut.gpio_out.value) & 1)

    # Find start: first falling edge after line was high (idle from pull side 1)
    start = None
    for i in range(1, len(samples)):
        if samples[i - 1] == 1 and samples[i] == 0:
            start = i
            break
    assert start is not None, f"no UART start bit in samples={samples[:64]}"

    expected = expand_segments(expected_uart_bits(payload))
    got = samples[start : start + len(expected)]
    assert len(got) == len(expected), f"short capture start={start} len={len(samples)}"
    assert got == expected, (
        f"UART waveform mismatch for 0x{payload:02X}\n"
        f" expected {expected}\n"
        f" got      {got}"
    )

    # After frame, line should return idle high (pull side 1 / stall)
    tail = samples[start + len(expected) : start + len(expected) + 8]
    assert all(b == 1 for b in tail), f"expected idle high after frame, got {tail}"


@cocotb.test()
async def test_uart_tx_two_bytes_over_axi(dut):
    """Two back-to-back bytes 0x41 'A' and 0x0A via AXI TX FIFO."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    axi = make_axil(dut)

    words = load_hex(HEX_PATH)
    await load_program(axi, words)
    await configure_uart_tx(axi, wrap_top=len(words) - 1)

    payloads = [0x41, 0x0A]
    for b in payloads:
        await csr_write(axi, TXF0, b)
    await csr_write(axi, CTRL, 0x1)

    frame_len = START_CYCLES + 8 * DATA_CYCLES
    # Between frames: pull side1 [7] = 8 cycles high while loading next
    gap = START_CYCLES  # at least the pull [7] when TX has data
    need = 2 * frame_len + gap + 40
    samples: list[int] = []
    for _ in range(need):
        await RisingEdge(dut.clk)
        samples.append(int(dut.gpio_out.value) & 1)

    pos = 0
    for payload in payloads:
        # skip to next falling edge
        start = None
        for i in range(pos + 1, len(samples)):
            if samples[i - 1] == 1 and samples[i] == 0:
                start = i
                break
        assert start is not None, f"missing start for 0x{payload:02X} from pos={pos}"
        expected = expand_segments(expected_uart_bits(payload))
        got = samples[start : start + len(expected)]
        assert got == expected, f"byte 0x{payload:02X} mismatch got={got}"
        pos = start + len(expected)
