#include <iostream>
#include <iomanip>
#include <memory>
#include "Vtt_um_omnicore_enterprise.h"
#include "verilated.h"

// Helper function to perform a 64-bit Wishbone Write transaction
void wb_write(Vtt_um_omnicore_enterprise* top, uint64_t addr, uint64_t data) {
    top->wb_cyc_i = 1;
    top->wb_stb_i = 1;
    top->wb_we_i  = 1;
    top->wb_adr_i = addr;
    top->wb_dat_i = data;
    
    // Cycle clock until ACK
    int timeout = 0;
    while (!top->wb_ack_o && timeout < 20) {
        top->clk = 1;
        top->eval();
        top->clk = 0;
        top->eval();
        timeout++;
    }
    
    top->wb_cyc_i = 0;
    top->wb_stb_i = 0;
    top->wb_we_i  = 0;
    top->eval();
    
    // Clear ACK
    top->clk = 1;
    top->eval();
    top->clk = 0;
    top->eval();
}

// Helper function to perform a 64-bit Wishbone Read transaction
uint64_t wb_read(Vtt_um_omnicore_enterprise* top, uint64_t addr) {
    top->wb_cyc_i = 1;
    top->wb_stb_i = 1;
    top->wb_we_i  = 0;
    top->wb_adr_i = addr;
    
    // Cycle clock until ACK
    int timeout = 0;
    while (!top->wb_ack_o && timeout < 20) {
        top->clk = 1;
        top->eval();
        top->clk = 0;
        top->eval();
        timeout++;
    }
    
    uint64_t data = top->wb_dat_o;
    
    top->wb_cyc_i = 0;
    top->wb_stb_i = 0;
    top->eval();
    
    // Clear ACK
    top->clk = 1;
    top->eval();
    top->clk = 0;
    top->eval();
    
    return data;
}

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    auto top = std::make_unique<Vtt_um_omnicore_enterprise>();

    std::cout << "==================================================" << std::endl;
    std::cout << "  OMNICORE-ENTERPRISE 64-BIT HARDWARE EMULATION  " << std::endl;
    std::cout << "==================================================" << std::endl;

    // Reset sequence
    top->clk = 0;
    top->rst_n = 0;
    top->wb_cyc_i = 0;
    top->wb_stb_i = 0;
    top->wb_we_i = 0;
    top->wb_adr_i = 0;
    top->wb_dat_i = 0;
    
    for (int i = 0; i < 10; ++i) {
        top->clk = 1;
        top->eval();
        top->clk = 0;
        top->eval();
    }
    
    top->rst_n = 1;
    top->eval();
    std::cout << "[EMU-ENT] Enterprise Hardware Reset Complete." << std::endl;

    // Write 64-bit program into inst_mem via 64-bit bus
    // Instruction memory starts at 0x0100. Each instruction is 8 bytes.
    
    // Inst 0: LOAD_IMMED_64 REG_1, 0x55555555555
    wb_write(top.get(), 0x0100 + 0, 0x1080005555555555ULL);
    
    // Inst 1: LOAD_IMMED_64 REG_2, 0x33333333333
    wb_write(top.get(), 0x0100 + 8, 0x1100003333333333ULL);
    
    // Inst 2: OP_IMC_NAND_64 REG_3, REG_1, REG_2
    wb_write(top.get(), 0x0100 + 16, 0x3184400000000000ULL);
    
    // Inst 3: BRANCH_ZERO_64 REG_4, 5
    wb_write(top.get(), 0x0100 + 24, 0x5200000000000005ULL);
    
    // Inst 4: OP_ADD_64 REG_1, REG_1, REG_1 (skipped by branch)
    wb_write(top.get(), 0x0100 + 32, 0x2084200000000000ULL);
    
    // Inst 5: HALT
    wb_write(top.get(), 0x0100 + 40, 0x0000000000000000ULL);

    std::cout << "[EMU-ENT] Enterprise 64-bit program written to virtual RAM." << std::endl;

    // Start CPU: write run_cpu = 1 to control register 0x0300
    wb_write(top.get(), 0x0300, 1);
    std::cout << "[EMU-ENT] CPU execution started." << std::endl;

    int cycle = 0;
    bool halted = false;
    
    while (cycle < 1000) {
        top->clk = 1;
        top->eval();
        top->clk = 0;
        top->eval();
        
        cycle++;

        // Read control status directly from top-level output pins
        bool run = top->run_cpu;
        bool halt = top->cpu_halted;

        if (cycle % 5 == 0) {
            std::cout << "[EMU-ENT] Cycle: " << std::setw(3) << cycle 
                      << " | run_cpu: " << run 
                      << " | cpu_halted: " << halt 
                      << std::endl;
        }

        if (halt) {
            std::cout << "[EMU-ENT] CPU Halted cleanly after " << cycle << " clock cycles." << std::endl;
            halted = true;
            break;
        }
    }

    if (!halted) {
        std::cerr << "[ERROR-ENT] Emulation timeout: CPU failed to halt." << std::endl;
        return 1;
    }

    // Read Registers REG 1, REG 2, REG 3, REG 4 via 64-bit bus
    // Reg space starts at 0x0000. Each register is 8 bytes.
    uint64_t reg1 = wb_read(top.get(), 0x0000 + 8);  // REG 1
    uint64_t reg2 = wb_read(top.get(), 0x0000 + 16); // REG 2
    uint64_t reg3 = wb_read(top.get(), 0x0000 + 24); // REG 3
    uint64_t reg4 = wb_read(top.get(), 0x0000 + 32); // REG 4

    // Expected value for REG 3:
    // 0x5555555555 & 0x3333333333 = 0x1111111111 (ten 1s)
    // ~0x0000001111111111 = 0xffffffeeeeeeeeee
    uint64_t expected_nand = ~0x0000001111111111ULL;

    std::cout << "==================================================" << std::endl;
    std::cout << "  EMULATION VERIFICATION RESULTS" << std::endl;
    std::cout << "==================================================" << std::endl;
    std::cout << "REG 1 (Expected: 0x5555555555):           0x" << std::hex << std::setw(16) << std::setfill('0') << reg1 << std::endl;
    std::cout << "REG 2 (Expected: 0x3333333333):           0x" << std::hex << std::setw(16) << std::setfill('0') << reg2 << std::endl;
    std::cout << "REG 3 (Expected: 0x" << std::hex << expected_nand << "): 0x" << reg3 << std::endl;
    std::cout << "REG 4 (Expected: 0x0):                     0x" << reg4 << std::endl;
    std::cout << "==================================================" << std::endl;

    if (reg1 == 0x5555555555ULL && reg2 == 0x3333333333ULL && reg3 == expected_nand && reg4 == 0) {
        std::cout << "[SUCCESS] Enterprise 64-bit Hardware Emulation Passed!" << std::endl;
        return 0;
    } else {
        std::cerr << "[FAILURE] Register verification mismatch." << std::endl;
        return 2;
    }
}
