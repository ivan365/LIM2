# LIM M2 Processor Architecture

<p align="center">
  <img src="Docs/diagram.png" alt="LIM M2 Datapath Schematic" width="850">
</p>

<p align="center">
  <b>High-Performance 16-Bit Microprogrammed CPU Core with Zero Tri-State Multiplexed Datapath & 24-Bit Linear Addressing (16 MB)</b>
</p>

<p align="center">
  <a href="README.md"><b>English</b></a> •
  <a href="README.ua.md"><b>Українська</b></a> •
  <a href="README.ru.md"><b>Русский</b></a> •
  <a href="README.sk.md"><b>Slovenčina</b></a>
</p>

---

## 🌟 Key Architectural Highlights

* **Pure Multiplexer Datapath (Zero Tri-State / No Hi-Z):**
  Internal buses completely discard high-impedance third-state (`Hi-Z`) lines. Data steering is implemented via active push-pull multiplexer trees (`MUX 1`, `DEST-DMUX`, `MUX 2`), entirely eliminating bus contention, floating lines, and capacitive decay. Ideal for FPGA and ASIC synthesis.
* **Extended 24-Bit Linear Memory & Stack Addressing (16 MB):**
  Features dedicated 24-bit pointer registers:
  * **`PTREG` (Pointer Register):** Linear flat addressing across 16 MB with optional hardware auto-increment (`AIP`).
  * **`SREG` (Stack Register):** Full 24-bit linear execution stack pointer supporting deep subroutine stacks and recursive frames.
* **Dual Accumulator Staging (`ACCA` & `ACCB`):**
  Dedicated 16-bit pre-ALU input latches isolate arithmetic propagation transients from the general register file (`R0–R7`).
* **Direct Register Bypass Channel (Reg-to-Reg Bypass):**
  Point-to-point datapath from `MUX 1` directly to `MUX 2` executes fast register transfers (`LRR / MOV`) without locking or stalling the ALU.
* **Hardware ALU Auto-Chaining (Multi-Word Arithmetic):**
  The ALU features an internal residual accumulator (`ALU_RESIDUAL`):
  * **Chained Addition (`ADD`):** When sum $> 2^{16}-1$, carry (`+1`) is latched and automatically added in the next `ADD`.
  * **Chained Subtraction (`SUB`):** When difference $< 0$, borrow (`-1`) is retained and automatically subtracted in the next `SUB`.
  * **Chained Multiplication (`MUL`):** Low 16 bits go to destination; upper 16 bits are retained in `ALU_RESIDUAL` and can be accumulated in following operations or extracted.
  * **Chained Division (`DIV`):** Quotient is written to destination register; remainder (modulo) is retained in `ALU_RESIDUAL`.
  * **Chain Flush (`NOP`):** Executing `NOP` flushes `ALU_RESIDUAL` and resets carry/borrow tracking for independent computations.
* **High Clock Frequency Envelope:**
  Designed for a baseline operating frequency of **200 MHz**, scaling towards **700+ MHz** in modern silicon (ASIC).

---

## 📑 Official Datasheets

Pre-compiled, ready-to-print comprehensive technical reference datasheets are located in [`Docs/`](Docs/):

| Language | LaTeX Source | Compiled PDF Specification |
| :--- | :--- | :--- |
| **English** | [`Docs/LIM_M2_Datasheet_EN.tex`](Docs/LIM_M2_Datasheet_EN.tex) | [**Download PDF (EN)**](Docs/LIM_M2_Datasheet_EN.pdf) |
| **Українська** | [`Docs/LIM_M2_Datasheet_UA.tex`](Docs/LIM_M2_Datasheet_UA.tex) | [**Download PDF (UA)**](Docs/LIM_M2_Datasheet_UA.pdf) |
| **Русский** | [`Docs/LIM_M2_Datasheet_RU.tex`](Docs/LIM_M2_Datasheet_RU.tex) | [**Download PDF (RU)**](Docs/LIM_M2_Datasheet_RU.pdf) |
| **Slovenčina** | [`Docs/LIM_M2_Datasheet_SK.tex`](Docs/LIM_M2_Datasheet_SK.tex) | [**Download PDF (SK)**](Docs/LIM_M2_Datasheet_SK.pdf) |

---

## 🗃️ Architectural Register File

| Register | Width | Architectural Role |
| :--- | :---: | :--- |
| **`R0` – `R7`** | 16-bit | General Purpose Registers (GPR). Low-latency read via `MUX 1`, gated writeback from `WB_DATA`. |
| **`SREG`** | **24-bit** | System Stack Register. Linear 24-bit addressing across 16 MB execution stack space. |
| **`PTREG`** | **24-bit** | Extended Pointer Register. Flat linear addressing across 16 MB with optional hardware auto-increment (`AIP`). |
| **`FREG`** | 16-bit | Processor Status and Control Register. Unifies condition flags and operational mode controls. |
| **`ACCA` / `ACCB`** | 16-bit | Auxiliary ALU Latches (Dual Accumulator Staging). Pre-stages ALU operands A and B. |

### Flag and Control Register (`FREG`) Bit Layout

```text
 15    14    13    12   11   10    9    8    7    6    5    4    3    2    1    0
+-----+-----+-----+----+----+----+----+----+----+----+----+----+----+----+----+----+
|INTR |SMOD |DBIT |AIP |M24 |DWR |MIE |PIE |CLK1|CLK0|CMP1|CMP0| EM | OF | CF | ZF |
+-----+-----+-----+----+----+----+----+----+----+----+----+----+----+----+----+----+
```

