; ==============================================================================
; LIM M2 Architecture Reference Examples
; Example 2: Modular Text Terminal & Hex Formatter
; ==============================================================================
; This program demonstrates:
;   1. Modular subroutines with CALL and RET.
;   2. Fast streaming of characters to TextScreen VRAM via PTREG (AIP=1).
;   3. Converting 16-bit binary integers into 4 hexadecimal ASCII characters.
;   4. Logical shifts (BSR) and bitwise masking (AND).
; ==============================================================================

.org 0x00000000

main:
    ; 1. Initialize Stack Pointer SP
    MSP.ld  $sp, 0x00007F00

    ; 2. Initialize FREG: Supervisor mode (PRV=1) + PTREG Auto-increment (AIP=1)
    MSP.ld  $freg, 0x1800

    ; 3. Set PTREG to the start of TextScreen VRAM (0x00010000)
    MSP.ld  $ptreg, 0x00010000

    ; 4. Print Title Banner: "LIM2 TERM: "
    CALL    print_title

    ; 5. Print Label: "R1=0x"
    CALL    print_r1_label

    ; 6. Format and Print 16-bit value in R1: 0xCAFE
    LMR.w   $1, 0xCAFE
    LRR     $0, $1              ; Pass argument in $0
    CALL    print_hex16

    ; 7. Print Label: " R2=0x"
    CALL    print_r2_label

    ; 8. Format and Print 16-bit value in R2: 0x015E (350 decimal)
    LMR.w   $2, 0x015E
    LRR     $0, $2
    CALL    print_hex16

    ; Done!
    HALT

; ==============================================================================
; Subroutine: print_title
; Writes "LIM2 TERM: " directly to screen via PTREG
; ==============================================================================
print_title:
    LRM.b   0x4C, [$ptreg]      ; 'L'
    LRM.b   0x49, [$ptreg]      ; 'I'
    LRM.b   0x4D, [$ptreg]      ; 'M'
    LRM.b   0x32, [$ptreg]      ; '2'
    LRM.b   0x20, [$ptreg]      ; ' '
    LRM.b   0x54, [$ptreg]      ; 'T'
    LRM.b   0x45, [$ptreg]      ; 'E'
    LRM.b   0x52, [$ptreg]      ; 'R'
    LRM.b   0x4D, [$ptreg]      ; 'M'
    LRM.b   0x3A, [$ptreg]      ; ':'
    LRM.b   0x20, [$ptreg]      ; ' '
    RET

print_r1_label:
    LRM.b   0x52, [$ptreg]      ; 'R'
    LRM.b   0x31, [$ptreg]      ; '1'
    LRM.b   0x3D, [$ptreg]      ; '='
    LRM.b   0x30, [$ptreg]      ; '0'
    LRM.b   0x78, [$ptreg]      ; 'x'
    RET

print_r2_label:
    LRM.b   0x20, [$ptreg]      ; ' '
    LRM.b   0x52, [$ptreg]      ; 'R'
    LRM.b   0x32, [$ptreg]      ; '2'
    LRM.b   0x3D, [$ptreg]      ; '='
    LRM.b   0x30, [$ptreg]      ; '0'
    LRM.b   0x78, [$ptreg]      ; 'x'
    RET

; ==============================================================================
; Subroutine: print_hex16
; Formats 16-bit integer in $0 into 4 hexadecimal ASCII characters.
; Destroys: $3, $4, $5, $6, $7
; Output: Streamed to screen via PTREG
; ==============================================================================
print_hex16:
    LRR     $7, $0              ; Preserve original value in $7
    LMR.w   $4, 0x000F          ; Mask constant for nibble

    ; --- Nibble 3 (bits 15..12) ---
    LRR     $3, $7
    BSR     $3, 12
    AND     $0, $3, $4
    CALL    print_nibble

    ; --- Nibble 2 (bits 11..8) ---
    LRR     $3, $7
    BSR     $3, 8
    AND     $0, $3, $4
    CALL    print_nibble

    ; --- Nibble 1 (bits 7..4) ---
    LRR     $3, $7
    BSR     $3, 4
    AND     $0, $3, $4
    CALL    print_nibble

    ; --- Nibble 0 (bits 3..0) ---
    LRR     $3, $7
    AND     $0, $3, $4
    CALL    print_nibble

    RET

; ==============================================================================
; Subroutine: print_nibble
; Converts integer 0..15 in $0 to ASCII character '0'..'9' or 'A'..'F'
; ==============================================================================
print_nibble:
    LMR.w   $5, 10
    CMP     $0, $5
    JCR     >=, nibble_is_af

    ; Nibble is 0..9 -> add '0' (0x30)
    LMR.w   $6, 0x30
    ADD     $3, $0, $6
    LRM.b   $3, [$ptreg]
    RET

nibble_is_af:
    ; Nibble is 10..15 -> val - 10 + 'A' (0x41) = val + 0x37
    LMR.w   $6, 0x37
    ADD     $3, $0, $6
    LRM.b   $3, [$ptreg]
    RET
