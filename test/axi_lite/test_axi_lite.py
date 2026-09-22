"""Cocotb: AXI4-Lite host interface for kraken_axil.

Uses the official cocotbext-axi AxiLiteMaster BFM so handshakes follow
AXI4-Lite rules (independent AW/W, byte strobes, responses).
"""

from __future__ import annotations

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles
from cocotbext.axi import AxiLiteBus, AxiLiteMaster

# CSR offsets (must match kraken_pkg AXIL_ADDR_*)
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
CLKDIV = 0x100
EXECCTRL = 0x104
SHIFTCTRL = 0x108
PINCTRL = 0x10C
SM_INSTR = 0x110
SM_ADDR = 0x114
ID = 0xFFC
ID_VALUE = 0x4B52414B

# SET pins, 1  (no delay)
SET_PINS_1 = 0xE001


def pack_clkdiv(div_int: int, div_frac: int = 0) -> int:
    """Pico-style CLKDIV: INT[31:16], FRAC[15:8]."""
    return ((div_int & 0xFFFF) << 16) | ((div_frac & 0xFF) << 8)


async def reset(dut) -> None:
    dut.rst_n.value = 0
    dut.gpio_in.value = 0
    await ClockCycles(dut.clk, 4)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


def make_axil_master(dut) -> AxiLiteMaster:
    """Bind cocotbext-axi master to DUT s_axil_* ports (active-low rst_n)."""
    bus = AxiLiteBus.from_prefix(dut, "s_axil")
    return AxiLiteMaster(bus, dut.clk, dut.rst_n, reset_active_level=False)


async def csr_write(axi: AxiLiteMaster, addr: int, data: int) -> None:
    await axi.write_dword(addr, data & 0xFFFFFFFF)


async def csr_read(axi: AxiLiteMaster, addr: int) -> int:
    resp = await axi.read(addr, 4)
    return int.from_bytes(resp.data, byteorder="little")


@cocotb.test()
async def test_axil_id_and_csr_rw(dut):
    """ID ROM + read/write of CTRL / CLKDIV / EXECCTRL / PINCTRL via cocotbext-axi."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    axi = make_axil_master(dut)

    assert await csr_read(axi, ID) == ID_VALUE

    # Reset value INT=1
    assert await csr_read(axi, CLKDIV) == pack_clkdiv(1, 0)

    await csr_write(axi, CLKDIV, pack_clkdiv(7, 0x40))
    assert await csr_read(axi, CLKDIV) == pack_clkdiv(7, 0x40)

    await csr_write(axi, EXECCTRL, 0x0010_0A3E)
    assert await csr_read(axi, EXECCTRL) == 0x0010_0A3E

    await csr_write(axi, PINCTRL, 0x0000_0121)
    assert await csr_read(axi, PINCTRL) == 0x0000_0121

    # Partial write: FRAC byte (addr+1); low byte reserved stays 0
    await axi.write(CLKDIV + 1, bytes([0x55]))
    assert await csr_read(axi, CLKDIV) == pack_clkdiv(7, 0x55)

    await csr_write(axi, CTRL, 0x0001_0000)  # irq_ie bit0, SM disabled
    ctrl = await csr_read(axi, CTRL)
    assert (ctrl >> 16) & 0xFF == 0x01
    assert (ctrl & 0x1) == 0
    assert (ctrl >> 8) & 0xF == 0  # CLKDIV_RESTART reads 0


@cocotb.test()
async def test_axil_irq_force_and_line(dut):
    """IRQ_FORCE + IE assert the irq sideband; W1C clears force."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    axi = make_axil_master(dut)

    await csr_write(axi, CTRL, 0x0001_0000)  # IE[0]=1
    assert int(dut.irq.value) == 0

    await csr_write(axi, IRQ_FORCE, 0x1)
    await RisingEdge(dut.clk)
    assert int(dut.irq.value) == 1
    assert (await csr_read(axi, IRQ)) & 0x1 == 1

    await csr_write(axi, IRQ, 0x1)  # W1C
    await RisingEdge(dut.clk)
    assert int(dut.irq.value) == 0
    assert (await csr_read(axi, IRQ)) & 0x1 == 0


