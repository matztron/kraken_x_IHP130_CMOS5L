"""Cocotb driver for the Kraken-X synchronous 2-wire host link.

Pads (see src/kraken_tt_host.sv):
    ui_in[7]     SCK
    uio[7]       SDIO, bidirectional
    uio[6:0]     gpio[6:0]    bidirectional protocol pins
    uo_out[7:0]  gpio[14:7]   output only
    ui_in[6:0]   gpio[21:15]  input only

A frame is 56 bits, MSB first: an 8-bit command holding the direction bit and
addr[11:8], then addr[7:0], then 8 turnaround bits, then 32 data bits.

The device samples SDIO on the rising edge of SCK and changes its own output on
the falling edge, so this driver holds a bit stable across both half periods and
samples the device at the end of the low phase.
"""

from __future__ import annotations

from pathlib import Path

import cocotb
from cocotb.triggers import ClockCycles, RisingEdge

# CSR byte offsets; must match kraken_pkg AXIL_ADDR_*.
CTRL = 0x000
FSTAT = 0x004
IRQ = 0x008
IRQ_FORCE = 0x00C
TXF0 = 0x010
RXF0 = 0x014
IMEM_ADDR = 0x020
IMEM_DATA = 0x024
FDEBUG = 0x028
FLEVEL = 0x02C
ID = 0xFFC

ID_VALUE = 0x4B52414B

SM_BASE = 0x100
SM_STRIDE = 0x20
CLKDIV = 0x100
EXECCTRL = 0x104
SHIFTCTRL = 0x108
PINCTRL = 0x10C
SM_INSTR = 0x110
SM_ADDR = 0x114

SCK_BIT = 7
SDIO_BIT = 7

FRAME_BITS = 56
DATA_LSB = 24


def sm_reg(sm: int, offset: int) -> int:
    """Byte offset of a per-SM register bank entry."""
    return SM_BASE + SM_STRIDE * sm + offset


def txf(sm: int) -> int:
    return TXF0 + 8 * sm


def rxf(sm: int) -> int:
    return RXF0 + 8 * sm


def encode_set_pindirs(value: int) -> int:
    """`SET PINDIRS, value` — what the Pico SDK's set_consecutive_pindirs does.

    Force this through SM_INSTR before enabling a program that expects its pins
    to be outputs: gpio_oe resets to 0, so every pad comes up as an input.
    Uses PINCTRL's set_base / set_count, so configure those first.
    """
    return 0xE080 | (value & 0x1F)


def load_hex(path: Path) -> list[int]:
    """Read a `pioasm -o hex` file into 16-bit instruction words."""
    words: list[int] = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("//"):
            words.append(int(line, 16))
    return words


