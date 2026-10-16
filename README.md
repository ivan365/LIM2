# LIM M2 Processor Architecture

<p align="center">
  <img src="Docs/diagram.png" alt="LIM M2 Datapath Schematic" width="850">
</p>

<p align="center">
  <b>High-Performance 16-Bit Microprogrammed CPU Core with Zero Tri-State Multiplexed Datapath & 32-Bit Linear Addressing (4 GB)</b>
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
* **Native 32-Bit Linear Memory & Stack Addressing (4 GB):**
  Features dedicated 32-bit linear address registers:
  * **`PTREG` (Pointer Register):** Linear flat addressing across 4 GB with optional hardware auto-increment (`AIP`).
  * **`SREG` (Stack Register):** Full 32-bit linear execution stack pointer supporting deep subroutine stacks and recursive frames.
* **Dual Execution Modes & Hardware Security (User & Supervisor):**
  Hardware privilege separation via `FREG.PRV` (bit 11). Transition to Supervisor Mode is strictly protected and allowed only from within 8 registered Privilege Zones (`$pv0..$pv15`) or on hardware interrupts.
* **32 Vector Registers (32-Bit Each):**
  16 hardware interrupt vectors (`$ir0..$ir15`) and 16 privilege zone boundary registers (`$pv0..$pv15`).
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
| **`SREG`** | **32-bit** | System Stack Register. Linear 32-bit addressing across 4 GB execution stack space. |
| **`PTREG`** | **32-bit** | Extended Pointer Register. Flat linear addressing across 4 GB with optional hardware auto-increment (`AIP`). |
| **`FREG`** | 16-bit | Processor Status and Control Register. Unifies condition flags and operational mode controls. |
| **`IR0`–`IR15`** | **32-bit** | 16 Hardware Interrupt Vector Registers. Base execution addresses for ISR routines. |
| **`PV0`–`PV15`** | **32-bit** | 16 Privilege Zone Registers (8 Protected Call Gate Ranges: `[pv0:pv1]` .. `[pv14:pv15]`). |
| **`ACCA` / `ACCB`** | 16-bit | Auxiliary ALU Latches (Dual Accumulator Staging). Pre-stages ALU operands A and B. |

### Flag and Control Register (`FREG`) Bit Layout