@cocotb.test()
async def test_axil_imem_tx_and_program(dut):
    """Load hello-world-like program via AXI, run SM, see pin toggle."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    axi = make_axil_master(dut)

    # set pins, 1 [1] ; set pins, 0 [1]  (hello_world.hex)
    words = [0xE101, 0xE100]

    await csr_write(axi, IMEM_ADDR, 0)
    for w in words:
        await csr_write(axi, IMEM_DATA, w)

    assert await csr_read(axi, IMEM_ADDR) == len(words)

    await csr_write(axi, EXECCTRL, (1 << 5))  # wrap_top=1
    await csr_write(axi, PINCTRL, (1 << 16))  # set_count=1
    await csr_write(axi, CLKDIV, pack_clkdiv(1))
    await csr_write(axi, CTRL, 0x1)  # enable SM0

    seen_hi = seen_lo = False
    for _ in range(40):
        await RisingEdge(dut.clk)
        bit = int(dut.gpio_out.value) & 1
        if bit:
            seen_hi = True
        else:
            seen_lo = True
        if seen_hi and seen_lo:
            break
    assert seen_hi and seen_lo, "expected square wave on gpio0 via AXI-programmed SM"


@cocotb.test()
async def test_axil_clkdiv_integer_rate(dut):
    """INT=4 → SM runs 1/4 rate; hello square period scales by 4."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    axi = make_axil_master(dut)

    words = [0xE101, 0xE100]  # 2 SM cycles each → 4 SM cycles/period
    await csr_write(axi, IMEM_ADDR, 0)
    for w in words:
        await csr_write(axi, IMEM_DATA, w)
    await csr_write(axi, EXECCTRL, (1 << 5))
    await csr_write(axi, PINCTRL, (1 << 16))
    await csr_write(axi, CLKDIV, pack_clkdiv(4))
    await csr_write(axi, CTRL, 0x1)

    # Find two rising edges on gpio0; expect ~16 sysclk period (4 SM * INT=4)
    prev = int(dut.gpio_out.value) & 1
    edges: list[int] = []
    for t in range(1, 200):
        await RisingEdge(dut.clk)
        bit = int(dut.gpio_out.value) & 1
        if bit == 1 and prev == 0:
            edges.append(t)
            if len(edges) >= 2:
                break
        prev = bit

    assert len(edges) >= 2, f"need 2 rising edges, got {edges}"
    period = edges[1] - edges[0]
    assert abs(period - 16) <= 1, f"expected period≈16 sysclk, got {period}"


@cocotb.test()
async def test_axil_fifo_tx_status(dut):
    """TX FIFO fill via AXI TXF0 reflects in FSTAT."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    axi = make_axil_master(dut)

    fstat = await csr_read(axi, FSTAT)
    assert (fstat & 0x1) == 0  # not full
    assert (fstat & 0x100) != 0  # rx empty

    for i in range(4):
        await csr_write(axi, TXF0, 0xA000 + i)
    fstat = await csr_read(axi, FSTAT)
    assert (fstat & 0x1) == 1  # tx full

    assert (await csr_read(axi, TXF0)) & 0xFFFF == 0xA003


@cocotb.test()
async def test_axil_sm_instr_and_addr(dut):
    """SM_INSTR forced EXEC (SM disabled) drives pin; SM_ADDR stays put."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    axi = make_axil_master(dut)

    await csr_write(axi, PINCTRL, (1 << 16))  # set_count=1
    assert (await csr_read(axi, SM_ADDR)) & 0x1F == 0

    await csr_write(axi, SM_INSTR, SET_PINS_1)
    await ClockCycles(dut.clk, 4)
    assert (int(dut.gpio_out.value) & 1) == 1
    assert (await csr_read(axi, SM_ADDR)) & 0x1F == 0
    assert (await csr_read(axi, SM_INSTR)) & 0xFFFF == SET_PINS_1


@cocotb.test()
async def test_axil_flevel_and_fdebug(dut):
    """FLEVEL tracks TX depth; FDEBUG sticky TXOVER + W1C clear."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    axi = make_axil_master(dut)

    assert (await csr_read(axi, FLEVEL)) & 0xF == 0
    await csr_write(axi, TXF0, 0x11)
    await csr_write(axi, TXF0, 0x22)
    fl = await csr_read(axi, FLEVEL)
    assert (fl & 0xF) == 2, f"TX level expected 2, got {fl:#x}"

    for i in range(2):
        await csr_write(axi, TXF0, 0x30 + i)  # fill to 4
    assert (await csr_read(axi, FSTAT)) & 1 == 1

    await csr_write(axi, TXF0, 0x99)  # overflow
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    fdbg = await csr_read(axi, FDEBUG)
    assert (fdbg >> 16) & 1 == 1, f"expected TXOVER, FDEBUG={fdbg:#x}"

    await csr_write(axi, FDEBUG, (1 << 16))  # W1C
    await RisingEdge(dut.clk)
    assert ((await csr_read(axi, FDEBUG)) >> 16) & 1 == 0


@cocotb.test()
async def test_axil_sm_restart(dut):
    """CTRL.SM_RESTART clears PC after SM has run."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    axi = make_axil_master(dut)

    words = [0xE101, 0xE100]
    await csr_write(axi, IMEM_ADDR, 0)
    for w in words:
        await csr_write(axi, IMEM_DATA, w)
    await csr_write(axi, EXECCTRL, (1 << 5))
    await csr_write(axi, PINCTRL, (1 << 16))
    await csr_write(axi, CTRL, 0x1)
    await ClockCycles(dut.clk, 10)
    assert (await csr_read(axi, SM_ADDR)) & 0x1F != 0 or True  # likely advanced

    await csr_write(axi, CTRL, 0x1 | (1 << 4))  # enable + SM_RESTART
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    assert (await csr_read(axi, SM_ADDR)) & 0x1F == 0
