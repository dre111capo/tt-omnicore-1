# OmniCore-1: 32-bit Standalone In-Memory Computing (IMC) CPU

OmniCore-1 is a 32-bit standalone CPU built for the SkyWater 130nm process node (Tiny Tapeout 08). It features In-Memory Computing (IMC) capabilities, allowing logical computations to occur directly inside the register file cells rather than moving data to/from a separate ALU, eliminating the Von Neumann bottleneck.

---

## 1. System Architecture & Multi-Cycle FSM

OmniCore-1 is a standalone CPU running a 5-state control engine (FSM) operating at 10 MHz:
* **IDLE**: The CPU waits for the host to assert `run_cpu = 1` via the Wishbone Control register.
* **FETCH**: Fetches the 32-bit instruction from dedicated `inst_mem` at the address pointed by `PC`.
* **DECODE**: Decodes opcode, registers, and immediate fields.
* **EXECUTE**: Executes the instruction. IMC operations (NAND, NOR) are multi-cycle (taking 2 execution cycles) to guarantee timing closure on SkyWater 130nm.
* **WRITE_BACK**: Writes result to the register, increments `PC`, and loops back to Fetch (or Idle if Halted).

---

## 2. Wishbone Page Multiplexing (Pages 0 to 10)

Due to TT08 pinout limitations, the 32-bit register file, instruction memory, and control registers are mapped to an 8-bit Wishbone slave interface using a **Page Register (`0x1F`)**.

To access a register or memory location, write the page index to address `0x1F` first:

| Page Index | Address Range | Target Access |
| :---: | :---: | :--- |
| **`0`** | `0x00 - 0x0F` | Data Registers **REG 0 - REG 3** (read/write byte-by-byte, little-endian) |
| **`1`** | `0x00 - 0x0F` | Data Registers **REG 4 - REG 7** (read/write byte-by-byte, little-endian) |
| **`2`** | `0x00 - 0x0F` | Instruction Memory words **0 - 3** |
| **`3`** | `0x00 - 0x0F` | Instruction Memory words **4 - 7** |
| **`4`** | `0x00 - 0x0F` | Instruction Memory words **8 - 11** |
| **`5`** | `0x00 - 0x0F` | Instruction Memory words **12 - 15** |
| **`6`** | `0x00 - 0x0F` | Instruction Memory words **16 - 19** |
| **`7`** | `0x00 - 0x0F` | Instruction Memory words **20 - 23** |
| **`8`** | `0x00 - 0x0F` | Instruction Memory words **24 - 27** |
| **`9`** | `0x00 - 0x0F` | Instruction Memory words **28 - 31** |
| **`10`** | `0x00` | Control & Status Register (`run_cpu` at bit 0, `halted` status) |

---

## 3. Instruction Set Architecture (ISA)

OmniCore-1 uses a custom 32-bit instruction format:
```
[31:28] Opcode | [27:25] Reg Dest | [24:22] Reg Src1 | [21:19] Reg Src2 | [18:0] Immediate / Offset
```

### Supported Opcodes
| Mnemonic | Opcode (Hex) | Description |
| :--- | :---: | :--- |
| **HALT** | `4'h0` | Stops CPU execution and asserts `cpu_halted` pin. |
| **LOAD_IMMED** | `4'h1` | Loads 19-bit immediate into `Reg Dest` (sign-extended to 32-bit). |
| **OP_ADD** | `4'h2` | Standard Addition: `Reg Dest = Reg Src1 + Reg Src2` |
| **OP_IMC_NAND** | `4'h3` | In-Memory NAND: `Reg Dest = Reg Src1 NAND Reg Src2` (2 cycles). |
| **BRANCH_ZERO** | `4'h4` | Branches to immediate instruction index if `Reg Dest == 0`. |
| **OP_IMC_NOR** | `4'h5` | In-Memory NOR: `Reg Dest = Reg Src1 NOR Reg Src2` (2 cycles). |
| **SHIFT_LEFT** | `4'h6` | Shifts `Reg Dest` left by value in `Reg Src1`. |

---

## 4. Hardware Configuration & Signoff

* **Target Process**: SkyWater 130nm
* **Area**: 4x2 Tiles
* **Clock Frequency**: 10 MHz
* **Signoff Compliance**:
  - `RUN_ANTENNA_CHECKER`: 1
  - `GRT_REPAIR_ANTENNAS`: 1
  - `DIODE_INSERTION_STRATEGY`: 3
  - `PL_TARGET_DENSITY`: 0.40 (mitigates routing congestion to allow auto-insertion of antenna protection diodes).
