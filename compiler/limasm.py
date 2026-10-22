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

SPEC_REG_MAP: Dict[str, Tuple[int, int]] = {
    "$FREG": (0, 0),
    "FREG": (0, 0),
    "$PTREG": (1, 0),
    "PTREG": (1, 0),
    "$SREG": (2, 0),
    "SREG": (2, 0),
    "$SP": (2, 0),
    "SP": (2, 0),
}
for _v in range(32):
    SPEC_REG_MAP[f"$VEC{_v}"] = (3, _v)
    SPEC_REG_MAP[f"VEC{_v}"] = (3, _v)
for _i in range(16):
    SPEC_REG_MAP[f"$IR{_i}"] = (3, _i)
    SPEC_REG_MAP[f"IR{_i}"] = (3, _i)
for _p in range(16):
    SPEC_REG_MAP[f"$PV{_p}"] = (3, 16 + _p)
    SPEC_REG_MAP[f"PV{_p}"] = (3, 16 + _p)

# Алиасы границ оперативной памяти RAM ($pv14 и $pv15, к которой разрешен доступ с любыми правами):
SPEC_REG_MAP["$RAM_BASE"] = (3, 30)
SPEC_REG_MAP["RAM_BASE"] = (3, 30)
SPEC_REG_MAP["$RAM_LIMIT"] = (3, 31)
SPEC_REG_MAP["RAM_LIMIT"] = (3, 31)
SPEC_REG_MAP["$RAM_START"] = (3, 30)
SPEC_REG_MAP["RAM_START"] = (3, 30)
SPEC_REG_MAP["$RAM_END"] = (3, 31)
SPEC_REG_MAP["RAM_END"] = (3, 31)

# Для совместимости: алиасы ROM:
SPEC_REG_MAP["$ROM_BASE"] = (3, 30)
SPEC_REG_MAP["ROM_BASE"] = (3, 30)
SPEC_REG_MAP["$ROM_LIMIT"] = (3, 31)
SPEC_REG_MAP["ROM_LIMIT"] = (3, 31)
SPEC_REG_MAP["$ROM_START"] = (3, 30)
SPEC_REG_MAP["ROM_START"] = (3, 30)
SPEC_REG_MAP["$ROM_END"] = (3, 31)
SPEC_REG_MAP["ROM_END"] = (3, 31)

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
    "JNZ": 11,
    "JZ": 12,
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
    "RSV29": 29,
    "RSV30": 30,
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


def is_spec_reg(token: str) -> bool:
    t = token.strip().upper()
    if t.startswith("[") and t.endswith("]"):
        t = t[1:-1].strip()
    return t in SPEC_REG_MAP


