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
        # 1. Пошаговая выборка двух 8-битных байтов (char) из памяти вручную:
        b0 = self.bus.read8(self.pc)
        self.pc += 1

        b1 = self.bus.read8(self.pc)
        self.pc += 1

        # 2. Вручную склеиваем два байта на шине данных (databus) в 16-битную инструкцию:
        self.databus = (b0 << 8) | b1

        # 3. Извлекаем поля инструкции через parse("[15-11] [10-8] [7-5] [4-2] [1-0]"):
        #   [15-11] — Opcode (5 бит)
        #   [10-8]  — Config / Mode (3 бита)
        #   [7-5]   — Целевой регистр Rd (3 бита: 0..7)
        #   [4-2]   — Первый регистр-источник Rs1 (3 бита: 0..7)
        #   [1-0]   — Второй регистр-источник Rs2 (2 бита: 0..3)
        opcode, cfg, rd, rs1, rs2 = self.parse("[15-11] [10-8] [7-5] [4-2] [1-0]")

        # ----------------------------------------------------------------------
        # ЛОГИКА ОПКОДОВ (ЧЕЛОВЕК ПИШЕТ САМ В ПРЯМОМ PYTHON):
        # ----------------------------------------------------------------------

        # 0: NOP — Нет операции
        if opcode == 0:
            pass

        # 1: ADD Rd, Rs1, Rs2 (Rd = Rs1 + Rs2)
        elif opcode == 1:
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

        # 5: MOV Rd, Rs1 (Копирование регистра через байпас MUX1 -> MUX2)
        elif opcode == 5:
            self.set_reg(rd, self.get_reg(rs1))

        # 6: MOVI Rd, #imm16 (Загрузка 16-битной константы: 2 байта вручную)
        elif opcode == 6:
            imm_hi = self.bus.read8(self.pc)
            self.pc += 1
            imm_lo = self.bus.read8(self.pc)
            self.pc += 1
            imm = (imm_hi << 8) | imm_lo
            self.set_reg(rd, imm)

        # 7: LOAD Rd, [Rs1] (Чтение 16-битного слова из ОЗУ по адресу Rs1)
        elif opcode == 7:
            addr = self.get_reg(rs1)
            val = self.bus.read16(addr)
            self.set_reg(rd, val)

        # 8: STORE [Rd], Rs1 (Запись 16-битного слова в ОЗУ по адресу Rd)
        elif opcode == 8:
            addr = self.get_reg(rd)
            val = self.get_reg(rs1)
            self.bus.write16(addr, val)

        # 9: AND Rd, Rs1, Rs2
        elif opcode == 9:
            res = self.get_reg(rs1) & self.get_reg(rs2)
            self.set_reg(rd, res)
            self._update_flags(res)

        # 10: OR Rd, Rs1, Rs2
        elif opcode == 10:
            res = self.get_reg(rs1) | self.get_reg(rs2)
            self.set_reg(rd, res)
            self._update_flags(res)

        # 11: XOR Rd, Rs1, Rs2
        elif opcode == 11:
            res = self.get_reg(rs1) ^ self.get_reg(rs2)
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

        # 31: HALT — Останов процессора
        elif opcode == 31:
            self.halt()

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