```text
 15    14    13    12   11   10    9    8    7    6    5    4    3    2    1    0
+-----+-----+-----+----+----+----+----+----+----+----+----+----+----+----+----+----+
|INTR |SMOD |DBIT |AIP |PRV |DWR |MIE |PIE |CLK1|CLK0|CMP1|CMP0| EM | OF | CF | ZF |
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
* **`PRV` (11):** Privilege Mode (`0`: User Mode, `1`: Supervisor Mode). Hardware-protected by 8 privilege zones.
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
   * `PUSH Rs` and `POP Rd`: word transfers via 32-bit stack pointer `SREG`.
   ```
   Octet 0: [ OPCODE (5b) | Rs / Rd [2:0] (Reg R0-R7) ]
   Octet 1: [ RSV=00000000 [7:0] ]
   ```

8. **Class VIII: Manage Special Registers (2–6 Bytes)**
   * `MSP sreg, [op], args`: direct access or functional modification of `FREG` (00), 32-bit `PTREG` (01), 32-bit stack pointer `SREG` (10), or 32 vector 32-bit registers `VEC` (11: `$ir0..$ir15` interrupt vectors and `$pv0..$pv15` privilege zone registers).
   ```
   Octet 0: [ 11010 (5b) | Mode (1b: 0=Load/LD, 1=Modify) | SREG (2b: 00=FREG, 01=PTREG, 10=SREG, 11=VEC) ]
   Octet 1 (VEC, 11):      [ Vector_ID [7:3] (0..31: ir0-15 / pv0-15) | Source [2:1] (00=Reg, 01=Imm32, 10=[$ptreg], 11=Ptr) | Sub/PtrType [0] ]
   Octet 2 (VEC Reg/Ptr):  [ Rd_hi [7:5] (high 16b) | Rs_lo [4:2] (low 16b) | RSV=00 [1:0] ] (for Source=00 or 11-reg)
   Octet 1 (FREG Load):    [ Rs [7:5] | RSV [4:3] | Source [2:1] | RSV [0] ]
   Octet 1 (FREG Logic):   [ OP [7:6] (00=AND, 01=OR, 10=XOR, 11=XNOR) | Rs [5:3] / RSV | Source [2:1] | RSV [0] ]
   Octet 1 (PTREG/SREG LD):[ Rd_hi [7:5] | Rs_lo [4:2] | Source [1:0] ]
   Octet 1 (PTREG/SREG Ar):[ OP [7] (0=ADD, 1=SUB) | Rs [6:4] | Source [3:2] | RSV [1:0] ]
   ```

9. **Class IX: Branch & Jump Instructions (2–6 Bytes)**
   * `JMP`, `JCR`, `JNZ`, `JZ`:
     * `MOD = 0` (000): 16-bit immediate address (3 bytes total).
     * `MOD = 1` (001): Indirect register branch via `Rs` (2 bytes total).
     * `MOD = 2` (010): 32-bit branch via pointer register `PTREG` (2 bytes total).
     * `MOD = 3` (011): 32-bit indirect branch via memory pointer `[addr32]` or register pair `[$rd:$rs]`.

10. **Class X: Memory Load & Store (2–4 Bytes)**
    * `LMR Rd, <SRC_MODE>` and `LRM Rs, <DST_MODE>`:
      * Bit 2 of Octet 0: `SZ` ($0 = 8$-bit byte, $1 = 16$-bit word).
      * Bits 1–0 of Octet 0: `Mode` (0 = Inline data, 1 = Imm pointer, 2 = 32-bit `PTREG` with auto-increment, 3 = Register pair 32-bit address).

---

## ⚡ Instruction Set Architecture (ISA - 32 Opcodes)

| Opcode | Hex | Mnemonic | Class | Functional Description |
| :---: | :---: | :--- | :--- | :--- |
| **00000** | `0x00` | **`NOP`** | Control | No operation; flushes `ALU_RESIDUAL` and resets carry/borrow tracking |
| **00001** | `0x01` | **`ADD`** | Arithmetic | 16-bit addition with automatic carry chaining via `ALU_RESIDUAL` |
| **00010** | `0x02` | **`SUB`** | Arithmetic | 16-bit subtraction with automatic borrow chaining via `ALU_RESIDUAL` |
| **00011** | `0x03` | **`MUL`** | Arithmetic | Integer multiplication; upper 16 bits latched into `ALU_RESIDUAL` |
| **00100** | `0x04` | **`DIV`** | Arithmetic | Integer division; remainder (modulo) latched into `ALU_RESIDUAL` |
| **00101** | `0x05` | **`LMR`** | Memory | Load byte/word into register (src: 0=Imm, 1=Ptr, 2=PTREG, 3=Register pair 32-bit; size: 8/16-bit) |
| **00110** | `0x06` | **`LRM`** | Memory | Store byte/word into memory (dst: 0=Inline, 1=Ptr, 2=PTREG, 3=Register pair 32-bit; size: 8/16-bit) |
| **00111** | `0x07` | **`LRR`** | Transfer | Fast register-to-register copy via bypass (`MUX 1` $\to$ `MUX 2`) |
| **01000** | `0x08` | **`CMP`** | Compare | Arithmetic compare; updates `FREG.CMP` (`01`: `<`, `10`: `=`, `11`: `>`), `ZF`, `CF`, `OF` non-destructively |
| **01001** | `0x09` | **`JMP`** | Branch | Unconditional branch (16-bit local or full 32-bit via `PTREG`) |
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
| **10110** | `0x16` | **`PUSH`** | Stack | Push 16-bit word onto 32-bit stack (`SREG <- SREG - 2`) |
| **10111** | `0x17` | **`POP`** | Stack | Pop 16-bit word from 32-bit stack (`SREG <- SREG + 2`) |
| **11000** | `0x18` | **`BSL`** | Shift | Barrel Shift Left (zero-fill or cyclic rotate via `DBIT` if `SMOD=1`) |
| **11001** | `0x19` | **`BSR`** | Shift | Barrel Shift Right (zero-fill or cyclic rotate via `DBIT` if `SMOD=1`) |
| **11010** | `0x1A` | **`MSP`** | System | Manage Special Registers (`FREG`, `PTREG`, `SREG`, `VEC`) |
| **11011** | `0x1B` | **`MOD`** | Arithmetic | Integer remainder (modulo): `Rd = Rs1 % Rs2` |
| **11100** | `0x1C` | **`INTR`** | System | Software interrupt (1 byte): lowest 3 bits `[2:0]` select vector `0..7` from the processor vector table |
| **11101** | `0x1D` | **`RSV29`** | Reserved | Floating-Point Unit (FPU) slot |
| **11110** | `0x1E` | **`RSV30`** | Reserved | Hardware cryptography accelerator slot |
| **11111** | `0x1F` | **`RSV31`** | Reserved | Future architecture expansion slot |

---

## 🔌 Physical Interface & 50-Pin Package with Native 32-Bit Address Bus

The LIM M2 processor features a **native 32-bit address bus (`A0–A31`)**, providing direct physical access to the entire linear address space of **4 Gigabytes**, and an **8-bit (1-byte) external data bus (`D0–D7`)**.

The processor is packaged in a **50-pin DIP-50 / QFP-52** footprint (25 pins per side, formed by adding 8 pins to each side relative to the baseline 34-pin package):

| Pin | Name | Direction | Description |
| :---: | :--- | :---: | :--- |
| **1–16** | `A0`–`A15` | Output | Lower 16 bits of 32-bit native physical address bus |
| **17–24** | `A16`–`A23` | Output | Middle 8 bits of address bus (+8 pins added to left side) |
| **25** | `CLK1` | Input | Phase 1 system clock input |
| **26** | `CLK2` | Input | Phase 2 system clock input (non-overlapping) |
| **27** | `RESET` | Input | Hardware reset line (active low) |
| **28** | `RDI` | Input | Raw Direct Interrupt: priority hardware interrupt request line |
| **29** | **`IA`** | **Output** | **Interrupt Acknowledge: processor grants interrupt request** |
| **30** | `RF` | Input | Ready Flag: slave device handshake ready acknowledge |
| **31** | `WD` | Output | Bus Write Enable strobe |
| **32** | `RD` | Output | Bus Read Enable strobe |
| **33** | `VCC` | Power | Primary digital power supply (+3.3 V / +5 V) |
| **34** | `GND` | Power | System ground reference (0 V) |
| **35–42** | `D0`–`D7` | Bidirectional | **8-bit (1-byte) external bidirectional data bus for memory and peripherals** |
| **43–50** | `A24`–`A31` | Output | **Upper 8 bits of address bus (+8 pins added to right side, 4 GB addressing)** |

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

### 3. Context Preservation on 32-Bit Stack (`SREG`) and Supervisor Mode Transition

Upon accepting an interrupt:
1. **Save Return PC (32-bit):** Program counter is pushed onto the 32-bit stack:
   $$\text{SREG} \leftarrow \text{SREG} - 4, \quad \text{Memory32}[\text{SREG}] \leftarrow \text{PC}_{31:0}$$
2. **Save Flags & Status (`FREG`):** Pushed with original `PRV` and $\text{INTR} = 0$:
   $$\text{SREG} \leftarrow \text{SREG} - 2, \quad \text{Memory16}[\text{SREG}] \leftarrow \text{FREG}$$
3. **Hardware Lockout & Supervisor Elevation:** `FREG.PRV` is set to `1` (Supervisor Mode), `FREG.INTR` is set to `1` (bit 15), and `FREG.MIE` is cleared to `0`, locking out nested re-entrancy.
4. **Dispatch:** The 32-bit vector handler address is loaded directly from `$ir0..$ir15` into `PC`.

### 4. Return from Interrupt (`RTI`)

Exiting the handler pops the saved architectural context:
1. $\text{FREG} \leftarrow \text{Memory16}[\text{SREG}], \quad \text{SREG} \leftarrow \text{SREG} + 2$ (automatically restoring original `PRV`, clearing `INTR` back to `0`, and restoring `MIE`).
2. $\text{PC} \leftarrow \text{Memory32}[\text{SREG}], \quad \text{SREG} \leftarrow \text{SREG} + 4$.
Execution resumes instantly on the subsequent cycle with zero state contamination in the original privilege mode.

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

The **`LMR`** instruction (`Opcode 00101` / `0x05`) serves as the primary gateway for transferring external data and memory into the LIM M2 general-purpose register file (`R0`–`R7`). It features a versatile encoding structure with native support for 32-bit physical addressing (up to 4 GB).

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
  * `10` (`2`): **`PTREG` Pointer** — Memory is accessed via the dedicated 32-bit system pointer register `PTREG`. If auto-increment flag `FREG.AIP` (bit 12) is set, `PTREG` automatically increments by $+1$ or $+2$, delivering hardware-accelerated streaming array transfers.
  * `11` (`3`): **User Register Pair (32-bit Addressing via GPR Pair)** — The user selects two 16-bit registers (`Arg1` and `Arg2`) forming a 32-bit address:
    * **`Arg1` (Bits [7:5] of Octet 1):** holds the **upper 16 address bits**. Crucially, this same register also serves as the destination register: after data is retrieved from memory, the upper address bits in `Arg1` are **overwritten with the loaded data**!
    * **`Arg2` (Bits [4:2] of Octet 1):** holds the **lower 16 address bits** and preserves its value.
    * The physical 32-bit address is synthesized in hardware:
      $$\text{EA}[31:0] = (\text{Arg1}[15:0] \ll 16) \mid \text{Arg2}[15:0]$$
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
  * `10` (`2`): **`PTREG` Pointer** — Stored via the 32-bit physical address in `PTREG`. If auto-increment flag `FREG.AIP` (bit 12) is active, `PTREG` automatically increments by $+1$ or $+2$, enabling high-throughput memory streaming.
  * `11` (`3`): **User Register Pair (32-bit Addressing via GPR Pair)**:
    * **`Arg1` (Bits [7:5] of Octet 1):** holds the **upper 16 address bits** and simultaneously acts as the **source register** (`Rs`) containing data to write.
    * **`Arg2` (Bits [4:2] of Octet 1):** holds the **lower 16 address bits** (`Rs_lo`).
    * The physical 32-bit effective address is synthesized in hardware:
      $$\text{EA}[31:0] = (\text{Arg1}[15:0] \ll 16) \mid \text{Arg2}[15:0]$$
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
| **`LMR`** | `LMR arg0(REG), arg1(SRC_MODE) : arg0 = MEM[...]` | `LMR R0, R1, R2 ; R0 = MEM[{R0, R2}]` | Load from memory into register (Immediate, Pointer, PTREG, or 32-bit register pair). |
| **`LRM`** | `LRM arg0(REG), arg1(DST_MODE) : MEM[...] = arg0` | `LRM R0, R1 ; MEM[{R0, R1}] = R0` | Store register into memory (Inline, Pointer, PTREG, or 32-bit register pair). |
| **`PUSH`** | `PUSH arg0(REG) : SREG -= 2, MEM[SREG] = arg0` | `PUSH R0 ; Push R0 to stack` | Decrement 32-bit SREG by 2 and push 16-bit word onto stack. |
| **`POP`** | `POP arg0(REG) : arg0 = MEM[SREG], SREG += 2` | `POP R0 ; Pop word into R0` | Pop word from stack into register and increment 32-bit SREG by 2. |

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
| **`CALL`** | `CALL target(IMM\|REG) : SREG -= 4, MEM32[SREG] = PC, PC = target` | `CALL func ; Call subroutine` | Push return address onto 32-bit stack and branch to target. |
| **`RET`** | `RET : PC = MEM32[SREG], SREG += 4` | `RET ; Return from subroutine` | Pop return address from 32-bit stack into PC. |

### 6. Control, Interrupts & System Registers
| Mnemonic | Programmer Signature | Code Example | Description |
|---|---|---|---|
| **`NOP`** | `NOP : No Operation` | `NOP ; Pipeline bubble` | Single-cycle no-operation. |
| **`HALT`** | `HALT : Stop execution until interrupt` | `HALT ; Wait for hardware event` | Enter low-power sleep mode waiting for interrupt. |
| **`CLI`** | `CLI : FREG.MIE = 0` | `CLI ; Disable interrupts` | Atomic interrupt masking (critical section). |
| **`STI`** | `STI : FREG.MIE = 1` | `STI ; Enable interrupts` | Atomic interrupt unmasking. |
| **`INTR`** | `INTR vec(IMM) : Software interrupt trigger` | `INTR 4 ; Software interrupt VEC 4` | Trap into interrupt vector table, pushing PC and FREG. |
| **`RETI`** | `RETI : FREG = MEM16[SREG], PC = MEM32[SREG+2], SREG += 6` | `RETI ; Return from ISR` | Atomic restoration of FREG (restoring PRV, clearing INTR) and PC. |
| **`MSP`** | `MSP sreg, [op], args : special register operations` | `MSP FREG, OR, R0 ; FREG = FREG \| R0` | Direct load FREG/PTREG/SREG/VEC, bitmask logic on FREG, local pointer arithmetic on PTREG/SREG, or vector register manipulation. |

---

## 🛠️ LIM M2 Assembly Language & Compiler (`limasm.py`)

The SDK includes the official two-pass assembler compiler **`limasm.py`**, which compiles `.asm` source files into both raw binary firmware images (`.bin`) and annotated hexadecimal dumps (`.hex`), and integrates directly with the interactive simulator (`python3 sim/sim.py program.asm -i`).

### 1. Register Naming & Size Suffixes (`.b`, `.w`, `.d`)
* **General-Purpose Registers (GPRs):** prefixed with `$` and numbered `$0`–`$7` (classic aliases `R0`–`R7` and `$r0`–`$r7` are also accepted).
* **Special Registers:**
  * `$ptreg` — 32-bit linear address pointer register (`PTREG`, 4 GB flat physical address space);
  * `$freg` — 16-bit status & flag register (`FREG`, bit 11: `PRV` privilege mode);
  * `$sreg` (or `$sp`) — 32-bit stack pointer register (`SREG`);
  * `$ir0`..`$ir15` — 16 vector 32-bit registers for interrupt handlers;
  * `$pv0`..`$pv15` — 16 vector 32-bit registers defining 8 Privilege Zones (`[$pv0:$pv1]` .. `[$pv14:$pv15]`).
* **Operand Size Suffixes:**
  * `.b` (*byte*, 8-bit) — e.g., `LMR.b $0, 0x42`
  * `.w` (*word*, 16-bit, default) — e.g., `LMR.w $0, 0x1234` or simply `LMR $0, 0x1234`
  * `.d` (*doubleword*, 32-bit) — e.g., `LMR.d $0, [0x1000]`

### 2. Register-Only ALU & Unary Instructions
3-operand ALU instructions (`ADD`, `SUB`, `MUL`, `DIV`, `MOD`) and 1-byte unary operations (`INC`, `DEC`, `NOT`) operate strictly on general-purpose registers:
```asm
ADD $0, $1, $2      ; $0 = $1 + $2 (also accepts: ADD R0, R1, R1)
SUB $3, $3, $1      ; $3 = $3 - $1
MUL $4, $0, $2      ; $4 = $0 * $2
DIV $5, $4, $1      ; $5 = $4 / $1
INC $0              ; $0 = $0 + 1 (or INC R0 — single-byte instruction)
DEC $1              ; $1 = $1 - 1 (or DEC R1 — single-byte instruction)
NOT $2              ; $2 = ~$2
```

### 3. Memory Load & Store Addressing Modes (`LMR` & `LRM`)
In memory transfer instructions, the operand syntax directly determines the hardware addressing mode:
* **Bare number (no brackets)** — immediate value (`SRC=0` / `DST=0`).
* **Square brackets `[...]`** — memory reference / pointer dereference.

| Addressing Mode | `LMR` Example (Load to Register) | `LRM` Example (Store to Memory) | Detailed Explanation |
|---|---|---|---|
| **Immediate** (`SRC=0`) | `LMR.w $0, 0x1234`<br>`LMR.b $1, 0x25` | `LRM.w $0, 0x2000` | Bare number without brackets: in `LMR`, loads the constant directly into `$0`; in `LRM`, specifies the 16-bit target address. |
| **Direct Reference `[addr]`** (`SRC=1`) | `LMR.w $0, [0x1000]` | `LRM.w $0, [0x1000]` | Square brackets dereference memory at address `0x1000` (`MEM[0x1000]`). |
| **Indirect via `[$ptreg]`** (`SRC=2`) | `LMR.w $0, [$ptreg]` | `LRM.b $4, [$ptreg]` | Dereferences the 32-bit physical address stored in `PTREG` (`MEM[PTREG]`). |
| **Register Pair `[$0:$1]`** (`SRC=3`) | `LMR $0, [$0:$1]`<br>*(or `LMR, $0, [$0:$1]`)* | `LRM $2, [$0:$1]` | Forms a 32-bit pointer from two registers (`($0 << 16) \| $1`). |

### 4. Native 32-Bit Addressing (4 GB), Privilege Modes & Comprehensive MSP Architecture

The LIM M2 architecture features a **native 32-bit linear address space** (`A0–A31`, up to **4 Gigabytes** of physical memory) without pin multiplexing or banking. The processor incorporates a hardware privilege protection system and 32 vector 32-bit registers.

#### 4.1. Dual Privilege Model (User & Supervisor)
The core operates in one of two hardware privilege modes, controlled by bit **11 (`PRV`)** of `FREG`:
* **Supervisor Mode (`PRV = 1`)** — privileged kernel/OS mode. Full access to all 4 GB address space, interrupt management, and Privilege Zone configuration.
* **User Mode (`PRV = 0`)** — unprivileged application mode. Arbitrary modification of system registers (`$ir0..$ir15`, `$pv0..$pv15`), disabling interrupts, and unauthorized elevation are strictly blocked.

#### 4.2. Protection Lifecycle, Privilege Zones & Elevation Rules

The LIM M2 protection architecture implements a secure boot and hardware Call Gate model:

1. **Automatic Boot in Supervisor Mode (Power-On / Reset):**
   * Upon power-on or hardware reset, the processor **automatically boots in Supervisor Mode (`PRV = 1`)**.
   * This guarantees that boot firmware and operating system kernels possess full privileges to initialize memory, stack pointers, vector tables, and hardware peripherals.

2. **Initial Setup and Dropping Privileges:**
   * During early boot in Supervisor Mode, the kernel registers interrupt service vectors (`$ir0..$ir15`) and configures the 8 Privilege Zones (`$pv0..$pv15`, pairs of `[Start:End]` bounds).
   * After completing initialization, the kernel clears the privilege bit (`PRV = 0`, e.g., via `MSP.and $freg, ~0x0800` or `MSP.ld $freg, ...`) and transfers execution to user space (User Mode).

3. **Elevation to Supervisor Mode & Zone Reconfiguration:**
   * When executing in User Mode (`PRV = 0`), any software attempt to arbitrarily assert `PRV = 1` from non-privileged memory is **blocked by hardware** and triggers a General Protection Fault.
   * Software elevation to Supervisor Mode (`PRV = 1`) is permitted **strictly when the current Program Counter (`PC`) resides inside one of the 8 registered Privilege Zones**:
     $$\exists\, k \in [0..7]: \quad \$pv_{2k} \le \text{PC} \le \$pv_{2k+1}$$
   * Modifying and reconfiguring the Privilege Zone registers (`$pv0..$pv15`) themselves is also **only permitted while executing code inside these Privilege Zones**.

4. **Exiting Privilege Zones Does NOT Drop Privileges Automatically:**
   * **Critical architectural rule:** When Supervisor Mode (`PRV = 1`) is enabled, **leaving the Privilege Zone boundary (via branch, call, or sequential execution) DOES NOT automatically clear `PRV`!**
   * The hardware does not perform hidden state drops — **the operating system / software is strictly responsible for clearing `PRV = 0`** before returning execution to unprivileged user code.

5. **Hardware Interrupts (IRQ):**
   * When an interrupt occurs, the core pushes current `PC` and `FREG` onto `SREG`, automatically asserts `PRV = 1`, clears `MIE = 0`, and branches to the vector in `$ir`. Return via `RETI` pops `FREG`, restoring the original user mode (`PRV = 0`).

---

### 4.3. Bit Structure of MSP (Opcode 26 / `0b11010`)

The `MSP` (Manipulate Special Register) instruction has a modular encoding from 2 to 6 bytes:

```text
Octet 0 (Base Opcode & Register Selector):
 7   6   5   4   3   2   1   0
