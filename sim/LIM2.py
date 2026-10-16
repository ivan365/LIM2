#!/usr/bin/env python3
# ==============================================================================
# LIM2 / sim / lim2_cpu.py — Реализация архитектуры процессора LIM M2
# ==============================================================================
import sys
from pathlib import Path
from typing import Optional

# Автоматически добавляем текущую папку в sys.path для независимого запуска
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from bus import MemoryBus
from core import BaseCPU
try:
    from .devices import RAMDevice, TextScreenDevice, UARTDevice, TimerDevice
except (ImportError, ValueError):
    from devices import RAMDevice, TextScreenDevice, UARTDevice, TimerDevice


class LIM2CPU(BaseCPU):
    """
    Процессор архитектуры LIM M2.
    Полный контроль в чистом Python:
      - 16-битные регистры R0..R7, аккумуляторы ACCA/ACCB
      - 32-битный указатель PTREG и стековый регистр SREG (линейная адресация до 4 ГБ)
      - Пошаговая выборка двух байтов (fetch8) и склейка в 16-битную инструкцию в databus
      - Битовый парсинг: parse("[15-11] [10-8] [7-5] [4-2] [1-0]")
      - Ручная реализация логики инструкций в on_step()
      - Поддержка режима супервизора (PRV=1) и зон привилегий ($pv0..$pv15)
    """

    def __init__(self, name: str = "LIM M2", bus: Optional[MemoryBus] = None):
        super().__init__(name=name, bus=bus, pc_bits=32)

    def setup(self):
        """1. Свободное объявление регистров (имя, разрядность, начальное значение)."""
        # Регистры общего назначения (16 бит каждый)
        for i in range(8):
            self.reg(f"r{i}", bits=16, default=0, indexed=True, title=f"R{i}")

        # Служебные аккумуляторы ALU
        self.reg("acca", bits=16, default=0, title="ACCA", is_acc=True, is_aux=True, block="ALU")
        self.reg("accb", bits=16, default=0, title="ACCB", is_acc=True, is_aux=True, block="ALU")

        # Системный указатель стека SREG (32 бита, формат как PTREG)
        self.reg("sreg", bits=32, default=0, aliases=["sp"], title="SREG", role="Stack 32b", block="SYS")

        # Регистр состояния и флагов FREG (16 бит) с полным битовым лейаутом
        flag_layout = [
            ("ZF", "Zero", 0),
            ("CF", "Carry", 1),
            ("OF", "Overflow", 2),
            ("EM", "ErrMath", 3),
            ("CMP0", "CmpBit0", 4),
            ("CMP1", "CmpBit1", 5),
            ("PIE", "ProgInt", 8),
            ("MIE", "MasterInt", 9),
            ("DWR", "NoWait", 10),
            ("PRV", "Supervisor", 11),
            ("AIP", "AutoInc", 12),
            ("DBIT", "DisplacedBit", 13),
            ("SMOD", "ShiftMode", 14),
            ("INTR", "InInterrupt", 15),
        ]
        self.reg("freg", bits=16, default=0x0800, title="FREG", is_flag=True, flag_layout=flag_layout, block="STATUS")

        # Расширенный 32-битный регистр указателя (до 4 ГБ)
        self.reg("ptreg", bits=32, default=0, title="PTREG", role="Pointer 32b", block="ADDR")

        # Внутренний стек/таблица векторов прерываний и привилегий (32 вектора: 0..15 = IR0..IR15, 16..31 = PV0..PV15)
        self.vectors = [0x00000000] * 32
        self.ivt = self.vectors

    def on_start(self):
        """2. Что процессор делает сразу при старте (сброс регистров, установка PC)."""
        self.pc = 0x00000000
        self.acca = 0
        self.accb = 0
        self.freg = 0x0800  # PRV = 1 (процессор автоматически запускается в режиме супервизора)
        self.ptreg = 0
        self.sreg = 0
        self.vectors = [0x00000000] * 32
        self.ivt = self.vectors
        for i in range(8):
            self.set_reg(i, 0)
        # Синхронизируем режим шины
        if hasattr(self.bus, "set_mode"):
            self.bus.set_mode("32bit")

    def in_privilege_zone(self, pc: Optional[int] = None) -> bool:
        """Проверяет, попадает ли адрес в одну из 8 сконфигурированных зон привилегий ($pv0..$pv15)."""
        addr = self.pc if pc is None else pc
        for i in range(8):
            base = self.vectors[16 + 2 * i]
            limit = self.vectors[16 + 2 * i + 1]
            if base != 0 or limit != 0:
                if base <= addr <= limit:
                    return True
        return False

    def on_step(self):
        """
        3. Выборка, сборка опкода и исполнение инструкции.
        Все операции с программным счетчиком (PC) выполняются ВРУЧНУЮ:
          - Читаем байт из шины: b0 = self.bus.read8(self.pc)
          - Вручную сдвигаем счетчик: self.pc += 1
          - Склеиваем байты в машинное слово в self.databus
        """
        # 1. Пошаговая выборка первого 8-битного байта (октет 0: опкод + конфиг):
        b0 = self.bus.read8(self.pc)
        self.pc += 1
        self.databus = b0

        # [7-3] — Opcode (5 бит), [2-0] — Config / Mode (3 бита в первом байте)
        opcode, cfg = self.parse("[7-3] [2-0]")

        # 0: NOP (1 байт) — пустая операция, второй байт не запрашивается
        if opcode == 0b00000:
            pass

        # 17: NOT Rd (1 байт: Побитовая инверсия, [7-3] опкод, [2-0] Rd)
        elif opcode == 0b10001:
            rd = cfg
            val = self.get_reg(rd)
            res = (~val) & 0xFFFF
            self.set_reg(rd, res)
            self._update_flags(res)

        # 20: INC Rd (1 байт: Инкремент операнда на единицу, [7-3] опкод 10100, [2-0] Rd)
        elif opcode == 0b10100:
            rd = cfg
            val = self.get_reg(rd)
            res = (val + 1) & 0xFFFF
            self.set_reg(rd, res)
            self._update_flags(res)

        # 21: DEC Rd (1 байт: Декремент операнда на единицу, [7-3] опкод 10101, [2-0] Rd)
        elif opcode == 0b10101:
            rd = cfg
            val = self.get_reg(rd)
            res = (val - 1) & 0xFFFF
            self.set_reg(rd, res)
            self._update_flags(res)

        # 28: INTR / SWI vec (1 байт вместо RSV28: [7-3] опкод 11100, [2-0] vec 0..7 из таблицы векторов)
        elif opcode == 0b11100:
            vec = cfg
            # Сохранение 32-битного PC и 16-битного FREG в стек
            self.sreg = (self.sreg - 4) & 0xFFFFFFFF
            self.bus.write32(self.sreg, self.pc & 0xFFFFFFFF)
            self.sreg = (self.sreg - 2) & 0xFFFFFFFF
            self.bus.write16(self.sreg, self.freg & 0xFFFF)
            # Вход в прерывание: PRV=1 (супервизор), INTR=1, сброс MIE=0
            self.freg = (self.freg | (1 << 15) | (1 << 11)) & ~(1 << 9)
            self.pc = self.vectors[vec] & 0xFFFFFFFF

        # 31: HALT (1 байт) — останов процессора
        elif opcode == 0b11111:
            self.halt()

        # 1: ADD Rd, Rs1, Rs2 (2 байта: Rd = Rs1 + Rs2)
        elif opcode == 0b00001:
            self.databus = (self.databus << 8) | self.bus.read8(self.pc)
            self.pc += 1
            cfg, rd, rs1, rs2 = self.parse("[10-8] [7-5] [4-2] [1-0]")
            alu_rd, alu_rs1, alu_rs2 = (cfg, rd, rs1) if (self.databus & 0x03) == 0 else (rd, rs1, rs2)
            val1 = self.get_reg(alu_rs1)
            val2 = self.get_reg(alu_rs2)
            self.acca, self.accb = val1, val2
            res = val1 + val2
            self.set_reg(alu_rd, res & 0xFFFF)
            self._update_flags(res)

        # 2: SUB Rd, Rs1, Rs2 (2 байта: Rd = Rs1 - Rs2)
        elif opcode == 0b00010:
            self.databus = (self.databus << 8) | self.bus.read8(self.pc)
            self.pc += 1
            cfg, rd, rs1, rs2 = self.parse("[10-8] [7-5] [4-2] [1-0]")
            alu_rd, alu_rs1, alu_rs2 = (cfg, rd, rs1) if (self.databus & 0x03) == 0 else (rd, rs1, rs2)
            val1 = self.get_reg(alu_rs1)
            val2 = self.get_reg(alu_rs2)
            self.acca, self.accb = val1, val2
            res = val1 - val2
            self.set_reg(alu_rd, res & 0xFFFF)
            self._update_flags(res)

        # 3: MUL Rd, Rs1, Rs2 (2 байта: Rd = Rs1 * Rs2)
        elif opcode == 0b00011:
            self.databus = (self.databus << 8) | self.bus.read8(self.pc)
            self.pc += 1
            cfg, rd, rs1, rs2 = self.parse("[10-8] [7-5] [4-2] [1-0]")
            alu_rd, alu_rs1, alu_rs2 = (cfg, rd, rs1) if (self.databus & 0x03) == 0 else (rd, rs1, rs2)
            val1 = self.get_reg(alu_rs1)
            val2 = self.get_reg(alu_rs2)
            self.acca, self.accb = val1, val2
            res = val1 * val2
            self.set_reg(alu_rd, res & 0xFFFF)
            self._update_flags(res)

        # 4: DIV Rd, Rs1, Rs2 (2 байта: Rd = Rs1 / Rs2)
        elif opcode == 0b00100:
            self.databus = (self.databus << 8) | self.bus.read8(self.pc)
            self.pc += 1
            cfg, rd, rs1, rs2 = self.parse("[10-8] [7-5] [4-2] [1-0]")
            alu_rd, alu_rs1, alu_rs2 = (cfg, rd, rs1) if (self.databus & 0x03) == 0 else (rd, rs1, rs2)
            val1 = self.get_reg(alu_rs1)
            val2 = self.get_reg(alu_rs2)
            self.acca, self.accb = val1, val2
            if val2 == 0:
                self.freg |= (1 << 3)  # EM: Error Math
                res = 0
            else:
                res = val1 // val2
            self.set_reg(alu_rd, res & 0xFFFF)
            self._update_flags(res)

        # 5: LMR (2..4 байта в зависимости от режима источника SRC и размера SZ)
        elif opcode == 0b00101:
            self.databus = (self.databus << 8) | self.bus.read8(self.pc)
            self.pc += 1
            arg0, arg1, arg3 = self.parse("[10][9][8]")
            src = (arg0 << 1) | arg1
            sz = int(arg3)
            rd = self.parse("[7-5]")

            # Выборка данных по режиму SRC
            if src == 0:  # 0: Непосредственные данные за инструкцией
                if sz == 0:
                    data = self.bus.read8(self.pc)
                    self.pc += 1
                else:
                    d_hi = self.bus.read8(self.pc)
                    self.pc += 1
                    d_lo = self.bus.read8(self.pc)
                    self.pc += 1
                    data = (d_hi << 8) | d_lo
            elif src == 1:  # 1: Непосредственный 16-битный указатель на данные
                p_hi = self.bus.read8(self.pc)
                self.pc += 1
                p_lo = self.bus.read8(self.pc)
                self.pc += 1
                ea = (p_hi << 8) | p_lo
                if sz == 0:
                    data = self.bus.read8(ea)
                else:
                    data = self.bus.read16(ea, little_endian=True)
            elif src == 2:  # 2: Косвенно через системный 32-битный регистр PTREG
                ea = self.ptreg & 0xFFFFFFFF
                if sz == 0:
                    data = self.bus.read8(ea)
                    if self.freg & (1 << 12):  # FREG.AIP автоинкремент
                        self.ptreg = (self.ptreg + 1) & 0xFFFFFFFF
                else:
                    data = self.bus.read16(ea, little_endian=True)
                    if self.freg & (1 << 12):  # FREG.AIP автоинкремент
                        self.ptreg = (self.ptreg + 2) & 0xFFFFFFFF
            elif src == 3:  # 3: Косвенно через пару регистров (32-битный линейный адрес)
                # Arg1 (rd) содержит старшие биты адреса, Arg2 (rs_lo) — младшие 16 бит.
                # При этом Arg1 (rd) одновременно является регистром назначения и перезаписывается данными!
                rs_lo = self.parse("[4-2]")
                addr32 = ((self.get_reg(rd) & 0xFFFF) << 16) | (self.get_reg(rs_lo) & 0xFFFF)
                ea = addr32 & 0xFFFFFFFF
                if sz == 0:
                    data = self.bus.read8(ea)
                else:
                    data = self.bus.read16(ea, little_endian=True)

            # Запись результата в Arg1 (rd): регистр со старшими битами адреса перезаписывается данными!
            if sz == 0:
                self.set_reg(rd, data & 0xFF)
            else:
                self.set_reg(rd, data & 0xFFFF)

        # 6: LRM (Запись данных из регистра в память / вывод: 4 режима DST, размер SZ)
        elif opcode == 0b00110:
            self.databus = (self.databus << 8) | self.bus.read8(self.pc)
            self.pc += 1
            arg0, arg1, arg3 = self.parse("[10][9][8]")
            dst_mode = (arg0 << 1) | arg1
            sz = int(arg3)
            rs = self.parse("[7-5]")

            # Данные для записи из регистра Arg1 (rs):
            val = self.get_reg(rs)

            # Выборка назначения по режиму DST (уничтожение данных — ответственность программиста):
            if dst_mode == 0:  # 0: Непосредственно в память за кодом инструкции
                if sz == 0:
                    self.bus.write8(self.pc, val & 0xFF)
                    self.pc += 1
                else:
                    self.bus.write16(self.pc, val & 0xFFFF)
                    self.pc += 2
            elif dst_mode == 1:  # 1: Непосредственный 16-битный указатель за инструкцией
                p_hi = self.bus.read8(self.pc)
                self.pc += 1
                p_lo = self.bus.read8(self.pc)
                self.pc += 1
                ea = (p_hi << 8) | p_lo
                if sz == 0:
                    self.bus.write8(ea, val & 0xFF)
                else:
                    self.bus.write16(ea, val & 0xFFFF, little_endian=True)
            elif dst_mode == 2:  # 2: Косвенно через системный 32-битный регистр PTREG
                ea = self.ptreg & 0xFFFFFFFF
                if sz == 0:
                    self.bus.write8(ea, val & 0xFF)
                    if self.freg & (1 << 12):  # FREG.AIP автоинкремент
                        self.ptreg = (self.ptreg + 1) & 0xFFFFFFFF
                else:
                    self.bus.write16(ea, val & 0xFFFF, little_endian=True)
                    if self.freg & (1 << 12):  # FREG.AIP автоинкремент
                        self.ptreg = (self.ptreg + 2) & 0xFFFFFFFF
            elif dst_mode == 3:  # 3: Косвенно через пару регистров (32-битный линейный адрес)
                # Arg1 (rs) содержит старшие биты адреса и одновременно является источником данных.
                # Arg2 (rs_lo) задает младшие 16 бит адреса.
                rs_lo = self.parse("[4-2]")
                addr32 = ((val & 0xFFFF) << 16) | (self.get_reg(rs_lo) & 0xFFFF)
                ea = addr32 & 0xFFFFFFFF
                if sz == 0:
                    self.bus.write8(ea, val & 0xFF)
                else:
                    self.bus.write16(ea, val & 0xFFFF, little_endian=True)

        # 7: LRR Rd, Rs (2 байта: Пересылка из регистра Rs в Rd: Rd = Rs, точка А = точка Б)
        elif opcode == 0b00111:
            self.databus = (self.databus << 8) | self.bus.read8(self.pc)
            self.pc += 1
            r0, r1 = self.parse("[7-5] [4-2]")
            rd, rs = (cfg, r0) if (cfg != 0 and (self.databus & 0x1F) == 0) else (r0, r1)
            self.set_reg(rd, self.get_reg(rs))

        # 8: CMP Rs1, Rs2 (2 байта: Аппаратное сравнение операндов без изменения данных)
        elif opcode == 0b01000:
            self.databus = (self.databus << 8) | self.bus.read8(self.pc)
            self.pc += 1
            r0, r1 = self.parse("[7-5] [4-2]")
            rs1, rs2 = (cfg, r0) if (cfg != 0 and (self.databus & 0x1F) == 0) else (r0, r1)
            val1 = self.get_reg(rs1)
            val2 = self.get_reg(rs2)
            self.acca, self.accb = val1, val2
            diff = (val1 - val2) & 0xFFFF
            self.freg &= ~(0b11 << 4)
            if val1 < val2:
                cmp_code = 0b01
            elif val1 == val2:
                cmp_code = 0b10
            elif val1 > val2:
                cmp_code = 0b11
            else:
                cmp_code = 0b00
            self.freg |= (cmp_code << 4)
            self._update_flags(diff)

        # 9..12: Переходы JMP (9), JCR (10), JNZ (11), JZ (12)
        elif opcode in (0b01001, 0b01010, 0b01011, 0b01100):
            b1 = self.bus.read8(self.pc)
            self.pc += 1
            self.databus = (self.databus << 8) | b1
            rd = self.parse("[7-5]")
            if cfg == 1:
                target = self.get_reg(rd)
            elif cfg == 2:
                target = self.ptreg & 0xFFFFFFFF
            elif cfg == 3:
                tgt_hi = b1
                tgt_lo = self.bus.read8(self.pc)
                self.pc += 1
                ptr16 = (tgt_hi << 8) | tgt_lo
                target = self.bus.read16(ptr16, little_endian=True)
            else:
                tgt_hi = b1
                tgt_lo = self.bus.read8(self.pc)
                self.pc += 1
                target = (tgt_hi << 8) | tgt_lo

            if opcode == 0b01001:    # JMP
                self.pc = target
            elif opcode == 0b01010:  # JCR (CF == 1)
                if (self.freg & 0x02) != 0:
                    self.pc = target
            elif opcode == 0b01011:  # JNZ (ZF == 0)
                if (self.freg & 0x01) == 0:
                    self.pc = target
            elif opcode == 0b01100:  # JZ (ZF == 1)
                if (self.freg & 0x01) != 0:
                    self.pc = target

        # 13: AND Rd, Rs (2 байта: Rd = Rd & Rs)
        elif opcode == 0b01101:
            self.databus = (self.databus << 8) | self.bus.read8(self.pc)
            self.pc += 1
            r0, r1 = self.parse("[7-5] [4-2]")
            rd, rs = (cfg, r0) if (cfg != 0 and (self.databus & 0x1F) == 0) else (r0, r1)
            res = self.get_reg(rd) & self.get_reg(rs)
            self.set_reg(rd, res)
            self._update_flags(res)

        # 14: OR Rd, Rs (2 байта: Rd = Rd | Rs)
        elif opcode == 0b01110:
            self.databus = (self.databus << 8) | self.bus.read8(self.pc)
            self.pc += 1
            r0, r1 = self.parse("[7-5] [4-2]")
            rd, rs = (cfg, r0) if (cfg != 0 and (self.databus & 0x1F) == 0) else (r0, r1)
            res = self.get_reg(rd) | self.get_reg(rs)
            self.set_reg(rd, res)
            self._update_flags(res)

        # 15: NAND Rd, Rs (2 байта: Rd = ~(Rd & Rs))
        elif opcode == 0b01111:
            self.databus = (self.databus << 8) | self.bus.read8(self.pc)
            self.pc += 1
            r0, r1 = self.parse("[7-5] [4-2]")
            rd, rs = (cfg, r0) if (cfg != 0 and (self.databus & 0x1F) == 0) else (r0, r1)
            res = (~(self.get_reg(rd) & self.get_reg(rs))) & 0xFFFF
            self.set_reg(rd, res)
            self._update_flags(res)

        # 16: NOR Rd, Rs (2 байта: Rd = ~(Rd | Rs))
        elif opcode == 0b10000:
            self.databus = (self.databus << 8) | self.bus.read8(self.pc)
            self.pc += 1
            r0, r1 = self.parse("[7-5] [4-2]")
            rd, rs = (cfg, r0) if (cfg != 0 and (self.databus & 0x1F) == 0) else (r0, r1)
            res = (~(self.get_reg(rd) | self.get_reg(rs))) & 0xFFFF
            self.set_reg(rd, res)
            self._update_flags(res)

        # 18: XOR Rd, Rs (2 байта: Rd = Rd ^ Rs)
        elif opcode == 0b10010:
            self.databus = (self.databus << 8) | self.bus.read8(self.pc)
            self.pc += 1
            r0, r1 = self.parse("[7-5] [4-2]")
            rd, rs = (cfg, r0) if (cfg != 0 and (self.databus & 0x1F) == 0) else (r0, r1)
            res = (self.get_reg(rd) ^ self.get_reg(rs)) & 0xFFFF
            self.set_reg(rd, res)
            self._update_flags(res)

        # 19: XNOR Rd, Rs (2 байта: Rd = ~(Rd ^ Rs))
        elif opcode == 0b10011:
            self.databus = (self.databus << 8) | self.bus.read8(self.pc)
            self.pc += 1
            r0, r1 = self.parse("[7-5] [4-2]")
            rd, rs = (cfg, r0) if (cfg != 0 and (self.databus & 0x1F) == 0) else (r0, r1)
            res = (~(self.get_reg(rd) ^ self.get_reg(rs))) & 0xFFFF
            self.set_reg(rd, res)
            self._update_flags(res)

        # 24: BSL Rd, shift (Итеративный аппаратный сдвиг влево: [15-11] 11000, [10-8] Rd, [7-0] shift)
        # В железе: аппаратный цикл сдвигового регистра из 16 D-триггеров (~300 транзисторов вместо ~30 000).
        # Сдвиг на N бит занимает ровно N тактов (сдвиг на 16 бит занимает на 15 тактов больше сдвига на 1 бит).
        elif opcode == 0b11000:
            self.databus = (self.databus << 8) | self.bus.read8(self.pc)
            self.pc += 1
            rd = (self.databus >> 8) & 0x07
            shift = self.databus & 0xFF
            val = self.get_reg(rd) & 0xFFFF
            smod = (self.freg >> 14) & 1
            dbit = (self.freg >> 13) & 1
            fill_bit = dbit
            last_displaced = dbit

            # Симуляция физического 16-битного регистра сдвига (цепочка триггеров [b0..b15])
            reg_bits = [(val >> i) & 1 for i in range(16)]

            # Аппаратный тактовый цикл: каждый шаг сдвигает регистр на 1 бит за 1 такт
            for _ in range(shift):
                if hasattr(self, "cycles"):
                    self.cycles += 1

                # Вытесняемый старший бит (выход 15-го триггера)
                last_displaced = reg_bits[15]

                # Входной бит в младший триггер:
                # - При SMOD=1 (кольцевой режим) влетает вытесненный бит 15
                # - При SMOD=0 (направленный режим) влетает бит из DBIT (0 или 1)
                in_bit = last_displaced if smod == 1 else fill_bit

                # Физический такт сдвига триггеров влево (b[i] <- b[i-1])
                for i in range(15, 0, -1):
                    reg_bits[i] = reg_bits[i - 1]
                reg_bits[0] = in_bit

            # Сборка 16-битного слова из триггеров регистра
            val = 0
            for i in range(16):
                val |= (reg_bits[i] << i)

            if shift > 0:
                self.freg = (self.freg & ~(1 << 13)) | (last_displaced << 13)

            self.set_reg(rd, val)
            self._update_flags(val)

        # 25: BSR Rd, shift (Итеративный аппаратный сдвиг вправо: [15-11] 11001, [10-8] Rd, [7-0] shift)
        # В железе: аппаратный цикл сдвигового регистра из 16 D-триггеров (~300 транзисторов вместо ~30 000).
        # Сдвиг на N бит занимает ровно N тактов (сдвиг на 16 бит занимает на 15 тактов больше сдвига на 1 бит).
        elif opcode == 0b11001:
            self.databus = (self.databus << 8) | self.bus.read8(self.pc)
            self.pc += 1
            rd = (self.databus >> 8) & 0x07
            shift = self.databus & 0xFF
            val = self.get_reg(rd) & 0xFFFF
            smod = (self.freg >> 14) & 1
            dbit = (self.freg >> 13) & 1
            fill_bit = dbit
            last_displaced = dbit

            # Симуляция физического 16-битного регистра сдвига (цепочка триггеров [b0..b15])
            reg_bits = [(val >> i) & 1 for i in range(16)]

            # Аппаратный тактовый цикл: каждый шаг сдвигает регистр на 1 бит за 1 такт
            for _ in range(shift):
                if hasattr(self, "cycles"):
                    self.cycles += 1

                # Вытесняемый младший бит (выход 0-го триггера)
                last_displaced = reg_bits[0]

                # Входной бит в старший триггер:
                # - При SMOD=1 (кольцевой режим) влетает вытесненный бит 0
                # - При SMOD=0 (направленный режим) влетает бит из DBIT (0 или 1)
                in_bit = last_displaced if smod == 1 else fill_bit

                # Физический такт сдвига триггеров вправо (b[i] <- b[i+1])
                for i in range(0, 15):
                    reg_bits[i] = reg_bits[i + 1]
                reg_bits[15] = in_bit

            # Сборка 16-битного слова из триггеров регистра
            val = 0
            for i in range(16):
                val |= (reg_bits[i] << i)

            if shift > 0:
                self.freg = (self.freg & ~(1 << 13)) | (last_displaced << 13)

            self.set_reg(rd, val)
            self._update_flags(val)

        # 22: PUSH Rs (2 байта: SREG -= 2, MEM[SREG] <- Rs; Октет 0: [7-3]=10110, [2-0]=Rs)
        elif opcode == 0b10110:
            self.databus = (self.databus << 8) | self.bus.read8(self.pc)
            self.pc += 1
            rs = (self.databus >> 8) & 0x07
            val = self.get_reg(rs) & 0xFFFF
            self.sreg = (self.sreg - 2) & 0xFFFFFFFF
            self.bus.write16(self.sreg, val)

        # 23: POP Rd (2 байта: Rd <- MEM[SREG], SREG += 2; Октет 0: [7-3]=10111, [2-0]=Rd)
        elif opcode == 0b10111:
            self.databus = (self.databus << 8) | self.bus.read8(self.pc)
            self.pc += 1
            rd = (self.databus >> 8) & 0x07
            val = self.bus.read16(self.sreg) & 0xFFFF
            self.sreg = (self.sreg + 2) & 0xFFFFFFFF
            self.set_reg(rd, val)

        # 26: MSP (Opcode 11010 / 0x1A: Манипуляция специальными регистрами FREG, PTREG, SREG, VECTORS)
        elif opcode == 0b11010:
            self.databus = (self.databus << 8) | self.bus.read8(self.pc)
            self.pc += 1
            act = (self.databus >> 10) & 0x01
            sreg_sel = (self.databus >> 8) & 0x03
            ext_mode = self.databus & 0x03
            sz24 = ((self.databus >> 2) & 0x01) or ((self.freg >> 11) & 0x01)

            def _fetch_msp_ext(force_32: bool = False) -> int:
                use_32 = force_32 or bool(sz24)
                if ext_mode == 1:  # Непосредственное значение за инструкцией
                    if use_32 and (self.databus & 0x04):
                        b2 = self.bus.read8(self.pc)
                        b1_imm = self.bus.read8(self.pc + 1)
                        b0_imm = self.bus.read8(self.pc + 2)
                        self.pc += 3
                        return (b2 << 16) | (b1_imm << 8) | b0_imm
                    b_hi = self.bus.read8(self.pc)
                    b_lo = self.bus.read8(self.pc + 1)
                    self.pc += 2
                    return (b_hi << 8) | b_lo
                elif ext_mode == 2:  # Разыменование [$ptreg]: MEM[PTREG]
                    ea = self.ptreg & 0xFFFFFFFF
                    if use_32:
                        return (
                            self.bus.read8(ea)
                            | (self.bus.read8((ea + 1) & 0xFFFFFFFF) << 8)
                            | (self.bus.read8((ea + 2) & 0xFFFFFFFF) << 16)
                            | (self.bus.read8((ea + 3) & 0xFFFFFFFF) << 24)
                        )
                    return self.bus.read16(ea, little_endian=True)
                elif ext_mode == 3:  # Разыменование [addr16]: MEM[addr16]
                    p_hi = self.bus.read8(self.pc)
                    p_lo = self.bus.read8(self.pc + 1)
                    self.pc += 2
                    ea = (p_hi << 8) | p_lo
                    if use_32:
                        return (
                            self.bus.read8(ea)
                            | (self.bus.read8((ea + 1) & 0xFFFFFFFF) << 8)
                            | (self.bus.read8((ea + 2) & 0xFFFFFFFF) << 16)
                            | (self.bus.read8((ea + 3) & 0xFFFFFFFF) << 24)
                        )
                    return self.bus.read16(ea, little_endian=True)
                return 0

            if act == 0:
                # --- LOAD MODE (Прямая запись / MSP.ld) ---
                if sreg_sel == 0:  # FREG
                    if ext_mode == 0:
                        rs = (self.databus >> 5) & 0x07
                        new_freg = self.get_reg(rs) & 0xFFFF
                    else:
                        new_freg = _fetch_msp_ext(False) & 0xFFFF
                    # Контроль прав режима супервизора (PRV = бит 11):
                    # Если процессор в пользовательском режиме (PRV == 0) пытается поднять PRV == 1,
                    # это допустимо ТОЛЬКО внутри зоны высоких привилегий!
                    cur_prv = (self.freg >> 11) & 1
                    target_prv = (new_freg >> 11) & 1
                    if cur_prv == 0 and target_prv == 1:
                        if not self.in_privilege_zone():
                            new_freg &= ~(1 << 11)  # Запрет несанкционированного повышения
                    self.freg = new_freg

                elif sreg_sel == 1:  # PTREG (32 бита)
                    if ext_mode == 0:
                        rs_hi = (self.databus >> 5) & 0x07
                        rs_lo = (self.databus >> 2) & 0x07
                        val_hi = self.get_reg(rs_hi)
                        val_lo = self.get_reg(rs_lo)
                        self.ptreg = ((val_hi << 16) | val_lo) & 0xFFFFFFFF
                    else:
                        self.ptreg = _fetch_msp_ext(False) & 0xFFFFFFFF

                elif sreg_sel == 2:  # SREG (32 бита, формат как PTREG)
                    if ext_mode == 0:
                        rs_hi = (self.databus >> 5) & 0x07
                        rs_lo = (self.databus >> 2) & 0x07
                        val_hi = self.get_reg(rs_hi)
                        val_lo = self.get_reg(rs_lo)
                        self.sreg = ((val_hi << 16) | val_lo) & 0xFFFFFFFF
                    else:
                        self.sreg = _fetch_msp_ext(False) & 0xFFFFFFFF

                elif sreg_sel == 3:  # VECTORS (32 регистра: $ir0..$ir15, $pv0..$pv15)
                    b1_val = self.databus & 0xFF
                    idx = (b1_val >> 3) & 0x1F
                    src_mode = (b1_val >> 1) & 0x03
                    bit0 = b1_val & 0x01

                    if src_mode == 0:  # 00: Пара регистров GPR
                        b2 = self.bus.read8(self.pc)
                        self.pc += 1
                        rd_hi = (b2 >> 5) & 0x07
                        rs_lo = (b2 >> 2) & 0x07
                        val = ((self.get_reg(rd_hi) & 0xFFFF) << 16) | (self.get_reg(rs_lo) & 0xFFFF)
                    elif src_mode == 1:  # 01: imm32 (4 байта)
                        b3 = self.bus.read8(self.pc)
                        b2 = self.bus.read8(self.pc + 1)
                        b1_imm = self.bus.read8(self.pc + 2)
                        b0_imm = self.bus.read8(self.pc + 3)
                        self.pc += 4
                        val = (b3 << 24) | (b2 << 16) | (b1_imm << 8) | b0_imm
                    elif src_mode == 2:  # 10: [$ptreg] (разыменование PTREG)
                        ea = self.ptreg & 0xFFFFFFFF
                        val = self.bus.read32(ea, little_endian=False)
                    else:  # 11: [$rd:$rs] (bit0==0) или [addr32] (bit0==1)
                        if bit0 == 0:
                            b2 = self.bus.read8(self.pc)
                            self.pc += 1
                            rd_hi = (b2 >> 5) & 0x07
                            rs_lo = (b2 >> 2) & 0x07
                            ea = (((self.get_reg(rd_hi) & 0xFFFF) << 16) | (self.get_reg(rs_lo) & 0xFFFF)) & 0xFFFFFFFF
                            val = self.bus.read32(ea, little_endian=False)
                        else:
                            a3 = self.bus.read8(self.pc)
                            a2 = self.bus.read8(self.pc + 1)
                            a1 = self.bus.read8(self.pc + 2)
                            a0 = self.bus.read8(self.pc + 3)
                            self.pc += 4
                            ea = ((a3 << 24) | (a2 << 16) | (a1 << 8) | a0) & 0xFFFFFFFF
                            val = self.bus.read32(ea, little_endian=False)

                    # Защита зон привилегий ($pv0..$pv15, idx >= 16):
                    # Модификация $pv разрешена только в режиме супервизора (PRV == 1)
                    # ЛИБО если текущий PC исполняется внутри одной из зон привилегий!
                    cur_prv = (self.freg >> 11) & 1
                    if idx >= 16 and cur_prv == 0 and not self.in_privilege_zone():
                        pass  # Блокировка записи в $pv вне зон привилегий
                    else:
                        self.vectors[idx] = val & 0xFFFFFFFF

            else:
                # --- OPERATE MODE (Операции) ---
                if sreg_sel == 0:  # Логика над FREG: AND, OR, XOR, XNOR
                    logic_op = (self.databus >> 6) & 0x03
                    if ext_mode == 0:
                        rs = (self.databus >> 3) & 0x07
                        mask = self.get_reg(rs) & 0xFFFF
                    else:
                        mask = _fetch_msp_ext(False) & 0xFFFF
                    if logic_op == 0:    # AND
                        new_freg = self.freg & mask
                    elif logic_op == 1:  # OR
                        new_freg = self.freg | mask
                    elif logic_op == 2:  # XOR
                        new_freg = self.freg ^ mask
                    elif logic_op == 3:  # XNOR
                        new_freg = ~(self.freg ^ mask) & 0xFFFF

                    # Контроль прав на бит PRV (бит 11):
                    cur_prv = (self.freg >> 11) & 1
                    target_prv = (new_freg >> 11) & 1
                    if cur_prv == 0 and target_prv == 1:
                        if not self.in_privilege_zone():
                            new_freg &= ~(1 << 11)
                    self.freg = new_freg

                elif sreg_sel == 1:  # Арифметика над PTREG: ADD / SUB
                    arith_op = (self.databus >> 7) & 0x01
                    if ext_mode == 0:
                        rs = (self.databus >> 4) & 0x07
                        offset = self.get_reg(rs) & 0xFFFF
                    else:
                        offset = _fetch_msp_ext(False) & 0xFFFFFFFF
                    if arith_op == 0:    # ADD
                        new_val = self.ptreg + offset
                    else:                # SUB
                        new_val = self.ptreg - offset
                    cf = 1 if (new_val > 0xFFFFFFFF or new_val < 0) else 0
                    self.freg = (self.freg & ~0x02) | (cf << 1)
                    self.ptreg = new_val & 0xFFFFFFFF

                elif sreg_sel == 2:  # Арифметика над SREG: ADD / SUB (формат как PTREG)
                    arith_op = (self.databus >> 7) & 0x01
                    if ext_mode == 0:
                        rs = (self.databus >> 4) & 0x07
                        offset = self.get_reg(rs) & 0xFFFF
                    else:
                        offset = _fetch_msp_ext(False) & 0xFFFFFFFF
                    if arith_op == 0:    # ADD
                        new_val = self.sreg + offset
                    else:                # SUB
                        new_val = self.sreg - offset
                    cf = 1 if (new_val > 0xFFFFFFFF or new_val < 0) else 0
                    self.freg = (self.freg & ~0x02) | (cf << 1)
                    self.sreg = new_val & 0xFFFFFFFF

        # 27: MOD Rd, Rs1, Rs2 (2 байта: Rd = Rs1 % Rs2)
        elif opcode == 0b11011:
            self.databus = (self.databus << 8) | self.bus.read8(self.pc)
            self.pc += 1
            rd_mod, rs1_mod, rs2_mod = self.parse("[10-8] [7-5] [4-2]")
            val1 = self.get_reg(rs1_mod)
            val2 = self.get_reg(rs2_mod)
            self.acca, self.accb = val1, val2
            if val2 == 0:
                self.freg |= (1 << 3)  # EM: Error Math
                res = 0
            else:
                res = val1 % val2
            self.set_reg(rd_mod, res & 0xFFFF)
            self._update_flags(res)


    def _update_flags(self, result: int):
        """Обновляет Zero Flag (бит 0) в FREG."""
        zf = 1 if (result & 0xFFFF) == 0 else 0
        self.freg = (self.freg & ~0x01) | zf


def configure_default_platform(bus: MemoryBus):
    """Базовая конфигурация периферии и памяти LIM2 по умолчанию прямо в коде."""
    # ОЗУ 16 КБ: 0x0000..0x3FFF
    bus.attach(RAMDevice(start=0x0000, end=0x3FFF, name="RAM"))
    # Текстовый видеомонитор 20x4: 0x8000..0x804F
    bus.attach(TextScreenDevice(start=0x8000, width=20, height=4, name="MONITOR"))
    # Последовательный порт UART: 0xF000..0xF003
    bus.attach(UARTDevice(start=0xF000, name="UART0"))
    # Аппаратный таймер с генерацией IRQ: 0xF010..0xF013
    bus.attach(TimerDevice(start=0xF010, name="TIMER0", irq_pin="IRQ"))


def create_lim2_cpu(bus: Optional[MemoryBus] = None) -> LIM2CPU:
    """Фабричная функция создания процессора LIM M2."""
    b = bus if bus is not None else MemoryBus()
    cpu = LIM2CPU(name="LIM M2", bus=b)
    return cpu