class KrakenSerial:
    """Drives SCK/SDIO and owns the shared ui_in / uio_in buses.

    Protocol input levels go through `set_gpio_in`, since SCK and SDIO share
    those buses with the PIO input pins.
    """

    def __init__(self, dut, half_period: int = 6, gap: int = 16):
        self.dut = dut
        self.half = half_period
        self.gap = gap
        self._uio_in = 0  # gpio[6:0]
        self._ui_in = 0  # gpio[21:15]
        self._sdio = 0
        self._sck = 0

    # ---- pin plumbing -----------------------------------------------------

    def _apply(self) -> None:
        self.dut.ui_in.value = (self._sck << SCK_BIT) | (self._ui_in & 0x7F)
        self.dut.uio_in.value = (self._sdio << SDIO_BIT) | (self._uio_in & 0x7F)

    def set_gpio_in(self, *, uio: int | None = None, ui: int | None = None) -> None:
        """Set the protocol input levels: uio drives gpio[6:0], ui drives gpio[21:15]."""
        if uio is not None:
            self._uio_in = uio & 0x7F
        if ui is not None:
            self._ui_in = ui & 0x7F
        self._apply()

    def gpio_out(self) -> int:
        """gpio[14:0] as seen on the pads: uio[6:0] plus uo_out[7:0]."""
        low = int(self.dut.uio_out.value) & 0x7F
        high = int(self.dut.uo_out.value) & 0xFF
        return (high << 7) | low

    def gpio_oe(self) -> int:
        """Output enables for the bidirectional bank, gpio[6:0]."""
        return int(self.dut.uio_oe.value) & 0x7F

    async def reset(self, cycles: int = 4) -> None:
        self.dut.ena.value = 1
        self._sck = 0
        self._sdio = 0
        self._apply()
        self.dut.rst_n.value = 0
        await ClockCycles(self.dut.clk, cycles)
        self.dut.rst_n.value = 1
        await ClockCycles(self.dut.clk, 2)

    # ---- link -------------------------------------------------------------

    async def _frame(self, write: bool, addr: int, data: int = 0) -> int:
        bits = [1 if write else 0, 0, 0, 0]
        bits += [(addr >> i) & 1 for i in range(11, 7, -1)]
        bits += [(addr >> i) & 1 for i in range(7, -1, -1)]
        bits += [0] * 8
        bits += [(data >> i) & 1 for i in range(31, -1, -1)]
        assert len(bits) == FRAME_BITS

        captured = 0
        for index, bit in enumerate(bits):
            self._sdio = 0 if (not write and index >= DATA_LSB) else bit
            self._sck = 0
            self._apply()
            await ClockCycles(self.dut.clk, self.half)

            if not write and index >= DATA_LSB:
                sampled = (int(self.dut.uio_out.value) >> SDIO_BIT) & 1
                captured = (captured << 1) | sampled

            self._sck = 1
            self._apply()
            await ClockCycles(self.dut.clk, self.half)

        self._sck = 0
        self._sdio = 0
        self._apply()
        await ClockCycles(self.dut.clk, self.gap)
        return captured

    async def write(self, addr: int, data: int) -> None:
        await self._frame(True, addr, data & 0xFFFFFFFF)

    async def read(self, addr: int) -> int:
        return await self._frame(False, addr)

    # ---- convenience ------------------------------------------------------

    async def load_imem(self, words: list[int], start: int = 0) -> None:
        """Write instruction words through IMEM_ADDR / auto-incrementing IMEM_DATA."""
        await self.write(IMEM_ADDR, start)
        for word in words:
            await self.write(IMEM_DATA, word & 0xFFFF)

    async def load_program(self, hex_path: Path, start: int = 0) -> list[int]:
        """Assemble-time hex file straight into IMEM. Returns the words written."""
        words = load_hex(hex_path)
        await self.load_imem(words, start)
        return words

    async def configure_sm(
        self,
        sm: int = 0,
        *,
        clkdiv: int | None = None,
        execctrl: int | None = None,
        shiftctrl: int | None = None,
        pinctrl: int | None = None,
    ) -> None:
        for offset, value in (
            (0x0, clkdiv),
            (0x4, execctrl),
            (0x8, shiftctrl),
            (0xC, pinctrl),
        ):
            if value is not None:
                await self.write(sm_reg(sm, offset), value)

    async def enable(self, sm_mask: int = 0x1) -> None:
        await self.write(CTRL, sm_mask & 0xF)

    async def exec_instr(self, instr: int, sm: int = 0) -> None:
        """Force one instruction through SM_INSTR; works while the SM is disabled."""
        await self.write(sm_reg(sm, 0x10), instr & 0xFFFF)


class PadTrace:
    """Background recorder for the pad view of gpio[14:0], one sample per clock.

    A CTRL write takes a whole 56-bit frame, so the state machine is already
    running by the time the write call returns. Start the trace before enabling.
    """

    def __init__(self, host: KrakenSerial):
        self.host = host
        self.samples: list[int] = []
        self._task = None

    def start(self) -> None:
        self._task = cocotb.start_soon(self._run())

    def stop(self) -> None:
        if self._task is not None:
            self._task.kill()
            self._task = None

    async def _run(self) -> None:
        while True:
            await RisingEdge(self.host.dut.clk)
            self.samples.append(self.host.gpio_out())

    def bit(self, index: int) -> list[int]:
        return [(s >> index) & 1 for s in self.samples]

    def high_runs(self, index: int) -> list[int]:
        """Lengths of the consecutive-high stretches on one pin, in clock cycles."""
        runs: list[int] = []
        run = 0
        for level in self.bit(index):
            if level:
                run += 1
            elif run:
                runs.append(run)
                run = 0
        if run:
            runs.append(run)
        return runs

    def sample_on_rising(self, clock_index: int, data_index: int) -> list[int]:
        """Data pin values captured at every rising edge of another pin."""
        clock = self.bit(clock_index)
        data = self.bit(data_index)
        return [data[i] for i in range(1, len(clock)) if clock[i] and not clock[i - 1]]