+---+---+---+---+---+---+---+---+
| 1   1   0   1   0 |MOD|  REG  |
+---+---+---+---+---+---+---+---+
 \_____ 5 bits _____/ \1/ \_ 2b _/
  Opcode = 26 (0x1A)
```
* **`MOD` (Bit 2):**
  * `0`: **Load (`MSP.ld`)** — direct write into target special register.
  * `1`: **Modify / Compute** — bitwise logic for `FREG` (`AND`, `OR`, `XOR`, `XNOR`) or offset arithmetic for `PTREG` / `SREG` (`ADD`, `SUB`).
* **`REG` (Bits [1:0]):**
  * `00`: **`FREG`** — 16-bit flag and status register.
  * `01`: **`PTREG`** — 32-bit pointer register (4 GB).
  * `10`: **`SREG`** — 32-bit stack pointer.
  * `11`: **`VEC`** — 32 vector registers of 32 bits (`$ir0..$ir15`, `$pv0..$pv15`).

---

#### Unified Source Encoding (Source Bits [2:1]):
Across all instruction variants, bits `[2:1]` are standardized:
* `00`: **GPR Registers (Direct)** — operand sourced from register `$rs` or pair `$rd:$rs`.
* `01`: **Immediate Constant** — `imm16` or `imm32` following instruction bytes.
* `10`: **Indirect via `PTREG` (`[$ptreg]`)** — native memory dereference.
* `11`: **Memory Pointer** — either register pair pointer `[$rd:$rs]` or direct address `[addr]`.

---

#### 4.3.1. Mode 1: Load into Flag Register FREG (MOD = 0, REG = 00)
Command: `MSP.ld $freg, <source>`

```text
Octet 0: [ 11010 | 0 | 00 ] = 0xD0 (26, LD, FREG)

