; ==============================================================================
; LIM M2 Architecture Reference Examples
; Example 3: Hardware Timer Interrupts (IRQ0)
; ==============================================================================
; This program demonstrates:
;   1. Setting up Interrupt Vector Table (IVT): Configuring $ir0 with MSP.ld.
;   2. Enabling Master Interrupts (MIE) in FREG.
;   3. Hardware Timer MMIO configuration at 0x00030010.
;   4. Background execution loop computing Fibonacci numbers in GPRs.
;   5. Interrupt Service Routine (ISR) that increments a tick counter in memory,
;      updates the display, and returns with RET (which clears FREG.INTR).
; ==============================================================================

.org 0x00000000

reset_entry:
    ; 1. Setup Stack Pointer SP (0x00007F00)
    MSP.ld  $sp, 0x00007F00

    ; 2. Configure Interrupt Vector 0 ($ir0) to point to timer_isr
    MSP.ld  $ir0, timer_isr

    ; 3. Setup FREG: Supervisor mode (PRV=1, bit 11) + Auto-increment (AIP=1, bit 12)
    MSP.ld  $freg, 0x1800

    ; 4. Clear Tick Counter in RAM at 0x00000200
    LMR.w   $0, 0
    LRM.w   $0, [0x00000200]

    ; 5. Print Initial Banner to Screen VRAM (0x00010000)
    MSP.ld  $ptreg, 0x00010000
    LRM.b   0x54, [$ptreg]      ; 'T'
    LRM.b   0x49, [$ptreg]      ; 'I'
    LRM.b   0x4D, [$ptreg]      ; 'M'
    LRM.b   0x45, [$ptreg]      ; 'E'
    LRM.b   0x52, [$ptreg]      ; 'R'
    LRM.b   0x20, [$ptreg]      ; ' '
    LRM.b   0x4F, [$ptreg]      ; 'O'
    LRM.b   0x4E, [$ptreg]      ; 'N'
    LRM.b   0x3A, [$ptreg]      ; ':'
    LRM.b   0x20, [$ptreg]      ; ' '

    ; 6. Configure Hardware Timer Device at 0x00030010
    ;    Offset +0: Reload Value = 25 cycles
    ;    Offset +2: Control / Enable Register = 1
    LMR.w   $1, 25
    LRM.w   $1, [0x00030010]
    LMR.w   $2, 1
    LRM.w   $2, [0x00030012]

    ; 7. Enable Master Interrupts (MIE, bit 9 of FREG)
    ;    0x0200 = (1 << 9)
    MSP.or  $freg, 0x0200

    ; 8. Background Work: Compute Fibonacci series in R1 and R2
    LMR.w   $1, 0               ; Fib(0)
    LMR.w   $2, 1               ; Fib(1)

background_loop:
    ADD     $3, $1, $2          ; Fib(n) = Fib(n-1) + Fib(n-2)
    LRR     $1, $2              ; Shift sequence
    LRR     $2, $3
    NOP
    NOP
    JMP     background_loop

; ==============================================================================
; Interrupt Service Routine for IRQ0 (Timer Interrupt)
; Hardware automatically:
;   1. Pushes 32-bit PC and 16-bit FREG onto stack SREG.
;   2. Sets FREG.INTR = 1 (in-interrupt flag).
;   3. Jumps to address stored in $ir0 (this routine).
; ==============================================================================
.org 0x00000080

timer_isr:
    ; Increment tick counter in RAM (0x00000200)
    LMR.w   $4, [0x00000200]
    INC     $4
    LRM.w   $4, [0x00000200]

    ; Append a visual tick mark '*' to the screen
    LRM.b   0x2A, [$ptreg]      ; '*' (auto-increments PTREG)

    ; Clear Timer interrupt acknowledge flag at 0x00030012
    LMR.w   $5, 1
    LRM.w   $5, [0x00030012]

    ; Return from interrupt:
    ; Hardware pops FREG and PC, automatically restoring CPU state and clearing INTR!
    RET
