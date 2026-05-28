#include <iostream>
#include <iomanip>
#include <memory>
#include "Vtt_um_omnicore.h"
#include "verilated.h"

// Helper function to perform a Wishbone Write transaction
void wb_write(Vtt_um_omnicore* top, uint8_t addr, uint8_t data) {
    // ui_in[0] = stb, ui_in[1] = cyc, ui_in[2] = we, ui_in[7:3] = addr
    top->ui_in = (addr << 3) | (1 << 2) | (1 << 1) | (1 << 0);
    top->uio_in = data;
    
    // Cycle clock until ACK (uo_out[0]) goes high
    int timeout = 0;
    while (!(top->uo_out & 0x01) && timeout < 20) {
        top->clk = 1;
        top->eval();
        top->clk = 0;
        top->eval();
        timeout++;
    }
    
    // Deassert Wishbone control lines
    top->ui_in = 0;
    top->eval();
    
    // Clear ACK
    top->clk = 1;
    top->eval();
    top->clk = 0;
    top->eval();
}

// Helper function to perform a Wishbone Read transaction
uint8_t wb_read(Vtt_um_omnicore* top, uint8_t addr) {
    // ui_in[0] = stb, ui_in[1] = cyc, ui_in[2] = we (0 for read), ui_in[7:3] = addr
    top->ui_in = (addr << 3) | (0 << 2) | (1 << 1) | (1 << 0);
    
    // Cycle clock until ACK (uo_out[0]) goes high
    int timeout = 0;
    while (!(top->uo_out & 0x01) && timeout < 20) {
        top->clk = 1;
        top->eval();
        top->clk = 0;
        top->eval();
        timeout++;
    }
    
    uint8_t data = top->uio_out;
    
    // Deassert Wishbone control lines
    top->ui_in = 0;
    top->eval();
    
    // Clear ACK
    top->clk = 1;
    top->eval();
    top->clk = 0;
    top->eval();
    
    return data;
}

// Set Wishbone Page Register
void set_page(Vtt_um_omnicore* top, uint8_t page) {
    wb_write(top, 0x1F, page);
}

// Helper to write a 32-bit word byte-by-byte (little-endian)
void write_word(Vtt_um_omnicore* top, uint8_t addr_offset, uint32_t val) {
    wb_write(top, addr_offset + 0, (val >> 0) & 0xFF);
    wb_write(top, addr_offset + 1, (val >> 8) & 0xFF);
    wb_write(top, addr_offset + 2, (val >> 16) & 0xFF);
    wb_write(top, addr_offset + 3, (val >> 24) & 0xFF);
}

// Helper to read a 32-bit word byte-by-byte (little-endian)
uint32_t read_word(Vtt_um_omnicore* top, uint8_t addr_offset) {
    uint32_t val = 0;
    val |= ((uint32_t)wb_read(top, addr_offset + 0)) << 0;
    val |= ((uint32_t)wb_read(top, addr_offset + 1)) << 8;
    val |= ((uint32_t)wb_read(top, addr_offset + 2)) << 16;
    val |= ((uint32_t)wb_read(top, addr_offset + 3)) << 24;
    return val;
}

