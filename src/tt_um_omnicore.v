`timescale 1ns / 1ps
`default_nettype none

module tt_um_omnicore (
    input  wire [7:0] ui_in,    // Dedicated inputs: Wishbone control & address
    output wire [7:0] uo_out,   // Dedicated outputs: CPU state & PC
    input  wire [7:0] uio_in,   // IOs: Input path (Wishbone write data)
    output wire [7:0] uio_out,  // IOs: Output path (Wishbone read data)
    output wire [7:0] uio_oe,   // IOs: Enable path (active high)
    input  wire       ena,      // chip enable (not used internally)
    input  wire       clk,      // clock
    input  wire       rst_n     // reset (active low)
);

    // Map Tiny Tapeout pins to Wishbone Slave interface signals
    wire        wb_clk_i  = clk;
    wire        wb_rst_i  = ~rst_n;      // Convert active-low reset to active-high Wishbone reset
    wire        wbs_stb_i = ui_in[0];     // Strobe
    wire        wbs_cyc_i = ui_in[1];     // Cycle
    wire        wbs_we_i  = ui_in[2];     // Write Enable
    wire [4:0]  wbs_adr_i = ui_in[7:3];   // 5-bit Address (0-31)
    wire [7:0]  wbs_dat_i = uio_in;       // 8-bit Data Input

    // Wishbone Slave outputs
    reg         wbs_ack_o;
    reg  [7:0]  wbs_dat_o;

    // Wishbone Page Register for Multiplexing Address Space
    reg  [7:0]  addr_page;

    // Unified Data Registers (8 x 32-bit)
    reg  [31:0] mem_reg [7:0];

    // Dedicated Instruction Memory (32 x 32-bit instructions)
    reg  [31:0] inst_mem [31:0];

    // CPU Control and Status registers
    reg         run_cpu;
    reg         cpu_halted;
    reg         reset_pc;
    reg  [4:0]  pc;

    // FSM States
    reg  [2:0]  state;
    localparam STATE_IDLE       = 3'd0;
    localparam STATE_FETCH      = 3'd1;
    localparam STATE_DECODE     = 3'd2;
    localparam STATE_EXECUTE_OP = 3'd3;
    localparam STATE_WRITE_BACK = 3'd4;

    // Instruction Decode Registers
    reg  [31:0] instruction;
    reg  [3:0]  opcode;
    reg  [2:0]  dest;
    reg  [2:0]  src1;
    reg  [2:0]  src2;
    reg  [4:0]  immediate;

    // Execution cycle counter (for 2-cycle IMC NAND/NOR execution)
    reg  [1:0]  exec_count;

    // Connect dedicated outputs
    assign uo_out[0]   = wbs_ack_o;
    assign uo_out[1]   = cpu_halted;
    assign uo_out[6:2] = pc;
    assign uo_out[7]   = run_cpu;

    // Bidirectional data bus control
    // Drive uio outputs only during a Wishbone read cycle
    assign uio_oe  = (wbs_cyc_i && wbs_stb_i && !wbs_we_i) ? 8'hFF : 8'h00;
    assign uio_out = wbs_dat_o;

    // Wishbone Handshake (Acknowledge) Logic
    always @(posedge wb_clk_i or posedge wb_rst_i) begin
        if (wb_rst_i) begin
            wbs_ack_o <= 1'b0;
        end else begin
            if (wbs_cyc_i && wbs_stb_i && !wbs_ack_o) begin
                wbs_ack_o <= 1'b1;
            end else begin
                wbs_ack_o <= 1'b0;
            end
        end
    end

    // Wishbone Write Transactions
    integer k;
    always @(posedge wb_clk_i or posedge wb_rst_i) begin
        if (wb_rst_i) begin
            addr_page <= 8'd0;
            reset_pc  <= 1'b0;
            // Clear data registers
            for (k = 0; k < 8; k = k + 1) begin
                mem_reg[k] <= 32'd0;
            end
            // Clear instruction memory (all HALT)
            for (k = 0; k < 32; k = k + 1) begin
                inst_mem[k] <= 32'd0;
            end
        end else begin
            // Reset PC trigger (self-clearing)
            if (reset_pc) begin
                reset_pc <= 1'b0;
            end

            // Process Wishbone Write
            if (wbs_cyc_i && wbs_stb_i && wbs_we_i && !wbs_ack_o) begin
                if (wbs_adr_i == 5'h1F) begin
                    addr_page <= wbs_dat_i;
                end else begin
                    case (addr_page)
                        8'd0: begin // Registers 0 to 3
                            if (wbs_adr_i[4:2] == 3'd0 || wbs_adr_i[4:2] == 3'd1 || wbs_adr_i[4:2] == 3'd2 || wbs_adr_i[4:2] == 3'd3) begin
                                mem_reg[wbs_adr_i[3:2]][wbs_adr_i[1:0] * 8 +: 8] <= wbs_dat_i;
                            end
                        end
                        8'd1: begin // Registers 4 to 7
                            if (wbs_adr_i[4:2] == 3'd0 || wbs_adr_i[4:2] == 3'd1 || wbs_adr_i[4:2] == 3'd2 || wbs_adr_i[4:2] == 3'd3) begin
                                mem_reg[4 + wbs_adr_i[3:2]][wbs_adr_i[1:0] * 8 +: 8] <= wbs_dat_i;
                            end
                        end
                        // Instructions 0 to 31 (grouped in pages of 4 instructions = 16 bytes each)
                        8'd2, 8'd3, 8'd4, 8'd5, 8'd6, 8'd7, 8'd8, 8'd9: begin
                            if (wbs_adr_i[4:2] == 3'd0 || wbs_adr_i[4:2] == 3'd1 || wbs_adr_i[4:2] == 3'd2 || wbs_adr_i[4:2] == 3'd3) begin
                                inst_mem[(addr_page - 8'd2) * 4 + wbs_adr_i[3:2]][wbs_adr_i[1:0] * 8 +: 8] <= wbs_dat_i;
                            end
                        end
                        8'd10: begin // Control Register
                            if (wbs_adr_i == 5'd0) begin
                                // Bit 0 is run_cpu. When written with 1, it starts the CPU.
                                // It will be cleared inside the FSM when execution hits HALT.
                                // If the CPU is already running, writing 0 stops it.
                                if (wbs_dat_i[0]) begin
                                    // Start CPU if not running
                                end
                                reset_pc <= wbs_dat_i[1];
                            end
                        end
                        default: ;
                    endcase
                end
            end
        end
    end

    // Wishbone Read Transactions (Combinational Address Decode)
    always @(*) begin
        wbs_dat_o = 8'h00;
        if (wbs_adr_i == 5'h1F) begin
            wbs_dat_o = addr_page;
        end else begin
            case (addr_page)
                8'd0: begin
                    wbs_dat_o = mem_reg[wbs_adr_i[3:2]][wbs_adr_i[1:0] * 8 +: 8];
                end
                8'd1: begin
                    wbs_dat_o = mem_reg[4 + wbs_adr_i[3:2]][wbs_adr_i[1:0] * 8 +: 8];
                end
                8'd2, 8'd3, 8'd4, 8'd5, 8'd6, 8'd7, 8'd8, 8'd9: begin
                    wbs_dat_o = inst_mem[(addr_page - 8'd2) * 4 + wbs_adr_i[3:2]][wbs_adr_i[1:0] * 8 +: 8];
                end
                8'd10: begin
                    case (wbs_adr_i)
                        5'd0: wbs_dat_o = {6'b000000, reset_pc, run_cpu};
                        5'd1: wbs_dat_o = {2'b00, pc, cpu_halted};
                        default: wbs_dat_o = 8'h00;
                    endcase
                end
                default: wbs_dat_o = 8'h00;
            endcase
        end
    end

    // Standalone CPU Execution FSM
    always @(posedge wb_clk_i or posedge wb_rst_i) begin
        if (wb_rst_i) begin
            pc         <= 5'd0;
            state      <= STATE_IDLE;
            cpu_halted <= 1'b0;
            run_cpu    <= 1'b0;
            opcode     <= 4'd0;
            dest       <= 3'd0;
            src1       <= 3'd0;
            src2       <= 3'd0;
            immediate  <= 5'd0;
            exec_count <= 2'd0;
        end else begin
            // Manual CPU start via Wishbone write to Page 10, Address 0
            if (wbs_cyc_i && wbs_stb_i && wbs_we_i && !wbs_ack_o && (wbs_adr_i == 5'd0) && (addr_page == 8'd10)) begin
                run_cpu <= wbs_dat_i[0];
                if (wbs_dat_i[0] && (state == STATE_IDLE)) begin
                    state      <= STATE_FETCH;
                    cpu_halted <= 1'b0;
                    pc         <= 5'd0;
                end
            end

            // Reset PC signal overrides PC value
            if (reset_pc) begin
                pc <= 5'd0;
            end

            // FSM transitions
            case (state)
                STATE_IDLE: begin
                    if (run_cpu) begin
                        state      <= STATE_FETCH;
                        cpu_halted <= 1'b0;
                        pc         <= 5'd0;
                    end
                end

                STATE_FETCH: begin
                    instruction <= inst_mem[pc];
                    state       <= STATE_DECODE;
                end

                STATE_DECODE: begin
                    opcode     <= instruction[31:28];
                    dest       <= instruction[27:25];
                    src1       <= instruction[24:22];
                    src2       <= instruction[21:19];
                    immediate  <= instruction[4:0];
                    exec_count <= 2'd0;
                    state      <= STATE_EXECUTE_OP;
                end

                STATE_EXECUTE_OP: begin
                    case (opcode)
                        // NAND and NOR operations require 2 execution cycles for timing closure
                        4'h2, 4'h3: begin
                            if (exec_count == 2'd1) begin
                                state <= STATE_WRITE_BACK;
                            end else begin
                                exec_count <= exec_count + 1;
                            end
                        end
                        default: begin
                            state <= STATE_WRITE_BACK;
                        end
                    endcase
                end

                STATE_WRITE_BACK: begin
                    case (opcode)
                        4'h0: begin // HALT
                            run_cpu    <= 1'b0;
                            cpu_halted <= 1'b1;
                            state      <= STATE_IDLE;
                        end

                        4'h1: begin // LOAD_IMMED
                            mem_reg[dest] <= {27'd0, immediate};
                            pc            <= pc + 1;
                            state         <= STATE_FETCH;
                        end

                        4'h2: begin // IMC_NOR
                            mem_reg[dest] <= ~(mem_reg[src1] | mem_reg[src2]);
                            pc            <= pc + 1;
                            state         <= STATE_FETCH;
                        end

                        4'h3: begin // IMC_NAND
                            mem_reg[dest] <= ~(mem_reg[src1] & mem_reg[src2]);
                            pc            <= pc + 1;
                            state         <= STATE_FETCH;
                        end

                        4'h4: begin // BRANCH_ZERO
                            if (mem_reg[src1] == 32'd0) begin
                                pc <= immediate;
                            end else begin
                                pc <= pc + 1;
                            end
                            state <= STATE_FETCH;
                        end

                        4'h5: begin // BRANCH_NEG
                            if (mem_reg[src1][31] == 1'b1) begin
                                pc <= immediate;
                            end else begin
                                pc <= pc + 1;
                            end
                            state <= STATE_FETCH;
                        end

                        4'h6: begin // SHIFT_LEFT
                            mem_reg[dest] <= mem_reg[src1] << 1;
                            pc            <= pc + 1;
                            state         <= STATE_FETCH;
                        end

                        4'h7: begin // SHIFT_RIGHT
                            mem_reg[dest] <= mem_reg[src1] >> 1;
                            pc            <= pc + 1;
                            state         <= STATE_FETCH;
                        end

                        default: begin
                            pc    <= pc + 1;
                            state <= STATE_FETCH;
                        end
                    endcase
                end

                default: begin
                    state <= STATE_IDLE;
                end
            endcase
        end
    end

    // Waveform dump for simulation debug
    `ifdef COCOTB_SIM
    initial begin
        $dumpfile("waveform.vcd");
        $dumpvars(0, tt_um_omnicore);
    end
    `endif

endmodule