* **`ZF` (0):** Zero Flag (result is zero).
* **`CF` (1):** Carry / Borrow Flag.
* **`OF` (2):** Overflow Flag (signed arithmetic).
* **`EM` (3):** Error Math (hardware trap on division by zero).
* **`CMP` (4–5):** 2-bit Hardware Comparator Result `cmp_flags` (`00`: initial reset / no compare / error; `01`: less; `10`: equal; `11`: greater).
* **`CLK` (6–7):** Core Clock Divider Mode.
* **`PIE` (8):** Program Interrupt Enable.
* **`MIE` (9):** Master Interrupt Enable.
* **`DWR` (10):** Disable Wait for Ready (forced non-blocking bus transfer).
* **`M24` (11):** 24-bit Extended Addressing Enable.
* **`AIP` (12):** Auto-Increment Pointer on memory operations.
* **`DBIT` (13):** Displaced Bit buffer (retains bit ejected during shift).
* **`SMOD` (14):** Shift Mode selector (`0`: zero-fill, `1`: cyclic rotate through `DBIT`).
* **`INTR` (15):** In-Interrupt execution flag (`1`: CPU is servicing an interrupt; subsequent interrupts locked out).

---

## 📐 Machine Instruction Formats & Bit Decoding

The LIM M2 processor implements a clean, orthogonal instruction encoding scheme with deterministic decoding:
* **Universal Architectural Syntax:** Destination register first, followed by source operands:
  * **Arithmetic (3 operands):** `ADD Rd, Rs1, Rs2` $\implies \text{Rd} = \text{Rs1} + \text{Rs2}$
  * **Logic (2 operands):** `AND Rd, Rs` $\implies \text{Rd} = \text{Rd} \ \& \ \text{Rs}$
  * **Unary (1 byte, 1 operand):** `NOT Rd`, `INC Rd`, `DEC Rd`
  * **Register transfer:** `LRR Rd, Rs` $\implies \text{Rd} = \text{Rs}$ (copy point B $\to$ point A)
  * **Comparator:** `CMP Rs1, Rs2` $\implies$ sets `FREG.CMP` (`01`: `<`, `10`: `=`, `11`: `>`, `00`: reset/error)
* **Direct first argument & modifier encoding:** Driven by the 5-bit opcode in Octet 0 bits `[7:3]`, while bits `[2:0]` directly encode the first register argument (`Rd` / `Rs1` / `Rs`) across arithmetic, logic, transfer, compare, and stack operations, or control/addressing modifiers (`CFG` / `MOD` / `SZ:Mode`) where applicable.

### Universal Instruction Layout
```
+------------------------+-------------------+------------------------------------------+
|      OPCODE [7:3]      |   Rd / CFG [2:0]  | Operands & Arguments (Dynamic Length)    |
|        (5 bits)        |     (3 bits)      |             (0 to 3 octets)              |
+------------------------+-------------------+------------------------------------------+
  Bit 7                3   Bit 2           0   Byte 1 ... Byte 3 (Optional)
```

### 10 Instruction Classes & Bit Breakdown

1. **Class I: Single-Byte Instructions (1 Byte, 0 Extra Bytes)**
   * `NOP`, `HALT`, `CLI`, `STI`, `RET` (`CFG = 000`)
   * `NOT Rd`, `INC Rd`, `DEC Rd` (`Bits [2:0] = Rd` directly, no second byte fetched)
   ```
   Octet 0: [ OPCODE (5b) | Rd / 000 (3b) ]
   ```

2. **Class II: Three-Operand Arithmetic (2 Bytes)**
   * `ADD`, `SUB`, `MUL`, `DIV`, `MOD` (`Rd = Rs1 op Rs2`)
   ```
   Octet 0: [ OPCODE (5b) | Rd [2:0] (Destination) ]
   Octet 1: [ Rs1 [7:5] (Src 1) | Rs2 [4:2] (Src 2) | RSV=00 [1:0] ]
   ```

3. **Class III: Two-Operand Logic (2 Bytes)**
   * `AND`, `OR`, `NAND`, `NOR`, `XOR`, `XNOR` (`Rd = Rd op Rs`)
   ```
   Octet 0: [ OPCODE (5b) | Rd [2:0] (Dest / Src 1) ]
   Octet 1: [ Rs [7:5] (Src 2) | RSV=00000 [4:0] ]
   ```

4. **Class IV: Register-to-Register Transfer (2 Bytes)**
   * `LRR Rd, Rs`: fast direct copy from source (`Rs`) to destination (`Rd`) via `MUX 1` $\to$ `MUX 2` bypass (1 cycle, `FREG` untouched).
   ```
   Octet 0: [ 00111 (5b) | Rd [2:0] (Destination) ]
   Octet 1: [ Rs [7:5] (Source) | RSV=00000 [4:0] ]
   ```

5. **Class V: Hardware Comparator (2 Bytes)**
   * `CMP Rs1, Rs2`: non-destructive compare setting `FREG.CMP` (`01`: `<`, `10`: `=`, `11`: `>`, `00`: reset/error).
   ```
   Octet 0: [ 01000 (5b) | Rs1 [2:0] (Operand 1) ]
   Octet 1: [ Rs2 [7:5] (Operand 2) | RSV=00000 [4:0] ]
   ```

