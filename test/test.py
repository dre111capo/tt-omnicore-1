# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: MIT

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

@cocotb.test()
async def test_project(dut):
    dut._log.info("Start OmniCore-1 test")

    # Impostiamo il clock a 20ns period (50 MHz)
    clock = Clock(dut.clk, 20, units="ns")
    cocotb.start_soon(clock.start())

    # 1. Reset iniziale attivo
    dut._log.info("Reset attivo")
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    
    # Disattivazione reset
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 1)

    # 2. Scrittura RAM (mode = 0, data_in = 4'b1100 -> ui_in = 8'b00011000)
    dut._log.info("Scrittura RAM: data_in = 1100, mode = 0")
    # ui_in[0] = 0 (mode), ui_in[4:1] = 4'b1100 (12 decimal) -> total ui_in = 12 << 1 = 24
    dut.ui_in.value = 24
    await ClockCycles(dut.clk, 1)
    
    # Verifica che q_out (uo_out[3:0]) sia 4'b1100 (12 decimal)
    assert dut.uo_out.value & 0xF == 12, f"Errore scrittura RAM: atteso 12, ottenuto {dut.uo_out.value & 0xF}"

    # 3. Calcolo In-Memory AND (mode = 1, data_in = 4'b1010 -> ui_in = 8'b00010101)
    dut._log.info("Calcolo In-Memory: data_in = 1010, mode = 1")
    # ui_in[0] = 1 (mode), ui_in[4:1] = 4'b1010 (10 decimal) -> total ui_in = (10 << 1) | 1 = 21
    dut.ui_in.value = 21
    await ClockCycles(dut.clk, 1)

    # Verifica che q_out (uo_out[3:0]) sia 4'b1100 AND 4'b1010 = 4'b1000 (8 decimal)
    assert dut.uo_out.value & 0xF == 8, f"Errore calcolo IMC AND: atteso 8, ottenuto {dut.uo_out.value & 0xF}"

    dut._log.info("SUCCESSO: Il registro OmniCore a 4-bit ha superato tutti i test del simulatore!")
