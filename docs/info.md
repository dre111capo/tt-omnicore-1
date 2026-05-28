## How it works

OmniCore-1 is a 32-bit standalone CPU built for the SkyWater 130nm process node. It features In-Memory Computing (IMC) capabilities, allowing logical computations (NAND, NOR) to occur directly inside the register file cells rather than moving data to/from a separate ALU.

### Multi-Cycle FSM States
* **IDLE**: The CPU waits for the host to assert `run_cpu = 1` via the Wishbone Control register.
* **FETCH**: Fetches the 32-bit instruction from dedicated `inst_mem` at the address pointed by `PC`.
* **DECODE**: Decodes opcode, registers, and immediate fields.
* **EXECUTE**: Executes the instruction. IMC operations (NAND, NOR) are multi-cycle (taking 2 execution cycles) to guarantee timing closure.
* **WRITE_BACK**: Writes result to the register, increments `PC`, and loops back to Fetch (or Idle if Halted).

### Wishbone Page Multiplexing (Pages 0 to 10)
Due to TT08 pinout limitations, the 32-bit register file, instruction memory, and control registers are mapped to an 8-bit Wishbone slave interface using a **Page Register (`0x1F`)**. Write the page index to address `0x1F` first:
* **Pagina `0`**: Data Registers **REG 0 - REG 3**
* **Pagina `1`**: Data Registers **REG 4 - REG 7**
* **Pagine `2 - 9`**: Instruction Memory words **0 - 31** (4 words per page)
* **Pagina `10`**: Control & Status Register (`run_cpu` at bit 0, `halted` status)

### Instruction Set Architecture (ISA)
Format: `[31:28] Opcode | [27:25] Reg Dest | [24:22] Reg Src1 | [21:19] Reg Src2 | [18:0] Immediate / Offset`
* **HALT** (`4'h0`): Stops CPU execution.
* **LOAD_IMMED** (`4'h1`): Loads 19-bit immediate into `Reg Dest`.
* **OP_ADD** (`4'h2`): `Reg Dest = Reg Src1 + Reg Src2`.
* **OP_IMC_NAND** (`4'h3`): In-Memory NAND: `Reg Dest = Reg Src1 NAND Reg Src2` (2 cycles).
* **BRANCH_ZERO** (`4'h4`): Branches to immediate index if `Reg Dest == 0`.
* **OP_IMC_NOR** (`4'h5`): In-Memory NOR: `Reg Dest = Reg Src1 NOR Reg Src2` (2 cycles).
* **SHIFT_LEFT** (`4'h6`): Shifts `Reg Dest` left by value in `Reg Src1`.

## How to test

1. Apply active-low reset (`rst_n = 0`) then release it (`rst_n = 1`).
2. Write the program to the instruction memory (pages 2 to 9) byte-by-byte using the Wishbone interface.
3. Write page `10` register to enable `run_cpu = 1` to start execution.
4. Monitor the `cpu_halted` pin (uo[1]) until asserted.
5. Inspect registers using Wishbone pages 0 and 1 to verify correctness.

## External hardware

None. Can be tested using standard digital inputs and outputs or a Wishbone-compatible microcontroller.
