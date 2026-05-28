`timescale 1ns / 1ps
`default_nettype none

module tt_um_omnicore (
    input  wire [7:0] ui_in,    // Ingressi dedicati: ui_in[0]=mode, ui_in[4:1]=data_in
    output wire [7:0] uo_out,   // Uscite dedicate: uo_out[3:0]=q_out
    input  wire [7:0] uio_in,   // IOs bidirezionali: Ingressi (non usati)
    output wire [7:0] uio_out,  // IOs bidirezionali: Uscite (non usate)
    output wire [7:0] uio_oe,   // IOs bidirezionali: Enable (impostati a 0 = input)
    input  wire       ena,      // Chip Enable (attivo alto, non usato internamente)
    input  wire       clk,      // Clock di sistema
    input  wire       rst_n     // Reset asincrono attivo basso
);

    // Registro interno a 4 bit per memorizzare lo stato del modulo
    reg [3:0] q_reg;

    // Assegnazione delle uscite
    assign uo_out[3:0] = q_reg;
    assign uo_out[7:4] = 4'b0000; // Pin non utilizzati impostati a 0

    // Configurazione dei pin bidirezionali come ingressi disattivati
    assign uio_out = 8'b00000000;
    assign uio_oe  = 8'b00000000;

    // Generazione delle 4 celle In-Memory Computing parallele
    genvar i;
    generate
        for (i = 0; i < 4; i = i + 1) begin : imc_cells
            always @(posedge clk or negedge rst_n) begin
                if (!rst_n) begin
                    q_reg[i] <= 1'b0;
                end else begin
                    // Se ui_in[0] (mode) == 1 -> IMC (AND logico sul posto tra data_in e Q)
                    // Se ui_in[0] (mode) == 0 -> Scrittura classica del dato data_in (ui_in[4:1])
                    q_reg[i] <= ui_in[0] ? (ui_in[i+1] & q_reg[i]) : ui_in[i+1];
                end
            end
        end
    endgenerate

endmodule
