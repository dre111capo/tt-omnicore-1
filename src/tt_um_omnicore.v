`timescale 1ns / 1ps
`default_nettype none

module tt_um_omnicore (
    input  wire [7:0] ui_in,    // Dedicated inputs: Wishbone control & address
    output wire [7:0] uo_out,   // Dedicated outputs: Wishbone ack & popcount
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

    // Internal 64-bit registers
    reg  [63:0] data_in;
    reg  [63:0] op_in;
    reg  [63:0] q_reg;
    reg         mode_reg;   // 0: AND, 1: XNOR (IMC Operation Mode)
    reg         run_imc;    // Trigger bit for IMC execution
    reg         load_data;  // Trigger bit to load data_in into q_reg

    // Combinational Popcount calculation (adder tree)
    wire [6:0]  popcount;
    reg  [6:0]  popcount_temp;
    integer j;
    always @(*) begin
        popcount_temp = 7'd0;
        for (j = 0; j < 64; j = j + 1) begin
            popcount_temp = popcount_temp + q_reg[j];
        end
    end
    assign popcount = popcount_temp;

    // Connect dedicated outputs
    assign uo_out[0]   = wbs_ack_o;
    assign uo_out[7:1] = popcount;

    // Bidirectional data bus control
    // Drive uio outputs only during a Wishbone read cycle
    assign uio_oe  = (wbs_cyc_i && wbs_stb_i && !wbs_we_i) ? 8'hFF : 8'h00;
    assign uio_out = wbs_dat_o;

    // Wishbone Handshake (Acknowledge) Logic
    always @(posedge wb_clk_i or posedge wb_rst_i) begin
        if (wb_rst_i) begin
            wbs_ack_o <= 1'b0;
        end else begin
            // Single-cycle acknowledge assertion
            if (wbs_cyc_i && wbs_stb_i && !wbs_ack_o) begin
                wbs_ack_o <= 1'b1;
            end else begin
                wbs_ack_o <= 1'b0;
            end
        end
    end

    // Wishbone Write Transactions & IMC Core Execution
    always @(posedge wb_clk_i or posedge wb_rst_i) begin
        if (wb_rst_i) begin
            data_in   <= 64'd0;
            op_in     <= 64'd0;
            q_reg     <= 64'd0;
            mode_reg  <= 1'b0;
            run_imc   <= 1'b0;
            load_data <= 1'b0;
        end else begin
            // 1. In-Memory Computing Core Logic (Self-clearing triggers)
            if (run_imc) begin
                run_imc <= 1'b0;
                if (mode_reg == 1'b0) begin
                    q_reg <= q_reg & op_in;          // IMC AND
                end else begin
                    q_reg <= ~(q_reg ^ op_in);       // IMC XNOR (BNN Multiplication)
                end
            end else if (load_data) begin
                load_data <= 1'b0;
                q_reg <= data_in;                    // Load input register to memory cells
            end

            // 2. Wishbone Write Handler
            if (wbs_cyc_i && wbs_stb_i && wbs_we_i && !wbs_ack_o) begin
                case (wbs_adr_i)
                    // Addresses 0x00 - 0x07: Write data_in byte-by-byte
                    5'h00: data_in[7:0]   <= wbs_dat_i;
                    5'h01: data_in[15:8]  <= wbs_dat_i;
                    5'h02: data_in[23:16] <= wbs_dat_i;
                    5'h03: data_in[31:24] <= wbs_dat_i;
                    5'h04: data_in[39:32] <= wbs_dat_i;
                    5'h05: data_in[47:40] <= wbs_dat_i;
                    5'h06: data_in[55:48] <= wbs_dat_i;
                    5'h07: data_in[63:56] <= wbs_dat_i;

                    // Addresses 0x08 - 0x0F: Write op_in byte-by-byte
                    5'h08: op_in[7:0]     <= wbs_dat_i;
                    5'h09: op_in[15:8]    <= wbs_dat_i;
                    5'h0a: op_in[23:16]   <= wbs_dat_i;
                    5'h0b: op_in[31:24]   <= wbs_dat_i;
                    5'h0c: op_in[39:32]   <= wbs_dat_i;
                    5'h0d: op_in[47:40]   <= wbs_dat_i;
                    5'h0e: op_in[55:48]   <= wbs_dat_i;
                    5'h0f: op_in[63:56]   <= wbs_dat_i;

                    // Address 0x10: Control/Mode register
                    5'h10: begin
                        run_imc   <= wbs_dat_i[0];
                        mode_reg  <= wbs_dat_i[1];
                        load_data <= wbs_dat_i[2];
                    end

                    // Addresses 0x11 - 0x18: Write q_reg byte-by-byte (direct cell override)
                    5'h11: q_reg[7:0]     <= wbs_dat_i;
                    5'h12: q_reg[15:8]    <= wbs_dat_i;
                    5'h13: q_reg[23:16]   <= wbs_dat_i;
                    5'h14: q_reg[31:24]   <= wbs_dat_i;
                    5'h15: q_reg[39:32]   <= wbs_dat_i;
                    5'h16: q_reg[47:40]   <= wbs_dat_i;
                    5'h17: q_reg[55:48]   <= wbs_dat_i;
                    5'h18: q_reg[63:56]   <= wbs_dat_i;

                    default: ;
                endcase
            end
        end
    end

    // Wishbone Read Transactions (Combinational Address Decode)
    always @(*) begin
        wbs_dat_o = 8'h00;
        case (wbs_adr_i)
            // Addresses 0x00 - 0x07: Read data_in
            5'h00: wbs_dat_o = data_in[7:0];
            5'h01: wbs_dat_o = data_in[15:8];
            5'h02: wbs_dat_o = data_in[23:16];
            5'h03: wbs_dat_o = data_in[31:24];
            5'h04: wbs_dat_o = data_in[39:32];
            5'h05: wbs_dat_o = data_in[47:40];
            5'h06: wbs_dat_o = data_in[55:48];
            5'h07: wbs_dat_o = data_in[63:56];

            // Addresses 0x08 - 0x0F: Read op_in
            5'h08: wbs_dat_o = op_in[7:0];
            5'h09: wbs_dat_o = op_in[15:8];
            5'h0a: wbs_dat_o = op_in[23:16];
            5'h0b: wbs_dat_o = op_in[31:24];
            5'h0c: wbs_dat_o = op_in[39:32];
            5'h0d: wbs_dat_o = op_in[47:40];
            5'h0e: wbs_dat_o = op_in[55:48];
            5'h0f: wbs_dat_o = op_in[63:56];

            // Address 0x10: Control/Mode register state
            5'h10: wbs_dat_o = {5'b00000, load_data, mode_reg, run_imc};

            // Addresses 0x11 - 0x18: Read q_reg
            5'h11: wbs_dat_o = q_reg[7:0];
            5'h12: wbs_dat_o = q_reg[15:8];
            5'h13: wbs_dat_o = q_reg[23:16];
            5'h14: wbs_dat_o = q_reg[31:24];
            5'h15: wbs_dat_o = q_reg[39:32];
            5'h16: wbs_dat_o = q_reg[47:40];
            5'h17: wbs_dat_o = q_reg[55:48];
            5'h18: wbs_dat_o = q_reg[63:56];

            // Address 0x19: Read Popcount result
            5'h19: wbs_dat_o = {1'b0, popcount};

            default: wbs_dat_o = 8'h00;
        endcase
    end

endmodule