Octet 1 with SRC=00 (from GPR $rs, length 2 bytes):
 7   6   5   4   3   2   1   0
+---+---+---+---+---+---+---+---+
|    Rs     | 0   0   0 | 0   0 |
+---+---+---+---+---+---+---+---+
 \_ 3 bits _/ \_Reserved/ \SRC=00/
Example: MSP.ld $freg, $0 -> D0 00

Octets 1..3 with SRC=01 (immediate constant imm16, length 4 bytes):
Octet 1: [ 0   0   0   0   0   0 | 0   1 ] = 0x01 (SRC=01)
Octet 2: [        imm16 [15:8]         ] (high byte)
Octet 3: [        imm16 [7:0]          ] (low byte)
Example: MSP.ld $freg, 0x0000 -> D0 01 00 00

Octet 1 with SRC=10 (from memory via pointer [$ptreg], length 2 bytes):
Octet 1: [ 0   0   0   0   0   0 | 1   0 ] = 0x02 (SRC=10)
Example: MSP.ld $freg, [$ptreg] -> D0 02

Octets 1..3 with SRC=11 (from memory at direct address [addr16], length 4 bytes):
Octet 1: [ 0   0   0   0   0   0 | 1   1 ] = 0x03 (SRC=11)
Octet 2..3: [ addr16_hi | addr16_lo ]
Example: MSP.ld $freg, [0x1000] -> D0 03 10 00
```

---

#### 4.3.2. Mode 2: FREG Bitwise Logic (MOD = 1, REG = 00)
Commands: `MSP.and $freg`, `MSP.or $freg`, `MSP.xor $freg`, `MSP.xnor $freg`
Operation: `OP [7:6]`: `00`=AND, `01`=OR, `10`=XOR, `11`=XNOR.

```text
Octet 0: [ 11010 | 1 | 00 ] = 0xD4 (26, MOD, FREG)

