; ==============================================================================
; LIM M2 Architecture Reference Examples
; Example 1: Stage-1 Direct Memory Bootloader
; ==============================================================================
; This program demonstrates:
;   1. System initialization: SP stack and FREG flags setup.
;   2. Screen output: Streaming a boot banner directly to TextScreen VRAM.
;   3. Memory copying: Relocating a kernel payload from ROM to RAM at 0x00008000.
;   4. Magic word validation: Verifying header 0x4C49 ("LI").
;   5. Execution handoff: 32-bit jump (JMP 0x00008002) to the relocated payload.
; ==============================================================================

.org 0x00000000

_start:
    ; 1. Initialize Stack Pointer SREG/SP to top of low RAM (0x00007F00)
    MSP.ld  $sp, 0x00007F00

    ; 2. Initialize FREG: Supervisor mode (PRV=1, bit 11) + Auto-increment (AIP=1, bit 12)
    ;    0x1800 = (1 << 12) | (1 << 11)
    MSP.ld  $freg, 0x1800

    ; 3. Print Boot Message to TextScreen VRAM (0x00010000)
    ;    PTREG points to screen VRAM; writing with LRM.b advances PTREG automatically!
    MSP.ld  $ptreg, 0x00010000
    LRM.b   0x4C, [$ptreg]      ; 'L'
    LRM.b   0x49, [$ptreg]      ; 'I'
    LRM.b   0x4D, [$ptreg]      ; 'M'
    LRM.b   0x32, [$ptreg]      ; '2'
    LRM.b   0x20, [$ptreg]      ; ' '
    LRM.b   0x42, [$ptreg]      ; 'B'
    LRM.b   0x4F, [$ptreg]      ; 'O'
    LRM.b   0x4F, [$ptreg]      ; 'O'
    LRM.b   0x54, [$ptreg]      ; 'T'
    LRM.b   0x20, [$ptreg]      ; ' '
    LRM.b   0x4F, [$ptreg]      ; 'O'
    LRM.b   0x4B, [$ptreg]      ; 'K'

    ; 4. Relocate Kernel Payload from ROM (0x00000100) to RAM (0x00008000)
    ;    Transfer 24 bytes of payload data
    MSP.ld  $ptreg, 0x00008000  ; Destination in RAM (auto-increments on write)

    ; Read words from ROM and stream into RAM
    LMR.w   $0, [0x00000100]
    LRM.w   $0, [$ptreg]
    LMR.w   $0, [0x00000102]
    LRM.w   $0, [$ptreg]
    LMR.w   $0, [0x00000104]
    LRM.w   $0, [$ptreg]
    LMR.w   $0, [0x00000106]
    LRM.w   $0, [$ptreg]
    LMR.w   $0, [0x00000108]
    LRM.w   $0, [$ptreg]
    LMR.w   $0, [0x0000010A]
    LRM.w   $0, [$ptreg]
    LMR.w   $0, [0x0000010C]
    LRM.w   $0, [$ptreg]
    LMR.w   $0, [0x0000010E]
    LRM.w   $0, [$ptreg]

    ; 5. Validate Payload Magic Word at RAM 0x00008000
    ;    Expected magic: 0x4C49 (ASCII "LI")
    LMR.w   $0, [0x00008000]
    LMR.w   $3, 0x4C49
    CMP     $0, $3
    JCR     !=, boot_error      ; Magic check failed!

    ; 6. Handoff Control: 32-bit Jump to the Entry Point of the relocated Kernel
    ;    Entry point is right after the 2-byte magic header (0x00008002)
    JMP     0x00008002

boot_error:
    ; Print "ERR" to screen and halt
    MSP.ld  $ptreg, 0x00010028  ; Row 2 of screen
    LRM.b   0x45, [$ptreg]      ; 'E'
    LRM.b   0x52, [$ptreg]      ; 'R'
    LRM.b   0x52, [$ptreg]      ; 'R'
    HALT

; ==============================================================================
; Embedded Kernel Payload (relocated to RAM 0x00008000 and executed there)
; ==============================================================================
.org 0x00000100

payload_start:
    ; Header: 2-byte Magic Signature (0x4C49 = "LI")
    dw 0x4C49

kernel_entry:
    ; This code runs from RAM at address 0x00008002!
    ; Print "KERNEL OK" at row 1 of the screen (0x00010014)
    MSP.ld  $ptreg, 0x00010014
    LRM.b   0x4B, [$ptreg]      ; 'K'
    LRM.b   0x45, [$ptreg]      ; 'E'
    LRM.b   0x52, [$ptreg]      ; 'R'
    LRM.b   0x4E, [$ptreg]      ; 'N'
    LRM.b   0x45, [$ptreg]      ; 'E'
    LRM.b   0x4C, [$ptreg]      ; 'L'
    LRM.b   0x20, [$ptreg]      ; ' '
    LRM.b   0x4F, [$ptreg]      ; 'O'
    LRM.b   0x4B, [$ptreg]      ; 'K'

    ; Calculation demo: compute 100 + 250 in R0
    LMR.w   $1, 100
    LMR.w   $2, 250
    ADD     $0, $1, $2          ; $0 = 350 (0x015E)

    HALT                        ; End of payload execution