6. **Class VI: Hardware Shift Register (2 Bytes, Iterative D-Flip-Flop Chain)**
   * `BSL Rd, shift` and `BSR Rd, shift`: iterative hardware shift register on D-flip-flops ($\approx 300$ transistors instead of $\approx 30,000$ for a barrel matrix).
   * **Shift execution is a hardware loop:** shifting by 16 bits takes 15 more clock cycles than shifting by 1 bit (1 cycle per bit).
   * Governed by `FREG.SMOD` (`1`: rotate via `DBIT`, `0`: zero-fill) and `FREG.DBIT` (holds last ejected bit).
   ```
   Octet 0: [ OPCODE (5b) | Rd [2:0] (Target Register R0-R7) ]
   Octet 1: [ Shift Count [7:0] (0 to 16 cycles / bits) ]
   ```

7. **Class VII: Stack Operations (2 Bytes)**
   * `PUSH Rs` and `POP Rd`: word transfers via 24-bit stack pointer `SREG`.
   ```
   Octet 0: [ OPCODE (5b) | Rs / Rd [2:0] (Reg R0-R7) ]
   Octet 1: [ RSV=00000000 [7:0] ]
   ```

8. **Class VIII: Manage Special Registers (2 Bytes)**
   * `MSP sreg, [op], args`: control `FREG` (00) or 24-bit `PTREG` (01).
   ```
   Octet 0: [ 11010 (5b) | Mode (1b: 0=Load, 1=Modify) | SREG (2b: 00=FREG, 01=PTREG) ]
   Octet 1 (Load):   [ Rs [7:5] (FREG) or Rs_hi [7:5] | Rs_lo [4:2] (PTREG) | RSV [1:0] ]
   Octet 1 (Modify): [ OP [7:6] (FREG: AND/OR/XOR/XNOR; PTREG: ADD/SUB) | Rs [5:3] (Mask/Offset) | RSV [2:0] ]
   ```

9. **Class IX: Branch & Jump Instructions (2–3 Bytes)**
   * `JMP`, `JCR`, `JNZ`, `JZ`:
     * `MOD = 0` (000): 16-bit immediate address (3 bytes total).
     * `MOD = 1` (001): Indirect register branch via `Rs` (2 bytes total).
     * `MOD = 2` (010): 24-bit extended branch via `PTREG`.

10. **Class X: Memory Load & Store (2–4 Bytes)**
    * `LMR Rd, <SRC_MODE>` and `LRM Rs, <DST_MODE>`:
      * Bit 2 of Octet 0: `SZ` ($0 = 8$-bit byte, $1 = 16$-bit word).
      * Bits 1–0 of Octet 0: `Mode` (0 = Inline data, 1 = Imm pointer, 2 = 24-bit `PTREG` with auto-increment, 3 = Register pair 24-bit address).

---

## ⚡ Instruction Set Architecture (ISA - 32 Opcodes)