Octet 1 with SRC=00 (mask from GPR $rs, length 2 bytes):
 7   6   5   4   3   2   1   0
+---+---+---+---+---+---+---+---+
|  OP   |    Rs     | 0 | 0   0 |
+---+---+---+---+---+---+---+---+
 \_ 2b _/ \_ 3 bits _/ \1/ \SRC=00/
Example: MSP.xor $freg, $2 -> D4 90 (OP=10_2, Rs=2, SRC=00)

Octets 1..3 with SRC=01 (immediate mask imm16, length 4 bytes):
Octet 1: [  OP  | 0   0   0   0 | 0   1 ] (bits [5:2] reserved, SRC=01)
Octet 2..3: [ mask [15:8] | mask [7:0] ]
Example: MSP.or $freg, 0x0200 -> D4 41 02 00 (OP=01_2, enables MIE=1)

Octet 1 with SRC=10 (mask from memory via pointer [$ptreg], length 2 bytes):
Octet 1: [  OP  | 0   0   0   0 | 1   0 ] (SRC=10)
Example: MSP.and $freg, [$ptreg] -> D4 02

Octets 1..3 with SRC=11 (mask from memory at direct address [addr16], length 4 bytes):
Octet 1: [  OP  | 0   0   0   0 | 1   1 ] (SRC=11)
Octet 2..3: [ addr16_hi | addr16_lo ]
Example: MSP.and $freg, [0x2000] -> D4 03 20 00
```

---

#### 4.3.3. Mode 3: Load Pointer Registers PTREG / SREG (MOD = 0, REG = 01 / 10)
Commands: `MSP.ld $ptreg, ...` (`REG=01`, octet 0 = `0xD1`), `MSP.ld $sreg, ...` (`REG=10`, octet 0 = `0xD2`).

```text
Octet 0: [ 11010 | 0 | REG ] (0xD1 for PTREG, 0xD2 for SREG)

