# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: MIT

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, FallingEdge

# Helper: Wishbone Write Transaction
async def wb_write(dut, addr, val):
    # ui_in[0] = stb, ui_in[1] = cyc, ui_in[2] = we, ui_in[7:3] = addr
    dut.ui_in.value = (addr << 3) | (1 << 2) | (1 << 1) | (1 << 0)
    dut.uio_in.value = val
    
    # Wait for ack (uo_out[0]) to be asserted
    while True:
        await RisingEdge(dut.clk)
        if (dut.uo_out.value & 1) == 1:
            break
            
    # Deassert on next falling edge
    await FallingEdge(dut.clk)
    dut.ui_in.value = 0
    dut.uio_in.value = 0

# Helper: Wishbone Read Transaction
async def wb_read(dut, addr):
    # ui_in[0] = stb, ui_in[1] = cyc, ui_in[2] = we (0), ui_in[7:3] = addr
    dut.ui_in.value = (addr << 3) | (0 << 2) | (1 << 1) | (1 << 0)
    
    # Wait for ack (uo_out[0]) to be asserted
    while True:
        await RisingEdge(dut.clk)
        if (dut.uo_out.value & 1) == 1:
            val = int(dut.uio_out.value)
            break
            
    # Deassert on next falling edge
    await FallingEdge(dut.clk)
    dut.ui_in.value = 0
    return val

# Helper: Write 64-bit register byte-by-byte
async def write_reg_64(dut, base_addr, val_64):
    for i in range(8):
        byte_val = (val_64 >> (i * 8)) & 0xFF
        await wb_write(dut, base_addr + i, byte_val)

# Helper: Read 64-bit register byte-by-byte
async def read_reg_64(dut, base_addr):
    val_64 = 0
    for i in range(8):
        byte_val = await wb_read(dut, base_addr + i)
        val_64 |= (byte_val << (i * 8))
    return val_64

@cocotb.test()
async def test_project(dut):
    dut._log.info("Start 64-bit OmniCore-1 Wishbone BNN test")

    # Start clock: 20ns period (50 MHz)
    clock = Clock(dut.clk, 20, units="ns")
    cocotb.start_soon(clock.start())

    # 1. Reset Sequence
    dut._log.info("Applying Reset...")
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)
    dut._log.info("Reset Deasserted.")

    # 2. Test Write/Read of 64-bit Register (REG_DATA_IN)
    test_val1 = 0xCAFEBABE12345678
    dut._log.info(f"Writing 64-bit test value: {hex(test_val1)} to REG_DATA_IN")
    await write_reg_64(dut, 0x00, test_val1)
    
    dut._log.info("Reading back 64-bit value from REG_DATA_IN...")
    read_val1 = await read_reg_64(dut, 0x00)
    assert read_val1 == test_val1, f"REG_DATA_IN mismatch: wrote {hex(test_val1)}, got {hex(read_val1)}"
    dut._log.info("REG_DATA_IN verification passed.")

    # 3. Test Load data_in into q_reg and verify Popcount
    dut._log.info("Triggering Load Data into IMC cells (q_reg)...")
    await wb_write(dut, 0x10, 4)  # load_data = 1 (bit 2)
    await ClockCycles(dut.clk, 2)  # Allow operation to execute

    dut._log.info("Reading q_reg state...")
    q_val = await read_reg_64(dut, 0x11)
    assert q_val == test_val1, f"q_reg load mismatch: expected {hex(test_val1)}, got {hex(q_val)}"

    # Check live Popcount output on uo_out[7:1]
    # Expected popcount of 0xCAFEBABE12345678 is 35 (0b100011)
    live_popcount = (dut.uo_out.value >> 1) & 0x7F
    assert live_popcount == 35, f"Live Popcount mismatch: expected 35, got {live_popcount}"
    
    # Check Popcount via Wishbone register read (REG_POPCOUNT at 0x19)
    reg_popcount = await wb_read(dut, 0x19)
    assert reg_popcount == 35, f"Register Popcount mismatch: expected 35, got {reg_popcount}"
    dut._log.info("Load and Popcount verification passed.")

    # 4. Test In-Memory AND operation
    # data = 0xCAFEBABE12345678, operand = 0xF0F0F0F0F0F0F0F0
    # Expected AND = 0xC0F0B0B010305070
    operand_and = 0xF0F0F0F0F0F0F0F0
    expected_and = test_val1 & operand_and
    
    dut._log.info(f"Loading operand {hex(operand_and)} into REG_OP_IN")
    await write_reg_64(dut, 0x08, operand_and)
    
    dut._log.info("Triggering IMC AND operation...")
    await wb_write(dut, 0x10, 1)  # run_imc = 1 (bit 0), mode_reg = 0 (bit 1)
    await ClockCycles(dut.clk, 2)
    
    q_val = await read_reg_64(dut, 0x11)
    assert q_val == expected_and, f"IMC AND mismatch: expected {hex(expected_and)}, got {hex(q_val)}"
    dut._log.info("IMC AND operation verification passed.")

    # 5. Test In-Memory XNOR (BNN logic)
    # Let's load q_reg with 0xAAAAAAAAAAAAAAAA (all alternating 10)
    # Let's load op_in with 0x5555555555555555 (all alternating 01)
    # XNOR of opposite bits is 0. Expected result = 0x0000000000000000, Popcount = 0
    val_xnor_q = 0xAAAAAAAAAAAAAAAA
    val_xnor_op = 0x5555555555555555
    
    dut._log.info("Loading q_reg directly for XNOR test...")
    await write_reg_64(dut, 0x11, val_xnor_q)
    await write_reg_64(dut, 0x08, val_xnor_op)
    
    dut._log.info("Triggering IMC XNOR (BNN) operation (complementary inputs)...")
    await wb_write(dut, 0x10, 3)  # run_imc = 1, mode_reg = 1 (XNOR)
    await ClockCycles(dut.clk, 2)
    
    q_val = await read_reg_64(dut, 0x11)
    assert q_val == 0, f"IMC XNOR complementary mismatch: expected 0, got {hex(q_val)}"
    
    reg_popcount = await wb_read(dut, 0x19)
    assert reg_popcount == 0, f"IMC XNOR popcount mismatch: expected 0, got {reg_popcount}"
    dut._log.info("IMC XNOR complementary test passed.")

    # Test XNOR with matching inputs
    # q_reg = 0xAAAAAAAAAAAAAAAA, op_in = 0xAAAAAAAAAAAAAAAA
    # XNOR of matching bits is 1. Expected result = 0xFFFFFFFFFFFFFFFF, Popcount = 64
    dut._log.info("Loading matching values for XNOR test...")
    await write_reg_64(dut, 0x11, val_xnor_q)
    await write_reg_64(dut, 0x08, val_xnor_q)
    
    dut._log.info("Triggering IMC XNOR (BNN) operation (matching inputs)...")
    await wb_write(dut, 0x10, 3)  # run_imc = 1, mode_reg = 1 (XNOR)
    await ClockCycles(dut.clk, 2)
    
    q_val = await read_reg_64(dut, 0x11)
    assert q_val == 0xFFFFFFFFFFFFFFFF, f"IMC XNOR matching mismatch: expected 0xFFFFFFFFFFFFFFFF, got {hex(q_val)}"
    
    reg_popcount = await wb_read(dut, 0x19)
    assert reg_popcount == 64, f"IMC XNOR matching popcount mismatch: expected 64, got {reg_popcount}"
    dut._log.info("IMC XNOR matching test passed.")

    dut._log.info("SUCCESS: All 64-bit Wishbone IMC BNN Accelerator tests passed successfully!")
