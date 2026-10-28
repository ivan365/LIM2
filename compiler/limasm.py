#!/usr/bin/env python3
# ==============================================================================
# LIM2 / sim / limasm.py — Компилятор Ассемблера архитектуры LIM M2
# ==============================================================================
"""
Двухпроходный ассемблер и CLI-компилятор для процессора LIM M2.
Компилирует исходный код (.asm / .lasm) одновременно в бинарный (.bin)
и шестнадцатеричный (.hex) файлы, а также интегрируется напрямую с симулятором LIM2.

Основные правила синтаксиса ассемблера LIM M2:
  1. Регистры:
     - Регистры общего назначения (16 бит): $0 .. $7 (также поддерживаются R0..R7, $r0..$r7)
     - Специальные регистры: $ptreg (24 бита), $freg (16 бит), $sreg / $sp (24 бита),
       а также векторы прерываний $vec0 .. $vec7
  2. Суффиксы размера операндов (.b / .w):
     - .b — byte (8 бит, 1 байт, аппаратный SZ=0)
     - .w — word (16 бит, 2 байта, аппаратный SZ=1, по умолчанию)
     (Инструкции памяти LMR и LRM поддерживают строго .b и .w; для 24/32 бит используются директивы данных и MSP.ld)
     Примеры: LMR.b $0, 0x42 | LMR.w $0, [0x1000] | LRM.b $0, [$ptreg]
  3. Арифметика и унарные операции (работа только с регистрами):
     - ADD, SUB, MUL, DIV, MOD:  ADD $0, $1, $2   (или ADD R0, R1, R1)
     - INC, DEC, NOT:            INC $0           (1-байтовые инструкции!)
     - Логика и сравнение:       AND $0, $1 | OR $0, $1 | XOR $0, $1 | CMP $0, $1 | LRR $0, $1
     - Сдвиги:                   BSL $0, 4  | BSR $0, 4
     - Стек и прерывания:        PUSH $0    | POP $0    | INTR 3 (1 байт)
  4. Загрузка и выгрузка памяти (LMR и LRM):
     - Просто число (без скобок) -> непосредственное значение (SRC=0 / DST=0):
         LMR.w $0, 0x1234
     - Число/метка в квадратных скобках [addr] -> ссылка на данные в памяти (SRC=1 / DST=1):
         LMR.w $0, [0x1000]
         LRM.w $0, [0x1000]
     - Косвенная ссылка через 24-битный указатель PTREG [$ptreg] (SRC=2 / DST=2):
         LMR.w $0, [$ptreg]
         LRM.w $0, [$ptreg]
     - Составной 32-битный поинтер на основе пары регистров [$0:$1] (SRC=3 / DST=3):
         LMR $0, [$0:$1]
         LRM $0, [$0:$1]
  5. Манипуляция специальными регистрами (MSP):
     - Модификация флагового регистра маской:
         MSP.and $freg, 0x0001
         MSP.or  $freg, 0x0200
         MSP.xor $freg, $2
     - Прямая загрузка глухой настройки или поинтера (MSP.ld):
         MSP.ld $freg, 0x0000
         MSP.ld $ptreg, 0x0001A000
         MSP.ld $ptreg, [$0:$1]    (загрузка составного 32-битного поинтера в PTREG из пары [$0:$1])
         MSP.ld $sreg, [$0:$1]     (загрузка составного указателя стека SREG из пары [$0:$1])
         MSP.ld $ir0, [$0:$1]      (загрузка 32-битного вектора прерывания из пары [$0:$1])
         MSP.ld $pv0, [$0:$1]      (загрузка границы зоны привилегий из пары [$0:$1])
         MSP.ld $ptreg, [0xA000]   (загрузка поинтера по непосредственной ссылке из памяти)
         MSP.ld $ptreg, [$ptreg]   (нативное разыменование указателя: PTREG <- MEM[PTREG])
         MSP.ld $sreg, 0x3F00      (работа со стек-поинтером в том же формате, что и PTREG)
         MSP.add $ptreg, 0x0010    (смещение указателя PTREG или SREG)
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class AssemblerError(Exception):
    """Ошибка синтаксиса или кодирования ассемблера LIM M2."""

    def __init__(self, message: str, line_no: Optional[int] = None, line_text: str = ""):
        self.line_no = line_no
        self.line_text = line_text
        loc = f" (строка {line_no}: '{line_text.strip()}')" if line_no is not None else ""
        super().__init__(f"Ошибка ассемблера LIM M2{loc}: {message}")


# ------------------------------------------------------------------------------
# Таблицы регистров и кодов операций LIM M2
# ------------------------------------------------------------------------------

GPR_MAP: Dict[str, int] = {
    "$0": 0, "$1": 1, "$2": 2, "$3": 3, "$4": 4, "$5": 5, "$6": 6, "$7": 7,
    "$R0": 0, "$R1": 1, "$R2": 2, "$R3": 3, "$R4": 4, "$R5": 5, "$R6": 6, "$R7": 7,
    "R0": 0, "R1": 1, "R2": 2, "R3": 3, "R4": 4, "R5": 5, "R6": 6, "R7": 7,
}

# ------------------------------------------------------------------------------
# Таблицы квантованных 16-битных ячеек системных регистров (MSP, 8-битный REG_ID 0..255)
# ------------------------------------------------------------------------------

MSP_CELL_MAP: Dict[str, int] = {
    # 128: Регистр состояния и флагов FREG
    "$FREG": 128, "FREG": 128, "$FLAGS": 128, "FLAGS": 128, "$SR": 128, "SR": 128, "$STATUS": 128, "STATUS": 128,

    # 129, 130: 32-битный указатель стека SP / SREG (пара по 16 бит)
    "$SP_LO": 129, "SP_LO": 129, "$SPL": 129, "SPL": 129, "$SP.L": 129, "SP.L": 129,
    "$SREG_LO": 129, "SREG_LO": 129, "$SREG.L": 129, "SREG.L": 129, "$SREGL": 129, "SREGL": 129,

    "$SP_HI": 130, "SP_HI": 130, "$SPH": 130, "SPH": 130, "$SP.H": 130, "SP.H": 130,
    "$SREG_HI": 130, "SREG_HI": 130, "$SREG.H": 130, "SREG.H": 130, "$SREGH": 130, "SREGH": 130,

    # 131, 132: 32-битный базовый указатель памяти PTREG (пара по 16 бит)
    "$PTREG_LO": 131, "PTREG_LO": 131, "$PTL": 131, "PTL": 131, "$PT.L": 131, "PT.L": 131,
    "$PT_LO": 131, "PT_LO": 131, "$PTREGL": 131, "PTREGL": 131,

    "$PTREG_HI": 132, "PTREG_HI": 132, "$PTH": 132, "PTH": 132, "$PT.H": 132, "PT.H": 132,
    "$PT_HI": 132, "PT_HI": 132, "$PTREGH": 132, "PTREGH": 132,
}

# 16 пар векторов прерываний INT_VEC (ячейки 0..31):
for _i in range(16):
    _lo = 2 * _i
    _hi = 2 * _i + 1
    for _pfx in (f"$IR{_i}", f"IR{_i}", f"$IV{_i}", f"IV{_i}", f"$INT{_i}", f"INT{_i}", f"$INT_VEC{_i}", f"INT_VEC{_i}", f"$VEC{_i}", f"VEC{_i}"):
        MSP_CELL_MAP[f"{_pfx}_LO"] = _lo
        MSP_CELL_MAP[f"{_pfx}.L"] = _lo
        MSP_CELL_MAP[f"{_pfx}_L"] = _lo
        MSP_CELL_MAP[f"{_pfx}L"] = _lo

        MSP_CELL_MAP[f"{_pfx}_HI"] = _hi
        MSP_CELL_MAP[f"{_pfx}.H"] = _hi
        MSP_CELL_MAP[f"{_pfx}_H"] = _hi
        MSP_CELL_MAP[f"{_pfx}H"] = _hi

# 14 пар зон привилегий PVZ_VEC (Зоны 0..6: 28 ячеек 32..59):
# Каждая зона z (0..6) имеет 2 вектора по 32 бита: START (пара ячеек) и END (пара ячеек)
for _z in range(7):
    _s_lo = 32 + 4 * _z
    _s_hi = 33 + 4 * _z
    _e_lo = 34 + 4 * _z
    _e_hi = 35 + 4 * _z
    
    # Семантические мнемоники зон: $pz0_start_lo / $pz0_end_lo / $pz0sl / $pz0el
    for _zpfx in (f"$PZ{_z}", f"PZ{_z}", f"$PVZ{_z}", f"PVZ{_z}", f"$ZONE{_z}", f"ZONE{_z}"):
        MSP_CELL_MAP[f"{_zpfx}_START_LO"] = _s_lo
        MSP_CELL_MAP[f"{_zpfx}_S_LO"] = _s_lo
        MSP_CELL_MAP[f"{_zpfx}.S.L"] = _s_lo
        MSP_CELL_MAP[f"{_zpfx}SL"] = _s_lo

        MSP_CELL_MAP[f"{_zpfx}_START_HI"] = _s_hi
        MSP_CELL_MAP[f"{_zpfx}_S_HI"] = _s_hi
        MSP_CELL_MAP[f"{_zpfx}.S.H"] = _s_hi
        MSP_CELL_MAP[f"{_zpfx}SH"] = _s_hi

        MSP_CELL_MAP[f"{_zpfx}_END_LO"] = _e_lo
        MSP_CELL_MAP[f"{_zpfx}_E_LO"] = _e_lo
        MSP_CELL_MAP[f"{_zpfx}.E.L"] = _e_lo
        MSP_CELL_MAP[f"{_zpfx}EL"] = _e_lo

        MSP_CELL_MAP[f"{_zpfx}_END_HI"] = _e_hi
        MSP_CELL_MAP[f"{_zpfx}_E_HI"] = _e_hi
        MSP_CELL_MAP[f"{_zpfx}.E.H"] = _e_hi
        MSP_CELL_MAP[f"{_zpfx}EH"] = _e_hi

# Векторные мнемоники $pv0..$pv13 (14 векторов по 32 бита = 28 ячеек 32..59):
for _p in range(14):
    _lo = 32 + 2 * _p
    _hi = 32 + 2 * _p + 1
    for _pfx in (f"$PV{_p}", f"PV{_p}", f"$PVZ_VEC{_p}", f"PVZ_VEC{_p}", f"$VEC{16+_p}", f"VEC{16+_p}"):
        MSP_CELL_MAP[f"{_pfx}_LO"] = _lo
        MSP_CELL_MAP[f"{_pfx}.L"] = _lo
        MSP_CELL_MAP[f"{_pfx}_L"] = _lo
        MSP_CELL_MAP[f"{_pfx}L"] = _lo

        MSP_CELL_MAP[f"{_pfx}_HI"] = _hi
        MSP_CELL_MAP[f"{_pfx}.H"] = _hi
        MSP_CELL_MAP[f"{_pfx}_H"] = _hi
        MSP_CELL_MAP[f"{_pfx}H"] = _hi

# Границы RAM (MEM_VEC: ячейки 60..63):
for _bl_name in ("$RAM_BASE_LO", "RAM_BASE_LO", "$RAM_START_LO", "RAM_START_LO", "$RAM_BL", "RAM_BL", "$RAM_SL", "RAM_SL", "$RAM_B_LO", "$RAM_BASE.L", "$PV14_LO", "$PV14L", "$VEC30_LO"):
    MSP_CELL_MAP[_bl_name] = 60
for _bh_name in ("$RAM_BASE_HI", "RAM_BASE_HI", "$RAM_START_HI", "RAM_START_HI", "$RAM_BH", "RAM_BH", "$RAM_SH", "RAM_SH", "$RAM_B_HI", "$RAM_BASE.H", "$PV14_HI", "$PV14H", "$VEC30_HI"):
    MSP_CELL_MAP[_bh_name] = 61
for _ll_name in ("$RAM_LIMIT_LO", "RAM_LIMIT_LO", "$RAM_END_LO", "RAM_END_LO", "$RAM_LL", "RAM_LL", "$RAM_EL", "RAM_EL", "$RAM_L_LO", "$RAM_LIMIT.L", "$PV15_LO", "$PV15L", "$VEC31_LO"):
    MSP_CELL_MAP[_ll_name] = 62
for _lh_name in ("$RAM_LIMIT_HI", "RAM_LIMIT_HI", "$RAM_END_HI", "RAM_END_HI", "$RAM_LH", "RAM_LH", "$RAM_EH", "RAM_EH", "$RAM_L_HI", "$RAM_LIMIT.H", "$PV15_HI", "$PV15H", "$VEC31_HI"):
    MSP_CELL_MAP[_lh_name] = 63

# 15 аппаратных регистров таймеров (ячейки 64..78):
TIMER_CELL_DEFINITIONS = [
    (64, ["T1_CNT_LO", "T1_CNTL", "T1_CNT.L", "T1_LO", "T1L"]),
    (65, ["T1_CNT_HI", "T1_CNTH", "T1_CNT.H", "T1_HI", "T1H"]),
    (66, ["T1_MATCH_LO", "T1_MATCHL", "T1_MATCH.L", "T1_CMP_LO", "T1_CMPL", "T1_CMP.L", "T1_RELOAD_LO"]),
    (67, ["T1_MATCH_HI", "T1_MATCHH", "T1_MATCH.H", "T1_CMP_HI", "T1_CMPH", "T1_CMP.H", "T1_RELOAD_HI"]),
    (68, ["T1_TIME_LO", "T1_TIMEL", "T1_TIME.L", "TIME_LO", "TIMEL"]),
    (69, ["T1_TIME_HI", "T1_TIMEH", "T1_TIME.H", "TIME_HI", "TIMEH"]),
    (70, ["T2_CNT_LO", "T2_CNTL", "T2_CNT.L", "T2_LO", "T2L"]),
    (71, ["T2_CNT_HI", "T2_CNTH", "T2_CNT.H", "T2_HI", "T2H"]),
    (72, ["T2_RELOAD_LO", "T2_RELOADL", "T2_RELOAD.L", "T2_RELL", "T2_MATCH_LO"]),
    (73, ["T2_RELOAD_HI", "T2_RELOADH", "T2_RELOAD.H", "T2_RELH", "T2_MATCH_HI"]),
    (74, ["T3_CNT_LO", "T3_CNTL", "T3_CNT.L", "T3_LO", "T3L"]),
    (75, ["T3_CNT_HI", "T3_CNTH", "T3_CNT.H", "T3_HI", "T3H"]),
    (76, ["T4_CNT", "T4_CNT_LO", "T4_CNTL", "T4_LO", "T4L", "T4"]),
    (77, ["T4_RELOAD", "T4_RELOAD_LO", "T4_RELL", "T4_REL", "T4_MATCH"]),
    (78, ["TSR", "TIMER_CFG", "TIMER_SETTING", "TIMER_SETTINGS", "TIMER_CTRL", "TMR_CTRL"]),
]

for _cid, _names in TIMER_CELL_DEFINITIONS:
    for _n in _names:
        MSP_CELL_MAP[_n] = _cid
        MSP_CELL_MAP[f"${_n}"] = _cid

# Также сохраняем общие алиасы $sys0..$sys14 для совместимости:
for _k in range(15):
    _cid = 64 + _k
    for _spfx in (f"$SYS{_k}", f"SYS{_k}", f"$SR{_k}", f"SR{_k}", f"$RSV{_k}", f"RSV{_k}", f"$SYS_REG{_k}", f"SYS_REG{_k}", f"$SYSREG{_k}", f"SYSREG{_k}"):
        MSP_CELL_MAP[_spfx] = _cid

# Составные 32-битные регистры (авторасширение в 2 инструкции при MSP.ld):
MSP_PAIR_MAP: Dict[str, Tuple[int, int]] = {
    "$SP": (129, 130), "SP": (129, 130),
    "$SREG": (129, 130), "SREG": (129, 130),
    "$PTREG": (131, 132), "PTREG": (131, 132),
    "$PT": (131, 132), "PT": (131, 132),
}

# 32-битные составные регистры таймеров:
TIMER_PAIR_DEFINITIONS = [
    ("T1_CNT", (64, 65)),
    ("T1", (64, 65)),
    ("T1_MATCH", (66, 67)),
    ("T1_CMP", (66, 67)),
    ("T1_RELOAD", (66, 67)),
    ("T1_TIME", (68, 69)),
    ("TIME", (68, 69)),
    ("T2_CNT", (70, 71)),
    ("T2", (70, 71)),
    ("T2_RELOAD", (72, 73)),
    ("T2_MATCH", (72, 73)),
    ("T3_CNT", (74, 75)),
    ("T3", (74, 75)),
]
for _n, _pair in TIMER_PAIR_DEFINITIONS:
    MSP_PAIR_MAP[_n] = _pair
    MSP_PAIR_MAP[f"${_n}"] = _pair
for _i in range(16):
    _pair = (2 * _i, 2 * _i + 1)
    for _pfx in (f"$IR{_i}", f"IR{_i}", f"$IV{_i}", f"IV{_i}", f"$INT{_i}", f"INT{_i}", f"$INT_VEC{_i}", f"INT_VEC{_i}", f"$VEC{_i}", f"VEC{_i}"):
        MSP_PAIR_MAP[_pfx] = _pair

for _z in range(7):
    _s_pair = (32 + 4 * _z, 33 + 4 * _z)
    _e_pair = (34 + 4 * _z, 35 + 4 * _z)
    for _zpfx in (f"$PZ{_z}", f"PZ{_z}", f"$PVZ{_z}", f"PVZ{_z}", f"$ZONE{_z}", f"ZONE{_z}"):
        MSP_PAIR_MAP[f"{_zpfx}_START"] = _s_pair
        MSP_PAIR_MAP[f"{_zpfx}S"] = _s_pair
        MSP_PAIR_MAP[f"{_zpfx}_END"] = _e_pair
        MSP_PAIR_MAP[f"{_zpfx}E"] = _e_pair

for _p in range(14):
    _pair = (32 + 2 * _p, 32 + 2 * _p + 1)
    for _pfx in (f"$PV{_p}", f"PV{_p}", f"$PVZ_VEC{_p}", f"PVZ_VEC{_p}", f"$VEC{16+_p}", f"VEC{16+_p}"):
        MSP_PAIR_MAP[_pfx] = _pair

MSP_PAIR_MAP["$RAM_BASE"] = (60, 61)
MSP_PAIR_MAP["RAM_BASE"] = (60, 61)
MSP_PAIR_MAP["$RAM_START"] = (60, 61)
MSP_PAIR_MAP["RAM_START"] = (60, 61)
MSP_PAIR_MAP["$RAM_B"] = (60, 61)
MSP_PAIR_MAP["$RAM_S"] = (60, 61)
MSP_PAIR_MAP["$PV14"] = (60, 61)
MSP_PAIR_MAP["$VEC30"] = (60, 61)

MSP_PAIR_MAP["$RAM_LIMIT"] = (62, 63)
MSP_PAIR_MAP["RAM_LIMIT"] = (62, 63)
MSP_PAIR_MAP["$RAM_END"] = (62, 63)
MSP_PAIR_MAP["RAM_END"] = (62, 63)
MSP_PAIR_MAP["$RAM_L"] = (62, 63)
MSP_PAIR_MAP["$RAM_E"] = (62, 63)
MSP_PAIR_MAP["$PV15"] = (62, 63)
MSP_PAIR_MAP["$VEC31"] = (62, 63)

# Обратная таблица для дизассемблера (чистые имена без знака $):
SYS_CELL_NAMES: Dict[int, str] = {
    # 4 аппаратных таймера (колонки 64..78):
    64: "t1_cnt_lo",
    65: "t1_cnt_hi",
    66: "t1_match_lo",
    67: "t1_match_hi",
    68: "t1_time_lo",
    69: "t1_time_hi",
    70: "t2_cnt_lo",
    71: "t2_cnt_hi",
    72: "t2_reload_lo",
    73: "t2_reload_hi",
    74: "t3_cnt_lo",
    75: "t3_cnt_hi",
    76: "t4_cnt",
    77: "t4_reload",
    78: "tsr",
    # Системные регистры управления и вказівники:
    128: "freg",
    129: "sp_lo",
    130: "sp_hi",
    131: "ptreg_lo",
    132: "ptreg_hi",
    60: "ram_base_lo",
    61: "ram_base_hi",
    62: "ram_limit_lo",
    63: "ram_limit_hi",
}
for _i in range(16):
    SYS_CELL_NAMES[2 * _i] = f"ir{_i}_lo"
    SYS_CELL_NAMES[2 * _i + 1] = f"ir{_i}_hi"
for _p in range(14):
    SYS_CELL_NAMES[32 + 2 * _p] = f"pv{_p}_lo"
    SYS_CELL_NAMES[32 + 2 * _p + 1] = f"pv{_p}_hi"

SPEC_REG_MAP: Dict[str, Tuple[int, int]] = {
    "$FREG": (0, 0), "FREG": (0, 0),
    "$PTREG": (1, 0), "PTREG": (1, 0),
    "$SREG": (2, 0), "SREG": (2, 0),
    "$SP": (2, 0), "SP": (2, 0),
}

OPCODES: Dict[str, int] = {
    "NOP": 0,
    "ADD": 1,
    "SUB": 2,
    "MUL": 3,
    "DIV": 4,
    "LMR": 5,
    "LRM": 6,
    "LRR": 7,
    "CMP": 8,
    "JMP": 9,
    "JCR": 10,
    "JO": 11,
    "JOB": 11,
    "JNO": 11,
    "JZ": 12,
    "JNZ": 12,
    "AND": 13,
    "OR": 14,
    "NAND": 15,
    "NOR": 16,
    "NOT": 17,
    "XOR": 18,
    "XNOR": 19,
    "INC": 20,
    "DEC": 21,
    "PUSH": 22,
    "POP": 23,
    "BSL": 24,
    "BSR": 25,
    "MSP": 26,
    "MOD": 27,
    "INTR": 28,
    "SWI": 28,
    "INT": 28,
    "CALL": 29,
    "RET": 30,
    "RSV31": 31,
    "HALT": 31,
    "HLT": 31,
}

MSP_LOGIC_OPS: Dict[str, int] = {
    "AND": 0,
    "OR": 1,
    "XOR": 2,
    "XNOR": 3,
}

MSP_ARITH_OPS: Dict[str, int] = {
    "ADD": 0,
    "SUB": 1,
}

# Таблица условий для условного перехода по результату сравнения JCR (Opcode 10):
# Поле CFG [2:0]:
#   Бит [2]: INV (0 = совпадение с кодом сравнения, 1 = несовпадение)
#   Биты [1:0]: ожидаемый код сравнения (01 = <, 10 = ==, 11 = >)
JCR_COND_MAP: Dict[str, int] = {
    # Прямые условия (INV = 0):
    "<": 0b001,   # 1: Меньше (Less, COND=01)
    "LT": 0b001,
    "==": 0b010,  # 2: Равно (Equal, COND=10)
    "=": 0b010,
    "EQ": 0b010,
    ">": 0b011,   # 3: Больше (Greater, COND=11)
    "GT": 0b011,
    # Инвертированные условия (INV = 1):
    ">=": 0b101,  # 5: Больше или равно (Greater or Equal, INV=1, COND=01)
    "=>": 0b101,
    "GE": 0b101,
    "!=": 0b110,  # 6: Не равно (Not Equal, INV=1, COND=10)
    "<>": 0b110,
    "/=": 0b110,
    "NE": 0b110,
    "<=": 0b111,  # 7: Меньше или равно (Less or Equal, INV=1, COND=11)
    "=<": 0b111,
    "LE": 0b111,
}

JCR_COND_NAME: Dict[int, str] = {
    0b001: "<",
    0b010: "==",
    0b011: ">",
    0b101: ">=",
    0b110: "!=",
    0b111: "<=",
}


def is_gpr(token: str) -> bool:
    return token.strip().upper() in GPR_MAP


def parse_gpr(token: str, line_no: Optional[int] = None, line_text: str = "") -> int:
    key = token.strip().upper()
    if key not in GPR_MAP:
        raise AssemblerError(
            f"Ожидался регистр общего назначения ($0..$7 или R0..R7), получено '{token}'",
            line_no,
            line_text,
        )
    return GPR_MAP[key]


def resolve_msp_target(token: str) -> Optional[Tuple[str, any]]:
    """
    Разрешает имя целевого регистра или номер ячейки MSP:
      - ('CELL', reg_id) для 16-битных ячеек (0..255)
      - ('PAIR', (lo_id, hi_id)) для 32-битных составных регистров
      - None если токен не относится к системным регистрам
    """
    raw = token.strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1].strip()
    key = raw.upper()
    if key in MSP_CELL_MAP:
        return ("CELL", MSP_CELL_MAP[key])
    if key in MSP_PAIR_MAP:
        return ("PAIR", MSP_PAIR_MAP[key])
    try:
        val = int(raw, 0)
        if 0 <= val <= 255:
            return ("CELL", val)
    except ValueError:
        pass
    return None


def is_spec_reg(token: str) -> bool:
    return resolve_msp_target(token) is not None


def parse_spec_reg(token: str, line_no: Optional[int] = None, line_text: str = "") -> Tuple[int, int, bool]:
    raw = token.strip()
    bracketed = False
    if raw.startswith("[") and raw.endswith("]"):
        bracketed = True
        raw = raw[1:-1].strip()
    info = resolve_msp_target(raw)
    if info is None:
        raise AssemblerError(
            f"Ожидался системный регистр или ячейка MSP, получено '{token}'",
            line_no,
            line_text,
        )
    kind, val = info
    if kind == "CELL":
        return 0, val, bracketed
    else:
        return 3, val[0], bracketed


class LimAssembler:
    """Двухпроходный компилятор ассемблера LIM M2."""

    def __init__(self, base_address: int = 0x0000):
        self.base_address = base_address & 0xFFFFFF
        self.labels: Dict[str, int] = {}
        self.constants: Dict[str, int] = {}
        self.source_map: Dict[int, str] = {}

    # --------------------------------------------------------------------------
    # Очистка комментариев
    # --------------------------------------------------------------------------

    def _strip_comment(self, line: str) -> str:
        in_quote = False
        quote_char = ""
        for i, ch in enumerate(line):
            if ch in ('"', "'"):
                if not in_quote:
                    in_quote = True
                    quote_char = ch
                elif quote_char == ch:
                    in_quote = False
            elif not in_quote:
                if ch == ";":
                    return line[:i]
                if ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
                    return line[:i]
                if ch == "#":
                    return line[:i]
        return line

    # --------------------------------------------------------------------------
    # Разбор выражений и аргументов
    # --------------------------------------------------------------------------

    def _eval_expr(
        self,
        expr: str,
        current_pc: int,
        pass_num: int,
        line_no: Optional[int] = None,
        line_text: str = "",
    ) -> int:
        s = expr.strip()
        if not s:
            raise AssemblerError("Пустое числовое выражение", line_no, line_text)

        # Символьная константа вида 'A'
        if len(s) == 3 and s[0] == "'" and s[2] == "'":
            return ord(s[1])

        # Поддержка $, $$, ., __LINE__
        base_org = getattr(self, "current_org", self.base_address)
        # $$ — базовый адрес текущей секции / программы
        s = re.sub(r"\$\$", str(base_org), s)
        # $ — текущий счетчик команд (адрес текущей строки/инструкции)
        # Не заменяем, если это регистр $0..$7 или специальный $ptreg/$freg
        s = re.sub(r"\$(?![0-9A-Za-z_])", str(current_pc), s)
        # Одиночная точка '.' как текущий адрес
        s = re.sub(r"(?<![0-9A-Za-z_])\.(?![0-9A-Za-z_])", str(current_pc), s)
        # Номер строки исходника
        s = re.sub(r"\b__LINE__\b", str(line_no or 0), s)

        # Заменяем метки и константы
        def replace_token(match: re.Match) -> str:
            tok = match.group(0)
            up = tok.upper()
            if up.startswith("0X") or up.startswith("0B") or up.startswith("0O") or tok.isdigit():
                return str(int(tok, 0))
            if up in self.constants:
                return str(self.constants[up])
            if up in self.labels:
                return str(self.labels[up])
            if pass_num == 1:
                return "0"
            raise AssemblerError(f"Неизвестная метка или константа '{tok}'", line_no, line_text)

        # Поддержка простых арифметических выражений (+, -, *, //, <<, >>, |, &, ^)
        token_pattern = re.compile(r"\b(?:0[xX][0-9a-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+|\d+|[A-Za-z_][A-Za-z0-9_]*)\b")
        evaluated = token_pattern.sub(replace_token, s)
        if not re.match(r"^[\d\s\+\-\*\/\%\(\)\<\>\&\|\^\~]+$", evaluated):
            if pass_num == 1:
                return 0
            raise AssemblerError(f"Недопустимое выражение '{expr}'", line_no, line_text)
        try:
            return int(eval(evaluated, {"__builtins__": None}, {}))
        except Exception as exc:
            if pass_num == 1:
                return 0
            raise AssemblerError(f"Не удалось вычислить '{expr}': {exc}", line_no, line_text)

    def _split_operands(self, ops_str: str) -> List[str]:
        if not ops_str.strip():
            return []
        parts: List[str] = []
        cur: List[str] = []
        bracket_depth = 0
        in_quote = False
        quote_ch = ""
        for ch in ops_str:
            if ch in ('"', "'"):
                if not in_quote:
                    in_quote = True
                    quote_ch = ch
                elif quote_ch == ch:
                    in_quote = False
                cur.append(ch)
            elif not in_quote:
                if ch == "[":
                    bracket_depth += 1
                    cur.append(ch)
                elif ch == "]":
                    bracket_depth = max(0, bracket_depth - 1)
                    cur.append(ch)
                elif ch == "," and bracket_depth == 0:
                    parts.append("".join(cur).strip())
                    cur = []
                else:
                    cur.append(ch)
            else:
                cur.append(ch)
        tail = "".join(cur).strip()
        if tail:
            parts.append(tail)
        return parts

    # --------------------------------------------------------------------------
    # Кодирование отдельной инструкции
    # --------------------------------------------------------------------------

    def _parse_mnemonic(
        self, raw_mnemonic: str, line_no: int, line_text: str
    ) -> Tuple[str, Optional[str], Optional[str]]:
        """
        Разбирает мнемонику с точечными суффиксами:
          - ADD.w -> ('ADD', None, 'W')
          - LMR.b -> ('LMR', None, 'B')
          - LRM.w -> ('LRM', None, 'W')
          - MSP.ld -> ('MSP', 'LD', None)
          - MSP.and -> ('MSP', 'AND', None)
          - MSP.ld.d -> ('MSP', 'LD', 'D')
        """
        clean = raw_mnemonic.rstrip(",").strip().upper()
        parts = clean.split(".")
        base = parts[0]
        sub_op: Optional[str] = None
        size_sfx: Optional[str] = None

        for p in parts[1:]:
            if p in ("B", "BYTE"):
                size_sfx = "B"
            elif p in ("W", "WORD"):
                size_sfx = "W"
            elif p in ("D", "DWORD", "DOUBLEWORD"):
                size_sfx = "D"
            elif base == "MSP" and p in (
                "LD", "LOAD", "LDR", "LDR7", "R7LD", "STR", "STR7", "R7ST", "ST", "STOR7",
                "AND", "OR", "XOR", "XNOR", "ONB", "OFFB", "ADD", "SUB"
            ):
                if p in ("LOAD", "LD"):
                    sub_op = "LD"
                elif p in ("LDR", "LDR7", "R7LD"):
                    sub_op = "LDR"
                elif p in ("STR", "STR7", "R7ST", "ST", "STOR7"):
                    sub_op = "STR"
                elif p == "XNOR":
                    sub_op = "XNOR"
                else:
                    sub_op = p
            elif base == "JCR" and p in JCR_COND_MAP:
                sub_op = p
            else:
                raise AssemblerError(f"Неизвестный суффикс '.{p}' в инструкции '{raw_mnemonic}'", line_no, line_text)

        return base, sub_op, size_sfx

    def _encode_instruction(
        self,
        raw_mnemonic: str,
        operands: List[str],
        current_pc: int,
        pass_num: int,
        line_no: int,
        line_text: str,
    ) -> bytes:
        base, sub_op, size_sfx = self._parse_mnemonic(raw_mnemonic, line_no, line_text)

        if base not in OPCODES:
            raise AssemblerError(f"Неизвестная инструкция '{base}'", line_no, line_text)

        op = OPCODES[base]

        # 1. Однобайтовые безаргументные инструкции: NOP (0), RET (30), HALT/HLT/RSV31 (31)
        if base in ("NOP", "RET", "HALT", "HLT", "RSV31"):
            if operands:
                raise AssemblerError(f"Инструкция '{base}' не принимает аргументов", line_no, line_text)
            return bytes([(op << 3) & 0xFF])

        # 2. Однобайтовые унарные регистровые инструкции: INC (20), DEC (21), PUSH (22), POP (23)
        if base in ("INC", "DEC", "PUSH", "POP"):
            if len(operands) != 1:
                raise AssemblerError(f"Инструкция '{base}' требует ровно 1 регистр (например, {base} $0)", line_no, line_text)
            reg = parse_gpr(operands[0], line_no, line_text)
            return bytes([((op << 3) | reg) & 0xFF])

        # 2a. Однобайтовые сдвиги на 1 бит за такт: BSL (24), BSR (25)
        if base in ("BSL", "BSR"):
            if len(operands) == 1:
                rd = parse_gpr(operands[0], line_no, line_text)
                return bytes([((op << 3) | rd) & 0xFF])
            elif len(operands) == 2:
                rd = parse_gpr(operands[0], line_no, line_text)
                count = self._eval_expr(operands[1], current_pc, pass_num, line_no, line_text)
                return bytes([((op << 3) | rd) & 0xFF]) * max(1, count)
            else:
                raise AssemblerError(f"Инструкция '{base}' требует 1 регистр (например, {base} $0)", line_no, line_text)

        # 3. Двухбайтовое побитовое инвертирование: NOT (17) (Target в [2:0] Byte 0, Source в [7:5] Byte 1)
        if base == "NOT":
            if len(operands) == 1:
                target = parse_gpr(operands[0], line_no, line_text)
                source = target
            elif len(operands) == 2:
                target = parse_gpr(operands[0], line_no, line_text)
                source = parse_gpr(operands[1], line_no, line_text)
            else:
                raise AssemblerError(f"Инструкция 'NOT' принимает 1 или 2 регистра: NOT $0 или NOT $0, $1", line_no, line_text)
            b0 = ((op << 3) | target) & 0xFF
            b1 = (source << 5) & 0xFF
            return bytes([b0, b1])

        # 3a. Двухбайтовое программное прерывание: INTR vec / SWI vec / INT vec (28)
        if base in ("INTR", "SWI", "INT"):
            if len(operands) != 1:
                raise AssemblerError(f"Инструкция '{base}' требует 1 аргумент — номер вектора 0..15", line_no, line_text)
            vec = self._eval_expr(operands[0], current_pc, pass_num, line_no, line_text)
            if pass_num == 2 and not (0 <= vec <= 15):
                raise AssemblerError(f"Номер вектора прерывания должен быть в диапазоне 0..15, получено {vec}", line_no, line_text)
            b0 = (op << 3) & 0xFF
            b1 = vec & 0x0F
            return bytes([b0, b1])

        # 4. Двухбайтовое прямое межрегистровое копирование LRR (7): Rd в [2:0] Byte 0, Rs в [7:5] Byte 1
        if base == "LRR":
            if len(operands) != 2:
                raise AssemblerError("Инструкция 'LRR' требует 2 регистра: LRR $rd, $rs", line_no, line_text)
            rd = parse_gpr(operands[0], line_no, line_text)
            rs = parse_gpr(operands[1], line_no, line_text)
            b0 = ((op << 3) | rd) & 0xFF
            b1 = (rs << 5) & 0xFF
            return bytes([b0, b1])

        # 4a. Двухбайтовое сравнение CMP (8): Rs0 в [2:0] Byte 0, Rs1 в [7:5] Byte 1
        if base == "CMP":
            if len(operands) != 2:
                raise AssemblerError("Инструкция 'CMP' требует 2 регистра: CMP $rs0, $rs1", line_no, line_text)
            rs0 = parse_gpr(operands[0], line_no, line_text)
            rs1 = parse_gpr(operands[1], line_no, line_text)
            b0 = ((op << 3) | rs0) & 0xFF
            b1 = (rs1 << 5) & 0xFF
            return bytes([b0, b1])

        # 5. Трехоперандные арифметические и логические инструкции (2 байта):
        #    ADD (1), SUB (2), MUL (3), DIV (4), MOD (27),
        #    AND (13), OR (14), NAND (15), NOR (16), XOR (18), XNOR (19)
        if base in ("ADD", "SUB", "MUL", "DIV", "MOD", "AND", "OR", "NAND", "NOR", "XOR", "XNOR"):
            if len(operands) == 2:
                rd = parse_gpr(operands[0], line_no, line_text)
                rs0 = rd
                rs1 = parse_gpr(operands[1], line_no, line_text)
            elif len(operands) == 3:
                rd = parse_gpr(operands[0], line_no, line_text)
                rs0 = parse_gpr(operands[1], line_no, line_text)
                rs1 = parse_gpr(operands[2], line_no, line_text)
            else:
                raise AssemblerError(
                    f"Инструкция '{base}' требует 3 (или 2) регистра: {base} $rd, $rs0, $rs1",
                    line_no,
                    line_text,
                )
            b0 = ((op << 3) | rd) & 0xFF
            b1 = ((rs0 << 5) | (rs1 << 2)) & 0xFF
            return bytes([b0, b1])

        # 6. Условный переход по результату сравнения: JCR (10)
        if base == "JCR":
            return self._encode_jcr(sub_op, operands, current_pc, pass_num, line_no, line_text)

        # 7. Переходы и вызовы подпрограмм (1..5 байт):
        #    JMP (9), JO/JOB (11, neg=0), JNO (11, neg=1), JZ (12, neg=0), JNZ (12, neg=1), CALL (29)
        if base in ("JMP", "JO", "JOB", "JNO", "JZ", "JNZ", "CALL"):
            return self._encode_branch(base, op, operands, current_pc, pass_num, line_no, line_text)

        # 8. Загрузка и выгрузка памяти: LMR (5) и LRM (6)
        if base in ("LMR", "LRM"):
            return self._encode_lmr_lrm(base, op, size_sfx, operands, current_pc, pass_num, line_no, line_text)

        # 9. Манипуляция специальными регистрами: MSP (26)
        if base == "MSP":
            return self._encode_msp(sub_op, size_sfx, operands, current_pc, pass_num, line_no, line_text)

        raise AssemblerError(f"Инструкция '{base}' не реализована", line_no, line_text)

    # --------------------------------------------------------------------------
    # Кодирование ветвлений (JMP, JO, JOB, JNO, JZ, JNZ, CALL)
    # --------------------------------------------------------------------------

    def _encode_branch(
        self,
        base: str,
        op: int,
        operands: List[str],
        current_pc: int,
        pass_num: int,
        line_no: int,
        line_text: str,
    ) -> bytes:
        neg = 1 if base in ("JNO", "JNZ") else 0

        # Вариант 1: пара регистров передана двумя аргументами (JMP $0, $1) -> mode=3
        if len(operands) == 2 and is_gpr(operands[0]) and is_gpr(operands[1]):
            r_hi = parse_gpr(operands[0], line_no, line_text)
            r_lo = parse_gpr(operands[1], line_no, line_text)
            b0 = ((op << 3) | (neg << 2) | 3) & 0xFF
            b1 = ((r_hi << 5) | (r_lo << 2)) & 0xFF
            return bytes([b0, b1])

        if len(operands) != 1:
            raise AssemblerError(
                f"Инструкция перехода '{base}' требует 1 целевой операнд (или пару регистров $hi, $lo)",
                line_no,
                line_text,
            )

        target_tok = operands[0].strip()
        is_bracketed = target_tok.startswith("[") and target_tok.endswith("]")
        unbracketed = target_tok[1:-1].strip() if is_bracketed else target_tok

        # Mode 2 (0b10): переход по указателю PTREG (JMP [$ptreg] или JMP $ptreg) -> 1 БАЙТ!
        if unbracketed.upper() in ("$PTREG", "PTREG"):
            b0 = ((op << 3) | (neg << 2) | 2) & 0xFF
            return bytes([b0])

        # Mode 3 (0b11): пара регистров в скобках [$hi:$lo] или [$hi, $lo] -> 2 БАЙТА!
        if is_bracketed and (":" in unbracketed or "," in unbracketed):
            sep = ":" if ":" in unbracketed else ","
            parts = [p.strip() for p in unbracketed.split(sep)]
            if len(parts) == 2 and is_gpr(parts[0]) and is_gpr(parts[1]):
                r_hi = parse_gpr(parts[0], line_no, line_text)
                r_lo = parse_gpr(parts[1], line_no, line_text)
                b0 = ((op << 3) | (neg << 2) | 3) & 0xFF
                b1 = ((r_hi << 5) | (r_lo << 2)) & 0xFF
                return bytes([b0, b1])

        if is_gpr(unbracketed):
            raise AssemblerError(
                f"Инструкция '{base}' требует 32-битный адрес (число/метку, [$ptreg], [addr32] или пару регистров [$hi:$lo]), "
                f"а одиночный регистр {unbracketed} является 16-битным",
                line_no,
                line_text,
            )

        # Mode 1 (0b01): косвенный переход по адресу в памяти (JMP [mark] / JMP [0x1000]) -> 5 БАЙТ
        if is_bracketed:
            addr = self._eval_expr(unbracketed, current_pc, pass_num, line_no, line_text) & 0xFFFFFFFF
            b0 = ((op << 3) | (neg << 2) | 1) & 0xFF
            return bytes([b0, addr & 0xFF, (addr >> 8) & 0xFF, (addr >> 16) & 0xFF, (addr >> 24) & 0xFF])

        # Mode 0 (0b00): прямой 32-битный адрес перехода (JMP mark / JMP 0x100000) -> 5 БАЙТ
        addr = self._eval_expr(unbracketed, current_pc, pass_num, line_no, line_text) & 0xFFFFFFFF
        b0 = ((op << 3) | (neg << 2) | 0) & 0xFF
        return bytes([b0, addr & 0xFF, (addr >> 8) & 0xFF, (addr >> 16) & 0xFF, (addr >> 24) & 0xFF])

    # --------------------------------------------------------------------------
    # Кодирование JCR (Opcode 10)
    # --------------------------------------------------------------------------

    def _encode_jcr(
        self,
        sub_op: Optional[str],
        operands: List[str],
        current_pc: int,
        pass_num: int,
        line_no: int,
        line_text: str,
    ) -> bytes:
        """
        Кодирует инструкцию условного перехода по результату сравнения JCR (Opcode 10):
        1) Упрощенный составной вариант (fused / macro, 7 байт):
           - JCR $1 > $2, addr (или JCR $1, >, $2, addr)
           Заменяет пару инструкций CMP $1, $2 + JCR >, addr.
        2) Прямой / ручной вариант (5 байт):
           - JCR <cond>, addr (например: JCR <, target | JCR ==, target | JCR !=, target | JCR.GT target)
           Байт 0: [7-3] опкод 10 (0b01010), [2] INV, [1-0] COND
           Байты 1-4: target32 (Little-Endian)
        """
        # Вариант 1: Условие в мнемонике (JCR.GT addr, JCR.< addr, etc.) (5 байт)
        if sub_op is not None:
            cond_key = sub_op.upper()
            if cond_key not in JCR_COND_MAP:
                raise AssemblerError(f"Неизвестное условие '{sub_op}' для JCR", line_no, line_text)
            if len(operands) != 1:
                raise AssemblerError(f"Инструкция JCR.{sub_op} требует 1 аргумент (целевой адрес перехода)", line_no, line_text)
            cfg = JCR_COND_MAP[cond_key]
            target = self._eval_expr(operands[0], current_pc, pass_num, line_no, line_text) & 0xFFFFFFFF
            b0 = ((10 << 3) | cfg) & 0xFF
            return bytes([b0, target & 0xFF, (target >> 8) & 0xFF, (target >> 16) & 0xFF, (target >> 24) & 0xFF])

        # Проверяем fused форму: JCR $1 > $2, addr (или $1, >, $2, addr) (7 байт: CMP 2 байта + JCR 5 байт)
        fused = self._match_fused_jcr(operands)
        if fused is not None:
            r1_tok, cond_tok, r2_tok, target_tok = fused
            r1 = parse_gpr(r1_tok, line_no, line_text)
            r2 = parse_gpr(r2_tok, line_no, line_text)
            cfg = JCR_COND_MAP[cond_tok]
            # 1. CMP $r1, $r2 (2 байта: [7-3] опкод 8, [2-0] r1; [7-5] r2)
            cmp_b0 = ((8 << 3) | r1) & 0xFF
            cmp_b1 = (r2 << 5) & 0xFF
            # 2. JCR cond, target (5 байт, адрес смещен на 2 байта относительно начала CMP)
            target = self._eval_expr(target_tok, current_pc + 2, pass_num, line_no, line_text) & 0xFFFFFFFF
            jcr_b0 = ((10 << 3) | cfg) & 0xFF
            return bytes([cmp_b0, cmp_b1, jcr_b0, target & 0xFF, (target >> 8) & 0xFF, (target >> 16) & 0xFF, (target >> 24) & 0xFF])

        # Вариант 2: Ручной синтаксис JCR <cond>, addr (2 операнда) (5 байт)
        if len(operands) == 2:
            op0 = operands[0].strip().upper()
            if op0 in JCR_COND_MAP:
                cfg = JCR_COND_MAP[op0]
            else:
                try:
                    cfg = int(op0, 0) & 0x07
                except ValueError:
                    raise AssemblerError(
                        f"Неизвестное условие '{operands[0]}' для JCR. Допустимые условия: <, <=, ==, !=, >=, > (или LT, LE, EQ, NE, GE, GT)",
                        line_no,
                        line_text,
                    )
            target = self._eval_expr(operands[1], current_pc, pass_num, line_no, line_text) & 0xFFFFFFFF
            b0 = ((10 << 3) | cfg) & 0xFF
            return bytes([b0, target & 0xFF, (target >> 8) & 0xFF, (target >> 16) & 0xFF, (target >> 24) & 0xFF])

        # Вариант 3: 1 операнд без спецификатора (например, JCR target — безусловный или cfg=0) (5 байт)
        if len(operands) == 1:
            cfg = 0
            target = self._eval_expr(operands[0], current_pc, pass_num, line_no, line_text) & 0xFFFFFFFF
            b0 = ((10 << 3) | cfg) & 0xFF
            return bytes([b0, target & 0xFF, (target >> 8) & 0xFF, (target >> 16) & 0xFF, (target >> 24) & 0xFF])

        raise AssemblerError(f"Недопустимый формат инструкции JCR: {operands}", line_no, line_text)

    def _match_fused_jcr(self, operands: List[str]) -> Optional[Tuple[str, str, str, str]]:
        """
        Проверяет, соответствует ли список операндов fused-форме JCR:
        Возвращает (r1_tok, cond_tok, r2_tok, target_tok) или None.
        Поддерживает:
          - JCR $1 > $2, addr             (2 операнда: "$1 > $2" и "addr")
          - JCR $1, >, $2, addr          (4 операнда)
          - JCR $1, $2, >, addr          (4 операнда)
          - JCR $1, > $2, addr           (3 операнда)
          - JCR $1 >, $2, addr           (3 операнда)
        """
        if len(operands) == 2:
            m = re.match(
                r"^(\$?[A-Za-z0-9]+)\s*(<=|>=|==|!=|=|<|>|LT|LE|GT|GE|EQ|NE)\s*(\$?[A-Za-z0-9]+)$",
                operands[0].strip(),
                re.IGNORECASE,
            )
            if m and is_gpr(m.group(1)) and is_gpr(m.group(3)) and m.group(2).upper() in JCR_COND_MAP:
                return m.group(1), m.group(2).upper(), m.group(3), operands[1].strip()

        elif len(operands) == 4:
            if is_gpr(operands[0]) and operands[1].strip().upper() in JCR_COND_MAP and is_gpr(operands[2]):
                return operands[0], operands[1].strip().upper(), operands[2], operands[3].strip()
            if is_gpr(operands[0]) and is_gpr(operands[1]) and operands[2].strip().upper() in JCR_COND_MAP:
                return operands[0], operands[2].strip().upper(), operands[1], operands[3].strip()

        elif len(operands) == 3:
            m = re.match(r"^(<=|>=|==|!=|=|<|>|LT|LE|GT|GE|EQ|NE)\s*(\$?[A-Za-z0-9]+)$", operands[1].strip(), re.IGNORECASE)
            if m and is_gpr(operands[0]) and m.group(1).upper() in JCR_COND_MAP and is_gpr(m.group(2)):
                return operands[0], m.group(1).upper(), m.group(2), operands[2].strip()
            m = re.match(r"^(\$?[A-Za-z0-9]+)\s*(<=|>=|==|!=|=|<|>|LT|LE|GT|GE|EQ|NE)$", operands[0].strip(), re.IGNORECASE)
            if m and is_gpr(m.group(1)) and m.group(2).upper() in JCR_COND_MAP and is_gpr(operands[1]):
                return m.group(1), m.group(2).upper(), operands[1], operands[2].strip()

        return None

    # --------------------------------------------------------------------------
    # Кодирование LMR и LRM
    # --------------------------------------------------------------------------

    def _encode_lmr_lrm(
        self,
        base: str,
        op: int,
        size_sfx: Optional[str],
        operands: List[str],
        current_pc: int,
        pass_num: int,
        line_no: int,
        line_text: str,
    ) -> bytes:
        """
        Кодирует инструкции LMR (opcode 5) и LRM (opcode 6):
          - LMR[.b/.w] $rd, value        -> SRC=0 (непосредственное число)
          - LMR[.b/.w] $rd, [addr]       -> SRC=1 (ссылка на память по адресу addr)
          - LMR[.b/.w] $rd, [$ptreg]     -> SRC=2 (ссылка на память по регистру PTREG)
          - LMR[.b/.w] $rd, [$hi:$lo]    -> SRC=3 (составной 24-битный адрес из пары регистров)
          (аналогично для LRM)
        Поддерживаются строго суффиксы .b (байт, 8 бит) и .w (слово, 16 бит).
        """
        if size_sfx not in (None, "B", "W"):
            raise AssemblerError(
                f"Инструкция '{base}' поддерживает только суффиксы размера .b (байт, 8 бит) и .w (слово, 16 бит), получено '.{size_sfx.lower()}'",
                line_no,
                line_text,
            )

        if len(operands) < 2:
            raise AssemblerError(
                f"Инструкция '{base}' требует целевой регистр и операнд источника/назначения",
                line_no,
                line_text,
            )

        sz_bit = 0 if size_sfx == "B" else 1  # 0 for .b, 1 for .w (бит 2 DS)

        if base == "LMR":
            reg_main = parse_gpr(operands[0], line_no, line_text)

            # Если передано 2 регистра без скобок: LMR $0, $1 -> режим 3 (пара регистров $0:$1)
            if len(operands) == 2 and is_gpr(operands[1]):
                rs_lo = parse_gpr(operands[1], line_no, line_text)
                mode = 3
                cfg = (sz_bit << 2) | mode
                b0 = ((op << 3) | cfg) & 0xFF
                b1 = ((reg_main << 5) | (rs_lo << 2)) & 0xFF
                return bytes([b0, b1])

            if len(operands) != 2:
                raise AssemblerError(f"Неверное число аргументов для '{base}'", line_no, line_text)

            arg = operands[1].strip()

            if arg.startswith("[") and arg.endswith("]"):
                inner = arg[1:-1].strip()

                # [$ptreg] -> режим 2
                if inner.upper() in ("$PTREG", "PTREG"):
                    mode = 2
                    cfg = (sz_bit << 2) | mode
                    b0 = ((op << 3) | cfg) & 0xFF
                    b1 = (reg_main << 5) & 0xFF
                    return bytes([b0, b1])

                # [$0:$1] -> режим 3
                if ":" in inner or "," in inner:
                    sep = ":" if ":" in inner else ","
                    pair = [p.strip() for p in inner.split(sep)]
                    if len(pair) != 2:
                        raise AssemblerError(f"Ожидалась пара регистров вида [$0:$1], получено '{arg}'", line_no, line_text)
                    r_hi = parse_gpr(pair[0], line_no, line_text)
                    r_lo = parse_gpr(pair[1], line_no, line_text)
                    mode = 3
                    cfg = (sz_bit << 2) | mode
                    b0 = ((op << 3) | cfg) & 0xFF
                    prefix = b""
                    if r_hi != reg_main:
                        prefix = bytes([((OPCODES["LRR"] << 3) | reg_main) & 0xFF, (r_hi << 5) & 0xFF])
                    b1 = ((reg_main << 5) | (r_lo << 2)) & 0xFF
                    return prefix + bytes([b0, b1])

                # [addr] -> режим 1 (непосредственный 32-битный адрес памяти)
                ptr = self._eval_expr(inner, current_pc, pass_num, line_no, line_text) & 0xFFFFFFFF
                mode = 1
                cfg = (sz_bit << 2) | mode
                b0 = ((op << 3) | cfg) & 0xFF
                b1 = (reg_main << 5) & 0xFF
                return bytes([
                    b0, b1,
                    ptr & 0xFF,
                    (ptr >> 8) & 0xFF,
                    (ptr >> 16) & 0xFF,
                    (ptr >> 24) & 0xFF,
                ])

            # Непосредственное значение -> режим 0
            val = self._eval_expr(arg, current_pc, pass_num, line_no, line_text)
            mode = 0
            cfg = (sz_bit << 2) | mode
            b0 = ((op << 3) | cfg) & 0xFF
            b1 = (reg_main << 5) & 0xFF
            if sz_bit == 0:
                return bytes([b0, b1, val & 0xFF])
            else:
                val16 = val & 0xFFFF
                return bytes([b0, b1, val16 & 0xFF, (val16 >> 8) & 0xFF])

        else:  # LRM
            if len(operands) != 2:
                raise AssemblerError(f"Неверное число аргументов для '{base}'", line_no, line_text)

            first_op = operands[0].strip()
            dest_op = operands[1].strip()

            if not (dest_op.startswith("[") and dest_op.endswith("]")):
                raise AssemblerError(f"Второй аргумент LRM должен быть целевой ячейкой в памяти ([addr] или [$ptreg]), получено '{dest_op}'", line_no, line_text)

            inner_dest = dest_op[1:-1].strip()

            if is_gpr(first_op):
                rs = parse_gpr(first_op, line_no, line_text)
                if inner_dest.upper() in ("$PTREG", "PTREG"):
                    mode = 2  # reg to [PTREG]
                    cfg = (sz_bit << 2) | mode
                    b0 = ((op << 3) | cfg) & 0xFF
                    b1 = (rs << 5) & 0xFF
                    return bytes([b0, b1])
                else:
                    mode = 1  # reg to [ADDR]
                    ptr = self._eval_expr(inner_dest, current_pc, pass_num, line_no, line_text) & 0xFFFFFFFF
                    cfg = (sz_bit << 2) | mode
                    b0 = ((op << 3) | cfg) & 0xFF
                    b1 = (rs << 5) & 0xFF
                    return bytes([
                        b0, b1,
                        ptr & 0xFF,
                        (ptr >> 8) & 0xFF,
                        (ptr >> 16) & 0xFF,
                        (ptr >> 24) & 0xFF,
                    ])
            else:
                val = self._eval_expr(first_op, current_pc, pass_num, line_no, line_text)
                if inner_dest.upper() in ("$PTREG", "PTREG"):
                    mode = 0  # imm to [PTREG]
                    cfg = (sz_bit << 2) | mode
                    b0 = ((op << 3) | cfg) & 0xFF
                    b1 = 0x00
                    if sz_bit == 0:
                        return bytes([b0, b1, val & 0xFF])
                    else:
                        val16 = val & 0xFFFF
                        return bytes([b0, b1, val16 & 0xFF, (val16 >> 8) & 0xFF])
                else:
                    raise AssemblerError(f"Прямая запись константы в память поддержана только через [$ptreg]: LRM imm, [$ptreg]", line_no, line_text)

    # --------------------------------------------------------------------------
    # Кодирование MSP (Квантованная 16-битная манипуляция системными регистрами)
    # --------------------------------------------------------------------------

    def _encode_msp(
        self,
        sub_op: Optional[str],
        size_sfx: Optional[str],
        operands: List[str],
        current_pc: int,
        pass_num: int,
        line_no: int,
        line_text: str,
    ) -> bytes:
        """
        Кодирует инструкцию MSP (Opcode 26 / 11010):
          - op3:
              000 (ld):   загрузка imm16 в SYS_REG[reg_id] (4 байта)
              001 (ldr7): загрузка SYS_REG[reg_id] из R7 (2 байта)
              010 (str7): выгрузка SYS_REG[reg_id] в R7 (2 байта)
              011 (and):  SYS_REG[reg_id] &= imm16 (4 байта)
              100 (or):   SYS_REG[reg_id] |= imm16 (4 байта)
              101 (xor):  SYS_REG[reg_id] ^= imm16 (4 байта)
              110 (onb):  побитовое включение битов SYS_REG[reg_id] |= imm16 (4 байта)
              111 (offb): побитовое выключение битов SYS_REG[reg_id] &= ~imm16 (4 байта)
          - Для 32-битных составных регистров ($sp, $ptreg, $irX, $pvX, $ram_base, $ram_limit)
            при MSP.ld генерируются 2 последовательные 4-байтные инструкции (младшая, затем старшая).
        """
        if not operands:
            raise AssemblerError("Инструкция MSP требует операнды", line_no, line_text)

        op_msp = OPCODES["MSP"]  # 26 (0b11010)

        if sub_op is None:
            sub_op = "LD"

        sub_op = sub_op.upper()
        first_tok = operands[0].strip()
        rest = operands[1:]

        # Распознавание альтернативного синтаксиса обмена с R7:
        # MSP.ld 7, <cell> / MSP.ld $7, <cell> -> str (чтение системной ячейки в R7)
        if sub_op == "LD" and first_tok.upper() in ("$7", "7", "R7", "$R7") and rest:
            sub_op = "STR"
            first_tok = rest[0].strip()
            rest = rest[1:]
        # MSP.ld <cell>, 7 / MSP.ld <cell>, $7 -> ldr (запись в системную ячейку из R7)
        elif sub_op == "LD" and rest and rest[0].strip().upper() in ("$7", "7", "R7", "$R7"):
            sub_op = "LDR"
            rest = rest[1:]
        elif sub_op in ("LDR", "STR", "LDR7", "STR7") and rest:
            # Очищаем второй аргумент, если передан явный R7 или 7 (например: MSP.ldr freg, R7)
            if rest[0].strip().upper() in ("$7", "7", "R7", "$R7"):
                rest = rest[1:]
            elif first_tok.upper() in ("$7", "7", "R7", "$R7"):
                first_tok = rest[0].strip()
                rest = rest[1:]

        target_info = resolve_msp_target(first_tok)
        if target_info is None:
            raise AssemblerError(
                f"Неизвестный системный регистр или ячейка MSP: '{first_tok}'",
                line_no,
                line_text,
            )

        target_kind, target_val = target_info

        # 2-байтовые инструкции: ldr (001) и str (010) (поддерживаются также ldr7 и str7)
        if sub_op in ("LDR", "STR", "LDR7", "STR7"):
            if target_kind == "PAIR":
                raise AssemblerError(
                    f"Операция {sub_op.lower()} работает с 16-битными ячейками (регистр R7 — 16 бит). "
                    f"Укажите _lo или _hi для '{first_tok}'",
                    line_no,
                    line_text,
                )
            cell_id = target_val
            op3 = 0b001 if sub_op in ("LDR", "LDR7") else 0b010
            b0 = ((op_msp << 3) | op3) & 0xFF
            b1 = cell_id & 0xFF
            return bytes([b0, b1])

        # Операции с непосредственным значением (imm16 / imm32)
        if not rest:
            raise AssemblerError(f"Не указано значение операнда для MSP.{sub_op.lower()}", line_no, line_text)

        val_str = rest[0].strip()
        if val_str.startswith("[") and val_str.endswith("]"):
            val_str = val_str[1:-1].strip()

        op_map = {
            "LD": 0b000,
            "AND": 0b011,
            "OR": 0b100,
            "XOR": 0b101,
            "ONB": 0b110,
            "OFFB": 0b111,
        }
        if sub_op not in op_map:
            raise AssemblerError(f"Неподдерживаемая операция MSP.{sub_op.lower()}", line_no, line_text)

        op3 = op_map[sub_op]

        # Для составного 32-битного регистра (PAIR):
        if target_kind == "PAIR":
            if sub_op != "LD":
                raise AssemblerError(
                    f"Для логических операций MSP.{sub_op.lower()} укажите конкретную 16-битную ячейку (_lo или _hi)",
                    line_no,
                    line_text,
                )
            lo_id, hi_id = target_val
            val32 = self._eval_expr(val_str, current_pc, pass_num, line_no, line_text) & 0xFFFFFFFF
            inst_lo = bytes([((op_msp << 3) | 0b000) & 0xFF, lo_id & 0xFF, val32 & 0xFF, (val32 >> 8) & 0xFF])
            inst_hi = bytes([((op_msp << 3) | 0b000) & 0xFF, hi_id & 0xFF, (val32 >> 16) & 0xFF, (val32 >> 24) & 0xFF])
            return inst_lo + inst_hi

        # Одиночная 16-битная ячейка (CELL): 4 байта
        cell_id = target_val
        val16 = self._eval_expr(val_str, current_pc, pass_num, line_no, line_text) & 0xFFFF
        b0 = ((op_msp << 3) | op3) & 0xFF
        b1 = cell_id & 0xFF
        return bytes([b0, b1, val16 & 0xFF, (val16 >> 8) & 0xFF])

    # --------------------------------------------------------------------------
    # Обработка директив данных (.org, db, dw, dd, equ)
    # --------------------------------------------------------------------------

    def _encode_data_directive(
        self,
        directive: str,
        operands: List[str],
        current_pc: int,
        pass_num: int,
        line_no: int,
        line_text: str,
    ) -> bytes:
        d = directive.upper().lstrip(".")
        out = bytearray()
        for op_str in operands:
            s = op_str.strip()
            if len(s) >= 2 and s[0] in ('"', "'") and s[-1] == s[0]:
                raw_bytes = s[1:-1].encode("utf-8")
                if d in ("DB", "BYTE", "ASCII", "ASCIZ"):
                    out.extend(raw_bytes)
                    if d == "ASCIZ":
                        out.append(0)
                elif d in ("DW", "WORD"):
                    for b in raw_bytes:
                        out.extend([b & 0xFF, 0x00])
                elif d in ("DP", "PTR", "POINTER", "DT"):
                    for b in raw_bytes:
                        out.extend([b & 0xFF, 0x00, 0x00])
                elif d in ("DD", "DWORD"):
                    for b in raw_bytes:
                        out.extend([b & 0xFF, 0x00, 0x00, 0x00])
                continue

            val = self._eval_expr(s, current_pc, pass_num, line_no, line_text)
            if d in ("DB", "BYTE"):
                out.append(val & 0xFF)
            elif d in ("DW", "WORD"):
                v16 = val & 0xFFFF
                out.extend([v16 & 0xFF, (v16 >> 8) & 0xFF])
            elif d in ("DP", "PTR", "POINTER", "DT"):
                v24 = val & 0xFFFFFF
                out.extend([v24 & 0xFF, (v24 >> 8) & 0xFF, (v24 >> 16) & 0xFF])
            elif d in ("DD", "DWORD"):
                v32 = val & 0xFFFFFFFF
                out.extend([v32 & 0xFF, (v32 >> 8) & 0xFF, (v32 >> 16) & 0xFF, (v32 >> 24) & 0xFF])
        return bytes(out)

    # --------------------------------------------------------------------------
    # Главный двухпроходный метод компиляции assemble()
    # --------------------------------------------------------------------------

    def assemble(self, source_code: str, base_address: Optional[int] = None) -> Tuple[bytes, Dict[int, str]]:
        """
        Компилирует текст программы на ассемблере LIM M2.
        Возвращает кортеж (bytecode: bytes, source_map: Dict[int, str]).
        """
        if base_address is not None:
            self.base_address = base_address & 0xFFFFFF

        self.labels.clear()
        self.constants.clear()
        self.source_map.clear()

        source_lines = list(enumerate(source_code.splitlines(), start=1))

        # Двухпроходная компиляция: проход 1 собирает метки, проход 2 генерирует финальный код
        output_segments: List[Tuple[int, bytes, str]] = []

        for pass_num in (1, 2):
            pc = self.base_address
            self.current_org = pc
            output_segments.clear()

            for line_no, raw_line in source_lines:
                clean = self._strip_comment(raw_line).strip()
                if not clean:
                    continue

                # 1. Проверяем присваивание констант / меток через = или EQU:
                #    name = expr | name equ expr | name: equ expr
                m_assign = re.match(r"^(\$?[A-Za-z_][A-Za-z0-9_]*)\s*(?<![=!<>])=(?![=!<>])\s*(.+)$", clean)
                m_equ = re.match(r"^(\$?[A-Za-z_][A-Za-z0-9_]*):?\s+(?:equ|\.equ)\s+(.+)$", clean, re.IGNORECASE)
                matched = m_assign or m_equ
                if matched and matched.group(1).upper() not in OPCODES:
                    lhs = matched.group(1).strip()
                    rhs = matched.group(2).strip()
                    if is_spec_reg(lhs):
                        inst_bytes = self._encode_instruction(
                            "MSP.ld", [lhs, rhs], pc, pass_num, line_no, raw_line
                        )
                        output_segments.append((pc, inst_bytes, clean))
                        pc += len(inst_bytes)
                        continue
                    else:
                        val = self._eval_expr(rhs, pc, pass_num, line_no, raw_line)
                        self.constants[lhs.upper()] = val
                        self.labels[lhs.upper()] = val
                        continue

                # 2. Извлекаем все метки в начале строки (например: loop: ADD $0, $1, $2)
                while True:
                    m_label = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:(.*)$", clean)
                    if not m_label:
                        break
                    lbl_name = m_label.group(1).upper()
                    if pass_num == 1:
                        if lbl_name in self.labels and self.labels[lbl_name] != pc:
                            raise AssemblerError(f"Повторное объявление метки '{m_label.group(1)}'", line_no, raw_line)
                        self.labels[lbl_name] = pc
                    clean = m_label.group(2).strip()
                    if not clean:
                        break

                if not clean:
                    continue

                # 3. Разделяем мнемонику/директиву и операнды
                parts = clean.split(None, 1)
                mnemonic_tok = parts[0].strip()
                ops_raw = parts[1].strip() if len(parts) > 1 else ""

                # Если после мнемоники стояла запятая (например: LMR, $0, [$0:$1]):
                if mnemonic_tok.endswith(","):
                    mnemonic_tok = mnemonic_tok[:-1].strip()
                elif ops_raw.startswith(","):
                    ops_raw = ops_raw[1:].strip()

                up_mnem = mnemonic_tok.upper()

                # 4. Директива .org
                if up_mnem in (".ORG", "ORG"):
                    new_pc = self._eval_expr(ops_raw, pc, pass_num, line_no, raw_line)
                    pc = new_pc & 0xFFFFFF
                    self.current_org = pc
                    continue

                # 5. Директива .equ / .set
                if up_mnem in (".EQU", "EQU", ".SET"):
                    ops = self._split_operands(ops_raw)
                    if len(ops) != 2:
                        raise AssemblerError(f"Директива {up_mnem} требует имя и значение", line_no, raw_line)
                    self.constants[ops[0].upper()] = self._eval_expr(ops[1], pc, pass_num, line_no, raw_line)
                    continue

                # 6. Директивы данных: db, dw, dd, dp, dt, .byte, .word, .dword, .ascii, .asciz
                if up_mnem in (
                    "DB", "DW", "DD", "DP", "DT", "PTR", "POINTER",
                    ".DB", ".DW", ".DD", ".DP", ".DT", ".PTR", ".POINTER",
                    ".BYTE", ".WORD", ".DWORD", ".ASCII", ".ASCIZ",
                    "BYTE", "WORD", "DWORD", "ASCII", "ASCIZ"
                ):
                    ops = self._split_operands(ops_raw)
                    data_bytes = self._encode_data_directive(up_mnem, ops, pc, pass_num, line_no, raw_line)
                    output_segments.append((pc, data_bytes, clean))
                    pc += len(data_bytes)
                    continue

                # 7. Кодирование машинной инструкции LIM M2
                ops = self._split_operands(ops_raw)
                inst_bytes = self._encode_instruction(mnemonic_tok, ops, pc, pass_num, line_no, raw_line)
                output_segments.append((pc, inst_bytes, clean))
                pc += len(inst_bytes)

        # Собираем итоговый образ памяти от base_address до максимального адреса
        if not output_segments:
            return b"", {}

        min_addr = min(seg[0] for seg in output_segments)
        start_addr = min(self.base_address, min_addr)
        max_addr = max(seg[0] + len(seg[1]) for seg in output_segments)
        image = bytearray(max_addr - start_addr)

        for seg_addr, seg_bytes, seg_src in output_segments:
            offset = seg_addr - start_addr
            image[offset : offset + len(seg_bytes)] = seg_bytes
            self.source_map[seg_addr] = seg_src

        return bytes(image), dict(self.source_map)

    # --------------------------------------------------------------------------
    # Экспорт в форматы .bin и .hex
    # --------------------------------------------------------------------------

    @staticmethod
    def to_hex_text(bytecode: bytes, base_address: int = 0x0000, intel_hex: bool = False) -> str:
        """
        Форматирует скомпилированный машинный код в текстовый .hex формат,
        полностью совместимый с загрузчиком симулятора LIM2 (sim.py / bus.py).
        """
        if intel_hex:
            lines: List[str] = []
            for offset in range(0, len(bytecode), 16):
                chunk = bytecode[offset : offset + 16]
                addr = (base_address + offset) & 0xFFFF
                count = len(chunk)
                rec_type = 0x00
                s = count + ((addr >> 8) & 0xFF) + (addr & 0xFF) + rec_type + sum(chunk)
                checksum = (-s) & 0xFF
                data_hex = "".join(f"{b:02X}" for b in chunk)
                lines.append(f":{count:02X}{addr:04X}{rec_type:02X}{data_hex}{checksum:02X}")
            lines.append(":00000001FF")
            return "\n".join(lines) + "\n"

        # Наглядный построчный HEX-дамп (поддерживается bus.load_hex в LIM2)
        lines = [
            f"# LIM M2 Compiled HEX Image (Base: 0x{base_address:04X}, Size: {len(bytecode)} bytes)"
        ]
        for offset in range(0, len(bytecode), 16):
            chunk = bytecode[offset : offset + 16]
            hex_bytes = " ".join(f"{b:02X}" for b in chunk)
            lines.append(f"{hex_bytes}  # 0x{base_address + offset:04X}")
        return "\n".join(lines) + "\n"

    def compile_file(
        self,
        input_path: str | Path,
        bin_output: Optional[str | Path] = None,
        hex_output: Optional[str | Path] = None,
        intel_hex: bool = False,
    ) -> Tuple[Path, Path, bytes]:
        """
        Компилирует исходный файл .asm и сохраняет результат одновременно в .bin и .hex файлы.
        Возвращает (bin_path, hex_path, bytecode).
        """
        in_p = Path(input_path).resolve()
        source = in_p.read_text(encoding="utf-8")
        bytecode, _ = self.assemble(source)

        bin_p = Path(bin_output).resolve() if bin_output else in_p.with_suffix(".bin")
        hex_p = Path(hex_output).resolve() if hex_output else in_p.with_suffix(".hex")

        bin_p.parent.mkdir(parents=True, exist_ok=True)
        hex_p.parent.mkdir(parents=True, exist_ok=True)

        bin_p.write_bytes(bytecode)
        hex_p.write_text(self.to_hex_text(bytecode, self.base_address, intel_hex=intel_hex), encoding="utf-8")
        return bin_p, hex_p, bytecode


# ------------------------------------------------------------------------------
# Дизассемблер одной инструкции LIM M2 (для UI симулятора и отладки)
# ------------------------------------------------------------------------------

def disassemble_one(read8_fn, addr: int) -> Tuple[str, int, List[int]]:
    """
    Декодирует одну инструкцию LIM M2 в памяти по адресу addr.
    Возвращает (мнемоника_в_новом_синтаксисе, длина_в_байтах, список_байтов).
    """
    b0 = read8_fn(addr) & 0xFF
    op = (b0 >> 3) & 0x1F
    cfg = b0 & 0x07

    # 1. 1-байтовые инструкции без операндов
    if op == 0:
        return "NOP", 1, [b0]
    if op == 31:
        return "HALT", 1, [b0]
    if op == 30:
        return "RET", 1, [b0]

    # 2. 1-байтовые инструкции с регистром (cfg = reg)
    if op == 20:
        return f"INC ${cfg}", 1, [b0]
    if op == 21:
        return f"DEC ${cfg}", 1, [b0]
    if op == 22:
        return f"PUSH ${cfg}", 1, [b0]
    if op == 23:
        return f"POP ${cfg}", 1, [b0]
    if op == 24:
        return f"BSL ${cfg}", 1, [b0]
    if op == 25:
        return f"BSR ${cfg}", 1, [b0]

    # 3. Переходы через [$ptreg] (mode == 2, 1 байт!)
    if op in (9, 11, 12, 29):
        neg = (cfg >> 2) & 1
        src_mode = cfg & 0b11
        if src_mode == 2:
            if op == 9:
                return "JMP [$ptreg]", 1, [b0]
            elif op == 11:
                name = "JNO" if neg == 1 else "JO"
                return f"{name} [$ptreg]", 1, [b0]
            elif op == 12:
                name = "JNZ" if neg == 1 else "JZ"
                return f"{name} [$ptreg]", 1, [b0]
            elif op == 29:
                return "CALL [$ptreg]", 1, [b0]

    # Для остальных инструкций считываем второй байт b1
    b1 = read8_fn(addr + 1) & 0xFF
    rd = (b1 >> 5) & 0x07
    rs1 = (b1 >> 2) & 0x07

    # 4. NOT (17) — 2 байта: Target в cfg, Source в b1[7:5]
    if op == 17:
        if cfg == rd:
            return f"NOT ${cfg}", 2, [b0, b1]
        return f"NOT ${cfg}, ${rd}", 2, [b0, b1]

    # 5. LRR (7) — 2 байта: Target в cfg, Source в b1[7:5]
    if op == 7:
        return f"LRR ${cfg}, ${rd}", 2, [b0, b1]

    # 6. CMP (8) — 2 байта: Rs0 в cfg, Rs1 в b1[7:5]
    if op == 8:
        return f"CMP ${cfg}, ${rd}", 2, [b0, b1]

    # 7. INT / INTR (28) — 2 байта
    if op == 28:
        vec = b1 & 0x0F
        return f"INT {vec}", 2, [b0, b1]

    # 8. 3-операндная арифметика и логика (2 байта)
    # Rd в cfg, Rs0 в b1[7:5], Rs1 в b1[4:2]
    alu_names = {
        1: "ADD", 2: "SUB", 3: "MUL", 4: "DIV", 27: "MOD",
        13: "AND", 14: "OR", 15: "NAND", 16: "NOR", 18: "XOR", 19: "XNOR"
    }
    if op in alu_names:
        name = alu_names[op]
        return f"{name} ${cfg}, ${rd}, ${rs1}", 2, [b0, b1]

    # 9. Переходы по паре регистров (mode == 3, 2 байта)
    if op in (9, 11, 12, 29):
        neg = (cfg >> 2) & 1
        src_mode = cfg & 0b11
        if src_mode == 3:
            if op == 9:
                return f"JMP [${rd}:${rs1}]", 2, [b0, b1]
            elif op == 11:
                name = "JNO" if neg == 1 else "JO"
                return f"{name} [${rd}:${rs1}]", 2, [b0, b1]
            elif op == 12:
                name = "JNZ" if neg == 1 else "JZ"
                return f"{name} [${rd}:${rs1}]", 2, [b0, b1]
            elif op == 29:
                return f"CALL [${rd}:${rs1}]", 2, [b0, b1]

    # 10. Память: LMR (5) и LRM (6)
    if op in (5, 6):
        name = "LMR" if op == 5 else "LRM"
        ds = (cfg >> 2) & 1
        mode = cfg & 0b11
        sfx = ".b" if ds == 0 else ".w"
        if mode == 0:
            if ds == 0:
                imm8 = read8_fn(addr + 2) & 0xFF
                if op == 5:
                    return f"{name}{sfx} ${rd}, 0x{imm8:02X}", 3, [b0, b1, imm8]
                else:
                    return f"{name}{sfx} 0x{imm8:02X}, [$ptreg]", 3, [b0, b1, imm8]
            else:
                lo = read8_fn(addr + 2) & 0xFF
                hi = read8_fn(addr + 3) & 0xFF
                imm16 = (hi << 8) | lo
                if op == 5:
                    return f"{name}{sfx} ${rd}, 0x{imm16:04X}", 4, [b0, b1, lo, hi]
                else:
                    return f"{name}{sfx} 0x{imm16:04X}, [$ptreg]", 4, [b0, b1, lo, hi]
        elif mode == 1:
            p0 = read8_fn(addr + 2) & 0xFF
            p1 = read8_fn(addr + 3) & 0xFF
            p2 = read8_fn(addr + 4) & 0xFF
            p3 = read8_fn(addr + 5) & 0xFF
            ptr32 = p0 | (p1 << 8) | (p2 << 16) | (p3 << 24)
            return f"{name}{sfx} ${rd}, [0x{ptr32:08X}]", 6, [b0, b1, p0, p1, p2, p3]
        elif mode == 2:
            return f"{name}{sfx} ${rd}, [$ptreg]", 2, [b0, b1]
        elif mode == 3:
            return f"{name}{sfx} ${rd}, [${rd}:${rs1}]", 2, [b0, b1]

    # 11. JCR (10): 5 байт
    if op == 10:
        b2 = read8_fn(addr + 2) & 0xFF
        b3 = read8_fn(addr + 3) & 0xFF
        b4 = read8_fn(addr + 4) & 0xFF
        target = b1 | (b2 << 8) | (b3 << 16) | (b4 << 24)
        cond_str = JCR_COND_NAME.get(cfg, f"?{cfg}")
        return f"JCR {cond_str}, 0x{target:08X}", 5, [b0, b1, b2, b3, b4]

    # 12. Переходы direct imm32 (mode == 0) и indirect [addr32] (mode == 1): 5 байт
    if op in (9, 11, 12, 29):
        neg = (cfg >> 2) & 1
        src_mode = cfg & 0b11
        if op == 9:
            name = "JMP"
        elif op == 11:
            name = "JNO" if neg == 1 else "JO"
        elif op == 12:
            name = "JNZ" if neg == 1 else "JZ"
        else:
            name = "CALL"

        b2 = read8_fn(addr + 2) & 0xFF
        b3 = read8_fn(addr + 3) & 0xFF
        b4 = read8_fn(addr + 4) & 0xFF
        target = b1 | (b2 << 8) | (b3 << 16) | (b4 << 24)
        if src_mode == 1:
            return f"{name} [0x{target:08X}]", 5, [b0, b1, b2, b3, b4]
        return f"{name} 0x{target:08X}", 5, [b0, b1, b2, b3, b4]

    # 13. MSP (26: квантованные 16-битные операции со специальными регистрами)
    if op == 26:
        op3 = cfg & 0x07
        reg_id = b1
        cell_name = SYS_CELL_NAMES.get(reg_id, f"0x{reg_id:02X}")
        if op3 == 0b001:
            return f"MSP.ldr {cell_name}", 2, [b0, b1]
        elif op3 == 0b010:
            return f"MSP.str {cell_name}", 2, [b0, b1]
        else:
            lo = read8_fn(addr + 2) & 0xFF
            hi = read8_fn(addr + 3) & 0xFF
            val16 = (hi << 8) | lo
            op_names = {0: "ld", 3: "and", 4: "or", 5: "xor", 6: "onb", 7: "offb"}
            name = op_names.get(op3, f"op{op3}")
            return f"MSP.{name} {cell_name}, 0x{val16:04X}", 4, [b0, b1, lo, hi]

    return f"DB 0x{b0:02X}, 0x{b1:02X}", 2, [b0, b1]

# ------------------------------------------------------------------------------
# CLI-интерфейс компилятора
# ------------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="LIM M2 Assembler Compiler — компиляция .asm кода в .bin и .hex файлы."
    )
    parser.add_argument("input", help="Путь к исходному файлу ассемблера (.asm / .lasm)")
    parser.add_argument("-o", "--bin", dest="bin_out", help="Путь для сохранения бинарного файла (.bin)")
    parser.add_argument("-x", "--hex", dest="hex_out", help="Путь для сохранения шестнадцатеричного файла (.hex)")
    parser.add_argument(
        "-b",
        "--base",
        default="0x0000",
        help="Базовый адрес загрузки кода (по умолчанию 0x0000)",
    )
    parser.add_argument(
        "--intel-hex",
        action="store_true",
        help="Генерировать .hex в стандарте Intel HEX (:LLAAAATTDD...CC)",
    )
    parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="Вывести таблицу меток и дизассемблированный листинг после компиляции",
    )

    args = parser.parse_args(argv)
    base_addr = int(args.base, 0)

    asm = LimAssembler(base_address=base_addr)
    try:
        bin_path, hex_path, bytecode = asm.compile_file(
            args.input,
            bin_output=args.bin_out,
            hex_output=args.hex_out,
            intel_hex=args.intel_hex,
        )
    except Exception as exc:
        print(f"[ОШИБКА] {exc}", file=sys.stderr)
        return 1

    print(f"[LIM M2 ASM] Успешно скомпилировано: {len(bytecode)} байт (база 0x{base_addr:04X})")
    print(f"  -> BIN: {bin_path}")
    print(f"  -> HEX: {hex_path}")

    if args.list:
        if asm.labels:
            print("\nТаблица меток:")
            for lbl, addr in sorted(asm.labels.items(), key=lambda x: x[1]):
                print(f"  {lbl:<16} = 0x{addr:04X}")
        print("\nМашинный код:")
        idx = 0
        while idx < len(bytecode):
            mnem, length, raw = disassemble_one(
                lambda a: bytecode[a - base_addr] if 0 <= (a - base_addr) < len(bytecode) else 0,
                base_addr + idx,
            )
            hex_str = " ".join(f"{b:02X}" for b in raw)
            print(f"  0x{base_addr + idx:04X}:  {hex_str:<14}  {mnem}")
            idx += length

    return 0


if __name__ == "__main__":
    sys.exit(main())