Variant 3.1: Load from GPR pair ($rd, $rs or [$rd:$rs]) (length 2 bytes):
 7   6   5   4   3   2   1   0
+---+---+---+---+---+---+---+---+
|    Rd_hi      |    Rs_lo      | 0   0 |
+---+---+---+---+---+---+---+---+
 \___ 3 bits ___/ \___ 3 bits ___/ \SRC=00/
   High 16 bits     Low 16 bits
Example: MSP.ld $ptreg, $0, $1 -> D1 04 (Rd_hi=0, Rs_lo=1, SRC=00)
Example: MSP.ld [$ptreg], $0, $1 -> D1 04 (pointer builder alias)

Variant 3.2: Direct load of imm32 / imm16 (length 4–6 bytes):
Octet 1: [ 0   0   0   0   0 | SZ | 0   1 ] (SZ: 0=16b, 1=24/32b; SRC=01)
Octets 2..5 (when SZ=1): [ imm32 (31:24) | imm32 (23:16) | imm32 (15:8) | imm32 (7:0) ]
Example: MSP.ld $ptreg, 0x00010000 -> D1 05 00 01 00 00 (6 bytes)
Example: MSP.ld $ptreg, 0xA000 -> D1 01 A0 00 (4 bytes)

Variant 3.3: NATIVE 1-CYCLE POINTER DEREFERENCING [$ptreg] (length 2 bytes!):
 7   6   5   4   3   2   1   0
+---+---+---+---+---+---+---+---+
| 0   0   0   0   0 | 0 | 1   0 | = 0x02
+---+---+---+---+---+---+---+---+
 \_____ 5 zero bits _____/ \1/ \SRC=10/
Function: Hardware CPU cycle PTREG <- MEM[PTREG] in a single 2-byte instruction!
Example: MSP.ld $ptreg, [$ptreg] -> D1 02 (2 bytes!)
Example: MSP.ld $sreg, [$ptreg]  -> D2 02 (2 bytes!)

Variant 3.4: Load pointer from memory by reference [addr] (length 4–6 bytes):
Octet 1: [ 0   0   0   0   0 | SZ | 1   1 ] (SRC=11)
Octets 2..3 (or 2..5): [ addr_hi | addr_lo ]
Example: MSP.ld $ptreg, [0xA000] -> D1 03 A0 00 (4 bytes: reads pointer from MEM[0xA000])
```

---

#### 4.3.4. Mode 4: Pointer Arithmetic for PTREG / SREG (MOD = 1, REG = 01 / 10)
Commands: `MSP.add $ptreg, ...`, `MSP.sub $ptreg, ...` (`0xD5`), `MSP.add/sub $sreg` (`0xD6`).
Operation: `OP [7]`: `0` = `ADD` (+offset), `1` = `SUB` (-offset).

```text
Octet 0: [ 11010 | 1 | REG ] (0xD5 for PTREG, 0xD6 for SREG)

Octet 1 with SRC=00 (offset from GPR $rs, length 2 bytes):
 7   6   5   4   3   2   1   0
+---+---+---+---+---+---+---+---+
|OP |    Rs     | 0   0 | 0   0 |
+---+---+---+---+---+---+---+---+
 \1/ \_ 3 bits _/ \_rsrv / \SRC=00/
Example: MSP.add $ptreg, $3 -> D5 30 (OP=0, Rs=3, SRC=00)
Example: MSP.sub $sreg, $4  -> D6 C0 (OP=1, Rs=4, SRC=00)

Octets 1..3 with SRC=01 (immediate offset imm16, length 4 bytes):
Octet 1: [ OP | 0   0   0   0   0 | 0   1 ] (SRC=01)
Octets 2..3: [ offset [15:8] | offset [7:0] ]
Example: MSP.add $ptreg, 0x0010 -> D5 01 00 10 (4 bytes)
Example: MSP.sub $sreg, 0x0004  -> D6 81 00 04 (4 bytes)

Octet 1 with SRC=10 (offset from memory via pointer [$ptreg], length 2 bytes):
Octet 1: [ OP | 0   0   0   0   0 | 1   0 ] (SRC=10)
Example: MSP.add $ptreg, [$ptreg] -> D5 02

Octets 1..3 with SRC=11 (offset from memory at address [addr16], length 4 bytes):
Octet 1: [ OP | 0   0   0   0   0 | 1   1 ] (SRC=11)
Octets 2..3: [ addr16_hi | addr16_lo ]
Example: MSP.add $ptreg, [0x3000] -> D5 03 30 00
```

---

#### 4.3.5. Mode 5: Load 32-bit Vector Registers (MOD = 0, REG = 11)
Commands: `MSP.ld $ir0..$ir15, ...` (interrupt vectors, IDs: 0..15), `MSP.ld $pv0..$pv15, ...` (Privilege Zone bounds, IDs: 16..31).
*Note:* Modification (`MOD=1`) for vector registers is hardware-blocked.

```text
Octet 0: [ 11010 | 0 | 11 ] = 0xD3 (26, LD, VEC)