def parse_spec_reg(token: str, line_no: Optional[int] = None, line_text: str = "") -> Tuple[int, int, bool]:
    """
    Возвращает (sreg_sel, vec_idx, was_bracketed).
    sreg_sel: 0=FREG, 1=PTREG, 2=SREG, 3=VECTORS[vec_idx].
    """
    raw = token.strip()
    bracketed = False
    if raw.startswith("[") and raw.endswith("]"):
        bracketed = True
        raw = raw[1:-1].strip()
    key = raw.upper()
    if key not in SPEC_REG_MAP:
        raise AssemblerError(
            f"Ожидался специальный регистр ($freg, $ptreg, $sreg), получено '{token}'",
            line_no,
            line_text,
        )
    sreg_sel, vec_idx = SPEC_REG_MAP[key]
    return sreg_sel, vec_idx, bracketed


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
            elif base == "MSP" and p in ("LD", "LOAD", "AND", "OR", "XOR", "XNOR", "ADD", "SUB"):
                sub_op = "LD" if p == "LOAD" else p
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

        # 1. Однобайтовые безаргументные инструкции: NOP (0), RSV29 (29), RSV30 (30), HALT/RSV31 (31)
        if base in ("NOP", "RSV29", "RSV30", "RSV31", "HALT", "HLT"):
            if operands:
                raise AssemblerError(f"Инструкция '{base}' не принимает аргументов", line_no, line_text)
            return bytes([(op << 3) & 0xFF])

        # 2. Однобайтовые унарные регистровые инструкции: NOT (17), INC (20), DEC (21)
        if base in ("NOT", "INC", "DEC"):
            if len(operands) != 1:
                raise AssemblerError(f"Инструкция '{base}' требует ровно 1 регистр (например, {base} $0)", line_no, line_text)
            rd = parse_gpr(operands[0], line_no, line_text)
            return bytes([((op << 3) | rd) & 0xFF])

        # 3. Двухбайтовое программное прерывание: INTR vec / SWI vec / INT vec (28)
        if base in ("INTR", "SWI", "INT"):
            if len(operands) != 1:
                raise AssemblerError(f"Инструкция '{base}' требует 1 аргумент — номер вектора 0..15", line_no, line_text)
            vec = self._eval_expr(operands[0], current_pc, pass_num, line_no, line_text)
            if pass_num == 2 and not (0 <= vec <= 15):
                raise AssemblerError(f"Номер вектора прерывания должен быть в диапазоне 0..15, получено {vec}", line_no, line_text)
            b0 = (op << 3) & 0xFF
            b1 = vec & 0x0F
            return bytes([b0, b1])

        # 3a. Возврат из подпрограммы (1 байт): RET (30)
        if base == "RET":
            if len(operands) != 0:
                raise AssemblerError(f"Инструкция 'RET' не принимает аргументов", line_no, line_text)
            return bytes([(op << 3) & 0xFF])

        # 4. Трехоперандные арифметические инструкции (2 байта): ADD (1), SUB (2), MUL (3), DIV (4), MOD (27)
        if base in ("ADD", "SUB", "MUL", "DIV", "MOD"):
            if len(operands) == 2:
                # Сокращенная запись ADD $0, $1 -> ADD $0, $0, $1
                rd = parse_gpr(operands[0], line_no, line_text)
                rs1 = rd
                rs2 = parse_gpr(operands[1], line_no, line_text)
            elif len(operands) == 3:
                rd = parse_gpr(operands[0], line_no, line_text)
                rs1 = parse_gpr(operands[1], line_no, line_text)
                rs2 = parse_gpr(operands[2], line_no, line_text)
            else:
                raise AssemblerError(
                    f"Инструкция '{base}' работает только с регистрами и требует 3 (или 2) регистра: {base} $0, $1, $2",
                    line_no,
                    line_text,
                )
            b0 = ((op << 3) | rd) & 0xFF
            b1 = ((rs1 << 5) | (rs2 << 2)) & 0xFF
            return bytes([b0, b1])

        # 5. Двухоперандные регистровые инструкции (2 байта): LRR (7), CMP (8), AND (13), OR (14), NAND (15), NOR (16), XOR (18), XNOR (19)
        if base in ("LRR", "CMP", "AND", "OR", "NAND", "NOR", "XOR", "XNOR"):
            if len(operands) != 2:
                raise AssemblerError(
                    f"Инструкция '{base}' требует 2 регистра: {base} $0, $1",
                    line_no,
                    line_text,
                )
            r_first = parse_gpr(operands[0], line_no, line_text)
            r_second = parse_gpr(operands[1], line_no, line_text)
            b0 = (op << 3) & 0xFF
            b1 = ((r_first << 5) | (r_second << 2)) & 0xFF
            return bytes([b0, b1])

        # 6. Сдвиги на D-триггерах (2 байта): BSL (24), BSR (25)
        if base in ("BSL", "BSR"):
            if len(operands) != 2:
                raise AssemblerError(
                    f"Инструкция '{base}' требует целевой регистр и константу сдвига (0..16): {base} $0, 4",
                    line_no,
                    line_text,
                )
            rd = parse_gpr(operands[0], line_no, line_text)
            shift = self._eval_expr(operands[1], current_pc, pass_num, line_no, line_text)
            b0 = ((op << 3) | rd) & 0xFF
            b1 = shift & 0xFF
            return bytes([b0, b1])

        # 7. Стековые инструкции (2 байта): PUSH (22), POP (23)
        if base in ("PUSH", "POP"):
            if len(operands) != 1:
                raise AssemblerError(
                    f"Инструкция '{base}' требует 1 регистр: {base} $0",
                    line_no,
                    line_text,
                )
            reg = parse_gpr(operands[0], line_no, line_text)
            b0 = ((op << 3) | reg) & 0xFF
            b1 = (reg << 5) & 0xFF
            return bytes([b0, b1])

        # 8. Условный переход по результату сравнения: JCR (10)
        if base == "JCR":
            return self._encode_jcr(sub_op, operands, current_pc, pass_num, line_no, line_text)

        # 9. Переходы и вызовы подпрограмм (2..5 байт): JMP (9), JNZ (11), JZ (12), CALL (29)
        if base in ("JMP", "JNZ", "JZ", "CALL"):
            if len(operands) != 1:
                raise AssemblerError(f"Инструкция перехода '{base}' требует 1 целевой операнд", line_no, line_text)
            target_tok = operands[0].strip()
            is_bracketed = target_tok.startswith("[") and target_tok.endswith("]")
            unbracketed = target_tok[1:-1].strip() if is_bracketed else target_tok

            # MOD=2: переход по 32-битному указателю PTREG (JMP [$ptreg] или JMP $ptreg)
            if unbracketed.upper() in ("$PTREG", "PTREG"):
                b0 = ((op << 3) | 0b010) & 0xFF
                return bytes([b0, 0x00])

            # MOD=1: косвенный регистровый переход (JMP $0 / JMP R0)
            if is_gpr(unbracketed):
                rs = parse_gpr(unbracketed, line_no, line_text)
                b0 = ((op << 3) | 0b001) & 0xFF
                b1 = (rs << 5) & 0xFF
                return bytes([b0, b1])

            # MOD=3: косвенный переход по адресу в памяти (JMP [mark] / JMP [0x1000]) (5 байт: 32-битный указатель Little-Endian)
            if is_bracketed:
                addr = self._eval_expr(unbracketed, current_pc, pass_num, line_no, line_text) & 0xFFFFFFFF
                b0 = ((op << 3) | 0b011) & 0xFF
                return bytes([b0, addr & 0xFF, (addr >> 8) & 0xFF, (addr >> 16) & 0xFF, (addr >> 24) & 0xFF])

            # MOD=0: непосредственный 32-битный адрес перехода (5 байт) (JMP mark / JMP 0x100000)
            addr = self._eval_expr(unbracketed, current_pc, pass_num, line_no, line_text) & 0xFFFFFFFF
            b0 = ((op << 3) | 0b000) & 0xFF
            return bytes([b0, addr & 0xFF, (addr >> 8) & 0xFF, (addr >> 16) & 0xFF, (addr >> 24) & 0xFF])

        # 9. Загрузка и выгрузка памяти: LMR (5) и LRM (6)
        if base in ("LMR", "LRM"):
            return self._encode_lmr_lrm(base, op, size_sfx, operands, current_pc, pass_num, line_no, line_text)

        # 10. Манипуляция специальными регистрами: MSP (26)
        if base == "MSP":
            return self._encode_msp(sub_op, size_sfx, operands, current_pc, pass_num, line_no, line_text)

        raise AssemblerError(f"Инструкция '{base}' не реализована", line_no, line_text)

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
            # 1. CMP $r1, $r2 (2 байта: [7-3] опкод 8, [2-0] 0; [7-5] r1, [4-2] r2)
            cmp_b0 = (8 << 3) & 0xFF
            cmp_b1 = ((r1 << 5) | (r2 << 2)) & 0xFF
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

        sz_bit = 0 if size_sfx == "B" else 1  # .b -> 0 (8-bit), .w / default -> 1 (16-bit)
        reg_main = parse_gpr(operands[0], line_no, line_text)

        # Если передано 2 регистра без скобок: LMR $0, $1 -> режим 3 (пара регистров $0:$1)
        if len(operands) == 2 and is_gpr(operands[1]):
            rs_lo = parse_gpr(operands[1], line_no, line_text)
            mode = 3
            cfg = (mode << 1) | sz_bit
            b0 = ((op << 3) | cfg) & 0xFF
            b1 = ((reg_main << 5) | (rs_lo << 2)) & 0xFF
            return bytes([b0, b1])

        if len(operands) != 2:
            raise AssemblerError(f"Неверное число аргументов для '{base}'", line_no, line_text)

        arg = operands[1].strip()

        # Случай А: Операнд в квадратных скобках [...] — это ссылка на данные (указатель)
        if arg.startswith("[") and arg.endswith("]"):
            inner = arg[1:-1].strip()

            # 1) [$ptreg] -> режим 2 (косвенно через 24-битный PTREG)
            if inner.upper() in ("$PTREG", "PTREG"):
                mode = 2
                cfg = (mode << 1) | sz_bit
                b0 = ((op << 3) | cfg) & 0xFF
                b1 = (reg_main << 5) & 0xFF
                return bytes([b0, b1])

            # 2) [$0:$1] или [$0, $1] -> режим 3 (24-битный поинтер на основе пары регистров)
            if ":" in inner or "," in inner:
                sep = ":" if ":" in inner else ","
                pair = [p.strip() for p in inner.split(sep)]
                if len(pair) != 2:
                    raise AssemblerError(f"Ожидалась пара регистров вида [$0:$1], получено '{arg}'", line_no, line_text)
                r_hi = parse_gpr(pair[0], line_no, line_text)
                r_lo = parse_gpr(pair[1], line_no, line_text)
                mode = 3
                cfg = (mode << 1) | sz_bit
                b0 = ((op << 3) | cfg) & 0xFF
                # В архитектуре LIM M2 старший регистр пары (Arg1) находится в битах [7:5], младший (Arg2) в [4:2].
                # Если пользователь указал LMR $2, [$0:$1] где $2 != $0, сначала копируем $0 в $2 (LRR $2, $0):
                prefix = b""
                if r_hi != reg_main:
                    prefix = bytes([(OPCODES["LRR"] << 3) & 0xFF, ((reg_main << 5) | (r_hi << 2)) & 0xFF])
                b1 = ((reg_main << 5) | (r_lo << 2)) & 0xFF
                return prefix + bytes([b0, b1])

            # 3) [addr] -> режим 1 (непосредственный 32-битный указатель на память, Little-Endian)
            ptr = self._eval_expr(inner, current_pc, pass_num, line_no, line_text) & 0xFFFFFFFF
            mode = 1
            cfg = (mode << 1) | sz_bit
            b0 = ((op << 3) | cfg) & 0xFF
            b1 = (reg_main << 5) & 0xFF
            return bytes([
                b0, b1,
                ptr & 0xFF,
                (ptr >> 8) & 0xFF,
                (ptr >> 16) & 0xFF,
                (ptr >> 24) & 0xFF,
            ])

        # Случай Б: Просто число/выражение без скобок -> непосредственное значение (SRC=0 / DST=0)
        val = self._eval_expr(arg, current_pc, pass_num, line_no, line_text)
        mode = 0
        cfg = (mode << 1) | sz_bit
        b0 = ((op << 3) | cfg) & 0xFF
        b1 = (reg_main << 5) & 0xFF
        if sz_bit == 0:
            return bytes([b0, b1, val & 0xFF])
        else:
            val16 = val & 0xFFFF
            return bytes([b0, b1, val16 & 0xFF, (val16 >> 8) & 0xFF])

    # --------------------------------------------------------------------------
    # Кодирование MSP (Манипуляция специальными регистрами FREG, PTREG, SREG)
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
        Поддерживает все формы MSP:
          - MSP.ld $freg, 0x0000        | MSP.ld $freg, $0        | MSP.ld $freg, [$ptreg] | MSP.ld $freg, [0xA000]
          - MSP.and $freg, 0x0001       | MSP.or $freg, 0x0200    | MSP.xor $freg, $1      | MSP.xnor $freg, 0xFFFF
          - MSP.ld $ptreg, [$0:$1]      | MSP.ld $sreg, [$0:$1]   | MSP.ld $ir0, [$0:$1]
          - MSP.ld $ptreg, 0xA000       | MSP.ld.d $ptreg, 0x01A000
          - MSP.ld $ptreg, [$ptreg]     (нативное разыменование указателя PTREG <- MEM[PTREG])
          - MSP.ld $ptreg, [0xA000]     (загрузка PTREG по ссылке из памяти MEM[0xA000])
          - MSP.add $ptreg, $3          | MSP.add $ptreg, 0x0010  | MSP.sub $ptreg, 0x0002
          - Те же операции для $sreg ($sp) и векторов $ir0..$ir15, $pv0..$pv15
          - Традиционный синтаксис без точки: MSP $freg, OR, $2 | MSP $ptreg, [$0:$1]
        """
        if not operands:
            raise AssemblerError("Инструкция MSP требует операнды", line_no, line_text)

        op_msp = OPCODES["MSP"]  # 26 (0b11010)

        # Если человек написал MSP.ld [0xA000], $0, $1 или MSP.ld 0xA000, $0, $1 (вместо $ptreg число/ссылка),
        # или традиционный вид: определяем целевой спецрегистр
        first_tok = operands[0].strip()
        if is_spec_reg(first_tok):
            sreg_sel, vec_idx, _ = parse_spec_reg(first_tok, line_no, line_text)
            rest = operands[1:]
        else:
            # Если вместо $ptreg первым аргументом написано число или [число], например MSP.ld [0xA000], $0, $1
            # или MSP.ld 0xA000: целевым спецрегистром выступает PTREG (sreg_sel = 1)
            sreg_sel = 1
            vec_idx = 0
            rest = operands

        # Определяем режим (LD vs AND/OR/XOR/XNOR/ADD/SUB), если он передан вторым аргументом по старому стилю
        if sub_op is None:
            if rest and rest[0].strip().upper() in ("LD", "LOAD", "AND", "OR", "XOR", "XNOR", "ADD", "SUB"):
                kw = rest[0].strip().upper()
                sub_op = "LD" if kw == "LOAD" else kw
                rest = rest[1:]
            else:
                sub_op = "LD"

        if not rest:
            raise AssemblerError(f"Не указан операнд-источник для MSP.{sub_op.lower()}", line_no, line_text)

        # --- РЕЖИМ 1: ПРЯМАЯ ЗАГРУЗКА (MSP.ld, act = 0) ---
        if sub_op == "LD":
            act = 0
            b0 = ((op_msp << 3) | (act << 2) | (sreg_sel & 0x03)) & 0xFF

            # Векторные регистры прерываний ($ir0..$ir15) и привилегированных зон ($pv0..$pv15)
            if sreg_sel == 3:
                # Источник 0: пара регистров $rd, $rs (3 байта)
                if len(rest) == 2 and is_gpr(rest[0]) and is_gpr(rest[1]):
                    rd_hi = parse_gpr(rest[0], line_no, line_text)
                    rs_lo = parse_gpr(rest[1], line_no, line_text)
                    b1 = (((vec_idx & 0x1F) << 3) | (0b00 << 1)) & 0xFF
                    b2 = ((rd_hi << 5) | (rs_lo << 2)) & 0xFF
                    return bytes([b0, b1, b2])

                if len(rest) == 1:
                    src_tok = rest[0].strip()

                    # Источник 0а: $rd:$rs (3 байта)
                    if ":" in src_tok and not (src_tok.startswith("[") and src_tok.endswith("]")):
                        pair = [p.strip() for p in src_tok.split(":")]
                        if len(pair) == 2 and is_gpr(pair[0]) and is_gpr(pair[1]):
                            rd_hi = parse_gpr(pair[0], line_no, line_text)
                            rs_lo = parse_gpr(pair[1], line_no, line_text)
                            b1 = (((vec_idx & 0x1F) << 3) | (0b00 << 1)) & 0xFF
                            b2 = ((rd_hi << 5) | (rs_lo << 2)) & 0xFF
                            return bytes([b0, b1, b2])

                    # Источник 0б: одиночный регистр $rd -> младшие 16 бит (3 байта, старшие 0)
                    if is_gpr(src_tok):
                        rs_lo = parse_gpr(src_tok, line_no, line_text)
                        b1 = (((vec_idx & 0x1F) << 3) | (0b00 << 1)) & 0xFF
                        b2 = (rs_lo << 2) & 0xFF
                        return bytes([b0, b1, b2])

                    # Источники в скобках [...]
                    if src_tok.startswith("[") and src_tok.endswith("]"):
                        inner = src_tok[1:-1].strip()

                        # Источник 2: по адресу в PTREG [$ptreg] (2 байта)
                        if inner.upper() in ("$PTREG", "PTREG"):
                            b1 = (((vec_idx & 0x1F) << 3) | (0b10 << 1)) & 0xFF
                            return bytes([b0, b1])

                        # Составной поинтер [$rd:$rs] (Источник 0: пара регистров GPR, 3 байта)
                        if ":" in inner:
                            pair = [p.strip() for p in inner.split(":")]
                            if len(pair) == 2 and is_gpr(pair[0]) and is_gpr(pair[1]):
                                rd_hi = parse_gpr(pair[0], line_no, line_text)
                                rs_lo = parse_gpr(pair[1], line_no, line_text)
                                b1 = (((vec_idx & 0x1F) << 3) | (0b00 << 1)) & 0xFF
                                b2 = ((rd_hi << 5) | (rs_lo << 2)) & 0xFF
                                return bytes([b0, b1, b2])

                        # Источник 3б: по прямому адресу памяти [addr32] (6 байт Little-Endian)
                        addr32 = self._eval_expr(inner, current_pc, pass_num, line_no, line_text) & 0xFFFFFFFF
                        b1 = (((vec_idx & 0x1F) << 3) | (0b11 << 1) | 1) & 0xFF
                        return bytes([
                            b0, b1,
                            addr32 & 0xFF,
                            (addr32 >> 8) & 0xFF,
                            (addr32 >> 16) & 0xFF,
                            (addr32 >> 24) & 0xFF
                        ])

                    # Источник 1: непосредственная загрузка imm32 (6 байт Little-Endian)
                    imm32 = self._eval_expr(src_tok, current_pc, pass_num, line_no, line_text) & 0xFFFFFFFF
                    b1 = (((vec_idx & 0x1F) << 3) | (0b01 << 1)) & 0xFF
                    return bytes([
                        b0, b1,
                        imm32 & 0xFF,
                        (imm32 >> 8) & 0xFF,
                        (imm32 >> 16) & 0xFF,
                        (imm32 >> 24) & 0xFF
                    ])

                raise AssemblerError(f"Неверное число операндов для MSP.ld: {rest}", line_no, line_text)

            # Случай 1: Два регистра общего назначения -> MSP.ld $ptreg, $0, $1 (или $sreg)
            if len(rest) == 2 and is_gpr(rest[0]) and is_gpr(rest[1]):
                rs_hi = parse_gpr(rest[0], line_no, line_text)
                rs_lo = parse_gpr(rest[1], line_no, line_text)
                if sreg_sel == 0:
                    raise AssemblerError("Для 16-битного регистра $freg требуется один регистр-источник, а не пара", line_no, line_text)
                b1 = ((rs_hi << 5) | (rs_lo << 2) | 0b00) & 0xFF
                return bytes([b0, b1])

            # Если в MSP.ld [0xA000], $0, $1 было 3 аргумента (адрес + 2 регистра):
            if len(rest) == 3 and is_gpr(rest[1]) and is_gpr(rest[2]):
                rs_hi = parse_gpr(rest[1], line_no, line_text)
                rs_lo = parse_gpr(rest[2], line_no, line_text)
                b1 = ((rs_hi << 5) | (rs_lo << 2) | 0b00) & 0xFF
                return bytes([b0, b1])

            if len(rest) != 1:
                raise AssemblerError(f"Неверное число операндов для MSP.ld: {rest}", line_no, line_text)

            src_tok = rest[0].strip()

            # Случай 2: Одиночный регистр общего назначения -> MSP.ld $freg, $0 (или $vec3, $0)
            if is_gpr(src_tok):
                rs = parse_gpr(src_tok, line_no, line_text)
                if sreg_sel == 0:
                    b1 = ((rs << 5) | 0b00) & 0xFF
                elif sreg_sel == 3:
                    b1 = ((vec_idx << 5) | (rs << 2) | 0b00) & 0xFF
                else:
                    # Для PTREG/SREG из одного регистра: rs как старший и младший? Нет, если 1 регистр, кладем его в rs_lo, а что если rs_hi=rs_lo?
                    # Если нужно загрузить 16-битный регистр в младшие 16 бит PTREG, используем rs_hi=rs, rs_lo=rs только если $0==0.
                    # Но по спецификации в регистровом режиме PTREG берет пару (rs_hi, rs_lo).
                    b1 = ((rs << 5) | (rs << 2) | 0b00) & 0xFF
                return bytes([b0, b1])

            # Случай 3: Операнд в квадратных скобках [...] -> разыменование указателя
            if src_tok.startswith("[") and src_tok.endswith("]"):
                inner = src_tok[1:-1].strip()

                # 3а) MSP.ld $ptreg, [$ptreg] -> нативное разыменование PTREG (ext_mode = 2 / 0b10, 2 байта!)
                if inner.upper() in ("$PTREG", "PTREG"):
                    sz24_bit = 1 if size_sfx == "D" else 0
                    hi_field = (vec_idx << 5) if sreg_sel == 3 else 0
                    b1 = (hi_field | (sz24_bit << 2) | 0b10) & 0xFF
                    return bytes([b0, b1])

                # 3б) MSP.ld $ptreg, [$0:$1] -> пара регистров
                if ":" in inner:
                    pair = [p.strip() for p in inner.split(":")]
                    if len(pair) == 2 and is_gpr(pair[0]) and is_gpr(pair[1]):
                        rs_hi = parse_gpr(pair[0], line_no, line_text)
                        rs_lo = parse_gpr(pair[1], line_no, line_text)
                        b1 = ((rs_hi << 5) | (rs_lo << 2) | 0b00) & 0xFF
                        return bytes([b0, b1])

                # 3в) MSP.ld $ptreg, [0xA000] -> косвенная загрузка по 32-битному адресу в памяти (ext_mode = 3 / 0b11, 6 байт Little-Endian)
                addr32 = self._eval_expr(inner, current_pc, pass_num, line_no, line_text) & 0xFFFFFFFF
                sz24_bit = 1 if size_sfx == "D" else 0
                hi_field = (vec_idx << 5) if sreg_sel == 3 else 0
                b1 = (hi_field | (sz24_bit << 2) | 0b11) & 0xFF
                return bytes([
                    b0, b1,
                    addr32 & 0xFF,
                    (addr32 >> 8) & 0xFF,
                    (addr32 >> 16) & 0xFF,
                    (addr32 >> 24) & 0xFF,
                ])

            # Случай 4: Непосредственное число (например MSP.ld $freg, 0x0000 или MSP.ld $ptreg, 0xA000) -> ext_mode = 1 (0b01)
            imm_val = self._eval_expr(src_tok, current_pc, pass_num, line_no, line_text)
            hi_field = (vec_idx << 5) if sreg_sel == 3 else 0
            if sreg_sel == 0:  # FREG (16 бит Little-Endian)
                imm16 = imm_val & 0xFFFF
                b1 = (hi_field | 0b01) & 0xFF
                return bytes([b0, b1, imm16 & 0xFF, (imm16 >> 8) & 0xFF])
            else:  # PTREG (1) и SREG (2): ОБЯЗАТЕЛЬНО 4 байта - 32 бита Little-Endian!
                imm32 = imm_val & 0xFFFFFFFF
                b1 = (hi_field | (1 << 2) | 0b01) & 0xFF
                return bytes([
                    b0, b1,
                    imm32 & 0xFF,
                    (imm32 >> 8) & 0xFF,
                    (imm32 >> 16) & 0xFF,
                    (imm32 >> 24) & 0xFF
                ])

        # --- РЕЖИМ 2: МОДИФИКАЦИЯ (MSP.and, MSP.or, MSP.xor, MSP.xnor, MSP.add, MSP.sub, act = 1) ---
        act = 1
        b0 = ((op_msp << 3) | (act << 2) | (sreg_sel & 0x03)) & 0xFF
        if len(rest) != 1:
            raise AssemblerError(f"Инструкция MSP.{sub_op.lower()} требует 1 операнд маски/смещения", line_no, line_text)
        src_tok = rest[0].strip()

        if sreg_sel == 3:
            raise AssemblerError(
                f"Векторные регистры ($ir0..$ir15, $pv0..$pv15) поддерживают только загрузку MSP.ld",
                line_no,
                line_text,
            )

        if sreg_sel == 0:
            # FREG поддерживает AND, OR, XOR, XNOR
            if sub_op not in MSP_LOGIC_OPS:
                raise AssemblerError(
                    f"Для регистра флагов $freg поддерживаются операции .and, .or, .xor, .xnor (получено .{sub_op.lower()})",
                    line_no,
                    line_text,
                )
            logic_code = MSP_LOGIC_OPS[sub_op]
            if is_gpr(src_tok):
                rs = parse_gpr(src_tok, line_no, line_text)
                b1 = ((logic_code << 6) | (rs << 3) | 0b00) & 0xFF
                return bytes([b0, b1])
            elif src_tok.startswith("[") and src_tok.endswith("]"):
                inner = src_tok[1:-1].strip()
                if inner.upper() in ("$PTREG", "PTREG"):
                    b1 = ((logic_code << 6) | 0b10) & 0xFF
                    return bytes([b0, b1])
                addr16 = self._eval_expr(inner, current_pc, pass_num, line_no, line_text) & 0xFFFF
                b1 = ((logic_code << 6) | 0b11) & 0xFF
                return bytes([b0, b1, addr16 & 0xFF, (addr16 >> 8) & 0xFF])
            else:
                imm16 = self._eval_expr(src_tok, current_pc, pass_num, line_no, line_text) & 0xFFFF
                b1 = ((logic_code << 6) | 0b01) & 0xFF
                return bytes([b0, b1, imm16 & 0xFF, (imm16 >> 8) & 0xFF])

        elif sreg_sel in (1, 2):
            # PTREG и SREG поддерживают ADD и SUB
            if sub_op not in MSP_ARITH_OPS:
                raise AssemblerError(
                    f"Для регистров $ptreg / $sreg поддерживаются операции .ld, .add, .sub (получено .{sub_op.lower()})",
                    line_no,
                    line_text,
                )
            arith_code = MSP_ARITH_OPS[sub_op]
            if is_gpr(src_tok):
                rs = parse_gpr(src_tok, line_no, line_text)
                b1 = ((arith_code << 7) | (rs << 4) | 0b00) & 0xFF
                return bytes([b0, b1])
            elif src_tok.startswith("[") and src_tok.endswith("]"):
                inner = src_tok[1:-1].strip()
                if inner.upper() in ("$PTREG", "PTREG"):
                    b1 = ((arith_code << 7) | 0b10) & 0xFF
                    return bytes([b0, b1])
                addr16 = self._eval_expr(inner, current_pc, pass_num, line_no, line_text) & 0xFFFF
                b1 = ((arith_code << 7) | 0b11) & 0xFF
                return bytes([b0, b1, addr16 & 0xFF, (addr16 >> 8) & 0xFF])
            else:
                imm16 = self._eval_expr(src_tok, current_pc, pass_num, line_no, line_text) & 0xFFFF
                b1 = ((arith_code << 7) | 0b01) & 0xFF
                return bytes([b0, b1, imm16 & 0xFF, (imm16 >> 8) & 0xFF])

        raise AssemblerError(f"Модификация MSP.{sub_op.lower()} не поддерживается для данного регистра", line_no, line_text)

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

    # 1-байтовые инструкции
    if op == 0:
        return "NOP", 1, [b0]
    if op == 31:
        return "HALT", 1, [b0]
    if op == 30:
        return "RET", 1, [b0]
    if op == 17:
        return f"NOT ${cfg}", 1, [b0]
    if op == 20:
        return f"INC ${cfg}", 1, [b0]
    if op == 21:
        return f"DEC ${cfg}", 1, [b0]

    b1 = read8_fn(addr + 1) & 0xFF
    rd = (b1 >> 5) & 0x07
    rs1 = (b1 >> 2) & 0x07
    rs2 = b1 & 0x03

    # Программное прерывание INT (28)
    if op == 28:
        vec = b1 & 0x0F
        return f"INT {vec}", 2, [b0, b1]

    # 3-операндная арифметика (ADD, SUB, MUL, DIV, MOD)
    alu_names = {1: "ADD", 2: "SUB", 3: "MUL", 4: "DIV", 27: "MOD"}
    if op in alu_names:
        name = alu_names[op]
        if op == 27 or rs2 == 0:
            return f"{name} ${cfg}, ${rd}, ${rs1}", 2, [b0, b1]
        return f"{name} ${rd}, ${rs1}, ${rs2}", 2, [b0, b1]

    # Память: LMR (5) и LRM (6)
    if op in (5, 6):
        name = "LMR" if op == 5 else "LRM"
        mode = (cfg >> 1) & 0x03
        sz = cfg & 0x01
        sfx = ".b" if sz == 0 else ".w"
        if mode == 0:
            if sz == 0:
                imm8 = read8_fn(addr + 2) & 0xFF
                return f"{name}{sfx} ${rd}, 0x{imm8:02X}", 3, [b0, b1, imm8]
            lo = read8_fn(addr + 2) & 0xFF
            hi = read8_fn(addr + 3) & 0xFF
            imm16 = (hi << 8) | lo
            return f"{name}{sfx} ${rd}, 0x{imm16:04X}", 4, [b0, b1, lo, hi]
        if mode == 1:
            p0 = read8_fn(addr + 2) & 0xFF
            p1 = read8_fn(addr + 3) & 0xFF
            p2 = read8_fn(addr + 4) & 0xFF
            p3 = read8_fn(addr + 5) & 0xFF
            ptr32 = p0 | (p1 << 8) | (p2 << 16) | (p3 << 24)
            return f"{name}{sfx} ${rd}, [0x{ptr32:08X}]", 6, [b0, b1, p0, p1, p2, p3]
        if mode == 2:
            return f"{name}{sfx} ${rd}, [$ptreg]", 2, [b0, b1]
        return f"{name}{sfx} ${rd}, [${rd}:${rs1}]", 2, [b0, b1]

    # 2-операндные регистровые (LRR, CMP, AND..XNOR)
    two_reg_names = {
        7: "LRR", 8: "CMP", 13: "AND", 14: "OR", 15: "NAND", 16: "NOR", 18: "XOR", 19: "XNOR"
    }
    if op in two_reg_names:
        return f"{two_reg_names[op]} ${rd}, ${rs1}", 2, [b0, b1]

    # JCR (10): Jump Compare Result (5 байт: [7-3] 10, [2] INV, [1-0] COND, target32 Little-Endian)
    if op == 10:
        b1 = read8_fn(addr + 1) & 0xFF
        b2 = read8_fn(addr + 2) & 0xFF
        b3 = read8_fn(addr + 3) & 0xFF
        b4 = read8_fn(addr + 4) & 0xFF
        target = b1 | (b2 << 8) | (b3 << 16) | (b4 << 24)
        cond_str = JCR_COND_NAME.get(cfg, f"?{cfg}")
        return f"JCR {cond_str}, 0x{target:08X}", 5, [b0, b1, b2, b3, b4]

    # Ветвления и вызовы подпрограмм: JMP (9), JNZ (11), JZ (12), CALL (29) (2..5 байт)
    br_names = {9: "JMP", 11: "JNZ", 12: "JZ", 29: "CALL"}
    if op in br_names:
        name = br_names[op]
        if cfg == 1:
            return f"{name} ${rd}", 2, [b0, b1]
        if cfg == 2:
            return f"{name} [$ptreg]", 2, [b0, b1]
        b1 = read8_fn(addr + 1) & 0xFF
        b2 = read8_fn(addr + 2) & 0xFF
        b3 = read8_fn(addr + 3) & 0xFF
        b4 = read8_fn(addr + 4) & 0xFF
        target = b1 | (b2 << 8) | (b3 << 16) | (b4 << 24)
        if cfg == 3:
            return f"{name} [0x{target:08X}]", 5, [b0, b1, b2, b3, b4]
        return f"{name} 0x{target:08X}", 5, [b0, b1, b2, b3, b4]

    # Стек: PUSH (22), POP (23)
    if op == 22:
        return f"PUSH ${cfg}", 2, [b0, b1]
    if op == 23:
        return f"POP ${cfg}", 2, [b0, b1]

    # Сдвиги: BSL (24), BSR (25)
    if op == 24:
        return f"BSL ${cfg}, {b1}", 2, [b0, b1]
    if op == 25:
        return f"BSR ${cfg}, {b1}", 2, [b0, b1]

    # MSP (26)
    if op == 26:
        act = (cfg >> 2) & 0x01
        sreg_sel = cfg & 0x03
        ext_mode = b1 & 0x03
        sz24 = (b1 >> 2) & 0x01

        if sreg_sel == 3:
            vec_idx = (b1 >> 3) & 0x1F
            v_name = f"$ir{vec_idx}" if vec_idx < 16 else f"$pv{vec_idx - 16}"
            src = (b1 >> 1) & 0x03
            ptr_sub = b1 & 0x01
            if act == 0:
                if src == 0b00:
                    b2 = read8_fn(addr + 2) & 0xFF
                    rd = (b2 >> 5) & 0x07
                    rs = (b2 >> 2) & 0x07
                    return f"MSP.ld {v_name}, [${rd}:${rs}]", 3, [b0, b1, b2]
                elif src == 0b10:
                    return f"MSP.ld {v_name}, [$ptreg]", 2, [b0, b1]
                elif src == 0b01:
                    b2 = read8_fn(addr + 2) & 0xFF
                    b3 = read8_fn(addr + 3) & 0xFF
                    b4 = read8_fn(addr + 4) & 0xFF
                    b5 = read8_fn(addr + 5) & 0xFF
                    v32 = (b5 << 24) | (b4 << 16) | (b3 << 8) | b2
                    return f"MSP.ld {v_name}, 0x{v32:08X}", 6, [b0, b1, b2, b3, b4, b5]
                elif src == 0b11:
                    if ptr_sub == 0:
                        b2 = read8_fn(addr + 2) & 0xFF
                        rd = (b2 >> 5) & 0x07
                        rs = (b2 >> 2) & 0x07
                        return f"MSP.ld {v_name}, [${rd}:${rs}]", 3, [b0, b1, b2]
                    else:
                        b2 = read8_fn(addr + 2) & 0xFF
                        b3 = read8_fn(addr + 3) & 0xFF
                        b4 = read8_fn(addr + 4) & 0xFF
                        b5 = read8_fn(addr + 5) & 0xFF
                        v32 = (b5 << 24) | (b4 << 16) | (b3 << 8) | b2
                        return f"MSP.ld {v_name}, [0x{v32:08X}]", 6, [b0, b1, b2, b3, b4, b5]
            return f"MSP.??? {v_name}", 2, [b0, b1]

        sreg_names = {0: "$freg", 1: "$ptreg", 2: "$sreg"}
        sreg_name = sreg_names.get(sreg_sel, "$ptreg")

        if act == 0:
            if ext_mode == 0:
                if sreg_sel in (1, 2):
                    return f"MSP.ld {sreg_name}, [${rd}:${rs1}]", 2, [b0, b1]
                return f"MSP.ld {sreg_name}, ${rd}", 2, [b0, b1]
            if ext_mode == 2:
                return f"MSP.ld {sreg_name}, [$ptreg]", 2, [b0, b1]
            if ext_mode == 3:
                p0 = read8_fn(addr + 2) & 0xFF
                p1 = read8_fn(addr + 3) & 0xFF
                p2 = read8_fn(addr + 4) & 0xFF
                p3 = read8_fn(addr + 5) & 0xFF
                ptr32 = p0 | (p1 << 8) | (p2 << 16) | (p3 << 24)
                return f"MSP.ld {sreg_name}, [0x{ptr32:08X}]", 6, [b0, b1, p0, p1, p2, p3]
            if ext_mode == 1:
                if sreg_sel in (1, 2):
                    # MSP.ld $ptreg / $sreg обязательно читает 4 байта - 32 бита (Little-Endian)
                    b2 = read8_fn(addr + 2) & 0xFF
                    b3 = read8_fn(addr + 3) & 0xFF
                    b4 = read8_fn(addr + 4) & 0xFF
                    b5 = read8_fn(addr + 5) & 0xFF
                    val32 = (b5 << 24) | (b4 << 16) | (b3 << 8) | b2
                    return f"MSP.ld {sreg_name}, 0x{val32:08X}", 6, [b0, b1, b2, b3, b4, b5]
                lo = read8_fn(addr + 2) & 0xFF
                hi = read8_fn(addr + 3) & 0xFF
                return f"MSP.ld {sreg_name}, 0x{(hi << 8) | lo:04X}", 4, [b0, b1, lo, hi]
        else:
            if sreg_sel == 0:
                l_op = {0: "and", 1: "or", 2: "xor", 3: "xnor"}[(b1 >> 6) & 0x03]
                if ext_mode == 0:
                    rs_m = (b1 >> 3) & 0x07
                    return f"MSP.{l_op} $freg, ${rs_m}", 2, [b0, b1]
                if ext_mode == 2:
                    return f"MSP.{l_op} $freg, [$ptreg]", 2, [b0, b1]
                if ext_mode == 3:
                    p0 = read8_fn(addr + 2) & 0xFF
                    p1 = read8_fn(addr + 3) & 0xFF
                    p2 = read8_fn(addr + 4) & 0xFF
                    p3 = read8_fn(addr + 5) & 0xFF
                    ptr32 = p0 | (p1 << 8) | (p2 << 16) | (p3 << 24)
                    return f"MSP.{l_op} $freg, [0x{ptr32:08X}]", 6, [b0, b1, p0, p1, p2, p3]
                lo = read8_fn(addr + 2) & 0xFF
                hi = read8_fn(addr + 3) & 0xFF
                val16 = (hi << 8) | lo
                return f"MSP.{l_op} $freg, 0x{val16:04X}", 4, [b0, b1, lo, hi]
            else:
                a_op = "add" if ((b1 >> 7) & 0x01) == 0 else "sub"
                if ext_mode == 0:
                    rs_a = (b1 >> 4) & 0x07
                    return f"MSP.{a_op} {sreg_name}, ${rs_a}", 2, [b0, b1]
                if ext_mode == 2:
                    return f"MSP.{a_op} {sreg_name}, [$ptreg]", 2, [b0, b1]
                lo = read8_fn(addr + 2) & 0xFF
                hi = read8_fn(addr + 3) & 0xFF
                val16 = (hi << 8) | lo
                rhs = f"[0x{val16:04X}]" if ext_mode == 3 else f"0x{val16:04X}"
                return f"MSP.{a_op} {sreg_name}, {rhs}", 4, [b0, b1, lo, hi]

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
