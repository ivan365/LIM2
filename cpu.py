import os
import sys
from pathlib import Path
from typing import Optional

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

try:
    from sim.bus import MemoryBus, RAMDevice, TextScreenDevice, UARTDevice, TimerDevice, PinBank, Pin
    from sim.core import BaseCPU
    from sim.ui import run_sim, render_full_simulator_screen
except (ImportError, ValueError):
    from bus import MemoryBus, RAMDevice, TextScreenDevice, UARTDevice, TimerDevice, PinBank, Pin
    from core import BaseCPU
    from ui import run_sim, render_full_simulator_screen


class VectorList:
    """Прокси-список для 32 векторных регистров ($ir0..$ir15, $pv0..$pv15) с прямой привязкой к RegisterBank."""

    def __init__(self, regs):
        self._regs = regs

    def __getitem__(self, idx: int) -> int:
        if 0 <= idx < 16:
            return self._regs.get(f"ir{idx}")
        elif 16 <= idx < 32:
            return self._regs.get(f"pv{idx - 16}")
        raise IndexError(f"Vector index out of range: {idx}")

    def __setitem__(self, idx: int, val: int):
        if 0 <= idx < 16:
            self._regs.set(f"ir{idx}", val & 0xFFFFFFFF)
        elif 16 <= idx < 32:
            self._regs.set(f"pv{idx - 16}", val & 0xFFFFFFFF)
        else:
            raise IndexError(f"Vector index out of range: {idx}")

    def __len__(self) -> int:
        return 32

    def __iter__(self):
        for i in range(32):
            yield self[i]