int main(int argc, char** argv) {
    // Initialize Verilator context and top module
    Verilated::commandArgs(argc, argv);
    auto top = std::make_unique<Vtt_um_omnicore>();

    std::cout << "==================================================" << std::endl;
    std::cout << "  OMNICORE-1 STANDALONE CPU HARDWARE EMULATION" << std::endl;
    std::cout << "==================================================" << std::endl;

    // Reset Sequence
    top->clk = 0;
    top->rst_n = 0;
    top->ui_in = 0;
    top->uio_in = 0;
    top->ena = 1;
    
    for (int i = 0; i < 10; ++i) {
        top->clk = 1;
        top->eval();
        top->clk = 0;
        top->eval();
    }
    
    top->rst_n = 1;
    top->eval();
    std::cout << "[EMU] Hardware Reset Complete." << std::endl;

    // Write Program Instructions to Instruction Memory (pages 2 to 9)
    // Inst 0: LOAD_IMMED REG_1, 3
    set_page(top.get(), 2);
    write_word(top.get(), 0, 0x12000003);
    
    // Inst 1: LOAD_IMMED REG_2, 12
    write_word(top.get(), 4, 0x1400000C);
    
    // Inst 2: IMC_NAND REG_3, REG_1, REG_2
    write_word(top.get(), 8, 0x36500000);
    
    // Inst 3: BRANCH_ZERO REG_4, 5
    write_word(top.get(), 12, 0x48000005);
    
    // Inst 4: SHIFT_LEFT REG_1, REG_1 (skipped by branch)
    set_page(top.get(), 3);
    write_word(top.get(), 0, 0x62400000);
    
    // Inst 5: HALT
    write_word(top.get(), 4, 0x00000000);

    std::cout << "[EMU] Standalone ISA program successfully written to inst_mem via Wishbone." << std::endl;

    // Run CPU: Write run_cpu = 1 in page 10, register 0
    set_page(top.get(), 10);
    wb_write(top.get(), 0, 1);
    std::cout << "[EMU] CPU execution started (run_cpu flag asserted)." << std::endl;

    // Clock evaluation loop: monitor PC and CPU state
    int cycle = 0;
    bool halted = false;
    
    while (cycle < 1000) {
        top->clk = 1;
        top->eval();
        top->clk = 0;
        top->eval();
        
        cycle++;

        // Read outputs from uo_out
        // uo_out[0]: wbs_ack_o
        // uo_out[1]: cpu_halted
        // uo_out[6:2]: PC
        // uo_out[7]: run_cpu
        uint8_t uo = top->uo_out;
        bool cpu_run = (uo >> 7) & 0x01;
        bool cpu_halt = (uo >> 1) & 0x01;
        uint8_t pc = (uo >> 2) & 0x1F;

        if (cycle % 5 == 0) {
            std::cout << "[EMU] Cycle: " << std::setw(3) << cycle 
                      << " | PC: " << std::setw(2) << (int)pc 
                      << " | run_cpu: " << cpu_run 
                      << " | cpu_halted: " << cpu_halt 
                      << std::endl;
        }

        if (cpu_halt) {
            std::cout << "[EMU] CPU Halted cleanly at PC " << (int)pc << " after " << cycle << " clock cycles." << std::endl;
            halted = true;
            break;
        }
    }

    if (!halted) {
        std::cerr << "[ERROR] Emulation timeout: CPU failed to halt." << std::endl;
        return 1;
    }

    // Verify Registers: Read REG 1, REG 2, REG 3 (page 0) and REG 4 (page 1)
    set_page(top.get(), 0);
    uint32_t reg1 = read_word(top.get(), 4);  // REG 1 is at offset 4 (bytes 4-7)
    uint32_t reg2 = read_word(top.get(), 8);  // REG 2 is at offset 8 (bytes 8-11)
    uint32_t reg3 = read_word(top.get(), 12); // REG 3 is at offset 12 (bytes 12-15)

    set_page(top.get(), 1);
    uint32_t reg4 = read_word(top.get(), 0);  // REG 4 is at offset 0 of page 1

    std::cout << "==================================================" << std::endl;
    std::cout << "  EMULATION VERIFICATION RESULTS" << std::endl;
    std::cout << "==================================================" << std::endl;
    std::cout << "REG 1 (Expected: 3):          " << reg1 << std::endl;
    std::cout << "REG 2 (Expected: 12):         " << reg2 << std::endl;
    std::cout << "REG 3 (Expected: 0xFFFFFFFF): 0x" << std::hex << std::setw(8) << std::setfill('0') << reg3 << std::endl;
    std::cout << "REG 4 (Expected: 0):          " << std::dec << reg4 << std::endl;
    std::cout << "==================================================" << std::endl;

    if (reg1 == 3 && reg2 == 12 && reg3 == 0xFFFFFFFF && reg4 == 0) {
        std::cout << "[SUCCESS] Hardware Emulation Passed all checkmarks!" << std::endl;
        return 0;
    } else {
        std::cerr << "[FAILURE] Register verification mismatch." << std::endl;
        return 2;
    }
}
