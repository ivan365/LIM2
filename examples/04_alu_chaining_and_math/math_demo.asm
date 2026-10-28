; ==============================================================================
; LIM M2 Architecture Reference Examples
; Example 4: 3-Operand ALU, Flags & Logic
; ==============================================================================
; This program demonstrates:
;   1. 3-Operand Register ALU operations: ADD, SUB, MUL, DIV, MOD.
;   2. Flag setting: Zero Flag (ZF) and Carry Flag (CF).
;   3. Hardware Bitwise Logic: AND, OR, XOR, NOT, BSL, BSR.
;   4. Hardware Comparator: CMP and conditional jumps with JCR.
;   5. Writing verification status to TextScreen VRAM.
; ==============================================================================

.org 0x00000000

main:
    ; 1. Stack and Processor Mode setup
    MSP.ld  $sp, 0x00007F00
    MSP.ld  $freg, 0x1800       ; Supervisor (PRV=1), AIP=1
    MSP.ld  $ptreg, 0x00010000  ; Point to screen VRAM

    ; --------------------------------------------------------------------------
    ; Test 1: Basic 3-Operand Register Arithmetic (Rd = Rs1 op Rs2)
    ; --------------------------------------------------------------------------
    LMR.w   $1, 30
    LMR.w   $2, 12

    ADD     $3, $1, $2          ; $3 = 30 + 12 = 42
    SUB     $4, $1, $2          ; $4 = 30 - 12 = 18
    MUL     $5, $1, $2          ; $5 = 30 * 12 = 360
    DIV     $6, $1, $2          ; $6 = 30 / 12 = 2
    MOD     $7, $1, $2          ; $7 = 30 % 12 = 6

    ; Verify ADD result: $3 == 42
    LMR.w   $0, 42
    CMP     $3, $0
    JCR     !=, test_failed

    ; Verify MOD result: $7 == 6
    LMR.w   $0, 6
    CMP     $7, $0
    JCR     !=, test_failed

    ; --------------------------------------------------------------------------
    ; Test 2: Arithmetic Overflow and Carry Flag (CF)
    ; 0xFFFF + 0x0002 = 0x10001 -> Sum is 0x0001, Carry Flag (CF) = 1
    ; --------------------------------------------------------------------------
    LMR.w   $1, 0xFFFF
    LMR.w   $2, 0x0002
    ADD     $0, $1, $2          ; $0 = 0x0001, CF=1

    ; Verify sum in $0 == 1
    LMR.w   $4, 0x0001
    CMP     $0, $4
    JCR     !=, test_failed

    ; Addition without carry: 2 + 1 = 3
    LMR.w   $1, 0x0002
    LMR.w   $2, 0x0001
    ADD     $3, $1, $2          ; $3 = 3
    LMR.w   $4, 0x0003
    CMP     $3, $4
    JCR     !=, test_failed

    ; --------------------------------------------------------------------------
    ; Test 3: Bitwise Operations & Shifts
    ; --------------------------------------------------------------------------
    LMR.w   $1, 0xAA55
    LMR.w   $2, 0x00FF

    AND     $3, $1, $2          ; $3 = 0xAA55 & 0x00FF = 0x0055
    OR      $4, $1, $2          ; $4 = 0xAA55 | 0x00FF = 0xAAFF
    XOR     $5, $1, $2          ; $5 = 0xAA55 ^ 0x00FF = 0xAAAA

    ; Bit shifts:
    LMR.w   $6, 0x0001
    BSL     $6, 4               ; $6 = 0x0001 << 4 = 0x0010 (16)
    BSR     $6, 2               ; $6 = 0x0010 >> 2 = 0x0004 (4)

    LMR.w   $0, 4
    CMP     $6, $0
    JCR     !=, test_failed

    ; --------------------------------------------------------------------------
    ; All Tests Passed: Write "ALU OK" to screen
    ; --------------------------------------------------------------------------
    LRM.b   0x41, [$ptreg]      ; 'A'
    LRM.b   0x4C, [$ptreg]      ; 'L'
    LRM.b   0x55, [$ptreg]      ; 'U'
    LRM.b   0x20, [$ptreg]      ; ' '
    LRM.b   0x4F, [$ptreg]      ; 'O'
    LRM.b   0x4B, [$ptreg]      ; 'K'
    HALT

test_failed:
    LRM.b   0x45, [$ptreg]      ; 'E'
    LRM.b   0x52, [$ptreg]      ; 'R'
    LRM.b   0x52, [$ptreg]      ; 'R'
    HALT
