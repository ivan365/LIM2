#!/usr/bin/env python3
# ==============================================================================
# LIM2 / sim / bus.py — Универсальная шина памяти и устройств
# ==============================================================================
import os
import re
from typing import Dict, List, Optional, Tuple, Union, Callable, Any

try:
    from .devices import BaseDevice, RAMDevice, ROMDevice, TextScreenDevice, UARTDevice, TimerDevice
except (ImportError, ValueError):
    from devices import BaseDevice, RAMDevice, ROMDevice, TextScreenDevice, UARTDevice, TimerDevice


class Pin:
    """Одиночная сигнальная линия (ножка) с поддержкой стробов и коллбэков."""
    def __init__(self, name: str, default: int = 0, mode: str = "IO", title: Optional[str] = None):
        self.name = name
        self.mode = mode.upper()  # "IN", "OUT", "IO"
        self.title = title or name
        self._val = default & 1
        self._listeners: List[Callable[[int], None]] = []

    def set(self, val: int):
        new_val = 1 if val else 0
        if self._val != new_val:
            self._val = new_val
            for cb in self._listeners:
                cb(new_val)

    def get(self) -> int:
        return self._val

    def pulse(self):
        """Короткий импульс: 1 -> 0."""
        self.set(1)
        self.set(0)

    def listen(self, cb: Callable[[int], None]):
        self._listeners.append(cb)

    def __bool__(self) -> bool:
        return bool(self._val)

    def __int__(self) -> int:
        return self._val

    def __index__(self) -> int:
        return self._val

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, int):
            return self._val == other
        if isinstance(other, Pin):
            return self._val == other._val
        if isinstance(other, bool):
            return bool(self._val) is other
        return False

    def __ne__(self, other: Any) -> bool:
        return not self.__eq__(other)

    def __repr__(self) -> str:
        return f"Pin({self.name}={self._val}, mode={self.mode})"


class PinBank:
    """Банк ножек шины процессора (RD, WR, MREQ, IORQ, CS, IRQ, IA и любые кастомные)."""
    def __init__(self):
        self._pins: Dict[str, Pin] = {}

    def define(self, name: str, mode: str = "IO", default: int = 0, title: Optional[str] = None) -> Pin:
        uname = name.upper()
        if uname not in self._pins:
            self._pins[uname] = Pin(uname, default=default, mode=mode, title=title)
        else:
            self._pins[uname].mode = mode.upper()
            if title:
                self._pins[uname].title = title
            if default:
                self._pins[uname].set(default)
        return self._pins[uname]

    def __getattr__(self, name: str) -> Pin:
        if name.startswith("_"):
            raise AttributeError(name)
        uname = name.upper()
        if uname not in self._pins:
            self._pins[uname] = Pin(uname)
        return self._pins[uname]

    def __setattr__(self, name: str, val: Any):
        if name.startswith("_"):
            super().__setattr__(name, val)
        else:
            uname = name.upper()
            if uname not in self._pins:
                self._pins[uname] = Pin(uname)
            self._pins[uname].set(int(val))

    def __getitem__(self, name: str) -> int:
        return int(getattr(self, name.upper()))

    def __setitem__(self, name: str, val: int):
        setattr(self, name.upper(), val)

    def __contains__(self, name: str) -> bool:
        return name.upper() in self._pins


