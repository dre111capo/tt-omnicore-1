`timescale 1ns / 1ps
`default_nettype none

module tt_um_omnicore_enterprise (
    input  wire        clk,
    input  wire        rst_n,
    
    // Native 64-bit memory bus interface
    input  wire        wb_cyc_i,
    input  wire        wb_stb_i,
    input  wire        wb_we_i,
    input  wire [63:0] wb_adr_i,
    input  wire [63:0] wb_dat_i,
    output reg  [63:0] wb_dat_o,
    output reg         wb_ack_o,
    
    // CPU Status Outputs
    output reg         cpu_halted,
    output reg         run_cpu
);

    // FSM States
    reg [2:0] state;
    localparam STATE_IDLE       = 3'd0;
    localparam STATE_FETCH      = 3'd1;
    localparam STATE_DECODE     = 3'd2;
    localparam STATE_EXECUTE_OP = 3'd3;
    localparam STATE_WRITE_BACK = 3'd4;

    // Registers and Memories
    reg [63:0] mem_reg [31:0];      // 32 x 64-bit Data Registers
    reg [63:0] inst_mem [63:0];     // 64 x 64-bit Instruction Memory
    reg [63:0] pc;                  // 64-bit Program Counter

    // Instruction Decode Registers
    reg [63:0] instruction;
    reg [3:0]  opcode;
    reg [4:0]  dest;
    reg [4:0]  src1;
    reg [4:0]  src2;
    reg [63:0] immediate;           // Sign-extended 64-bit immediate

    // Execution counter for multi-cycle operations
    reg [1:0] exec_count;

    // Address Decode Wires
    wire is_reg_space   = (wb_adr_i >= 64'h0000) && (wb_adr_i < 64'h0100); // 32 regs * 8 bytes = 256 bytes
    wire is_inst_space  = (wb_adr_i >= 64'h0100) && (wb_adr_i < 64'h0300); // 64 insts * 8 bytes = 512 bytes
    wire is_ctrl_space  = (wb_adr_i == 64'h0300);

    // Wishbone Handshake (Acknowledge) Logic
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wb_ack_o <= 1'b0;
        end else begin
            if (wb_cyc_i && wb_stb_i && !wb_ack_o) begin
                wb_ack_o <= 1'b1;
            end else begin
                wb_ack_o <= 1'b0;
            end
        end
    end

    // Sequential CPU & Bus Logic
    integer i;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            run_cpu     <= 1'b0;
            cpu_halted  <= 1'b0;
            pc          <= 64'd0;
            state       <= STATE_IDLE;
            opcode      <= 4'd0;
            dest        <= 5'd0;
            src1        <= 5'd0;
            src2        <= 5'd0;
            immediate   <= 64'd0;
            exec_count  <= 2'd0;
            instruction <= 64'd0;
            
            // Reset registers
            for (i = 0; i < 32; i = i + 1) begin
                mem_reg[i] <= 64'd0;
            end
            
            // Reset instruction memory
            for (i = 0; i < 64; i = i + 1) begin
                inst_mem[i] <= 64'd0;
            end
        end else begin
            // 1. CPU Execution State Machine
            case (state)
                STATE_IDLE: begin
                    // Control via external bus write
                    if (wb_cyc_i && wb_stb_i && wb_we_i && !wb_ack_o && is_ctrl_space) begin
                        run_cpu <= wb_dat_i[0];
                        if (wb_dat_i[0]) begin
                            state      <= STATE_FETCH;
                            cpu_halted <= 1'b0;
                            pc         <= 64'd0;
                        end
                    end
                end

                STATE_FETCH: begin
                    instruction <= inst_mem[pc[5:0]];
                    state       <= STATE_DECODE;
                end

                STATE_DECODE: begin
                    opcode    <= instruction[63:60];
                    dest      <= instruction[59:55];
                    src1      <= instruction[54:50];
                    src2      <= instruction[49:45];
                    
                    // Sign-extend 45-bit immediate to 64-bit
                    if (instruction[44]) begin
                        immediate <= {19'h7FFFF, instruction[44:0]};
                    end else begin
                        immediate <= {19'h00000, instruction[44:0]};
                    end
                    
                    exec_count <= 2'd0;
                    state      <= STATE_EXECUTE_OP;
                end

                STATE_EXECUTE_OP: begin
                    case (opcode)
                        // NAND and NOR IMC operations require 2 execution cycles
                        4'h3, 4'h4: begin
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

                        4'h1: begin // LOAD_IMMED_64
                            mem_reg[dest] <= immediate;
                            pc            <= pc + 1;
                            state         <= STATE_FETCH;
                        end

                        4'h2: begin // OP_ADD_64
                            mem_reg[dest] <= mem_reg[src1] + mem_reg[src2];
                            pc            <= pc + 1;
                            state         <= STATE_FETCH;
                        end

                        4'h3: begin // OP_IMC_NAND_64
                            mem_reg[dest] <= ~(mem_reg[src1] & mem_reg[src2]);
                            pc            <= pc + 1;
                            state         <= STATE_FETCH;
                        end

                        4'h4: begin // OP_IMC_NOR_64
                            mem_reg[dest] <= ~(mem_reg[src1] | mem_reg[src2]);
                            pc            <= pc + 1;
                            state         <= STATE_FETCH;
                        end

                        4'h5: begin // BRANCH_ZERO_64
                            if (mem_reg[dest] == 64'd0) begin
                                pc <= immediate;
                            end else begin
                                pc <= pc + 1;
                            end
                            state <= STATE_FETCH;
                        end

                        default: begin
                            pc    <= pc + 1;
                            state <= STATE_FETCH;
                        end
                    endcase
                end
                
                default: state <= STATE_IDLE;
            endcase

            // 2. Bus Write Access (only when CPU is in IDLE)
            if (wb_cyc_i && wb_stb_i && wb_we_i && !wb_ack_o && (state == STATE_IDLE)) begin
                if (is_reg_space) begin
                    mem_reg[wb_adr_i[7:3]] <= wb_dat_i;
                end else if (is_inst_space) begin
                    inst_mem[wb_adr_i[8:3] - 6'd32] <= wb_dat_i; // Offset subtract for 0x100
                end
            end
        end
    end

    // Bus Read Access (Combinational)
    always @(*) begin
        wb_dat_o = 64'h0000000000000000;
        if (is_reg_space) begin
            wb_dat_o = mem_reg[wb_adr_i[7:3]];
        end else if (is_inst_space) begin
            wb_dat_o = inst_mem[wb_adr_i[8:3] - 6'd32];
        end else if (is_ctrl_space) begin
            wb_dat_o = {62'b0, cpu_halted, run_cpu};
        end
    end

endmodule
