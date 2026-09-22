"""Per-SM Pico CLKDIV + independent EXEC/SHIFT/PINCTRL banks (NUM_SM=2)."""

from __future__ import annotations

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles
from cocotbext.axi import AxiLiteBus, AxiLiteMaster

from lib.sm_cfg import pack_clkdiv, pack_execctrl, pack_pinctrl, sm_addr

CTRL = 0x000
IMEM_ADDR = 0x020
IMEM_DATA = 0x024
CLKDIV0 = sm_addr(0, 0)
EXEC0 = sm_addr(0, 4)
PIN0 = sm_addr(0, 0xC)
CLKDIV1 = sm_addr(1, 0)
EXEC1 = sm_addr(1, 4)
PIN1 = sm_addr(1, 0xC)


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


async def load_square(axi: AxiLiteMaster) -> None:
    # set pins, 1 [1] ; set pins, 0 [1]
    await csr_write(axi, IMEM_ADDR, 0)
    await csr_write(axi, IMEM_DATA, 0xE101)
    await csr_write(axi, IMEM_DATA, 0xE100)


@cocotb.test()
async def test_per_sm_clkdiv_csr(dut):
    """SM0/SM1 CLKDIV registers are independent (Pico INT/FRAC layout)."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    axi = make_axil(dut)

    assert await csr_read(axi, CLKDIV0) == pack_clkdiv(1)
    assert await csr_read(axi, CLKDIV1) == pack_clkdiv(1)

    await csr_write(axi, CLKDIV0, pack_clkdiv(2, 0))
    await csr_write(axi, CLKDIV1, pack_clkdiv(5, 0x80))
    assert await csr_read(axi, CLKDIV0) == pack_clkdiv(2, 0)
    assert await csr_read(axi, CLKDIV1) == pack_clkdiv(5, 0x80)


@cocotb.test()
async def test_per_sm_cfg_banks_rw(dut):
    """EXEC/PINCTRL banks are independent per SM."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    axi = make_axil(dut)

    e0 = pack_execctrl(wrap_top=1, side_en=0)
    e1 = pack_execctrl(wrap_top=3, side_en=1)
    p0 = pack_pinctrl(set_count=1, set_base=0)
    p1 = pack_pinctrl(set_count=1, set_base=1)

    await csr_write(axi, EXEC0, e0)
    await csr_write(axi, EXEC1, e1)
    await csr_write(axi, PIN0, p0)
    await csr_write(axi, PIN1, p1)

    assert await csr_read(axi, EXEC0) == e0
    assert await csr_read(axi, EXEC1) == e1
    assert await csr_read(axi, PIN0) == p0
    assert await csr_read(axi, PIN1) == p1


@cocotb.test()
async def test_independent_set_pins(dut):
    """SM0 toggles gpio0, SM1 toggles gpio1 with different PINCTRL set_base."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    axi = make_axil(dut)
    await load_square(axi)

    wrap = pack_execctrl(wrap_bottom=0, wrap_top=1)
    await csr_write(axi, EXEC0, wrap)
    await csr_write(axi, EXEC1, wrap)
    await csr_write(axi, PIN0, pack_pinctrl(set_count=1, set_base=0))
    await csr_write(axi, PIN1, pack_pinctrl(set_count=1, set_base=1))
    await csr_write(axi, CLKDIV0, pack_clkdiv(1))
    await csr_write(axi, CLKDIV1, pack_clkdiv(1))
    await csr_write(axi, CTRL, 0x3)  # enable both

    seen0 = seen1 = False
    for _ in range(40):
        await RisingEdge(dut.clk)
        g = int(dut.gpio_out.value)
        if (g >> 0) & 1:
            seen0 = True
        if (g >> 1) & 1:
            seen1 = True
        if seen0 and seen1:
            break
    assert seen0 and seen1, "expected independent SET on gpio0 and gpio1"


@cocotb.test()
async def test_sm0_rate_with_div(dut):
    """Only SM0 enabled; INT=2 doubles square period vs INT=1."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    axi = make_axil(dut)
    await load_square(axi)
    await csr_write(axi, EXEC0, pack_execctrl(wrap_top=1))
    await csr_write(axi, PIN0, pack_pinctrl(set_count=1))
    await csr_write(axi, CLKDIV0, pack_clkdiv(2))
    await csr_write(axi, CTRL, 0x1)  # SM0 only

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

    assert len(edges) >= 2
    period = edges[1] - edges[0]
    assert abs(period - 8) <= 1, f"expected≈8, got {period}"


@cocotb.test()
async def test_clkdiv_restart_sc(dut):
    """CTRL.CLKDIV_RESTART is self-clearing on readback."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    axi = make_axil(dut)

    await csr_write(axi, CTRL, (0x3 << 8))  # restart SM0+SM1
    await RisingEdge(dut.clk)
    ctrl = await csr_read(axi, CTRL)
    assert (ctrl >> 8) & 0xF == 0
