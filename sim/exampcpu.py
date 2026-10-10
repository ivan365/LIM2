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
      - 16-битные регистры R0..R7, аккумуляторы ACCA/ACCB, 24-битный указатель PTREG
      - Пошаговая выборка двух байтов (fetch8) и склейка в 16-битную инструкцию в databus
      - Битовый парсинг: parse("[15-11] [10-8] [7-5] [4-2] [1-0]")
      - Ручная реализация логики инструкций в on_step()
    """

    def setup(self):
        """1. Свободное объявление регистров (имя, разрядность, начальное значение)."""
        # Регистры общего назначения (16 бит каждый)
        for i in range(8):
            self.reg(f"r{i}", bits=16, default=0, indexed=True, title=f"R{i}")

        # Служебные аккумуляторы ALU
        self.reg("acca", bits=16, default=0, title="ACCA", is_acc=True, is_aux=True, block="ALU")
        self.reg("accb", bits=16, default=0, title="ACCB", is_acc=True, is_aux=True, block="ALU")

        # Системный стек / статус (24 бита)
        self.reg("sreg", bits=24, default=0, title="SREG", role="Stack 24b", block="SYS")

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
            ("M24", "24-bit Mode", 11),
            ("AIP", "AutoInc", 12),
            ("DBIT", "DisplacedBit", 13),
            ("SMOD", "ShiftMode", 14),
            ("INTR", "InInterrupt", 15),
        ]
        self.reg("freg", bits=16, default=0, title="FREG", is_flag=True, flag_layout=flag_layout, block="STATUS")

        # Расширенный 24-битный регистр указателя (до 16 МБ)
        self.reg("ptreg", bits=24, default=0, title="PTREG", role="Pointer 24b", block="ADDR")

    def on_start(self):
        """2. Что процессор делает сразу при старте (сброс регистров, установка PC)."""
        self.pc = 0x0000
        self.acca = 0
        self.accb = 0
        self.freg = 0
        self.ptreg = 0
        for i in range(8):
            self.set_reg(i, 0)
        # Синхронизируем режим шины
        if hasattr(self.bus, "set_mode"):
            self.bus.set_mode("16bit")

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
        opcode = self.parse("[7-3]")
        cfg = self.parse("[2-0]")

        # ----------------------------------------------------------------------
        # ЛОГИКА ОПКОДОВ:
        # ----------------------------------------------------------------------

        # 0: NOP — Нет операции (1-байтовая инструкция, второй байт не запрашивается)
        if opcode == 0:
            return

        # 31: HALT — Останов процессора (1-байтовая инструкция)
        if opcode == 31:
            self.halt()
            return

        # 17: NOT Rd — Побитовая инверсия (1-байтовая инструкция: [7-3] опкод, [2-0] регистр Rd)
        if opcode == 17:
            rd = cfg
            val = self.get_reg(rd)
            res = (~val) & 0xFFFF
            self.set_reg(rd, res)
            self._update_flags(res)
            return

        # 20: INC Rd — Инкремент операнда на единицу (1-байтовая инструкция: [7-3] опкод 10100, [2-0] регистр Rd)
        if opcode == 20:
            rd = cfg
            val = self.get_reg(rd)
            res = (val + 1) & 0xFFFF
            self.set_reg(rd, res)
            self._update_flags(res)
            return

        # 21: DEC Rd — Декремент операнда на единицу (1-байтовая инструкция: [7-3] опкод 10101, [2-0] регистр Rd)
        if opcode == 21:
            rd = cfg
            val = self.get_reg(rd)
            res = (val - 1) & 0xFFFF
            self.set_reg(rd, res)
            self._update_flags(res)
            return

        # Для 2-байтовых (и более) инструкций дочитываем второй байт (октет 1: аргументы):
        b1 = self.bus.read8(self.pc)
        self.pc += 1
        self.databus = (self.databus << 8) | b1
        cfg, rd, rs1, rs2 = self.parse("[10-8] [7-5] [4-2] [1-0]")

        # 1: ADD Rd, Rs1, Rs2 (Rd = Rs1 + Rs2)
        if opcode == 1:
            val1 = self.get_reg(rs1)
            val2 = self.get_reg(rs2)
            self.acca, self.accb = val1, val2
            res = val1 + val2
            self.set_reg(rd, res)
            self._update_flags(res)

        # 2: SUB Rd, Rs1, Rs2 (Rd = Rs1 - Rs2)
        elif opcode == 2:
            val1 = self.get_reg(rs1)
            val2 = self.get_reg(rs2)
            self.acca, self.accb = val1, val2
            res = val1 - val2
            self.set_reg(rd, res)
            self._update_flags(res)

        # 3: MUL Rd, Rs1, Rs2 (Rd = Rs1 * Rs2)
        elif opcode == 3:
            val1 = self.get_reg(rs1)
            val2 = self.get_reg(rs2)
            self.acca, self.accb = val1, val2
            res = val1 * val2
            self.set_reg(rd, res)
            self._update_flags(res)

        # 4: DIV Rd, Rs1, Rs2
        elif opcode == 4:
            val1 = self.get_reg(rs1)
            val2 = self.get_reg(rs2)
            self.acca, self.accb = val1, val2
            res = (val1 // val2) if val2 != 0 else 0
            self.set_reg(rd, res)
            self._update_flags(res)

        # 5: LMR Rd, ... (Загрузка данных из памяти/ввода в регистры: src_mode 0-3, sz 8/16-bit)
        elif opcode == 5:
            src_mode, sz, rd, rs_lo = self.parse("[10-9] [8] [7-5] [4-2]")
            if src_mode == 0:
                # 0 = Непосредственные данные сразу за кодом команды
                if sz == 0:
                    val = self.bus.read8(self.pc)
                    self.pc += 1
                else:
                    b_hi = self.bus.read8(self.pc)
                    b_lo = self.bus.read8(self.pc + 1)
                    self.pc += 2
                    val = (b_hi << 8) | b_lo
                self.set_reg(rd, val)
            elif src_mode == 1:
                # 1 = Непосредственный указатель сразу за инструкцией
                p_hi = self.bus.read8(self.pc)
                p_lo = self.bus.read8(self.pc + 1)
                self.pc += 2
                ptr = (p_hi << 8) | p_lo
                val = self.bus.read8(ptr) if sz == 0 else self.bus.read16(ptr)
                self.set_reg(rd, val)
            elif src_mode == 2:
                # 2 = Косвенно через 24-битный указатель PTREG
                val = self.bus.read8(self.ptreg) if sz == 0 else self.bus.read16(self.ptreg)
                if (self.freg & (1 << 12)):  # AIP: автоинкремент указателя
                    self.ptreg = (self.ptreg + (1 if sz == 0 else 2)) & 0xFFFFFF
                self.set_reg(rd, val)
            elif src_mode == 3:
                # 3 = Косвенно через пару регистров: Rd (старшие биты) : Rs_lo (младшие биты) -> 32-бит, адрес 24-бит.
                # При этом Rd (старшие биты) перезаписывается загруженными данными!
                addr32 = ((self.get_reg(rd) & 0xFFFF) << 16) | (self.get_reg(rs_lo) & 0xFFFF)
                ea = addr32 & 0xFFFFFF
                val = self.bus.read8(ea) if sz == 0 else self.bus.read16(ea)
                self.set_reg(rd, val)

        # 6: LRM Rs, ... (Запись данных из регистра в память/вывод: dst_mode 0-3, sz 8/16-bit)
        elif opcode == 6:
            dst_mode, sz, rs, rs_lo = self.parse("[10-9] [8] [7-5] [4-2]")
            val = self.get_reg(rs)
            if dst_mode == 0:
                # 0 = Непосредственно в память сразу за кодом команды (самомодифицирующийся код / буфер)
                if sz == 0:
                    self.bus.write8(self.pc, val & 0xFF)
                    self.pc += 1
                else:
                    self.bus.write16(self.pc, val & 0xFFFF)
                    self.pc += 2
            elif dst_mode == 1:
                # 1 = Непосредственный 16-битный указатель сразу за инструкцией
                p_hi = self.bus.read8(self.pc)
                p_lo = self.bus.read8(self.pc + 1)
                self.pc += 2
                ptr = (p_hi << 8) | p_lo
                if sz == 0:
                    self.bus.write8(ptr, val & 0xFF)
                else:
                    self.bus.write16(ptr, val & 0xFFFF)
            elif dst_mode == 2:
                # 2 = Косвенно через 24-битный указатель PTREG
                ea = self.ptreg & 0xFFFFFF
                if sz == 0:
                    self.bus.write8(ea, val & 0xFF)
                    if (self.freg & (1 << 12)):  # AIP: автоинкремент указателя
                        self.ptreg = (self.ptreg + 1) & 0xFFFFFF
                else:
                    self.bus.write16(ea, val & 0xFFFF)
                    if (self.freg & (1 << 12)):  # AIP: автоинкремент указателя
                        self.ptreg = (self.ptreg + 2) & 0xFFFFFF
            elif dst_mode == 3:
                # 3 = Косвенно через пару регистров: Rs (старшие биты) : Rs_lo (младшие биты) -> 32-бит, адрес 24-бит.
                # Уничтожение данных в целевой памяти — ответственность программиста.
                addr32 = ((val & 0xFFFF) << 16) | (self.get_reg(rs_lo) & 0xFFFF)
                ea = addr32 & 0xFFFFFF
                if sz == 0:
                    self.bus.write8(ea, val & 0xFF)
                else:
                    self.bus.write16(ea, val & 0xFFFF)


        # 7: LRR Rd, Rs (Пересылка из регистра Rs в Rd: Rd = Rs, точка А = точка Б)
        elif opcode == 7:
            rd, rs = self.parse("[7-5] [4-2]")
            self.set_reg(rd, self.get_reg(rs))

        # 8: CMP Rs1, Rs2 (Аппаратное сравнение операндов)
        elif opcode == 8:
            rs1, rs2 = self.parse("[7-5] [4-2]")
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


        # 13 (и 9): AND Rd, Rs (Rd = Rd & Rs)
        elif opcode in (9, 13):
            res = self.get_reg(rd) & self.get_reg(rs1)
            self.set_reg(rd, res)
            self._update_flags(res)

        # 14 (и 10): OR Rd, Rs (Rd = Rd | Rs)
        elif opcode in (10, 14):
            res = self.get_reg(rd) | self.get_reg(rs1)
            self.set_reg(rd, res)
            self._update_flags(res)

        # 15: NAND Rd, Rs (Rd = ~(Rd & Rs))
        elif opcode == 15:
            res = (~(self.get_reg(rd) & self.get_reg(rs1))) & 0xFFFF
            self.set_reg(rd, res)
            self._update_flags(res)

        # 16: NOR Rd, Rs (Rd = ~(Rd | Rs))
        elif opcode == 16:
            res = (~(self.get_reg(rd) | self.get_reg(rs1))) & 0xFFFF
            self.set_reg(rd, res)
            self._update_flags(res)

        # 18 (и 11): XOR Rd, Rs (Rd = Rd ^ Rs)
        elif opcode in (11, 18):
            res = (self.get_reg(rd) ^ self.get_reg(rs1)) & 0xFFFF
            self.set_reg(rd, res)
            self._update_flags(res)

        # 19: XNOR Rd, Rs (Rd = ~(Rd ^ Rs))
        elif opcode == 19:
            res = (~(self.get_reg(rd) ^ self.get_reg(rs1))) & 0xFFFF
            self.set_reg(rd, res)
            self._update_flags(res)

        # 12: JMP target (Безусловный переход: прямая установка self.pc)
        elif opcode == 12:
            if cfg == 1:
                target = self.get_reg(rd)
            else:
                tgt_hi = self.bus.read8(self.pc)
                self.pc += 1
                tgt_lo = self.bus.read8(self.pc)
                self.pc += 1
                target = (tgt_hi << 8) | tgt_lo
            self.pc = target

        # 13: JZ target (Переход если Zero Flag == 1)
        elif opcode == 13:
            tgt_hi = self.bus.read8(self.pc)
            self.pc += 1
            tgt_lo = self.bus.read8(self.pc)
            self.pc += 1
            target = (tgt_hi << 8) | tgt_lo
            if (self.freg & 0x01) != 0:
                self.pc = target

        # 14: JNZ target (Переход если Zero Flag == 0)
        elif opcode == 14:
            tgt_hi = self.bus.read8(self.pc)
            self.pc += 1
            tgt_lo = self.bus.read8(self.pc)
            self.pc += 1
            target = (tgt_hi << 8) | tgt_lo
            if (self.freg & 0x01) == 0:
                self.pc = target
        # 24: BSL Rd, shift (Итеративный аппаратный сдвиг влево: [15-11] 11000, [10-8] Rd, [7-0] shift)
        # В железе: аппаратный цикл сдвигового регистра из 16 D-триггеров (~300 транзисторов вместо ~30 000).
        # Сдвиг на N бит занимает ровно N тактов (сдвиг на 16 бит занимает на 15 тактов больше сдвига на 1 бит).
        elif opcode == 24:
            rd = cfg
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
        elif opcode == 25:
            rd = cfg
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

        # 26: MSP (Opcode 11010 / 0x1A: Манипуляция специальными регистрами FREG, PTREG)
        elif opcode == 26:
            act = (self.databus >> 10) & 0x01
            sreg_sel = (self.databus >> 8) & 0x03

            if act == 0:
                # --- LOAD MODE (Прямая запись) ---
                if sreg_sel == 0:  # FREG <- Rs
                    rs = (self.databus >> 5) & 0x07
                    self.freg = self.get_reg(rs) & 0xFFFF
                elif sreg_sel == 1:  # PTREG <- (Rs_hi << 16) | Rs_lo
                    rs_hi = (self.databus >> 5) & 0x07
                    rs_lo = (self.databus >> 2) & 0x07
                    val_hi = self.get_reg(rs_hi)
                    val_lo = self.get_reg(rs_lo)
                    self.ptreg = ((val_hi << 16) | val_lo) & 0xFFFFFF
            else:
                # --- OPERATE MODE (Операции) ---
                if sreg_sel == 0:  # Логика над FREG: AND, OR, XOR, XNOR с маской Rs
                    logic_op = (self.databus >> 6) & 0x03
                    rs = (self.databus >> 3) & 0x07
                    mask = self.get_reg(rs) & 0xFFFF
                    if logic_op == 0:    # AND
                        self.freg &= mask
                    elif logic_op == 1:  # OR
                        self.freg |= mask
                    elif logic_op == 2:  # XOR
                        self.freg ^= mask
                    elif logic_op == 3:  # XNOR
                        self.freg = ~(self.freg ^ mask) & 0xFFFF
                elif sreg_sel == 1:  # Арифметика над PTREG: ADD / SUB со смещением Rs
                    arith_op = (self.databus >> 7) & 0x01
                    rs = (self.databus >> 4) & 0x07
                    offset = self.get_reg(rs) & 0xFFFF
                    if arith_op == 0:    # ADD
                        new_val = self.ptreg + offset
                    else:                # SUB
                        new_val = self.ptreg - offset
                    cf = 1 if (new_val > 0xFFFFFF or new_val < 0) else 0
                    self.freg = (self.freg & ~0x02) | (cf << 1)
                    self.ptreg = new_val & 0xFFFFFF
        else:
            # Пользовательский опкод или расширение
            pass

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