class LIM2CPU(BaseCPU):
    """
    Процессор архитектуры LIM M2 (по спецификации LIM2 Datasheet).
      - 16-битные регистры R0..R7, аккумуляторы ACCA/ACCB
      - 32-битный указатель PTREG и стековый регистр SREG (SP) (линейная адресация до 4 ГБ)
      - Регистр состояния FREG (16 бит)
      - Массив из 32 системных 32-битных векторов (IR0..IR15, PV0..PV13, PV14..PV15 границы RAM)
      - 32 базовых опкода (0..31)
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

        # Системный указатель стека SREG / SP (32 бита)
        self.reg("sreg", bits=32, default=0, aliases=["sp"], title="SREG", role="Stack 32b", block="SYS")

        # Регистр состояния и флагов FREG (16 бит) по Разделу 4 Даташита LIM2:
        # [0]=ZF, [1]=CF, [2]=OF, [3]=EM, [4]=CMP0, [5]=CMP1, [6]=CLK0, [7]=CLK1,
        # [8]=SSRC, [9]=MIE, [10]=DWR, [11]=PRV, [12]=AIP, [13]=DBIT, [14]=SMOD, [15]=INTR
        flag_layout = [
            ("ZF", "Zero", 0),
            ("CF", "Carry", 1),
            ("OF", "Overflow", 2),
            ("EM", "ErrMath", 3),
            ("CMP0", "CmpBit0", 4),
            ("CMP1", "CmpBit1", 5),
            ("CLK0", "ClkBit0", 6),
            ("CLK1", "ClkBit1", 7),
            ("SSRC", "ShiftSrc", 8),
            ("MIE", "MasterInt", 9),
            ("DWR", "NoWait", 10),
            ("PRV", "Superv", 11),
            ("AIP", "AutoInc", 12),
            ("DBIT", "DispBit", 13),
            ("SMOD", "ShiftMod", 14),
            ("INTR", "InIntr", 15),
        ]
        self.reg("freg", bits=16, default=0x1800, title="FREG", is_flag=True, flag_layout=flag_layout, block="STATUS")

        # Расширенный 32-битный регистр указателя (до 4 ГБ)
        self.reg("ptreg", bits=32, default=0, title="PTREG", role="Pointer 32b", block="ADDR")

        # Таблица векторов прерываний (16 векторов: IR0..IR15, 32 бита)
        for i in range(16):
            self.compact_reg(f"ir{i}", bits=32, default=0, title=f"IR{i}", role="Interrupt Vector 32b", block="IVT")

        # Зоны защиты привилегий (14 регистров / 7 пар: PV0..PV13, 32 бита)
        for i in range(14):
            self.compact_reg(f"pv{i}", bits=32, default=0, title=f"PV{i}", role="Privilege Zone 32b", block="PROT")

        # Границы оперативной памяти RAM (2 регистра / 1 пара: PV14..PV15, 32 бита)
        self.compact_reg("pv14", bits=32, default=0, title="PV14", role="RAM Base 32b", block="PROT")
        self.compact_reg("pv15", bits=32, default=0, title="PV15", role="RAM Limit 32b", block="PROT")

        # Физические ножки процессора (PINS):
        self.pin("RD", mode="OUT", title="Read Strobe")
        self.pin("WR", mode="OUT", title="Write Strobe")
        self.pin("MREQ", mode="OUT", title="Memory Request")
        self.pin("IORQ", mode="OUT", title="I/O Request")
        self.pin("IRQ", mode="IN", title="Interrupt Request")
        self.pin("IA", mode="OUT", title="Interrupt Acknowledge")
        self.pin("HALT", mode="OUT", title="Halt Output")
        self.pin("RESET", mode="IN", title="Reset Input")
        self.pin("RF", mode="IN", title="Ready Flag")

        self.vectors = VectorList(self.regs)
        self.ivt = self.vectors
        self.sys_regs_ext = [0] * 15

        # 4 встроенных аппаратных таймера (кодируются в 15 ячейках 64..78):
        self.t1_cnt = 0
        self.t1_match = 0
        self.t1_time = 0
        self.t2_cnt = 0
        self.t2_reload = 0
        self.t3_cnt = 0
        self.t4_cnt = 0
        self.t4_reload = 0
        self.tsr = 0

    def on_start(self):
        """2. Что процессор делает сразу при старте (сброс регистров, установка PC)."""
        self.pc = 0x00000000
        self.acca = 0
        self.accb = 0
        # При старте/сбросе ядро находится в режиме супервизора PRV=1 (бит 11) и автоинкремент AIP=1 (бит 12):
        self.freg = 0x1800
        self.ptreg = 0
        self.sreg = 0
        self.sys_regs_ext = [0] * 15

        # Сброс встроенных аппаратных таймеров:
        self.t1_cnt = 0
        self.t1_match = 0
        self.t1_time = 0
        self.t2_cnt = 0
        self.t2_reload = 0
        self.t3_cnt = 0
        self.t4_cnt = 0
        self.t4_reload = 0
        self.tsr = 0

        for i in range(32):
            self.vectors[i] = 0
        for i in range(8):
            self.set_reg(i, 0)
        if hasattr(self.bus, "set_mode"):
            self.bus.set_mode("32bit")

    def read_sys_cell(self, reg_id: int) -> int:
        """Чтение квантованной 16-битной ячейки системного регистра по её номеру REG_ID (0..255)."""
        if 0 <= reg_id < 64:
            vec_idx = reg_id // 2
            val32 = self.vectors[vec_idx]
            if reg_id % 2 == 0:
                return val32 & 0xFFFF
            else:
                return (val32 >> 16) & 0xFFFF
        elif 64 <= reg_id <= 78:
            if reg_id == 64: return self.t1_cnt & 0xFFFF
            elif reg_id == 65: return (self.t1_cnt >> 16) & 0xFFFF
            elif reg_id == 66: return self.t1_match & 0xFFFF
            elif reg_id == 67: return (self.t1_match >> 16) & 0xFFFF
            elif reg_id == 68: return self.t1_time & 0xFFFF
            elif reg_id == 69: return (self.t1_time >> 16) & 0xFFFF
            elif reg_id == 70: return self.t2_cnt & 0xFFFF
            elif reg_id == 71: return (self.t2_cnt >> 16) & 0xFFFF
            elif reg_id == 72: return self.t2_reload & 0xFFFF
            elif reg_id == 73: return (self.t2_reload >> 16) & 0xFFFF
            elif reg_id == 74: return self.t3_cnt & 0xFFFF
            elif reg_id == 75: return (self.t3_cnt >> 16) & 0xFFFF
            elif reg_id == 76: return self.t4_cnt & 0xFFFF
            elif reg_id == 77: return self.t4_reload & 0xFFFF
            elif reg_id == 78: return self.tsr & 0xFFFF
            return self.sys_regs_ext[reg_id - 64] & 0xFFFF
        elif reg_id == 128:
            return self.freg & 0xFFFF
        elif reg_id == 129:
            return self.sreg & 0xFFFF
        elif reg_id == 130:
            return (self.sreg >> 16) & 0xFFFF
        elif reg_id == 131:
            return self.ptreg & 0xFFFF
        elif reg_id == 132:
            return (self.ptreg >> 16) & 0xFFFF
        return 0

    def write_sys_cell(self, reg_id: int, val16: int) -> None:
        """Запись в квантованную 16-битную ячейку системного регистра с контролем привилегий."""
        val16 &= 0xFFFF
        if 0 <= reg_id < 64:
            vec_idx = reg_id // 2
            cur_prv = (self.freg >> 11) & 1
            # Защита зон привилегий (PVZ_VEC: векторы 16..29, ячейки 32..59):
            if 16 <= vec_idx <= 29 and cur_prv == 0 and not self.in_privilege_zone():
                return
            old32 = self.vectors[vec_idx]
            if reg_id % 2 == 0:
                self.vectors[vec_idx] = (old32 & 0xFFFF0000) | val16
            else:
                self.vectors[vec_idx] = (old32 & 0x0000FFFF) | (val16 << 16)
        elif 64 <= reg_id <= 78:
            self.sys_regs_ext[reg_id - 64] = val16
            if reg_id == 64:
                self.t1_cnt = (self.t1_cnt & 0xFFFF0000) | val16
            elif reg_id == 65:
                self.t1_cnt = (self.t1_cnt & 0x0000FFFF) | (val16 << 16)
            elif reg_id == 66:
                self.t1_match = (self.t1_match & 0xFFFF0000) | val16
            elif reg_id == 67:
                self.t1_match = (self.t1_match & 0x0000FFFF) | (val16 << 16)
            elif reg_id == 68:
                self.t1_time = (self.t1_time & 0xFFFF0000) | val16
            elif reg_id == 69:
                self.t1_time = (self.t1_time & 0x0000FFFF) | (val16 << 16)
            elif reg_id == 70:
                self.t2_cnt = (self.t2_cnt & 0xFFFF0000) | val16
            elif reg_id == 71:
                self.t2_cnt = (self.t2_cnt & 0x0000FFFF) | (val16 << 16)
            elif reg_id == 72:
                self.t2_reload = (self.t2_reload & 0xFFFF0000) | val16
            elif reg_id == 73:
                self.t2_reload = (self.t2_reload & 0x0000FFFF) | (val16 << 16)
            elif reg_id == 74:
                self.t3_cnt = (self.t3_cnt & 0xFFFF0000) | val16
            elif reg_id == 75:
                self.t3_cnt = (self.t3_cnt & 0x0000FFFF) | (val16 << 16)
            elif reg_id == 76:
                self.t4_cnt = val16
            elif reg_id == 77:
                self.t4_reload = val16
            elif reg_id == 78:
                self.tsr = val16
        elif reg_id == 128:
            cur_prv = (self.freg >> 11) & 1
            target_prv = (val16 >> 11) & 1
            if cur_prv == 0 and target_prv == 1 and not self.in_privilege_zone():
                val16 &= ~(1 << 11)
            self.freg = val16
        elif reg_id == 129:
            self.sreg = (self.sreg & 0xFFFF0000) | val16
        elif reg_id == 130:
            self.sreg = (self.sreg & 0x0000FFFF) | (val16 << 16)
        elif reg_id == 131:
            self.ptreg = (self.ptreg & 0xFFFF0000) | val16
        elif reg_id == 132:
            self.ptreg = (self.ptreg & 0x0000FFFF) | (val16 << 16)

    def in_privilege_zone(self, pc: Optional[int] = None) -> bool:
        """Проверяет, попадает ли адрес в одну из 7 сконфигурированных зон привилегий ($pv0..$pv13)."""
        addr = self.pc if pc is None else pc
        for i in range(7):
            base = self.vectors[16 + 2 * i]
            limit = self.vectors[16 + 2 * i + 1]
            if base != 0 or limit != 0:
                if base <= addr <= limit:
                    return True
        return False

    def is_ram_address(self, addr: int) -> bool:
        """
        Проверяет, попадает ли адрес в диапазон оперативной памяти RAM ($pv14..$pv15 / векторы 30..31).
        К диапазону RAM разрешен доступ с любыми правами (включая пользовательский режим PRV=0).
        """
        ram_base = self.vectors[30]
        ram_limit = self.vectors[31]
        if ram_base == 0 and ram_limit == 0:
            return True
        return ram_base <= addr <= ram_limit

    def can_write_address(self, addr: int) -> bool:
        """
        Проверяет права доступа на запись по адресу addr:
        - К оперативной памяти (RAM) можно обращаться с ЛЮБЫМИ правами (включая PRV=0).
        - Ко всем остальным адресам (вне RAM) запись разрешена ТОЛЬКО с правами супервизора (PRV=1)
          либо при исполнении внутри одной из зон привилегий ($pv0..$pv13).
        """
        cur_prv = (self.freg >> 11) & 1
        if cur_prv == 1 or self.in_privilege_zone():
            return True
        return self.is_ram_address(addr)

    def is_rom_address(self, addr: int) -> bool:
        """Совместимость: адрес защищен от записи пользователем, если он находится вне диапазона RAM."""
        return not self.can_write_address(addr)

    def trigger_irq(self, vector_num: int = 0, force: bool = False) -> bool:
        """
        Аппаратный вызов прерывания по вектору IRQ (0..15).
        Сохраняет 32-битный PC в стек SP, устанавливает INTR=1 во FREG.
        """
        if not force and not (self.freg & (1 << 9)):
            return False

        # Сохранение 32-битного PC в стек SREG (SP)
        self.sreg = (self.sreg - 4) & 0xFFFFFFFF
        self.bus.write32(self.sreg, self.pc & 0xFFFFFFFF, little_endian=True)

        vec_idx = min(15, max(0, vector_num))
        self.pc = self.vectors[vec_idx] & 0xFFFFFFFF
        self.freg |= (1 << 15)  # INTR = 1
        if hasattr(self, "pins"):
            self.pins.IRQ.set(0)
            self.pins.IA.set(1)  # Аппаратное подтверждение: IA = 1 (Interrupt Acknowledge)
        return True

    def _fetch_jump_target(self, src_mode: int) -> int:
        """
        Универсальный декодер целевого 32-битного адреса для инструкций ветвления (JMP, JO, JNO, JZ, JNZ, CALL):
          0 (00): Прямой 32-битный адрес imm32 (5 байтов)
          1 (01): Косвенный адрес из памяти [ADDR] (5 байтов)
          2 (10): Адрес из указателя [PTREG] (1 байт)
          3 (11): Адрес из пары РОН [Rh:Rl] (2 байта)
        """
        if src_mode == 0:
            target = self.bus.read32(self.pc, little_endian=True)
            self.pc += 4
            return target & 0xFFFFFFFF
        elif src_mode == 1:
            ptr32 = self.bus.read32(self.pc, little_endian=True)
            self.pc += 4
            target = self.bus.read32(ptr32, little_endian=True)
            return target & 0xFFFFFFFF
        elif src_mode == 2:
            return self.ptreg & 0xFFFFFFFF
        elif src_mode == 3:
            b1 = self.bus.read8(self.pc)
            self.pc += 1
            r_hi = (b1 >> 5) & 0x07
            r_lo = (b1 >> 2) & 0x07
            return (((self.get_reg(r_hi) & 0xFFFF) << 16) | (self.get_reg(r_lo) & 0xFFFF)) & 0xFFFFFFFF
        return 0

    def on_step(self):
        """
        Выборка, сборка опкода и исполнение инструкции.
        Все операции с PC выполняются вручную и пошагово.
        """
        # Сброс строба подтверждения прерывания IA при начале исполнения команд обработчика:
        if hasattr(self, "pins") and self.pins.IA.get() == 1:
            self.pins.IA.set(0)

        # 0. Проверка аппаратного запроса прерывания на ножке IRQ:
        if hasattr(self, "pins") and self.pins.IRQ.get() == 1:
            if self.trigger_irq(0, force=False):
                return

        # 1. Выборка октета 0:
        self.addressbus = self.pc
        b0 = self.bus.read8(self.pc)
        self.pc += 1
        self.databus = b0

        # [7:3] — Opcode (5 бит), [2:0] — Config / Args (3 бита в первом байте)
        opcode = (b0 >> 3) & 0x1F
        cfg = b0 & 0x07

        # ----------------------------------------------------------------------
        # 0: NOP (1 байт)
        # ----------------------------------------------------------------------
        if opcode == 0b00000:
            pass

        # ----------------------------------------------------------------------
        # 1: ADD Rd, Rs0, Rs1 (2 байта: Rd = Rs0 + Rs1)
        # ----------------------------------------------------------------------
        elif opcode == 0b00001:
            rd = cfg & 0x07
            b1 = self.bus.read8(self.pc); self.pc += 1
            rs0 = (b1 >> 5) & 0x07
            rs1 = (b1 >> 2) & 0x07
            val0 = self.get_reg(rs0)
            val1 = self.get_reg(rs1)
            self.acca, self.accb = val0, val1
            res = val0 + val1
            self.set_reg(rd, res & 0xFFFF)
            self._update_flags(res)

        # ----------------------------------------------------------------------
        # 2: SUB Rd, Rs0, Rs1 (2 байта: Rd = Rs0 - Rs1)
        # ----------------------------------------------------------------------
        elif opcode == 0b00010:
            rd = cfg & 0x07
            b1 = self.bus.read8(self.pc); self.pc += 1
            rs0 = (b1 >> 5) & 0x07
            rs1 = (b1 >> 2) & 0x07
            val0 = self.get_reg(rs0)
            val1 = self.get_reg(rs1)
            self.acca, self.accb = val0, val1
            res = val0 - val1
            self.set_reg(rd, res & 0xFFFF)
            self._update_flags(res)

        # ----------------------------------------------------------------------
        # 3: MUL Rd, Rs0, Rs1 (2 байта: Rd = (Rs0 * Rs1) & 0xFFFF)
        # ----------------------------------------------------------------------
        elif opcode == 0b00011:
            rd = cfg & 0x07
            b1 = self.bus.read8(self.pc); self.pc += 1
            rs0 = (b1 >> 5) & 0x07
            rs1 = (b1 >> 2) & 0x07
            val0 = self.get_reg(rs0)
            val1 = self.get_reg(rs1)
            self.acca, self.accb = val0, val1
            res = val0 * val1
            self.set_reg(rd, res & 0xFFFF)
            self._update_flags(res)

        # ----------------------------------------------------------------------
        # 4: DIV Rd, Rs0, Rs1 (2 байта: Rd = Rs0 // Rs1)
        # ----------------------------------------------------------------------
        elif opcode == 0b00100:
            rd = cfg & 0x07
            b1 = self.bus.read8(self.pc); self.pc += 1
            rs0 = (b1 >> 5) & 0x07
            rs1 = (b1 >> 2) & 0x07
            val0 = self.get_reg(rs0)
            val1 = self.get_reg(rs1)
            self.acca, self.accb = val0, val1
            if val1 == 0:
                self.freg |= (1 << 3) | 1  # EM=1, ZF=1
                res = 0
            else:
                res = val0 // val1
                self._update_flags(res)
            self.set_reg(rd, res & 0xFFFF)

        # ----------------------------------------------------------------------
        # 5: LMR (Загрузка в регистр из памяти/непосредственных данных: 2..6 байт)
        #   [2] = DS (0: 8-бит .b, 1: 16-бит .w)
        #   [1:0] = Source (0: imm, 1: [ADDR], 2: [PTREG], 3: [Rh:Rl])
        # ----------------------------------------------------------------------
        elif opcode == 0b00101:
            ds = (cfg >> 2) & 1
            src_mode = cfg & 0b11
            if src_mode == 0:  # Непосредственные данные
                b1 = self.bus.read8(self.pc); self.pc += 1
                rd = (b1 >> 5) & 0x07
                if ds == 0:
                    data = self.bus.read8(self.pc); self.pc += 1
                else:
                    data = self.bus.read16(self.pc, little_endian=True); self.pc += 2
                self.set_reg(rd, data & (0xFF if ds == 0 else 0xFFFF))
            elif src_mode == 1:  # [ADDR] (6 байт: опкод + rd + 4 байта addr32)
                b1 = self.bus.read8(self.pc); self.pc += 1
                rd = (b1 >> 5) & 0x07
                ea = self.bus.read32(self.pc, little_endian=True); self.pc += 4
                if ds == 0:
                    data = self.bus.read8(ea)
                else:
                    data = self.bus.read16(ea, little_endian=True)
                self.set_reg(rd, data & (0xFF if ds == 0 else 0xFFFF))
            elif src_mode == 2:  # [PTREG] (2 байта: опкод + rd)
                b1 = self.bus.read8(self.pc); self.pc += 1
                rd = (b1 >> 5) & 0x07
                ea = self.ptreg & 0xFFFFFFFF
                if ds == 0:
                    data = self.bus.read8(ea)
                    self.ptreg = (self.ptreg + 1) & 0xFFFFFFFF
                else:
                    data = self.bus.read16(ea, little_endian=True)
                    self.ptreg = (self.ptreg + 2) & 0xFFFFFFFF
                self.set_reg(rd, data & (0xFF if ds == 0 else 0xFFFF))
            elif src_mode == 3:  # [Rh:Rl] (2 байта: опкод + Rh:Rl)
                b1 = self.bus.read8(self.pc); self.pc += 1
                rd_hi = (b1 >> 5) & 0x07
                rs_lo = (b1 >> 2) & 0x07
                ea = (((self.get_reg(rd_hi) & 0xFFFF) << 16) | (self.get_reg(rs_lo) & 0xFFFF)) & 0xFFFFFFFF
                if ds == 0:
                    data = self.bus.read8(ea)
                else:
                    data = self.bus.read16(ea, little_endian=True)
                self.set_reg(rd_hi, data & (0xFF if ds == 0 else 0xFFFF))

        # ----------------------------------------------------------------------
        # 6: LRM (Запись из регистра/константы в память: 2..6 байт)
        #   [2] = DS (0: 8-бит .b, 1: 16-бит .w)
        #   [1:0] = Source (0: imm в [PTREG], 1: Reg в [ADDR], 2: Reg в [PTREG])
        # ----------------------------------------------------------------------
        elif opcode == 0b00110:
            ds = (cfg >> 2) & 1
            dst_mode = cfg & 0b11
            if dst_mode == 0:  # Непосредственные данные в [PTREG]
                b1 = self.bus.read8(self.pc); self.pc += 1
                if ds == 0:
                    val = self.bus.read8(self.pc); self.pc += 1
                    if self.can_write_address(self.ptreg):
                        self.bus.write8(self.ptreg, val & 0xFF)
                    self.ptreg = (self.ptreg + 1) & 0xFFFFFFFF
                else:
                    val = self.bus.read16(self.pc, little_endian=True); self.pc += 2
                    if self.can_write_address(self.ptreg):
                        self.bus.write16(self.ptreg, val & 0xFFFF, little_endian=True)
                    self.ptreg = (self.ptreg + 2) & 0xFFFFFFFF
            elif dst_mode == 1:  # Запись регистра в [ADDR] (6 байт)
                b1 = self.bus.read8(self.pc); self.pc += 1
                rs = (b1 >> 5) & 0x07
                val = self.get_reg(rs)
                ea = self.bus.read32(self.pc, little_endian=True); self.pc += 4
                if self.can_write_address(ea):
                    if ds == 0:
                        self.bus.write8(ea, val & 0xFF)
                    else:
                        self.bus.write16(ea, val & 0xFFFF, little_endian=True)
            elif dst_mode == 2:  # Запись регистра в [PTREG] (2 байта)
                b1 = self.bus.read8(self.pc); self.pc += 1
                rs = (b1 >> 5) & 0x07
                val = self.get_reg(rs)
                if self.can_write_address(self.ptreg):
                    if ds == 0:
                        self.bus.write8(self.ptreg, val & 0xFF)
                    else:
                        self.bus.write16(self.ptreg, val & 0xFFFF, little_endian=True)
                if ds == 0:
                    self.ptreg = (self.ptreg + 1) & 0xFFFFFFFF
                else:
                    self.ptreg = (self.ptreg + 2) & 0xFFFFFFFF

        # ----------------------------------------------------------------------
        # 7: LRR Rd, Rs (2 байта: прямое копирование между РОН)
        # ----------------------------------------------------------------------
        elif opcode == 0b00111:
            rd = cfg & 0x07
            b1 = self.bus.read8(self.pc); self.pc += 1
            rs = (b1 >> 5) & 0x07
            self.set_reg(rd, self.get_reg(rs))

        # ----------------------------------------------------------------------
        # 8: CMP Rs0, Rs1 (2 байта: сравнение операндов)
        # ----------------------------------------------------------------------
        elif opcode == 0b01000:
            rs0 = cfg & 0x07
            b1 = self.bus.read8(self.pc); self.pc += 1
            rs1 = (b1 >> 5) & 0x07
            val0 = self.get_reg(rs0)
            val1 = self.get_reg(rs1)
            diff = val0 - val1
            cmp_code = 0b01 if val0 < val1 else (0b10 if val0 == val1 else 0b11)
            # Код сравнения фиксируется в битах [5:4] регистра FREG
            self.freg = (self.freg & ~(0b11 << 4)) | (cmp_code << 4)
            self._update_flags(diff)

        # ----------------------------------------------------------------------
        # 9: JMP target (1..5 байт: безусловный 32-битный переход)
        # ----------------------------------------------------------------------
        elif opcode == 0b01001:
            src_mode = cfg & 0b11
            target = self._fetch_jump_target(src_mode)
            self.pc = target & 0xFFFFFFFF

        # ----------------------------------------------------------------------
        # 10: JCR cond, target32 (5 байт: условный переход по результату CMP)
        # ----------------------------------------------------------------------
        elif opcode == 0b01010:
            inv = (cfg >> 2) & 1
            expected_cmp = cfg & 0b11
            target = self.bus.read32(self.pc, little_endian=True) & 0xFFFFFFFF
            self.pc += 4
            actual_cmp = (self.freg >> 4) & 0b11
            take = (actual_cmp == expected_cmp) if inv == 0 else (actual_cmp != expected_cmp)
            if take:
                self.pc = target & 0xFFFFFFFF

        # ----------------------------------------------------------------------
        # 11: JO / JOB (Neg=0) / JNO (Neg=1) (1..5 байт: по флагу OF или CF)
        # ----------------------------------------------------------------------
        elif opcode == 0b01011:
            neg = (cfg >> 2) & 1
            src_mode = cfg & 0b11
            target = self._fetch_jump_target(src_mode)
            has_ovf_or_cf = bool((self.freg & (1 << 2)) or (self.freg & (1 << 1)))
            take = has_ovf_or_cf if neg == 0 else (not has_ovf_or_cf)
            if take:
                self.pc = target & 0xFFFFFFFF

        # ----------------------------------------------------------------------
        # 12: JZ (Neg=0) / JNZ (Neg=1) (1..5 байт: по флагу ZF)
        # ----------------------------------------------------------------------
        elif opcode == 0b01100:
            neg = (cfg >> 2) & 1
            src_mode = cfg & 0b11
            target = self._fetch_jump_target(src_mode)
            is_zero = bool(self.freg & 0x01)
            take = is_zero if neg == 0 else (not is_zero)
            if take:
                self.pc = target & 0xFFFFFFFF

        # ----------------------------------------------------------------------
        # 13: AND Rd, Rs0, Rs1 (2 байта)
        # ----------------------------------------------------------------------
        elif opcode == 0b01101:
            rd = cfg & 0x07
            b1 = self.bus.read8(self.pc); self.pc += 1
            rs0 = (b1 >> 5) & 0x07
            rs1 = (b1 >> 2) & 0x07
            res = self.get_reg(rs0) & self.get_reg(rs1)
            self.set_reg(rd, res & 0xFFFF)
            self._update_flags(res)

        # ----------------------------------------------------------------------
        # 14: OR Rd, Rs0, Rs1 (2 байта)
        # ----------------------------------------------------------------------
        elif opcode == 0b01110:
            rd = cfg & 0x07
            b1 = self.bus.read8(self.pc); self.pc += 1
            rs0 = (b1 >> 5) & 0x07
            rs1 = (b1 >> 2) & 0x07
            res = self.get_reg(rs0) | self.get_reg(rs1)
            self.set_reg(rd, res & 0xFFFF)
            self._update_flags(res)

        # ----------------------------------------------------------------------
        # 15: NAND Rd, Rs0, Rs1 (2 байта)
        # ----------------------------------------------------------------------
        elif opcode == 0b01111:
            rd = cfg & 0x07
            b1 = self.bus.read8(self.pc); self.pc += 1
            rs0 = (b1 >> 5) & 0x07
            rs1 = (b1 >> 2) & 0x07
            res = (~(self.get_reg(rs0) & self.get_reg(rs1))) & 0xFFFF
            self.set_reg(rd, res)
            self._update_flags(res)

        # ----------------------------------------------------------------------
        # 16: NOR Rd, Rs0, Rs1 (2 байта)
        # ----------------------------------------------------------------------
        elif opcode == 0b10000:
            rd = cfg & 0x07
            b1 = self.bus.read8(self.pc); self.pc += 1
            rs0 = (b1 >> 5) & 0x07
            rs1 = (b1 >> 2) & 0x07
            res = (~(self.get_reg(rs0) | self.get_reg(rs1))) & 0xFFFF
            self.set_reg(rd, res)
            self._update_flags(res)

        # ----------------------------------------------------------------------
        # 17: NOT Target, Source (2 байта)
        # ----------------------------------------------------------------------
        elif opcode == 0b10001:
            target = cfg & 0x07
            b1 = self.bus.read8(self.pc); self.pc += 1
            source = (b1 >> 5) & 0x07
            res = (~self.get_reg(source)) & 0xFFFF
            self.set_reg(target, res)
            self._update_flags(res)

        # ----------------------------------------------------------------------
        # 18: XOR Rd, Rs0, Rs1 (2 байта)
        # ----------------------------------------------------------------------
        elif opcode == 0b10010:
            rd = cfg & 0x07
            b1 = self.bus.read8(self.pc); self.pc += 1
            rs0 = (b1 >> 5) & 0x07
            rs1 = (b1 >> 2) & 0x07
            res = (self.get_reg(rs0) ^ self.get_reg(rs1)) & 0xFFFF
            self.set_reg(rd, res)
            self._update_flags(res)

        # ----------------------------------------------------------------------
        # 19: XNOR Rd, Rs0, Rs1 (2 байта)
        # ----------------------------------------------------------------------
        elif opcode == 0b10011:
            rd = cfg & 0x07
            b1 = self.bus.read8(self.pc); self.pc += 1
            rs0 = (b1 >> 5) & 0x07
            rs1 = (b1 >> 2) & 0x07
            res = (~(self.get_reg(rs0) ^ self.get_reg(rs1))) & 0xFFFF
            self.set_reg(rd, res)
            self._update_flags(res)

        # ----------------------------------------------------------------------
        # 20: INC Rd (1 байт)
        # ----------------------------------------------------------------------
        elif opcode == 0b10100:
            rd = cfg & 0x07
            val = self.get_reg(rd)
            res = (val + 1) & 0xFFFF
            self.set_reg(rd, res)
            zf = 1 if res == 0 else 0
            of = 1 if val == 0x7FFF else 0
            self.freg = (self.freg & ~0x05) | (of << 2) | zf

        # ----------------------------------------------------------------------
        # 21: DEC Rd (1 байт)
        # ----------------------------------------------------------------------
        elif opcode == 0b10101:
            rd = cfg & 0x07
            val = self.get_reg(rd)
            res = (val - 1) & 0xFFFF
            self.set_reg(rd, res)
            zf = 1 if res == 0 else 0
            of = 1 if val == 0x8000 else 0
            self.freg = (self.freg & ~0x05) | (of << 2) | zf

        # ----------------------------------------------------------------------
        # 22: PUSH Rs (1 байт)
        # ----------------------------------------------------------------------
        elif opcode == 0b10110:
            rs = cfg & 0x07
            val = self.get_reg(rs) & 0xFFFF
            self.sreg = (self.sreg - 2) & 0xFFFFFFFF
            self.bus.write16(self.sreg, val, little_endian=True)

        # ----------------------------------------------------------------------
        # 23: POP Rd (1 байт)
        # ----------------------------------------------------------------------
        elif opcode == 0b10111:
            rd = cfg & 0x07
            val = self.bus.read16(self.sreg, little_endian=True) & 0xFFFF
            self.sreg = (self.sreg + 2) & 0xFFFFFFFF
            self.set_reg(rd, val)

        # ----------------------------------------------------------------------
        # 24: BSL Rd (1 байт: сдвиг влево на 1 бит)
        # ----------------------------------------------------------------------
        elif opcode == 0b11000:
            rd = cfg & 0x07
            val = self.get_reg(rd) & 0xFFFF
            smod = (self.freg >> 14) & 1
            dbit = (self.freg >> 13) & 1
            ssrc = (self.freg >> 8) & 1
            last_displaced = (val >> 15) & 1
            in_bit = last_displaced if smod == 1 else (dbit if ssrc == 1 else 0)
            res = ((val << 1) | in_bit) & 0xFFFF
            self.set_reg(rd, res)
            # Флаг DBIT (бит 13) и флаг CF (бит 1) фиксируют вытесненный бит:
            self.freg = (self.freg & ~(1 << 13)) | (last_displaced << 13)
            self.freg = (self.freg & ~(1 << 1)) | (last_displaced << 1)
            zf = 1 if res == 0 else 0
            self.freg = (self.freg & ~0x01) | zf

        # ----------------------------------------------------------------------
        # 25: BSR Rd (1 байт: сдвиг вправо на 1 бит)
        # ----------------------------------------------------------------------
        elif opcode == 0b11001:
            rd = cfg & 0x07
            val = self.get_reg(rd) & 0xFFFF
            smod = (self.freg >> 14) & 1
            dbit = (self.freg >> 13) & 1
            ssrc = (self.freg >> 8) & 1
            last_displaced = val & 1
            in_bit = last_displaced if smod == 1 else (dbit if ssrc == 1 else 0)
            res = (val >> 1) | (in_bit << 15)
            self.set_reg(rd, res)
            self.freg = (self.freg & ~(1 << 13)) | (last_displaced << 13)
            self.freg = (self.freg & ~(1 << 1)) | (last_displaced << 1)
            zf = 1 if res == 0 else 0
            self.freg = (self.freg & ~0x01) | zf

        # ----------------------------------------------------------------------
        # 26: MSP (2 или 4 байта: манипуляция квантованными 16-битными системными регистрами)
        # ----------------------------------------------------------------------
        elif opcode == 0b11010:
            op3 = cfg & 0x07
            reg_id = self.bus.read8(self.pc)
            self.pc += 1

            if op3 == 0b001:  # 001: ldr7 (2 байта: SYS_REG[reg_id] = R7)
                val16 = self.get_reg(7) & 0xFFFF
                self.write_sys_cell(reg_id, val16)
            elif op3 == 0b010:  # 010: str7 (2 байта: R7 = SYS_REG[reg_id])
                val16 = self.read_sys_cell(reg_id)
                self.set_reg(7, val16)
            else:  # 4-байтовые операции с 16-битным immediate (Little-Endian)
                imm16 = self.bus.read16(self.pc, little_endian=True) & 0xFFFF
                self.pc += 2
                if op3 == 0b000:  # 000: ld (SYS_REG[reg_id] = imm16)
                    self.write_sys_cell(reg_id, imm16)
                elif op3 == 0b011:  # 011: and (SYS_REG[reg_id] &= imm16)
                    cur = self.read_sys_cell(reg_id)
                    self.write_sys_cell(reg_id, cur & imm16)
                elif op3 == 0b100:  # 100: or (SYS_REG[reg_id] |= imm16)
                    cur = self.read_sys_cell(reg_id)
                    self.write_sys_cell(reg_id, cur | imm16)
                elif op3 == 0b101:  # 101: xor (SYS_REG[reg_id] ^= imm16)
                    cur = self.read_sys_cell(reg_id)
                    self.write_sys_cell(reg_id, cur ^ imm16)
                elif op3 == 0b110:  # 110: onb (SYS_REG[reg_id] |= imm16)
                    cur = self.read_sys_cell(reg_id)
                    self.write_sys_cell(reg_id, cur | imm16)
                elif op3 == 0b111:  # 111: offb (SYS_REG[reg_id] &= ~imm16)
                    cur = self.read_sys_cell(reg_id)
                    self.write_sys_cell(reg_id, cur & (~imm16 & 0xFFFF))

        # ----------------------------------------------------------------------
        # 27: MOD Rd, Rs0, Rs1 (2 байта: Rd = Rs0 % Rs1)
        # ----------------------------------------------------------------------
        elif opcode == 0b11011:
            rd = cfg & 0x07
            b1 = self.bus.read8(self.pc); self.pc += 1
            rs0 = (b1 >> 5) & 0x07
            rs1 = (b1 >> 2) & 0x07
            val0 = self.get_reg(rs0)
            val1 = self.get_reg(rs1)
            self.acca, self.accb = val0, val1
            if val1 == 0:
                self.freg |= (1 << 3) | 1  # EM=1, ZF=1
                res = 0
            else:
                res = val0 % val1
                self._update_flags(res)
            self.set_reg(rd, res & 0xFFFF)

        # ----------------------------------------------------------------------
        # 28: INTR / INT / SWI (2 байта: программное прерывание)
        # ----------------------------------------------------------------------
        elif opcode == 0b11100:
            b1 = self.bus.read8(self.pc); self.pc += 1
            vec = b1 & 0x0F
            # Сохранение только 32-битного PC в стек SP (SREG):
            self.sreg = (self.sreg - 4) & 0xFFFFFFFF
            self.bus.write32(self.sreg, self.pc & 0xFFFFFFFF, little_endian=True)
            self.freg |= (1 << 15)  # INTR = 1
            self.pc = self.vectors[vec] & 0xFFFFFFFF

        # ----------------------------------------------------------------------
        # 29: CALL target (1..5 байт: вызов подпрограммы)
        # ----------------------------------------------------------------------
        elif opcode == 0b11101:
            src_mode = cfg & 0b11
            target = self._fetch_jump_target(src_mode)
            ret_addr = self.pc & 0xFFFFFFFF
            self.sreg = (self.sreg - 4) & 0xFFFFFFFF
            self.bus.write32(self.sreg, ret_addr, little_endian=True)
            self.pc = target & 0xFFFFFFFF

        # ----------------------------------------------------------------------
        # 30: RET (1 байт: возврат из подпрограммы)
        # ----------------------------------------------------------------------
        elif opcode == 0b11110:
            ret_addr = self.bus.read32(self.sreg, little_endian=True) & 0xFFFFFFFF
            self.sreg = (self.sreg + 4) & 0xFFFFFFFF
            self.pc = ret_addr
            self.freg &= ~(1 << 15)  # сброс бита INTR в FREG

        # ----------------------------------------------------------------------
        # 31: HALT (1 байт: останов)
        # ----------------------------------------------------------------------
        elif opcode == 0b11111:
            if hasattr(self, "pins"):
                self.pins.HALT.set(1)
                self.pins.MREQ.set(0)
                self.pins.RD.set(0)
            self.halt()

        # Вычисление аппаратных тактов текущей инструкции и обновление таймеров:
        cycles = self._calculate_instruction_cycles(opcode, cfg)
        self._update_timers(cycles=cycles)

    def _calculate_instruction_cycles(self, opcode: int, cfg: int) -> int:
        """
        Вычисляет число тактов тактового генератора, затраченных на выполнение завершенной инструкции.
        Определяется сложностью операции, числом обращений к шине и латентностью АЛУ.
        """
        import random
        # 1. NOP и HALT: базовый 1 такт (гарантирует детерминизм в тестах и задержках)
        if opcode == 0 or opcode == 31:
            return 1

        # 2. Быстрые унарные инструкции РОН (1..2 такта):
        elif opcode in (21, 22):  # INC, DEC
            return random.randint(1, 2)
        elif opcode in (23, 24):  # BSL, BSR
            return random.randint(1, 2)
        elif opcode in (27, 28):  # PUSH, POP
            return random.randint(2, 3)
        elif opcode == 30:  # RET
            return random.randint(3, 4)

        # 3. Базовая 16-битная арифметика и побитовая логика (2..3 такта):
        elif opcode in (1, 2, 7, 8, 13, 14, 15, 16, 17, 18, 20):  # ADD, SUB, LRR, CMP, AND, OR, NAND, NOR, XOR, XNOR, NOT
            return random.randint(2, 3)

        # 4. Многотактовая арифметика:
        elif opcode == 3:  # MUL (4..6 тактов)
            return random.randint(4, 6)
        elif opcode in (4, 19):  # DIV, MOD (6..10 тактов)
            return random.randint(6, 10)

        # 5. Инструкции обмена с памятью (LMR, LRM):
        elif opcode in (5, 6):
            mode = cfg & 0b11
            if mode == 0:     # Непосредственные данные
                return random.randint(2, 3)
            elif mode == 1:   # Прямой 32-битный адрес [ADDR] (шинный цикл + декодирование)
                return random.randint(4, 6)
            elif mode == 2:   # Потоковый доступ [PTREG] (с автоинкрементом)
                return random.randint(2, 4)
            elif mode == 3:   # Составной указатель [Rh:Rl]
                return random.randint(3, 5)
            return random.randint(3, 5)

        # 6. Ветвления и вызовы:
        elif opcode in (9, 10, 11, 12):  # JMP, JCR, JO, JZ
            return random.randint(3, 4)
        elif opcode == 29:  # CALL (сохранение PC и FREG в стек)
            return random.randint(5, 7)
        elif opcode == 25:  # INT
            return random.randint(4, 6)

        # 7. Настройка спецрегистров (MSP):
        elif opcode == 26:
            return random.randint(2, 4)

        return random.randint(2, 4)

    def _update_timers(self, cycles: int = 1):
        """
        Обновление аппаратных таймеров процессора:
          - T1: 32-битный тактовый up-counter: добавляет cycles.
                При t1_cnt >= t1_match:
                  matches = t1_cnt // t1_match
                  t1_time += matches
                  t1_cnt = t1_cnt % t1_match  (излишек тактів переносится в новый отсчет!)
                  T1_IF = 1, IRQ 12
          - T2: 32-битный периодический down-counter: вычитает cycles.
                При t2_cnt <= 0:
                  излишек (deficit) корректно переносится в перезагруженный счетчик:
                  excess = cycles - old_t2_cnt
                  rem = excess % t2_reload
                  t2_cnt = t2_reload if rem == 0 else (t2_reload - rem)
                  T2_IF = 1, IRQ 13
          - T3: 32-битный разовый (one-shot) down-counter: вычитает cycles.
                При t3_cnt <= cycles:
                  t3_cnt = 0, сброс T3_EN, T3_IF = 1, IRQ 14
          - T4: 16-битный квантователь инструкций: ВСЕГДА декрементирует строго на 1 завершенную инструкцию!
                При t4_cnt == 0:
                  t4_cnt = t4_reload, T4_IF = 1, IRQ 15
        """
        if cycles <= 0:
            cycles = 1

        # 1. Таймер 1 (T1_EN = bit 15 TSR): Up-counter
        if self.tsr & (1 << 15):
            self.t1_cnt = (self.t1_cnt + cycles) & 0xFFFFFFFF
            if self.t1_match > 0 and self.t1_cnt >= self.t1_match:
                matches = self.t1_cnt // self.t1_match
                self.t1_time = (self.t1_time + matches) & 0xFFFFFFFF
                self.t1_cnt = self.t1_cnt % self.t1_match  # Излишек сохраняется в счетчике
                self.tsr |= (1 << 7)  # T1_IF
                if (self.tsr & (1 << 11)) and (self.freg & (1 << 9)) and not (self.freg & (1 << 15)):
                    self.trigger_irq(12)

        # 2. Таймер 2 (T2_EN = bit 14 TSR): Periodic Down-counter
        if self.tsr & (1 << 14):
            if self.t2_reload > 0:
                if self.t2_cnt > cycles:
                    self.t2_cnt -= cycles
                else:
                    excess = cycles - self.t2_cnt
                    rem = excess % self.t2_reload
                    self.t2_cnt = self.t2_reload if rem == 0 else (self.t2_reload - rem)
                    self.tsr |= (1 << 6)  # T2_IF
                    if (self.tsr & (1 << 10)) and (self.freg & (1 << 9)) and not (self.freg & (1 << 15)):
                        self.trigger_irq(13)
            elif self.t2_cnt > 0:
                self.t2_cnt = max(0, self.t2_cnt - cycles)

        # 3. Таймер 3 (T3_EN = bit 13 TSR, разовый / one-shot):
        if self.tsr & (1 << 13):
            if self.t3_cnt > cycles:
                self.t3_cnt -= cycles
            else:
                self.t3_cnt = 0
                self.tsr &= ~(1 << 13)  # Автоматическая остановка: сброс T3_EN
                self.tsr |= (1 << 5)   # T3_IF
                if (self.tsr & (1 << 9)) and (self.freg & (1 << 9)) and not (self.freg & (1 << 15)):
                    self.trigger_irq(14)

        # 4. Таймер 4 (T4_EN = bit 12 TSR, квантователь инструкций):
        # Декрементируется строго на 1 за каждую ЗАВЕРШЕННУЮ инструкцию процессора!
        if self.tsr & (1 << 12):
            if self.t4_cnt > 0:
                self.t4_cnt = (self.t4_cnt - 1) & 0xFFFF
            if self.t4_cnt == 0:
                self.t4_cnt = self.t4_reload & 0xFFFF
                self.tsr |= (1 << 4)  # T4_IF
                if (self.tsr & (1 << 8)) and (self.freg & (1 << 9)) and not (self.freg & (1 << 15)):
                    self.trigger_irq(15)

    def _update_flags(self, result: int):
        """Обновляет флаги ZF, CF, OF в регистре FREG."""
        zf = 1 if (result & 0xFFFF) == 0 else 0
        cf = 1 if (result > 0xFFFF or result < 0) else 0
        of = 1 if (result > 32767 or result < -32768) else 0
        self.freg = (self.freg & ~0x07) | (of << 2) | (cf << 1) | zf


def create_lim2_cpu(bus: Optional[MemoryBus] = None) -> LIM2CPU:
    """Фабричная функция создания процессора LIM M2."""
    b = bus if bus is not None else MemoryBus()
    cpu = LIM2CPU(name="LIM M2", bus=b)
    return cpu


def main():
    """
    Главная точка входа для запуска симулятора процессора LIM M2.
    """
    import sys

    bus = MemoryBus()
    bus.attach(RAMDevice(start=0x000000, end=0x0FFFFF, file="drive.bin", persist=True, name="NVM1"))
    bus.attach(RAMDevice(start=0x100000, end=0x1FFFFF, name="RAM1"))

    cpu = LIM2CPU(bus=bus)
    interactive = "-i" in sys.argv or "--interactive" in sys.argv
    gui = "-g" in sys.argv or "--gui" in sys.argv

    speed = 0.0
    max_steps = None
    for idx, arg in enumerate(sys.argv):
        if arg in ("-s", "--speed", "--delay", "-ss", "--simulation-speed") and idx + 1 < len(sys.argv):
            try:
                speed = float(sys.argv[idx + 1])
            except ValueError:
                pass
        elif arg.startswith("--speed=") or arg.startswith("--delay=") or arg.startswith("-s="):
            try:
                speed = float(arg.split("=")[1])
            except ValueError:
                pass
        elif arg in ("-n", "--steps", "--max-steps") and idx + 1 < len(sys.argv):
            try:
                max_steps = int(sys.argv[idx + 1], 0)
            except ValueError:
                pass
        elif arg.startswith("--steps=") or arg.startswith("-n=") or arg.startswith("--max-steps="):
            try:
                max_steps = int(arg.split("=")[1], 0)
            except ValueError:
                pass

    run_sim(cpu, interactive=interactive, gui=gui, speed=speed, max_steps=max_steps)


if __name__ == "__main__":
    main()
