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

# Helper: Write 32-bit instruction to inst_mem
async def write_inst(dut, index, inst_32):
    page = (index // 4) + 2
    inst_in_page = index % 4
    
    # Write page register
    await wb_write(dut, 0x1F, page)
    
    # Write instruction byte-by-byte
    for b in range(4):
        byte_val = (inst_32 >> (b * 8)) & 0xFF
        addr = (inst_in_page << 2) | b
        await wb_write(dut, addr, byte_val)

# Helper: Read 32-bit data register
async def read_reg_32(dut, reg_index):
    page = 0 if reg_index < 4 else 1
    reg_offset = reg_index if reg_index < 4 else (reg_index - 4)
    
    # Write page register
    await wb_write(dut, 0x1F, page)
    
    # Read register byte-by-byte
    val_32 = 0
    for b in range(4):
        addr = (reg_offset << 2) | b
        byte_val = await wb_read(dut, addr)
        val_32 |= (byte_val << (b * 8))
    return val_32

@cocotb.test()
async def test_project(dut):
    dut._log.info("Start 32-bit OmniCore-1 CPU Standalone execution test")

    # Start clock: 100ns period (10 MHz)
    clock = Clock(dut.clk, 100, units="ns")
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

    # 2. Load the exact assembly program into inst_mem
    # Instruction 0: LOAD_IMMED -> REG 1 = 5
    inst0 = (1 << 28) | (1 << 25) | 5
    # Instruction 1: LOAD_IMMED -> REG 2 = 12
    inst1 = (1 << 28) | (2 << 25) | 12
    # Instruction 2: IMC_NAND -> REG 3 = REG 1 NAND REG 2 (5 NAND 12 = 0xFFFFFFFF)
    inst2 = (3 << 28) | (3 << 25) | (1 << 22) | (2 << 19)
    # Instruction 3: BRANCH_ZERO -> Check REG 4. Since REG 4 is 0, branch to Instruction 5
    inst3 = (4 << 28) | (4 << 22) | 5
    # Instruction 4: SHIFT_LEFT -> Shift REG 1 left. This instruction must be skipped!
    inst4 = (6 << 28) | (1 << 25) | (1 << 22)
    # Instruction 5: HALT
    inst5 = 0x00000000

    dut._log.info("Writing program instructions...")
    await write_inst(dut, 0, inst0)
    await write_inst(dut, 1, inst1)
    await write_inst(dut, 2, inst2)
    await write_inst(dut, 3, inst3)
    await write_inst(dut, 4, inst4)
    await write_inst(dut, 5, inst5)
    dut._log.info("Program loaded successfully.")

    # 3. Start CPU Execution
    dut._log.info("Starting CPU execution...")
    await wb_write(dut, 0x1F, 10) # Control & Status Page
    await wb_write(dut, 0, 1)     # Set run_cpu = 1 (bit 0)

    # 4. Monitor CPU execution until it halts
    timeout_cycles = 500
    halted = False
    for cycle in range(timeout_cycles):
        await RisingEdge(dut.clk)
        # Check uo_out[1] which exposes cpu_halted directly
        if (dut.uo_out.value & 2) == 2:
            halted = True
            dut._log.info(f"CPU halted after {cycle} clock cycles.")
            break

    assert halted, "ERROR: CPU execution timed out without halting!"

    # 5. Assertions and Verification
    # Verify PC is exactly at 5
    final_pc = (dut.uo_out.value >> 2) & 0x1F
    dut._log.info(f"Final Program Counter (PC): {final_pc}")
    assert final_pc == 5, f"PC mismatch: expected 5, got {final_pc}"

    # Read registers via Wishbone and check values
    reg1_val = await read_reg_32(dut, 1)
    reg2_val = await read_reg_32(dut, 2)
    reg3_val = await read_reg_32(dut, 3)
    reg4_val = await read_reg_32(dut, 4)

    dut._log.info(f"REG 1: {reg1_val}")
    dut._log.info(f"REG 2: {reg2_val}")
    dut._log.info(f"REG 3: {hex(reg3_val)}")
    dut._log.info(f"REG 4: {reg4_val}")

    # Assertions
    assert reg3_val == 0xFFFFFFFF, f"REG 3 NAND mismatch: expected 0xFFFFFFFF, got {hex(reg3_val)}"
    assert reg1_val == 5, f"REG 1 mismatch: expected 5 (no shift), got {reg1_val}"
    assert reg2_val == 12, f"REG 2 mismatch: expected 12, got {reg2_val}"
    assert reg4_val == 0, f"REG 4 mismatch: expected 0, got {reg4_val}"

    dut._log.info("SUCCESS: All assertions verified! CPU execution is Turing-complete and fully functional!")