Variant 5.1: From GPR pair ($rd, $rs or $rd:$rs) (length 3 bytes):
Octet 1: [      Vector_ID [7:3]      | 0   0 | 0 ] (SRC=00, SUB=0)
Octet 2: [    Rd_hi [7:5]    |    Rs_lo [4:2]    | 0   0 ]
Example: MSP.ld $ir0, $0, $1  -> D3 00 04 (3 bytes: ID=0, Rd=0, Rs=1)
Example: MSP.ld $pv0, $2, $3  -> D3 80 4C (3 bytes: ID=16, Rd=2, Rs=3)

Variant 5.2: Direct 32-bit address vector imm32 (length 6 bytes):
Octet 1: [      Vector_ID [7:3]      | 0   1 | 0 ] (SRC=01, SUB=0)
Octet 2: [          imm32 [31:24]            ]
Octet 3: [          imm32 [23:16]            ]
Octet 4: [          imm32 [15:8]             ]
Octet 5: [          imm32 [7:0]              ]
Example: MSP.ld $ir0, 0x00010000 -> D3 02 00 01 00 00 (6 bytes)
Example: MSP.ld $pv0, 0x00008000 -> D3 82 00 00 80 00 (6 bytes)

Variant 5.3: Read vector from memory via pointer [$ptreg] (length 2 bytes!):
Octet 1: [      Vector_ID [7:3]      | 1   0 | 0 ] (SRC=10, SUB=0)
Example: MSP.ld $ir1, [$ptreg] -> D3 0C (2 bytes: reads MEM32[PTREG])
Example: MSP.ld $pv1, [$ptreg] -> D3 8C (2 bytes)

Variant 5.4: Read vector from memory via GPR pair pointer [$rd:$rs] (length 3 bytes):
Octet 1: [      Vector_ID [7:3]      | 1   1 | 0 ] (SRC=11, SUB=0)
Octet 2: [    Rd_hi [7:5]    |    Rs_lo [4:2]    | 0   0 ]
Example: MSP.ld $ir2, [$0:$1] -> D3 16 04 (3 bytes: reads MEM32[(R0<<16)|R1])