class MemoryFrame(BaseDevice):
    """
    Устройство памяти / дисплея / буфера, совместимое с полным визуальным TUI.
    """
    def __init__(
        self,
        start_add: int,
        end_add: int,
        name: str = "DEV",
        readonly: bool = False,
        is_video: bool = False,
        width: int = 0,
        height: int = 0,
        on_write: Any = None,
        latency: int = 0,
        ready_pin: str = "RF",
        default_data: Any = None,
        default_offset: int = 0
    ):
        if isinstance(name, bool) and isinstance(readonly, str):
            name, readonly = readonly, name

        super().__init__(
            start=start_add,
            end=end_add,
            name=name,
            readonly=bool(readonly),
            is_video=is_video,
            width=width,
            height=height,
            latency=latency,
            ready_pin=ready_pin,
            default_data=default_data,
            default_offset=default_offset
        )
        self.on_write = on_write
        self.bus: Any = None
        self._last_modified_step: Dict[int, int] = {}
        self._last_accessed_offset: int = 0
        self.orphaned_bytes: int = 0
        self.orphaned_range: Optional[Tuple[int, int]] = None
        self.data_ranges: List[dict] = []
        self.annotations: Dict[int, str] = {}

    def read_phys(self, address: int) -> int:
        idx = address - self.start
        if 0 <= idx < self.size:
            self._last_accessed_offset = idx
            return self._raw[idx]
        return 0

    def write_phys(self, address: int, value: int):
        if self.readonly:
            return
        idx = address - self.start
        if 0 <= idx < self.size:
            val8 = value & 0xFF
            self._raw[idx] = val8
            self._last_accessed_offset = idx
            cur_st = getattr(self.bus, "current_step", 0)
            self._last_modified_step[idx] = cur_st
            if self.on_write is not None:
                self.on_write(self, address, val8)

    read_physical = read_phys
    write_physical = write_phys

    def read_raw(self, offset: int) -> int:
        return self._raw[offset] if 0 <= offset < self.size else 0

    def write_raw(self, offset: int, value: int):
        if 0 <= offset < self.size:
            self._raw[offset] = value & 0xFF

    def flash(self, data: Union[List[int], bytes, bytearray], offset: int = 0):
        for i, val in enumerate(data):
            target = offset + i
            if target < self.size:
                self._raw[target] = val & 0xFF

    def is_data_offset(self, offset: int) -> Tuple[bool, Optional[dict]]:
        for r in getattr(self, "data_ranges", []):
            if r['start'] <= offset < r['end']:
                return True, r
        return False, None

    def dump(self) -> bytes:
        return bytes(self._raw)

    def render_screen(self) -> str:
        """Отрисовка физического монитора в рамке."""
        if not self.is_video or self.width <= 0 or self.height <= 0:
            return ""
        w = max(80, self.width + 6)
        title = f"{self.name} MONITOR ({self.width}x{self.height}) @ 0x{self.start:04X}"
        side_info = [
            f"Разрешение: {self.width}x{self.height} ({self.size} байт)",
            f"Диапазон: 0x{self.start:04X}..0x{self.end:04X}"
        ]
        lines = [f"┌── [{title}] " + ("─" * max(0, w - 8 - len(title))) + "┐"]
        top_side = f"  {side_info[0]}" if len(side_info) > 0 else ""
        inner_top = f"╔{'═' * self.width}╗{top_side}"
        lines.append(f"│ {inner_top:<{w - 4}} │")

        for row in range(self.height):
            chars = []
            for col in range(self.width):
                offset = row * self.width + col
                if offset < self.size:
                    b = self._raw[offset]
                    chars.append(chr(b) if 32 <= b <= 126 else (" " if b == 0 else "·"))
                else:
                    chars.append(" ")
            row_str = "".join(chars)
            side_txt = f"  {side_info[row + 1]}" if (row + 1) < len(side_info) else ""
            inner_row = f"║{row_str}║{side_txt}"
            lines.append(f"│ {inner_row:<{w - 4}} │")

        inner_bot = f"╚{'═' * self.width}╝"
        lines.append(f"│ {inner_bot:<{w - 4}} │")
        lines.append("└" + ("─" * (w - 2)) + "┘")
        return "\n".join(lines)

    def format_windowed_hexdump(
        self,
        center_offset: Optional[int] = None,
        window_rows: int = 4,
        current_step: int = 0,
        pc_addr: Optional[int] = None,
        start_row_override: Optional[int] = None
    ) -> str:
        """Форматирует окно памяти со стабильным числом строк."""
        if self.size == 0:
            return "(память пуста)"

        total_dev_rows = (self.size + 15) // 16
        if center_offset is None:
            center_offset = self._last_accessed_offset
        center_offset = max(0, min(self.size - 1, center_offset))
        center_row = center_offset // 16

        w_rows = max(1, min(total_dev_rows, window_rows))
        if start_row_override is not None:
            start_row = max(0, min(total_dev_rows - w_rows, start_row_override))
        else:
            start_row = max(0, min(total_dev_rows - w_rows, center_row - w_rows // 2))
        end_row = start_row + w_rows

        fmt = "06X" if self.end > 0xFFFF else "04X"
        lines = []
        if start_row > 0:
            lines.append(f"... [пропущено 0x{self.start:{fmt}}..0x{self.start + start_row * 16 - 1:{fmt}}] ...")
        else:
            lines.append(f"... [0x{self.start:{fmt}} начало памяти] ...")

        for r in range(start_row, end_row):
            row_start = r * 16
            hex_left, hex_right, ascii_parts = [], [], []
            for i in range(16):
                off = row_start + i
                if off < self.size:
                    val = self._raw[off]
                    is_pc_byte = (pc_addr is not None and self.start + off == pc_addr)
                    if is_pc_byte:
                        c_pre, c_suf = "\033[7;1m", "\033[0m"
                    elif val != 0:
                        c_pre, c_suf = "\033[36m", "\033[0m"
                    else:
                        c_pre, c_suf = "\033[90m", "\033[0m"
                    token = f"{c_pre}{val:02X}{c_suf}"
                    ch = chr(val) if 32 <= val <= 126 else "."
                    ascii_parts.append(f"{c_pre}{ch}{c_suf}")
                else:
                    token = "  "
                    ascii_parts.append(" ")

                if i < 8:
                    hex_left.append(token)
                else:
                    hex_right.append(token)

            h_l = " ".join(hex_left)
            h_r = " ".join(hex_right)
            a_s = "".join(ascii_parts)
            addr_val = self.start + row_start
            if self.end > 0xFFFF:
                lines.append(f"0x{addr_val:06X}: {h_l} {h_r} |{a_s}|")
            else:
                lines.append(f"0x{addr_val:04X}: {h_l}  {h_r}  |{a_s}|")

        if end_row < total_dev_rows:
            lines.append(f"... [пропущено 0x{self.start + end_row * 16:{fmt}}..0x{self.end:{fmt}}] ...")
        else:
            lines.append(f"... [0x{self.end:{fmt}} конец памяти] ...")

        return "\n".join(lines)


class MemoryBus:
    """
    Универсальная шина памяти для симулятора с поддержкой нескольких режимов
    и строгой физической симуляцией линий управления (RD, WR, MREQ, IORQ, ножек адреса и данных).
    """

    def __init__(self, size: int = 65536, address_bits: int = 32, data_bits: int = 8, mode: str = "32bit"):
        self.mode = mode.lower()  # "16bit", "24bit" или "32bit"
        if "16" in self.mode:
            self.address_bits = 16
        elif "24" in self.mode:
            self.address_bits = 24
        else:
            self.address_bits = address_bits
        self.data_bits = data_bits
        self.mask = (1 << self.address_bits) - 1
        self.size = size if size != 65536 or self.address_bits == 16 else (1 << min(self.address_bits, 24))
        self.ram = bytearray(min(self.size, 16 * 1024 * 1024))
        self.pins = PinBank()
        self.devices: List[Tuple[int, int, str, Callable[[int], int], Callable[[int, int], None], Optional[Any]]] = []
        self.devices_by_name: Dict[str, Any] = {}
        self._devices_list: List[Any] = []
        self.current_step: int = 0
        self.cpu: Optional[Any] = None

        # Физические шины адреса и данных
        self._addressbus: int = 0
        self._databus: int = 0

        # Мониторинг конфликтов (Bus Contention)
        self.collision_warnings: List[str] = []
        self.last_collision: Optional[str] = None
        self.on_collision: Optional[Callable[[str], None]] = None

        # Подключение обработчиков аппаратных стробов RD и WR
        self.pins.RD.listen(self._on_pin_rd_change)
        self.pins.WR.listen(self._on_pin_wr_change)

    # --------------------------------------------------------------------------
    # Физические шины: Address Bus и Data Bus
    # --------------------------------------------------------------------------
    @property
    def addressbus(self) -> int:
        return self._addressbus

    @addressbus.setter
    def addressbus(self, val: int):
        val &= self.mask
        self._addressbus = val
        if self.cpu is not None and getattr(self.cpu, "_addressbus", None) != val:
            self.cpu._addressbus = val
        # Если сигнал чтения уже поднят на ножке, смена адреса немедленно меняет данные на шине
        if self.pins.RD.get() == 1:
            self._update_read_databus()

    @property
    def address(self) -> int:
        return self._addressbus

    @address.setter
    def address(self, val: int):
        self.addressbus = val

    @property
    def databus(self) -> int:
        return self._databus

    @databus.setter
    def databus(self, val: int):
        val &= 0xFF
        self._databus = val
        if self.cpu is not None and getattr(self.cpu, "_databus", None) != val:
            self.cpu._databus = val
        # Если сигнал записи уже активен, смена данных фиксируется адресуемым устройством
        if self.pins.WR.get() == 1:
            self._update_write_latch()

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if hasattr(self, "pins"):
            uname = name.upper()
            if uname in ("RD", "WR", "MREQ", "IORQ", "IRQ", "IA", "RF", "HALT", "RESET", "CS") or (hasattr(self.pins, "_pins") and uname in self.pins._pins):
                return getattr(self.pins, uname)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any):
        if name.startswith("_") or name in (
            "mode", "address_bits", "data_bits", "mask", "size", "ram", "pins",
            "devices", "devices_by_name", "_devices_list", "current_step", "cpu",
            "collision_warnings", "last_collision", "on_collision", "addressbus", "address", "databus"
        ):
            super().__setattr__(name, value)
            return
        uname = name.upper()
        if hasattr(self, "pins") and (uname in ("RD", "WR", "MREQ", "IORQ", "IRQ", "IA", "RF", "HALT", "RESET", "CS") or (hasattr(self.pins, "_pins") and uname in self.pins._pins)):
            if isinstance(value, (int, bool)):
                getattr(self.pins, uname).set(int(value))
                return
        super().__setattr__(name, value)

    # --------------------------------------------------------------------------
    # Определение активных устройств и детектирование аппаратных конфликтов
    # --------------------------------------------------------------------------
    def get_matching_devices(self, addr: int) -> List[Tuple[str, Callable[[], int], Callable[[int], None], Any]]:
        """
        Возвращает список всех активных устройств, подключенных к физическому адресу addr.
        Каждый элемент кортежа: (name, read_fn, write_fn, dev_obj)
        """
        addr &= self.mask
        matched = []
        seen_objs = set()

        for dev in self._devices_list:
            if dev.start <= addr <= dev.end:
                seen_objs.add(id(dev))
                name = getattr(dev, "name", "DEV")
                r_fn = lambda d=dev, a=addr: d.read_phys(a) if hasattr(d, "read_phys") else (d.read(a - d.start) if hasattr(d, "read") else 0)
                w_fn = lambda v, d=dev, a=addr: d.write_phys(a, v) if hasattr(d, "write_phys") else (d.write(a - d.start, v) if hasattr(d, "write") else None)
                matched.append((name, r_fn, w_fn, dev))

        for start, end, name, read_fn, write_fn, dev_obj in self.devices:
            if start <= addr <= end:
                if dev_obj is not None and id(dev_obj) in seen_objs:
                    continue
                if dev_obj is not None:
                    seen_objs.add(id(dev_obj))
                r_fn = lambda rf=read_fn, st=start, a=addr: rf(a - st)
                w_fn = lambda v, wf=write_fn, st=start, a=addr: wf(a - st, v)
                matched.append((name, r_fn, w_fn, dev_obj))

        return matched

    def _record_collision(self, warning: str):
        self.last_collision = warning
        self.collision_warnings.append(warning)
        if len(self.collision_warnings) > 100:
            self.collision_warnings.pop(0)
        if self.on_collision is not None:
            try:
                self.on_collision(warning)
            except Exception:
                pass
        print(f"\033[91m{warning}\033[0m")

    def _on_pin_rd_change(self, val: int):
        if val == 1:
            self._update_read_databus()

    def _update_read_databus(self):
        """
        Физический такт чтения: устройство(а) выставляют данные на шину данных databus.
        Чтение происходит ТОЛЬКО при наличии строба RD = 1.
        Если к одной линии адреса одновременно обращаются несколько устройств,
        фиксируется аппаратный конфликт (Bus Contention).
        """
        addr = self._addressbus
        matched = self.get_matching_devices(addr)
        # Опрашиваем устройства: None означает третье состояние (Hi-Z, шина не нагружена)
        active_drivers = []
        for d_name, r_fn, _, _ in matched:
            v = r_fn()
            if v is not None:
                active_drivers.append((d_name, v & 0xFF))

        if len(active_drivers) > 1:
            dev_names = [d[0] for d in active_drivers]
            warning = (
                f"⚠️ [КОНФЛИКТ ШИНЫ / BUS CONTENTION]: Несколько устройств одновременно "
                f"выдают данные на шину данных по адресу 0x{addr:06X} (устройства: {', '.join(dev_names)})"
            )
            self._record_collision(warning)
            # При аппаратном конфликте сигналы нескольких драйверов накладываются (open-collector AND):
            resolved = active_drivers[0][1]
            for _, val in active_drivers[1:]:
                resolved &= val
            self._databus = resolved
        elif len(active_drivers) == 1:
            self._databus = active_drivers[0][1]
        else:
            if addr < len(self.ram) and not matched:
                self._databus = self.ram[addr]
            else:
                self._databus = 0xFF  # Подтяжка висящей в воздухе шины (Floating bus pull-up)

        # Вызов пользовательского хука прямого управления шиной (максимальный приоритет)
        for dev in list(self._devices_list):
            if hasattr(dev, "on_bus_cycle"):
                dev.on_bus_cycle(self)

    def _on_pin_wr_change(self, val: int):
        if val == 1:
            self._update_write_latch()

    def _update_write_latch(self):
        """
        Физический такт записи: устройство(а) фиксируют (latch) данные с шины databus.
        Запись в память происходит ТОЛЬКО когда на ножке WR выставлена логическая 1.
        """
        addr = self._addressbus
        val = self._databus
        matched = self.get_matching_devices(addr)

        # Вызов пользовательского хука прямого управления шиной
        for dev in list(self._devices_list):
            if hasattr(dev, "on_bus_cycle"):
                dev.on_bus_cycle(self)

        if len(matched) > 1:
            dev_names = [d[0] for d in matched]
            warning = (
                f"⚠️ [КОНФЛИКТ ШИНЫ / BUS CONTENTION]: Попытка одновременной записи нескольких "
                f"устройств по адресу 0x{addr:06X} (устройства: {', '.join(dev_names)})"
            )
            self._record_collision(warning)
            for _, _, w_fn, _ in matched:
                w_fn(val)
        elif len(matched) == 1:
            _, _, w_fn, _ = matched[0]
            w_fn(val)
        else:
            if addr < len(self.ram):
                self.ram[addr] = val

    # --------------------------------------------------------------------------
    # Физические такты шины (Physical Bus Cycles)
    # --------------------------------------------------------------------------
    def read_cycle(self, addr: int) -> int:
        """
        Выполняет физический цикл чтения:
          1. Выставляет адрес на шину адреса.
          2. Поднимает сигналы MREQ = 1 и RD = 1 (WR = 0).
          3. Устройство(а) выставляют данные на databus.
          4. Считывает байт с шины databus.
          5. Сбрасывает сигналы RD и MREQ в 0.
        """
        addr &= self.mask
        self.addressbus = addr
        self.pins.MREQ.set(1)
        self.pins.WR.set(0)
        self.pins.RD.set(1)
        data = self._databus
        self.pins.RD.set(0)
        self.pins.MREQ.set(0)
        return data

    def write_cycle(self, addr: int, val: int):
        """
        Выполняет физический цикл записи:
          1. Выставляет адрес на шину адреса.
          2. Выставляет данные на шину данных databus.
          3. Поднимает сигналы MREQ = 1 и WR = 1 (RD = 0).
          4. Адресуемое устройство(а) или ОЗУ фиксируют данные.
          5. Сбрасывает сигналы WR и MREQ в 0.
        """
        addr &= self.mask
        val &= 0xFF
        self.addressbus = addr
        self.databus = val
        self.pins.MREQ.set(1)
        self.pins.RD.set(0)
        self.pins.WR.set(1)
        self.pins.WR.set(0)
        self.pins.MREQ.set(0)

    # --------------------------------------------------------------------------
    # Неинвазивный доступ (для GUI, TUI, отладчика без стробов и конфликтов)
    # --------------------------------------------------------------------------
    def peek(self, addr: int) -> int:
        """
        Неинвазивное чтение одного байта памяти (для отладчика, UI, дизассемблера).
        НЕ дергает сигнальные ножки шины (RD/WR/MREQ), не вызывает side-effects
        и не порождает предупреждений о конфликтах шины при инспекции.
        """
        addr &= self.mask
        for dev in self._devices_list:
            if dev.start <= addr <= dev.end:
                if hasattr(dev, "read_raw"):
                    return dev.read_raw(addr - dev.start) & 0xFF
                if hasattr(dev, "read_phys"):
                    return dev.read_phys(addr) & 0xFF
                if hasattr(dev, "read"):
                    return dev.read(addr - dev.start) & 0xFF
        for start, end, _, read_fn, _, _ in self.devices:
            if start <= addr <= end:
                return read_fn(addr - start) & 0xFF
        if addr < len(self.ram):
            return self.ram[addr]
        return 0

    def poke(self, addr: int, val: int):
        """
        Неинвазивная прямая запись байта (для отладчика/загрузчика памяти).
        """
        addr &= self.mask
        val &= 0xFF
        for dev in self._devices_list:
            if dev.start <= addr <= dev.end:
                if hasattr(dev, "write_raw"):
                    dev.write_raw(addr - dev.start, val)
                    return
                if hasattr(dev, "write_phys"):
                    dev.write_phys(addr, val)
                    return
                if hasattr(dev, "write"):
                    dev.write(addr - dev.start, val)
                    return
        for start, end, _, _, write_fn, _ in self.devices:
            if start <= addr <= end:
                write_fn(addr - start, val)
                return
        if addr < len(self.ram):
            self.ram[addr] = val

    def peek16(self, addr: int, little_endian: bool = True) -> int:
        b0 = self.peek(addr)
        b1 = self.peek(addr + 1)
        return (b1 << 8) | b0 if little_endian else (b0 << 8) | b1

    def peek32(self, addr: int, little_endian: bool = True) -> int:
        b0 = self.peek(addr)
        b1 = self.peek(addr + 1)
        b2 = self.peek(addr + 2)
        b3 = self.peek(addr + 3)
        if little_endian:
            return (b3 << 24) | (b2 << 16) | (b1 << 8) | b0
        return (b0 << 24) | (b1 << 16) | (b2 << 8) | b3

    def set_mode(self, mode: str):
        """Переключение режима работы шины ('16bit' / '24bit' / '32bit')."""
        self.mode = mode.lower()
        if "32" in self.mode:
            self.address_bits = 32
            self.mask = 0xFFFFFFFF
            if len(self.ram) < 1048576:
                self.ram.extend(bytearray(1048576 - len(self.ram)))
        elif "24" in self.mode:
            self.address_bits = 24
            self.mask = 0xFFFFFF
            if len(self.ram) < 1048576:
                self.ram.extend(bytearray(1048576 - len(self.ram)))
        else:
            self.address_bits = 16
            self.mask = 0xFFFF

    @property
    def busbits(self) -> int:
        return self.address_bits

    @property
    def _devices(self) -> List[Any]:
        return self._devices_list

    def read8(self, addr: int, physical: bool = True) -> int:
        """
        Чтение одного байта памяти.
        В физическом режиме (physical=True) выполняет физический цикл со стробом RD=1.
        """
        if not physical:
            return self.peek(addr)
        return self.read_cycle(addr)

    def write8(self, addr: int, val: int, physical: bool = True):
        """
        Запись одного байта памяти.
        В физическом режиме (physical=True) выполняет физический цикл со стробом WR=1.
        """
        if not physical:
            self.poke(addr, val)
            return
        self.write_cycle(addr, val)

    def read16(self, addr: int, little_endian: bool = True, physical: bool = True) -> int:
        """Чтение 16-битного слова."""
        b0 = self.read8(addr, physical=physical)
        b1 = self.read8(addr + 1, physical=physical)
        if little_endian:
            return (b1 << 8) | b0
        return (b0 << 8) | b1

    def write16(self, addr: int, val: int, little_endian: bool = True, physical: bool = True):
        """Запись 16-битного слова."""
        val &= 0xFFFF
        if little_endian:
            self.write8(addr, val & 0xFF, physical=physical)
            self.write8(addr + 1, (val >> 8) & 0xFF, physical=physical)
        else:
            self.write8(addr, (val >> 8) & 0xFF, physical=physical)
            self.write8(addr + 1, val & 0xFF, physical=physical)

    def read32(self, addr: int, little_endian: bool = True, physical: bool = True) -> int:
        """Чтение 32-битного двойного слова."""
        b0 = self.read8(addr, physical=physical)
        b1 = self.read8(addr + 1, physical=physical)
        b2 = self.read8(addr + 2, physical=physical)
        b3 = self.read8(addr + 3, physical=physical)
        if little_endian:
            return (b3 << 24) | (b2 << 16) | (b1 << 8) | b0
        return (b0 << 24) | (b1 << 16) | (b2 << 8) | b3

    def write32(self, addr: int, val: int, little_endian: bool = True, physical: bool = True):
        """Запись 32-битного двойного слова."""
        val &= 0xFFFFFFFF
        if little_endian:
            self.write8(addr, val & 0xFF, physical=physical)
            self.write8(addr + 1, (val >> 8) & 0xFF, physical=physical)
            self.write8(addr + 2, (val >> 16) & 0xFF, physical=physical)
            self.write8(addr + 3, (val >> 24) & 0xFF, physical=physical)
        else:
            self.write8(addr, (val >> 24) & 0xFF, physical=physical)
            self.write8(addr + 1, (val >> 16) & 0xFF, physical=physical)
            self.write8(addr + 2, (val >> 8) & 0xFF, physical=physical)
            self.write8(addr + 3, val & 0xFF, physical=physical)

    # --------------------------------------------------------------------------
    # Подключение устройств (MMIO)
    # --------------------------------------------------------------------------
    def attach(self, device: Any) -> Any:
        """
        Подключает устройство (BaseDevice, MemoryFrame или совместимый объект) к шине.
        """
        device.bus = self
        if hasattr(device, "on_attach"):
            device.on_attach(self)
        if device not in self._devices_list:
            self._devices_list.append(device)
        self.devices_by_name[device.name] = device

        r_fn = getattr(device, "read", lambda off: device.read_phys(device.start + off) if hasattr(device, "read_phys") else 0)
        w_fn = getattr(device, "write", lambda off, val: device.write_phys(device.start + off, val) if hasattr(device, "write_phys") else None)
        self.devices.append((device.start, device.end, device.name, r_fn, w_fn, device))
        return device

    def detach(self, device: Any):
        """Отключает устройство от шины."""
        if device in self._devices_list:
            self._devices_list.remove(device)
        name = getattr(device, "name", None)
        if name in self.devices_by_name:
            del self.devices_by_name[name]
        self.devices = [d for d in self.devices if d[5] is not device]

    def tick(self, step_count: Optional[int] = None):
        """
        Такт шины: продвигает шаг и вызывает on_step() / on_tick()
        у всех подключенных устройств.
        """
        if step_count is not None:
            self.current_step = step_count
        else:
            self.current_step += 1

        for dev in list(self._devices_list):
            if hasattr(dev, "on_step"):
                dev.on_step()
            elif hasattr(dev, "on_tick"):
                dev.on_tick()

    def add_device(
        self,
        start: int,
        end: int,
        name: str,
        read_fn: Optional[Callable[[int], int]] = None,
        write_fn: Optional[Callable[[int, int], None]] = None,
        device: Optional[Any] = None
    ):
        """
        Подключает устройство к диапазону [start..end].
        Можно передать объект с методами read(offset) / write(offset, val)
        или отдельные функции.
        """
        dev_obj = device
        if dev_obj is not None:
            if read_fn is None and hasattr(dev_obj, "read"):
                read_fn = getattr(dev_obj, "read")
            if write_fn is None and hasattr(dev_obj, "write"):
                write_fn = getattr(dev_obj, "write")

        if dev_obj is not None and isinstance(dev_obj, (bytearray, list)):
            if read_fn is None:
                read_fn = lambda off: dev_obj[off] if 0 <= off < len(dev_obj) else 0
            if write_fn is None:
                write_fn = lambda off, val: dev_obj.__setitem__(off, val) if 0 <= off < len(dev_obj) else None

        r_fn = read_fn if read_fn is not None else (lambda off: 0)
        w_fn = write_fn if write_fn is not None else (lambda off, val: None)

        if dev_obj is not None and hasattr(dev_obj, "start") and hasattr(dev_obj, "end"):
            dev_obj.bus = self
            if hasattr(dev_obj, "on_attach"):
                dev_obj.on_attach(self)
            if dev_obj not in self._devices_list:
                self._devices_list.append(dev_obj)
        elif isinstance(dev_obj, MemoryFrame):
            dev_obj.bus = self
            if dev_obj not in self._devices_list:
                self._devices_list.append(dev_obj)

        self.devices.append((start, end, name, r_fn, w_fn, dev_obj))
        self.devices_by_name[name] = dev_obj if dev_obj is not None else {"read": r_fn, "write": w_fn}

    def create_dev(
        self,
        start: int,
        end: int,
        name: str = "DEV",
        readonly: bool = False,
        is_video: bool = False,
        width: int = 0,
        height: int = 0,
        on_write: Any = None,
        latency: int = 0,
        ready_pin: str = "RF",
        default_data: Any = None,
        default_offset: int = 0
    ) -> MemoryFrame:
        """Создает и регистрирует MemoryFrame устройство на шине."""
        dev = MemoryFrame(
            start_add=start,
            end_add=end,
            name=name,
            readonly=readonly,
            is_video=is_video,
            width=width,
            height=height,
            on_write=on_write,
            latency=latency,
            ready_pin=ready_pin,
            default_data=default_data,
            default_offset=default_offset
        )
        self.attach(dev)
        return dev

    def device(self, start: int, end: int, name: Optional[str] = None):
        """Декоратор для простого создания устройств."""
        def decorator(cls_or_fn):
            dev_name = name or getattr(cls_or_fn, "__name__", f"dev_{start:04X}").lower()
            if isinstance(cls_or_fn, type):
                instance = cls_or_fn()
                self.add_device(start=start, end=end, name=dev_name, device=instance)
                return instance
            else:
                self.add_device(start=start, end=end, name=dev_name, device=cls_or_fn)
                return cls_or_fn
        return decorator

    def cycle(self, addr: Optional[int] = None, data: Optional[int] = None, **pins) -> Optional[int]:
        """
        Прямой такт шины с ручным контролем сигналов и ножек (RD, WR, ALE, IORQ и др.).
        """
        for p_name, p_val in pins.items():
            setattr(self.pins, p_name, p_val)

        if addr is not None:
            self.address = addr & self.mask

        if self.pins.WR or pins.get("write") or pins.get("WR"):
            if addr is not None and data is not None:
                self.write8(addr, data)
            return None

        if self.pins.RD or pins.get("read") or pins.get("RD"):
            if addr is not None:
                return self.read8(addr)
        return None

    def read_handshake(self, addr: int, timeout: int = 100) -> Tuple[int, int]:
        """
        Чтение с аппаратным рукопожатием (Handshake) и ожиданием ножки готовности:
          1. Процессор выставляет адрес и поднимает ножку RD=1.
          2. Устройство принимает запрос; если у него есть latency > 0, сбрасывает RF=0.
          3. Шина тикает (bus.tick()), симулируя такты ожидания (Wait States).
          4. Когда память отсчитала задержку, она поднимает ножку RF=1.
          5. Процессор считывает байт данных и сбрасывает ножку RD=0.
        Возвращает: (значение_байта, количество_тактов_ожидания)
        """
        addr &= self.mask
        self.pins.RD.set(1)

        target_dev = None
        for dev in self._devices_list:
            if dev.start <= addr <= dev.end:
                target_dev = dev
                break

        ready_pin_name = getattr(target_dev, "ready_pin", "RF")
        wait_cycles = 0

        if target_dev is not None and hasattr(target_dev, "start_read"):
            target_dev.start_read(addr - target_dev.start)

        ready_pin = getattr(self.pins, ready_pin_name)
        while not ready_pin.get() and wait_cycles < timeout:
            self.tick()
            wait_cycles += 1

        data = self.read8(addr)
        self.pins.RD.set(0)
        return data, wait_cycles

    def write_handshake(self, addr: int, val: int, timeout: int = 100) -> int:
        """
        Запись с аппаратным рукопожатием и ожиданием ножки готовности.
        Возвращает: количество_тактов_ожидания
        """
        addr &= self.mask
        val &= 0xFF
        self.pins.WR.set(1)

        target_dev = None
        for dev in self._devices_list:
            if dev.start <= addr <= dev.end:
                target_dev = dev
                break

        ready_pin_name = getattr(target_dev, "ready_pin", "RF")
        wait_cycles = 0

        if target_dev is not None and hasattr(target_dev, "start_write"):
            target_dev.start_write(addr - target_dev.start, val)
        else:
            self.write8(addr, val)

        ready_pin = getattr(self.pins, ready_pin_name)
        while not ready_pin.get() and wait_cycles < timeout:
            self.tick()
            wait_cycles += 1

        self.pins.WR.set(0)
        return wait_cycles

    # --------------------------------------------------------------------------
    # Загрузка бинарных данных и дампов
    # --------------------------------------------------------------------------
    def load_bin(self, source: Union[str, bytes, bytearray], at: int = 0x0000) -> int:
        """Загружает бинарный файл или байты в память."""
        if isinstance(source, str):
            with open(source, "rb") as f:
                data = f.read()
        else:
            data = bytes(source)

        for i, b in enumerate(data):
            self.write8(at + i, b)
        return len(data)

    def load_hex(self, source: str, at: Optional[int] = None) -> int:
        """Загружает файл .hex (Intel HEX) или текстовый шестнадцатеричный дамп."""
        if os.path.exists(source):
            with open(source, "r", encoding="utf-8") as f:
                text = f.read()
        else:
            text = source

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        total = 0

        # Intel HEX
        if any(line.startswith(":") for line in lines):
            base_upper = 0
            for line in lines:
                if not line.startswith(":"):
                    continue
                count = int(line[1:3], 16)
                addr = int(line[3:7], 16)
                rtype = int(line[7:9], 16)
                data_hex = line[9:9 + count * 2]

                if rtype == 0x00:
                    target = base_upper + addr
                    for i in range(count):
                        self.write8(target + i, int(data_hex[i * 2:(i + 1) * 2], 16))
                        total += 1
                elif rtype == 0x01:
                    break
                elif rtype == 0x04:
                    base_upper = int(data_hex, 16) << 16
            return total

        # Текстовый дамп (например: 0x0100: 12 34 56 78...)
        current = at if at is not None else 0x0000
        for line in lines:
            if ";" in line: line = line.split(";", 1)[0].strip()
            if "#" in line and not line.startswith("#!"): line = line.split("#", 1)[0].strip()
            if not line: continue

            m = re.match(r'^(?:0x)?([0-9a-fA-F]+)\s*:\s*(.*)$', line)
            if m:
                current = int(m.group(1), 16)
                tokens = m.group(2).split()
            else:
                tokens = line.split()

            for tok in tokens:
                clean = tok.strip().lower()
                if clean.startswith("0x"): clean = clean[2:]
                if re.match(r'^[0-9a-f]{2}$', clean):
                    self.write8(current, int(clean, 16))
                    current += 1
                    total += 1
        return total

    def load(self, file_path: str, at: Optional[int] = None) -> int:
        """Автоматически определяет формат (.bin, .hex, .asm) и загружает файл."""
        # Умный поиск файла по возможным стандартным каталогам проекта
        real_path = None
        candidates = [
            file_path,
            os.path.join(os.path.dirname(__file__), file_path),
            os.path.join(os.path.dirname(__file__), "..", "programs_asm", file_path),
            os.path.join(os.path.dirname(__file__), "..", file_path),
            os.path.join(os.getcwd(), file_path),
            os.path.join(os.getcwd(), "LIM2", "programs_asm", file_path),
            os.path.join(os.getcwd(), "LIM2", "sim", file_path),
            os.path.join(os.getcwd(), "programs_asm", file_path),
        ]
        for c in candidates:
            if os.path.isfile(c):
                real_path = os.path.abspath(c)
                break

        if not real_path:
            raise FileNotFoundError(f"Файл '{file_path}' не найден (проверены пути в sim/, programs_asm/ и корне проекта).")
        file_path = real_path

        ext = os.path.splitext(file_path)[1].lower()
        target = at if at is not None else 0x0000

        if ext == ".bin":
            return self.load_bin(file_path, at=target)
        elif ext == ".hex":
            return self.load_hex(file_path, at=at)
        elif ext in (".asm", ".lasm"):
            import importlib.util
            from pathlib import Path
            compiler_dir = Path(__file__).resolve().parent.parent / "compiler"
            lim2_asm_path = compiler_dir / "limasm.py"
            if not lim2_asm_path.exists():
                lim2_asm_path = Path(__file__).resolve().parent / "limasm.py"
            spec = importlib.util.spec_from_file_location("lim2_limasm", lim2_asm_path)
            lim2_asm_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(lim2_asm_mod)
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()
            asm = lim2_asm_mod.LimAssembler(base_address=target)
            bytecode, _ = asm.assemble(code, base_address=target)
            return self.load_bin(bytecode, at=target)
        else:
            return self.load_bin(file_path, at=target)

    def dump(self, start: int = 0x0000, length: int = 32, bytes_per_line: int = 16) -> str:
        """Форматирует участок памяти в красивую шестнадцатеричную таблицу."""
        lines = []
        for offset in range(0, length, bytes_per_line):
            curr = (start + offset) & self.mask
            chunk_len = min(bytes_per_line, length - offset)
            chunk = [self.peek(curr + i) for i in range(chunk_len)]
            hex_str = " ".join(f"{b:02X}" for b in chunk)
            ascii_str = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
            lines.append(f"0x{curr:04X}  {hex_str:<{bytes_per_line * 3}}  |{ascii_str}|")
        return "\n".join(lines)

    # --------------------------------------------------------------------------
    # Долговременное сохранение и восстановление состояния (Long-Term Dump)
    # --------------------------------------------------------------------------
    def save_dump(self, path: str, extra_state: Optional[dict] = None) -> str:
        """
        Сохраняет полный дамп памяти шины, ОЗУ и всех подключенных устройств.
        Если передан extra_state (например регистры CPU), сохраняет полный снимок машины.
        """
        import json
        import time
        state = {
            "version": "LIM2_DUMP_V1",
            "timestamp": time.time(),
            "mode": self.mode,
            "address_bits": self.address_bits,
            "current_step": self.current_step,
            "ram": self.ram.hex(),
            "devices": {}
        }
        for dev in self._devices_list:
            if hasattr(dev, "name") and hasattr(dev, "_raw"):
                state["devices"][dev.name] = {
                    "start": dev.start,
                    "end": dev.end,
                    "data": dev._raw.hex()
                }
        if extra_state:
            state["extra"] = extra_state

        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        return path

    def load_dump(self, path: str) -> dict:
        """
        Загружает дамп памяти. Поддерживает структурированные дампы JSON (.dump),
        дампы регистров и памяти, а также прямые бинарные образы (.bin).
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"Файл дампа '{path}' не найден.")

        with open(path, "rb") as f:
            head = f.read(64)

        if b"LIM2_DUMP" in head or (head.strip().startswith(b"{") and b"version" in head):
            import json
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
            if "ram" in state:
                raw_ram = bytes.fromhex(state["ram"])
                self.ram[:len(raw_ram)] = raw_ram
            if "devices" in state:
                for dev_name, d_info in state["devices"].items():
                    if dev_name in self.devices_by_name:
                        dev = self.devices_by_name[dev_name]
                        if hasattr(dev, "_raw"):
                            dev_bytes = bytes.fromhex(d_info["data"])
                            dev._raw[:len(dev_bytes)] = dev_bytes
            if "mode" in state:
                self.set_mode(state["mode"])
            if "current_step" in state:
                self.current_step = state["current_step"]
            return state.get("extra", {})
        else:
            # Прямой бинарный файл памяти (.bin)
            self.load_bin(path, at=0x0000)
            return {}

    def save_persistent_devices(self) -> List[str]:
        """
        Сохраняет образы всех энергонезависимых устройств (persist=True).
        Возвращает список сохраненных файлов.
        """
        saved = []
        for dev in self._devices_list:
            if getattr(dev, "persist", False) and hasattr(dev, "save"):
                out = dev.save()
                if out:
                    saved.append(out)
        return saved