| Opcode | Hex | Mnemonic | Class | Functional Description |
| :---: | :---: | :--- | :--- | :--- |
| **00000** | `0x00` | **`NOP`** | Control | No operation; flushes `ALU_RESIDUAL` and resets carry/borrow tracking |
| **00001** | `0x01` | **`ADD`** | Arithmetic | 16-bit addition with automatic carry chaining via `ALU_RESIDUAL` |
| **00010** | `0x02` | **`SUB`** | Arithmetic | 16-bit subtraction with automatic borrow chaining via `ALU_RESIDUAL` |
| **00011** | `0x03` | **`MUL`** | Arithmetic | Integer multiplication; upper 16 bits latched into `ALU_RESIDUAL` |
| **00100** | `0x04` | **`DIV`** | Arithmetic | Integer division; remainder (modulo) latched into `ALU_RESIDUAL` |
| **00101** | `0x05` | **`LMR`** | Memory | Load byte/word into register (src: 0=Imm, 1=Ptr, 2=PTREG, 3=Register pair 24-bit; size: 8/16-bit) |
| **00110** | `0x06` | **`LRM`** | Memory | Store byte/word into memory (dst: 0=Inline, 1=Ptr, 2=PTREG, 3=Register pair 24-bit; size: 8/16-bit) |
| **00111** | `0x07` | **`LRR`** | Transfer | Fast register-to-register copy via bypass (`MUX 1` $\to$ `MUX 2`) |
| **01000** | `0x08` | **`CMP`** | Compare | Arithmetic compare; updates `FREG.CMP` (`01`: `<`, `10`: `=`, `11`: `>`), `ZF`, `CF`, `OF` non-destructively |
| **01001** | `0x09` | **`JMP`** | Branch | Unconditional branch (16-bit local or full 24-bit via `PTREG`) |
| **01010** | `0x0A` | **`JCR`** | Branch | Conditional branch on Carry Flag (`CF == 1`) |
| **01011** | `0x0B` | **`JNZ`** | Branch | Conditional branch on Non-Zero (`ZF == 0`) |
| **01100** | `0x0C` | **`JZ`** | Branch | Conditional branch on Zero (`ZF == 1`) |
| **01101** | `0x0D` | **`AND`** | Logic | Bitwise logical AND |
| **01110** | `0x0E` | **`OR`** | Logic | Bitwise logical OR |
| **01111** | `0x0F` | **`NAND`** | Logic | Bitwise logical NAND |
| **10000** | `0x10` | **`NOR`** | Logic | Bitwise logical NOR |
| **10001** | `0x11` | **`NOT`** | Logic | Bitwise NOT (One's Complement) |
| **10010** | `0x12` | **`XOR`** | Logic | Bitwise exclusive OR |
| **10011** | `0x13` | **`XNOR`** | Logic | Bitwise equivalence |
| **10100** | `0x14` | **`INC`** | Arithmetic | Atomic increment by 1 |
| **10101** | `0x15` | **`DEC`** | Arithmetic | Atomic decrement by 1 |
| **10110** | `0x16` | **`PUSH`** | Stack | Push 16-bit word onto 24-bit stack (`SREG <- SREG - 2`) |
| **10111** | `0x17` | **`POP`** | Stack | Pop 16-bit word from 24-bit stack (`SREG <- SREG + 2`) |
| **11000** | `0x18` | **`BSL`** | Shift | Barrel Shift Left (zero-fill or cyclic rotate via `DBIT` if `SMOD=1`) |
| **11001** | `0x19` | **`BSR`** | Shift | Barrel Shift Right (zero-fill or cyclic rotate via `DBIT` if `SMOD=1`) |
| **11010** | `0x1A` | **`MSP`** | System | Manage Special Registers (`FREG`, `PTREG`) |
| **11011** | `0x1B` | **`MOD`** | Arithmetic | Integer remainder (modulo): `Rd = Rs1 % Rs2` |
| **11100** | `0x1C` | **`RSV28`** | Reserved | Extended addressing coprocessor slot |
| **11101** | `0x1D` | **`RSV29`** | Reserved | Floating-Point Unit (FPU) slot |
| **11110** | `0x1E` | **`RSV30`** | Reserved | Hardware cryptography accelerator slot |
| **11111** | `0x1F` | **`RSV31`** | Reserved | Future architecture expansion slot |

---

## 🔌 Physical Interface & 34-Pin Package

The LIM M2 processor is packaged in an industry-standard 34-pin dual-row footprint engineered for signal integrity, noise immunity, and deterministic timing:

| Pin | Name | Direction | Description |
| :---: | :--- | :---: | :--- |
| **1–8** | `A0`–`A7` | Output | Multiplexed lower 8 bits of 16-bit physical address bus |
| **9–16** | `A8`–`A15` | Output | Multiplexed upper 8 bits of 16-bit physical address bus |
| **17** | `CLK1` | Input | Phase 1 system clock input |
| **18** | `CLK2` | Input | Phase 2 system clock input (non-overlapping) |
| **19** | `RDI` | Input | Raw Direct Interrupt: priority hardware interrupt request line |
| **20** | `AL` | Output | Address Latch strobe for external transparent latch / buffer |
| **21** | `RF` | Input | Ready Flag: slave device handshake ready acknowledge |
| **22** | `WD` | Output | Bus Write Enable strobe |
| **23** | `RD` | Output | Bus Read Enable strobe |
| **24** | `GND` | Power | System ground reference (0 V) |
| **25** | `VCC` | Power | Primary core and I/O power supply (+5 V nominal) |
| **26** | **`IA`** | **Output** | **Interruption Accepted / Interrupt Acknowledge: informs peripherals that the request is accepted; core shifts `D0–D7` to input to sample vector ID** |
| **27–34** | `D7`–`D0` | Bidirectional | 8-bit bidirectional data bus for memory and peripheral transfers |

---

## ⚡ Interrupt Architecture & Vector Processing Subsystem (16 Vectors)

The LIM M2 interrupt subsystem is designed for hard real-time determinism, sub-cycle arbitration, and complete protection against bus contention. It seamlessly unifies external hardware interrupts and internal traps into an orthogonal 16-vector hierarchy:

### 1. Unified 16-Vector System Space

| Vector | Hex Code | Source / Trigger | Architectural Role |
| :---: | :---: | :--- | :--- |
| **`VEC 0`** | `0x00` | Hardware / Reset | Power-on Reset: cold initialization of CPU registers & pipeline |
| **`VEC 1`** | `0x01` | Hardware (NMI) | Non-Maskable Interrupt: power fail, hardware fault alert |
| **`VEC 2`** | `0x02` | Software Trap | Arithmetic Exception (division by zero, `FREG.EM` flag) |
| **`VEC 3`** | `0x03` | Software Trap | OS System Call dispatcher (`Syscall / Trap` handler) |
| **`VEC 4`** | `0x04` | Hardware / Device | System Interval Timer tick |
| **`VEC 5`** | `0x05` | Hardware / Device | UART Serial communications interface (RX/TX ready) |
| **`VEC 6`** | `0x06` | Hardware / Device | DMA Controller transfer complete |
| **`VEC 7`** | `0x07` | Hardware / Device | External Interrupt Controller / System bridge |
| **`VEC 8–15`** | `0x08–0x0F` | Shared (HW / SW) | User peripheral interrupts and software vector handlers |

### 2. Cycle-Accurate Hardware Handshake (`RDI` $\to$ `IA` $\to$ `D0–D7`)

External interrupt servicing follows a deterministic 5-step hardware sequence:
1. **Request Phase (`RDI`):** Peripheral asserts active-high level on the `RDI` pin. The core samples `RDI` at atomic micro-op boundaries.
2. **Mask & Lockout Evaluation:** If interrupts are enabled (`FREG.MIE == 1`) and the CPU is not already in an interrupt handler (`FREG.INTR == 0`), the CPU commits its current datapath micro-operation. If `INTR == 1`, new interrupts are locked out.
3. **Acknowledge Strobe (`IA`):** The core asserts active-high `IA` (Pin 26), signaling to the bus that the request is granted.
4. **Vector Ingestion (`D0–D7`):** The core turns `D0–D7` into high-impedance input mode and asserts read strobe `RD`. The peripheral drives its 8-bit vector ID (lower 4 bits address vectors 0–15).
5. **Latch & Vector Dispatch:** The CPU latches the vector, deasserts `IA`, and advances to context preservation.

### 3. Context Preservation on 24-Bit Stack (`SREG`)

Upon accepting an interrupt:
1. **Save Return PC:** Program counter is pushed onto the 24-bit stack:
   $$\text{SREG} \leftarrow \text{SREG} - 2, \quad \text{Memory}[\text{SREG}] \leftarrow \text{PC}_{15:0}$$
2. **Save Flags & Status (`FREG`):** Pushed with original $\text{INTR} = 0$:
   $$\text{SREG} \leftarrow \text{SREG} - 2, \quad \text{Memory}[\text{SREG}] \leftarrow \text{FREG}$$
3. **Hardware Lockout:** `FREG.INTR` is set to `1` (bit 15) and `FREG.MIE` is cleared to `0`, locking out nested re-entrancy.
4. **Dispatch:** The vector handler address is indexed from the vector table and loaded into `PC`.

### 4. Return from Interrupt

Exiting the handler pops the saved architectural context:
1. $\text{FREG} \leftarrow \text{Memory}[\text{SREG}], \quad \text{SREG} \leftarrow \text{SREG} + 2$ (automatically clearing `INTR` back to `0` and restoring `MIE`).
2. $\text{PC} \leftarrow \text{Memory}[\text{SREG}], \quad \text{SREG} \leftarrow \text{SREG} + 2$.
Execution resumes instantly on the subsequent cycle with zero state contamination.

---

## 📐 Unified Instruction Syntax Philosophy (Destination First)

The LIM M2 architecture enforces a strict and consistent operand order across all instructions:

> **The destination operand (target, "where to") is always declared first, followed by input source operands ("where from").**

* **Arithmetic (3 Operands):** `ADD Rd, Rs1, Rs2` denotes $\text{Rd} = \text{Rs1} + \text{Rs2}$ (e.g., `ADD R0, R1, R2` computes $R0 = R1 + R2$). Similarly: `SUB`, `MUL`, `DIV`.
* **Logic (2 Operands):** `AND Rd, Rs` denotes $\text{Rd} = \text{Rd} \ \& \ \text{Rs}$ (e.g., `AND R0, R1` computes $R0 = R0 \ \& \ R1$). Similarly: `OR`, `NAND`, `NOR`, `XOR`, `XNOR`.
* **Single-Byte Unary Operations (1 Operand):** `INC Rd` ($\text{Rd} = \text{Rd} + 1$), `DEC Rd` ($\text{Rd} = \text{Rd} - 1$), and `NOT Rd` ($\text{Rd} = \sim\text{Rd}$). Operate on a single register `Rd` in place. Encoded in exactly 1 byte (`[7:3]` opcode, `[2:0]` Rd), no second byte is fetched from memory.
* **Register-to-Register Transfer:** `LRR Rd, Rs` executes a direct transfer from source (point B, `Rs`) to destination (point A, `Rd`): $\text{Rd} = \text{Rs}$ (e.g., `LRR R0, R1` computes $R0 = R1$).
* **Memory Loads:** `LMR Rd, ...` stores data read from memory into the first argument `Rd`.

---

## 📥 LMR Instruction Architecture (Load Memory to Register)

The **`LMR`** instruction (`Opcode 00101` / `0x05`) serves as the primary gateway for transferring external data and memory into the LIM M2 general-purpose register file (`R0`–`R7`). It features a versatile encoding structure with native support for 24-bit physical addressing (up to 16 MB).

### 1. Instruction Bit Encoding
The instruction is composed of two primary 8-bit octets (bytes):

```text
Octet 0 (Opcode & Mode Configuration):
 7   6   5   4   3   2   1   0
+---+---+---+---+---+---+---+---+
| 0   0   1   0   1 |  SRC  |SZ |
+---+---+---+---+---+---+---+---+
 \_____ 5 bits ____/ \_2b._/ \1b/

Octet 1 (Register Arguments):
 7   6   5   4   3   2   1   0
+---+---+---+---+---+---+---+---+
|  Arg1 (R_hi/Dst)  |   Arg2    | 0   0 |
+---+---+---+---+---+---+---+---+
 \_____ 3 bits _____/ \_ 3 bits _/ \_2b._/
```

* **Data Size (`SZ`, Bit 0 of Octet 0):**
  * `0`: Load **1 Byte** (8-bit). Lower byte of target register receives value, upper byte is zero-extended (`{8'b0, data[7:0]}`).
  * `1`: Load **2 Bytes** (16-bit / machine word).
* **Data Source Mode (`SRC`, Bits [2:1] of Octet 0):**
  * `00` (`0`): **Immediate Data** — Literal data resides in memory directly following the instruction opcode (`[PC]`). `PC` advances by $1$ or $2$ bytes automatically.
  * `01` (`1`): **Immediate Pointer** — An absolute memory pointer immediately follows the instruction in code (`[[PC]]`), through which the operand is dereferenced.
  * `10` (`2`): **`PTREG` Pointer** — Memory is accessed via the dedicated 24-bit system pointer register `PTREG`. If auto-increment flag `FREG.AIP` (bit 12) is set, `PTREG` automatically increments by $+1$ or $+2$, delivering hardware-accelerated streaming array transfers.
  * `11` (`3`): **User Register Pair (24-bit Addressing via 32-bit Composite)** — The user selects two 16-bit registers (`Arg1` and `Arg2`) forming a 32-bit composite word, of which the lower 24 bits are used for physical addressing:
    * **`Arg1` (Bits [7:5] of Octet 1):** holds the **upper address bits**. Crucially, this same register also serves as the destination register: after data is retrieved from memory, the upper address bits in `Arg1` are **overwritten with the loaded data**!
    * **`Arg2` (Bits [4:2] of Octet 1):** holds the **lower 16 address bits** and preserves its value.
    * The physical 24-bit address is synthesized in hardware:
      $$\text{EA}[23:0] = ((\text{Arg1}[15:0] \ll 16) \mid \text{Arg2}[15:0]) \;\&\; \text{0xFFFFFF}$$
    * The loaded data is stored directly into `Arg1`.

---

## 📤 LRM Instruction Architecture (Load Register to Memory)

The **`LRM`** instruction (`Opcode 00110` / `0x06`) provides a symmetrical mechanism for storing data from internal general-purpose registers to memory or external address spaces. Overwriting/destroying existing code or data at the target address is strictly the programmer's responsibility!

### 1. Instruction Bit Encoding
The instruction is composed of two primary 8-bit octets (bytes):

```text
Octet 0 (Opcode & Destination Mode Configuration):
 7   6   5   4   3   2   1   0
+---+---+---+---+---+---+---+---+
| 0   0   1   1   0 |  DST  |SZ |
+---+---+---+---+---+---+---+---+
 \_____ 5 bits ____/ \_2b._/ \1b/

Octet 1 (Register Arguments):
 7   6   5   4   3   2   1   0
+---+---+---+---+---+---+---+---+
|  Arg1 (Rs/R_hi)   |   Arg2    | 0   0 |
+---+---+---+---+---+---+---+---+
 \_____ 3 bits _____/ \_ 3 bits _/ \_2b._/
```

* **Data Size (`SZ`, Bit 0 of Octet 0):**
  * `0`: Store **1 Byte** (8-bit). Only the lower byte of source register `Rs[7:0]` is written to memory.
  * `1`: Store **2 Bytes** (16-bit / machine word `Rs[15:0]`).
* **Destination Mode (`DST`, Bits [2:1] of Octet 0):**
  * `00` (`0`): **Inline Memory (Code Tail Store)** — Data is written directly into memory immediately following the instruction opcode (`[PC]`). `PC` automatically advances by $1$ or $2$ bytes. Designed for self-modifying code generation and inline buffer initialization. Overwriting instructions is the programmer's responsibility.
  * `01` (`1`): **Immediate Pointer** — An absolute 16-bit pointer directly follows the instruction (`[[PC]]`), through which the store is performed.
  * `10` (`2`): **`PTREG` Pointer** — Stored via the 24-bit physical address in `PTREG`. If auto-increment flag `FREG.AIP` (bit 12) is active, `PTREG` automatically increments by $+1$ or $+2$, enabling high-throughput memory streaming.
  * `11` (`3`): **User Register Pair (24-bit Addressing via 32-bit Composite)**:
    * **`Arg1` (Bits [7:5] of Octet 1):** holds the **upper address bits** and simultaneously acts as the **source register** (`Rs`) containing data to write.
    * **`Arg2` (Bits [4:2] of Octet 1):** holds the **lower 16 address bits** (`Rs_lo`).
    * The physical 24-bit effective address is synthesized in hardware:
      $$\text{EA}[23:0] = ((\text{Arg1}[15:0] \ll 16) \mid \text{Arg2}[15:0]) \;\&\; \text{0xFFFFFF}$$
    * The data from `Arg1` is written to memory at address $\text{EA}$. Data destruction at destination is exclusively managed by the programmer.

---

## 🔄 LRR Instruction Architecture (Load Register to Register)

The **`LRR`** instruction (`Opcode 00111` / `0x07`) provides a high-speed, direct register-to-register move mechanism across general-purpose registers (`R0`–`R7`), transferring data from source (point B, `Rs`) to destination (point A, `Rd`).

### 1. Instruction Bit Encoding
The instruction is composed of two 8-bit octets (16 bits):

```text
Octet 0 (Opcode & Reserved):
 7   6   5   4   3   2   1   0
+---+---+---+---+---+---+---+---+
| 0   0   1   1   1 | 0   0   0 |
+---+---+---+---+---+---+---+---+
 \_____ 5 bits ____/ \_ 3 bits _/

Octet 1 (Register Arguments):
 7   6   5   4   3   2   1   0
+---+---+---+---+---+---+---+---+
|  Arg1 (Rd, WHERE TO)| Arg2 (Rs, FROM)| 0   0 |
+---+---+---+---+---+---+---+---+
 \_____ 3 bits _____/ \_ 3 bits ______/ \_2b._/
```

* **Destination Register (`Arg1` / `Rd`, Bits [7:5] of Octet 1):** Point A (receives data).
* **Source Register (`Arg2` / `Rs`, Bits [4:2] of Octet 1):** Point B (provides data).
* **Operation Semantics:**
  $$\text{Rd} \leftarrow \text{Rs}$$
  For example: `LRR R0, R1` $\implies R0 = R1$ (value of `R1` is copied into `R0`).
* **Hardware Implementation:** Data bypasses the ALU entirely, traversing the dedicated single-cycle multiplexer bus `MUX 1` $\to$ `MUX 2` directly into `DEST-DMUX`. All flags in `FREG` remain untouched.

---

## 💻 Programmer ISA Reference & Instruction Semantics

The LIM M2 processor enforces a strict **Destination First** paradigm across all multi-operand instructions. In all operations, the first argument (`arg0`) explicitly defines the destination register where the result is committed.

In assembly and the compiler toolchain, general-purpose registers are designated as `R0`, `R1`, `R2`, `R3`, `R4`, `R5`, `R6`, `R7`.

### 1. Data Transfer & Memory
| Mnemonic | Programmer Signature | Code Example | Description |
|---|---|---|---|
| **`LRR`** | `LRR arg0(REG), arg1(REG) : arg0 = arg1` | `LRR R0, R1 ; R0 = R1` | Fast register-to-register copy (flags untouched). |
| **`LMR`** | `LMR arg0(REG), arg1(SRC_MODE) : arg0 = MEM[...]` | `LMR R0, R1, R2 ; R0 = MEM[{R0, R2}]` | Load from memory into register (Immediate, Pointer, PTREG, or 24-bit register pair). |
| **`LRM`** | `LRM arg0(REG), arg1(DST_MODE) : MEM[...] = arg0` | `LRM R0, R1 ; MEM[{R0, R1}] = R0` | Store register into memory (Inline, Pointer, PTREG, or 24-bit register pair). |
| **`PUSH`** | `PUSH arg0(REG) : SREG -= 2, MEM[SREG] = arg0` | `PUSH R0 ; Push R0 to stack` | Decrement SREG by 2 and push 16-bit word onto stack. |
| **`POP`** | `POP arg0(REG) : arg0 = MEM[SREG], SREG += 2` | `POP R0 ; Pop word into R0` | Pop word from stack into register and increment SREG by 2. |

### 2. Arithmetic & Comparison
| Mnemonic | Programmer Signature | Code Example | Description |
|---|---|---|---|
| **`ADD`** | `ADD arg0(REG), arg1(REG), arg2(REG) : arg0 = arg1 + arg2` | `ADD R0, R1, R2 ; R0 = R1 + R2` | 16-bit addition updating ZF, CF, OF flags. |
| **`SUB`** | `SUB arg0(REG), arg1(REG), arg2(REG) : arg0 = arg1 - arg2` | `SUB R0, R1, R2 ; R0 = R1 - R2` | 16-bit subtraction with borrow and zero flags. |
| **`MUL`** | `MUL arg0(REG), arg1(REG), arg2(REG) : arg0 = arg1 * arg2` | `MUL R0, R1, R2 ; R0 = R1 * R2` | Unsigned 16x16-bit multiplication (high bits in FREG/DBIT). |
| **`DIV`** | `DIV arg0(REG), arg1(REG), arg2(REG) : arg0 = arg1 / arg2` | `DIV R0, R1, R2 ; R0 = R1 / R2` | Integer division (division by zero triggers VEC 0 fault). |
| **`INC`** | `INC arg0(REG) : arg0 = arg0 + 1` | `INC R0 ; R0 = R0 + 1` | 1-byte instruction (`[7:3]` opcode, `[2:0]` Rd): atomic register increment by 1. |
| **`DEC`** | `DEC arg0(REG) : arg0 = arg0 - 1` | `DEC R0 ; R0 = R0 - 1` | 1-byte instruction (`[7:3]` opcode, `[2:0]` Rd): atomic register decrement by 1. |
| **`CMP`** | `CMP arg0(REG), arg1(REG) : compare(arg0, arg1)` | `CMP R0, R1 ; Compare R0 with R1` | Non-destructive compare setting `FREG.CMP` (`01`: R0<R1, `10`: R0==R1, `11`: R0>R1; `00`: reset/error) and ZF, CF flags. |

### 3. Bitwise Logic
| Mnemonic | Programmer Signature | Code Example | Description |
|---|---|---|---|
| **`AND`** | `AND arg0(REG), arg1(REG) : arg0 = arg0 & arg1` | `AND R0, R1 ; R0 = R0 & R1` | Bitwise logical AND (2 operands). |
| **`OR`** | `OR arg0(REG), arg1(REG) : arg0 = arg0 \| arg1` | `OR R0, R1 ; R0 = R0 \| R1` | Bitwise logical OR (2 operands). |
| **`XOR`** | `XOR arg0(REG), arg1(REG) : arg0 = arg0 ^ arg1` | `XOR R0, R1 ; R0 = R0 ^ R1` | Bitwise exclusive OR (2 operands, clears register if R0==R1). |
| **`NOT`** | `NOT arg0(REG) : arg0 = ~arg0` | `NOT R0 ; R0 = ~R0` | 1-byte instruction (`[7:3]` opcode, `[2:0]` Rd): bitwise inversion. |
| **`NAND`** | `NAND arg0(REG), arg1(REG) : arg0 = ~(arg0 & arg1)` | `NAND R0, R1 ; R0 = ~(R0 & R1)` | Bitwise NAND (2 operands). |
| **`NOR`** | `NOR arg0(REG), arg1(REG) : arg0 = ~(arg0 \| arg1)` | `NOR R0, R1 ; R0 = ~(R0 \| R1)` | Bitwise NOR (2 operands). |
| **`XNOR`** | `XNOR arg0(REG), arg1(REG) : arg0 = ~(arg0 ^ arg1)` | `XNOR R0, R1 ; R0 = ~(R0 ^ R1)` | Bitwise equivalence check (2 operands). |

### 4. Bit Shifts (with SMOD and DBIT Support)
| Mnemonic | Programmer Signature | Code Example | Description |
|---|---|---|---|
| **`BSL`** | `BSL arg0(REG), arg1(IMM) : arg0 = arg0 << arg1` | `BSL R0, 4 ; Shift R0 left by 4 bits` | Iterative in-place hardware shift left. Implemented via clocked shift register loop (1 cycle per bit, $\approx 300$ transistors instead of $\approx 30\,000$). Shifting by 16 bits takes 15 more cycles than shifting by 1 bit. Byte 0: `[7:3]` opcode 11000, `[2:0]` Rd. Byte 1: `[7:0]` shift (0--16). Circular rotation when `SMOD=1` (bit 15 wraps to bit 0); DBIT-filled (0 or 1) when `SMOD=0`. Last displaced bit is captured in `FREG.DBIT`. |
| **`BSR`** | `BSR arg0(REG), arg1(IMM) : arg0 = arg0 >> arg1` | `BSR R0, 4 ; Shift R0 right by 4 bits` | Iterative in-place hardware shift right. Implemented via clocked shift register loop (1 cycle per bit, $\approx 300$ transistors instead of $\approx 30\,000$). Shifting by 16 bits takes 15 more cycles than shifting by 1 bit. Byte 0: `[7:3]` opcode 11001, `[2:0]` Rd. Byte 1: `[7:0]` shift (0--16). Circular rotation when `SMOD=1` (bit 0 wraps to bit 15); DBIT-filled (0 or 1) when `SMOD=0`. Last displaced bit is captured in `FREG.DBIT`. |

### 5. Control Flow & Subroutines
| Mnemonic | Programmer Signature | Code Example | Description |
|---|---|---|---|
| **`JMP`** | `JMP target(IMM\|REG) : PC = target` | `JMP R0 ; Unconditional jump` | Unconditional jump to literal or register address. |
| **`JZ`** | `JZ target(IMM\|REG) : if FREG.ZF == 1 then PC = target` | `JZ loop_end ; Jump if ZF == 1` | Conditional branch if Zero Flag is asserted. |
| **`CALL`** | `CALL target(IMM\|REG) : SREG -= 2, MEM[SREG] = PC, PC = target` | `CALL func ; Call subroutine` | Push return address onto stack and branch to target. |
| **`RET`** | `RET : PC = MEM[SREG], SREG += 2` | `RET ; Return from subroutine` | Pop return address from stack into PC. |

### 6. Control, Interrupts & System Registers
| Mnemonic | Programmer Signature | Code Example | Description |
|---|---|---|---|
| **`NOP`** | `NOP : No Operation` | `NOP ; Pipeline bubble` | Single-cycle no-operation. |
| **`HALT`** | `HALT : Stop execution until interrupt` | `HALT ; Wait for hardware event` | Enter low-power sleep mode waiting for interrupt. |
| **`CLI`** | `CLI : FREG.MIE = 0` | `CLI ; Disable interrupts` | Atomic interrupt masking (critical section). |
| **`STI`** | `STI : FREG.MIE = 1` | `STI ; Enable interrupts` | Atomic interrupt unmasking. |
| **`INTR`** | `INTR vec(IMM) : Software interrupt trigger` | `INTR 4 ; Software interrupt VEC 4` | Trap into interrupt vector table, pushing PC and FREG. |
| **`RETI`** | `RETI : FREG = MEM[SREG], PC = MEM[SREG+2], SREG += 4` | `RETI ; Return from ISR` | Atomic restoration of FREG (clearing INTR to 0) and PC. |
| **`MSP`** | `MSP sreg, [op], args : special register operations` | `MSP FREG, OR, R0 ; FREG = FREG \| R0` | Direct load FREG/PTREG, bitmask logic on FREG (AND/OR/XOR/XNOR), or local pointer arithmetic on PTREG (ADD/SUB). |

---

## 📁 Repository Structure

```text
LIM2/
├── .gitignore               # Clean Git ignore rules (LaTeX, Python, macOS)
├── README.md                # Main documentation (English)
├── README.ua.md             # Українська документація
├── README.ru.md             # Русскоязычная документация
├── README.sk.md             # Slovenská dokumentácia
├── Docs/                    # Formal technical specifications & figures
│   ├── LIM_M2_Datasheet_EN.tex  # LaTeX source (English)
│   ├── LIM_M2_Datasheet_UA.tex  # LaTeX source (Ukrainian)
│   ├── LIM_M2_Datasheet_RU.tex  # LaTeX source (Russian)
│   ├── LIM_M2_Datasheet_SK.tex  # LaTeX source (Slovak)
│   ├── LIM_M2_Datasheet_*.pdf   # Compiled PDFs (48 pages each)
│   ├── test.tex                 # Standalone TikZ architectural datapath
│   ├── diagram.png / .svg       # Vector & Ultra-HD schematic assets
│   └── compile_datasheets.sh    # Build automation script
└── sim/                     # Python architectural simulator & GUI
    ├── sim.py               # Main CLI launcher
    ├── exampcpu.py          # LIM M2 CPU core model
    ├── core.py              # Base CPU abstraction
    ├── bus.py               # Memory bus and memory-mapped IO
    ├── devices.py           # RAM, Text Screen, UART, Timer peripherals
    ├── runner.py            # Execution and trace engine
    ├── ui.py                # Terminal / GUI monitor interface
    └── demo.hex             # Sample machine code binary
```

---

## 🚀 Quickstart & Simulation

### 1. Running the Simulator

Run the interactive architectural simulation with the bundled demo program:

```bash
# Launch interactive terminal simulation
python3 sim/sim.py sim/demo.hex -i
```

### 2. Compiling the Datasheets

To rebuild the formal LaTeX documentation and export fresh PDF specifications:

```bash
cd Docs
chmod +x compile_datasheets.sh
./compile_datasheets.sh
```

---

## 📜 License & Acknowledgments

* **Architecture & Concept:** Ivan Hniedash
* **Status:** Official Reference Architecture Specification (Draft 0.2)