Variant 5.5: Read vector from memory at direct 32-bit address [addr32] (length 6 bytes):
Octet 1: [      Vector_ID [7:3]      | 1   1 | 1 ] (SRC=11, SUB=1)
Octets 2..5: [ addr32 (31:24) | addr32 (23:16) | addr32 (15:8) | addr32 (7:0) ]
Example: MSP.ld $ir0, [0x00005000] -> D3 07 00 00 50 00 (6 bytes)
```

---

### 4.4. 25 Concrete MSP Examples with Bit-Level Breakdown

| # | Assembly Instruction | Octet 0 (bits / hex) | Octet 1 (bits / hex) | Octet 2..5 (hex) | Result (Hex Bytes) | Operational Description |
|---|---|---|---|---|---|---|
| **1** | `MSP.ld $ir0, 0x00010000` | `11010 0 11` (`0xD3`) | `00000 01 0` (`0x02`) | `00 01 00 00` | `D3 02 00 01 00 00` | Configure IRQ0 interrupt vector to address 0x00010000 |
| **2** | `MSP.ld $ir1, 0x00025000` | `11010 0 11` (`0xD3`) | `00001 01 0` (`0x0A`) | `00 02 50 00` | `D3 0A 00 02 50 00` | Configure IRQ1 interrupt vector to address 0x00025000 |
| **3** | `MSP.ld $pv0, 0x00008000` | `11010 0 11` (`0xD3`) | `10000 01 0` (`0x82`) | `00 00 80 00` | `D3 82 00 00 80 00` | Lower boundary of Privilege Zone 0 ($pv0 = 0x8000) |
| **4** | `MSP.ld $pv1, 0x00008FFF` | `11010 0 11` (`0xD3`) | `10001 01 0` (`0x8A`) | `00 00 8F FF` | `D3 8A 00 00 8F FF` | Upper boundary of Privilege Zone 0 ($pv1 = 0x8FFF) |
| **5** | `MSP.ld $ir2, $0:$1` | `11010 0 11` (`0xD3`) | `00010 00 0` (`0x10`) | `000 001 00` (`0x04`) | `D3 10 04` | Load IRQ2 vector from GPR pair ($0 = high, $1 = low) |
| **6** | `MSP.ld $pv2, $2, $3` | `11010 0 11` (`0xD3`) | `10010 00 0` (`0x90`) | `010 011 00` (`0x4C`) | `D3 90 4C` | Load Zone 1 start ($pv2) from GPR pair $2 and $3 |
| **7** | `MSP.ld $ir3, [$ptreg]` | `11010 0 11` (`0xD3`) | `00011 10 0` (`0x1C`) | — | `D3 1C` | Indirect load of IRQ3 vector from memory via PTREG (2 bytes) |
| **8** | `MSP.ld $pv3, [$ptreg]` | `11010 0 11` (`0xD3`) | `10011 10 0` (`0x9C`) | — | `D3 9C` | Indirect load of Zone 1 limit ($pv3) via PTREG (2 bytes) |
| **9** | `MSP.ld $ir4, [$4:$5]` | `11010 0 11` (`0xD3`) | `00100 11 0` (`0x26`) | `100 101 00` (`0x94`) | `D3 26 94` | Load IRQ4 vector via 32-bit pointer in registers [$4:$5] |
| **10** | `MSP.ld $pv4, [0x0000A000]` | `11010 0 11` (`0xD3`) | `10100 11 1` (`0xA7`) | `00 00 A0 00` | `D3 A7 00 00 A0 00` | Load $pv4 from memory at direct 32-bit address [0xA000] |
| **11** | `MSP.ld $freg, 0x0000` | `11010 0 00` (`0xD0`) | `000 00 01 0` (`0x02`) | `00 00` | `D0 02 00 00` | Clear status flags register (FREG = 0) |
| **12** | `MSP.or $freg, 0x0200` | `11010 1 00` (`0xD4`) | `01 000 01 0` (`0x42`) | `02 00` | `D4 42 02 00` | Enable interrupts (FREG \|= 0x0200, MIE bit) |
| **13** | `MSP.and $freg, 0x0001` | `11010 1 00` (`0xD4`) | `00 000 01 0` (`0x02`) | `00 01` | `D4 02 00 01` | Mask AND: preserve only Zero Flag (ZF) |
| **14** | `MSP.xor $freg, $1` | `11010 1 00` (`0xD4`) | `10 001 00 0` (`0x88`) | — | `D4 88` | Toggle FREG bits using mask in register $1 |
| **15** | `MSP.xnor $freg, 0x00FF` | `11010 1 00` (`0xD4`) | `11 000 01 0` (`0xC2`) | `00 FF` | `D4 C2 00 FF` | Bitwise XNOR of FREG with immediate mask |
| **16** | `MSP.ld $freg, $2` | `11010 0 00` (`0xD0`) | `010 00 00 0` (`0x40`) | — | `D0 40` | Direct restoration of FREG from register $2 |
| **17** | `MSP.ld $freg, [$ptreg]` | `11010 0 00` (`0xD0`) | `000 00 10 0` (`0x04`) | — | `D0 04` | Load saved flags word from stack buffer via PTREG |
| **18** | `MSP.ld $ptreg, 0x00100000` | `11010 0 01` (`0xD1`) | `000 000 01` (`0x01`) | `00 10 00 00` | `D1 01 00 10 00 00` | Direct load of 32-bit address into PTREG (1 Megabyte) |
| **19** | `MSP.ld $ptreg, $0, $1` | `11010 0 01` (`0xD1`) | `000 001 00` (`0x04`) | — | `D1 04` | Assemble 32-bit PTREG from two GPRs ($0 = high, $1 = low) |
| **20** | `MSP.ld $ptreg, [$ptreg]` | `11010 0 01` (`0xD1`) | `000 000 10` (`0x02`) | — | `D1 02` | **Single-cycle native pointer dereference** (PTREG <- MEM[PTREG]) |
| **21** | `MSP.ld $ptreg, [0x5000]` | `11010 0 01` (`0xD1`) | `000 000 11` (`0x03`) | `50 00` | `D1 03 50 00` | Load pointer from fixed address table in memory |
| **22** | `MSP.add $ptreg, 0x0020` | `11010 1 01` (`0xD5`) | `0 000 01 00` (`0x04`) | `00 20` | `D5 04 00 20` | Hardware advance of PTREG by +32 bytes |
| **23** | `MSP.sub $ptreg, $3` | `11010 1 01` (`0xD5`) | `1 011 00 00` (`0xB0`) | — | `D5 B0` | Decrement PTREG by dynamic offset in register $3 |
| **24** | `MSP.ld $sreg, 0x00003F00` | `11010 0 10` (`0xD2`) | `000 000 01` (`0x01`) | `00 00 3F 00` | `D2 01 00 00 3F 00` | Initialize 32-bit stack pointer SREG = 0x00003F00 |
| **25** | `MSP.add $sreg, 0x0010` | `11010 1 10` (`0xD6`) | `0 000 01 00` (`0x04`) | `00 10` | `D6 04 00 10` | Deallocate stack frame (+16 bytes to SREG) |

### 5. Native Multi-Level Pointer Dereferencing via `PTREG`
In LIM M2, native multi-level pointer dereferencing (`**ptr`, `***ptr`) is performed through `PTREG` using `MSP.ld $ptreg, [$ptreg]`, which executes `PTREG = MEM16[PTREG]` in a single instruction. Executing `MSP.ld $ptreg, [$ptreg]` $N$ times (sequentially or in a loop) performs $N$ pointer dereferences:
```asm
; Load root pointer address 0xA000 into PTREG:
MSP.ld $ptreg, 0xA000
MSP.ld $ptreg, [$ptreg]     ; 1st dereference: PTREG = *0xA000
MSP.ld $ptreg, [$ptreg]     ; 2nd dereference: PTREG = **0xA000
MSP.ld $ptreg, [$ptreg]     ; 3rd dereference: PTREG = ***0xA000
; Read the final target word into $0:
LMR.w  $0, [$ptreg]
```

### 6. Compiling to `.bin` and `.hex`
```bash
# Compile demo.asm into both demo.bin and demo.hex:
python3 compiler/compiler.py compiler/demo.asm -l

# Or run an .asm source file directly in the interactive simulator:
python3 sim/sim.py compiler/demo.asm -i
```

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
│   ├── LIM_M2_Datasheet_*.pdf   # Compiled PDFs
│   ├── test.tex                 # Standalone TikZ architectural datapath
│   ├── diagram.png / .svg       # Vector & Ultra-HD schematic assets
│   └── compile_datasheets.sh    # Build automation script
├── compiler/                # Dedicated Assembler Compiler SDK
│   ├── README.md            # Compiler documentation & CLI usage
│   ├── compiler.py          # CLI runner & compiler entrypoint
│   ├── limasm.py            # Official LIM M2 Assembler Compiler & Disassembler
│   ├── demo.asm             # Reference assembly source program
│   ├── demo.bin             # Compiled raw binary firmware
│   └── demo.hex             # Compiled annotated hex image
└── sim/                     # Python architectural simulator
    ├── sim.py               # Main CLI launcher
    ├── exampcpu.py          # LIM M2 CPU core model
    ├── core.py              # Base CPU abstraction
    ├── bus.py               # Memory bus and memory-mapped IO
    ├── devices.py           # RAM, Text Screen, UART, Timer peripherals
    ├── runner.py            # Execution and trace engine
    └── ui.py                # Terminal / GUI monitor interface
```

---

## 🚀 Quickstart & Simulation

### 1. Running the Simulator

Run the interactive architectural simulation with the bundled demo program:

```bash
# Launch interactive terminal simulation (accepts .asm, .bin, or .hex)
python3 sim/sim.py compiler/demo.asm -i
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

