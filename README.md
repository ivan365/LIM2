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
 15   14   13   12   11   10    9    8    7    6    5    4    3    2    1    0
+----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+
|AIP |SBIT|SMOD|DBIT|M24 |DWR |MIE |PIE |CLK1|CLK0|CMP1|CMP0| EM | OF | CF | ZF |
+----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+
```

* **`ZF` (0):** Zero Flag (result is zero).
* **`CF` (1):** Carry / Borrow Flag.
* **`OF` (2):** Overflow Flag (signed arithmetic).
* **`EM` (3):** Error Math (hardware trap on division by zero).
* **`CMP` (4–5):** 2-bit Hardware Comparator Result (`<`, `=`, `>`).
* **`CLK` (6–7):** Core Clock Divider Mode.
* **`PIE` (8):** Program Interrupt Enable.
* **`MIE` (9):** Master Interrupt Enable.
* **`DWR` (10):** Disable Wait for Ready (forced non-blocking bus transfer).
* **`M24` (11):** 24-bit Extended Addressing Enable.
* **`DBIT` (12):** Discarded Shift Bit buffer.
* **`SMOD` (13):** Shift Mode modifier.
* **`SBIT` (14):** Shift Bit value for serial injection.
* **`AIP` (15):** Auto-Increment Pointer on memory operations.

---

## ⚡ Instruction Set Architecture (ISA - 32 Opcodes)

| Opcode | Hex | Mnemonic | Class | Functional Description |
| :---: | :---: | :--- | :--- | :--- |
| **00000** | `0x00` | **`NOP`** | Control | No operation; flushes `ALU_RESIDUAL` and resets carry/borrow tracking |
| **00001** | `0x01` | **`ADD`** | Arithmetic | 16-bit addition with automatic carry chaining via `ALU_RESIDUAL` |
| **00010** | `0x02` | **`SUB`** | Arithmetic | 16-bit subtraction with automatic borrow chaining via `ALU_RESIDUAL` |
| **00011** | `0x03` | **`MUL`** | Arithmetic | Integer multiplication; upper 16 bits latched into `ALU_RESIDUAL` |
| **00100** | `0x04` | **`DIV`** | Arithmetic | Integer division; remainder (modulo) latched into `ALU_RESIDUAL` |
| **00101** | `0x05` | **`LMR`** | Memory | Load word from memory into register (supports 24-bit `PTREG`) |
| **00110** | `0x06` | **`LRM`** | Memory | Store word from register into memory |
| **00111** | `0x07` | **`LRR`** | Transfer | Fast register-to-register copy via bypass (`MUX 1` $\to$ `MUX 2`) |
| **01000** | `0x08` | **`CMP`** | Compare | Arithmetic compare; updates `FREG.CMP`, `ZF`, `CF`, `OF` non-destructively |
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
| **11000** | `0x18` | **`BSL`** | Shift | Barrel Shift Left with `FREG.DBIT` capture |
| **11001** | `0x19` | **`BSR`** | Shift | Barrel Shift Right with `FREG.DBIT` capture |
| **11010** | `0x1A` | **`CSRM`** | System | Control and Status Register Access (`FREG`, `PTREG`, `SREG`) |
| **11011** | `0x1B` | **`RSV27`** | Reserved | Vector / SIMD hardware extensions slot |
| **11100** | `0x1C` | **`RSV28`** | Reserved | Extended addressing coprocessor slot |
| **11101** | `0x1D` | **`RSV29`** | Reserved | Floating-Point Unit (FPU) slot |
| **11110** | `0x1E` | **`RSV30`** | Reserved | Hardware cryptography accelerator slot |
| **11111** | `0x1F` | **`RSV31`** | Reserved | Future architecture expansion slot |

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
