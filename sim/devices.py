#!/usr/bin/env python3
# ==============================================================================
# LIM2 / sim / devices.py — Система внешних устройств и адресных пространств
# ==============================================================================
"""
Модуль для создания и подключения любых внешних устройств (MMIO):
  - BaseDevice: базовый класс для написания собственных устройств
  - RAMDevice: блок оперативной памяти
  - ROMDevice: блок постоянной памяти (Read-Only)
  - TextScreenDevice: видеопамять / текстовый терминал с отрисовкой в TUI
  - UARTDevice: последовательный порт ввода-вывода с буфером
  - TimerDevice: аппаратный таймер с генерацией сигналов на ножке IRQ
  - CustomDevice: готовый шаблон для любых пользовательских контроллеров
"""

import re
from typing import Dict, List, Optional, Tuple, Union, Callable, Any


class BaseDevice:
    """
    Базовый класс внешнего периферийного устройства.

    Каждое устройство имеет:
      - Адресное пространство: [start .. end], размер size = end - start + 1
      - Имя (name) для отображения на карте памяти шины (diskmgmt style)
      - Методы read(offset) / write(offset, value) — смещение от 0 до size-1
      - Доступ к шине self.bus и ножкам self.bus.pins (RD, WR, MREQ, IORQ, CS, IRQ...)
      - Хук on_step() / on_tick(), вызываемый на каждом такте процессора
      - Хук on_pin_change(pin_name, val), реагирующий на изменение ножек
      - Опциональный визуальный виджет render_panel() или render_screen() для TUI
    """

    def __init__(
        self,
        start: int,
        end: Optional[int] = None,
        size: Optional[int] = None,
        name: str = "DEV",
        readonly: bool = False,
        is_video: bool = False,
        width: int = 0,
        height: int = 0,
        latency: int = 0,
        ready_pin: str = "RF",
        default_data: Optional[Union[bytes, bytearray, List[int], str]] = None,
        default_offset: int = 0
    ):
        self.start = start
        if end is not None:
            self.end = end
            self.size = max(0, end - start + 1)
        elif size is not None:
            self.size = max(0, size)
            self.end = start + self.size - 1
        else:
            self.size = 256
            self.end = start + 255

        self.name = name
        self.readonly = readonly
        self.is_video = is_video
        self.width = width
        self.height = height
        self.latency = max(0, latency)
        self.ready_pin = ready_pin
        self._wait_counter = 0
        self._pending_op: Optional[Tuple] = None

        self.bus: Any = None
        self._raw = bytearray(self.size)
        self._last_accessed_offset: int = 0
        self._last_modified_step: Dict[int, int] = {}
        self.orphaned_bytes: int = 0
        self.orphaned_range: Optional[Tuple[int, int]] = None
        self.data_ranges: List[dict] = []
        self.annotations: Dict[int, str] = {}

        if default_data is not None:
            self.load_data(default_data, offset=default_offset)

    # --------------------------------------------------------------------------
    # Основные методы чтения/записи (пользователь переопределяет их)
    # --------------------------------------------------------------------------
    def read(self, offset: int) -> int:
        """
        Чтение одного байта по относительному смещению (0 <= offset < size).
        """
        if 0 <= offset < self.size:
            return self._raw[offset]
        return 0

    def write(self, offset: int, value: int):
        """
        Запись одного байта по относительному смещению (0 <= offset < size).
        """
        if self.readonly:
            return
        if 0 <= offset < self.size:
            val8 = value & 0xFF
            self._raw[offset] = val8
            cur_st = getattr(self.bus, "current_step", 0) if self.bus else 0
            self._last_modified_step[offset] = cur_st

    # --------------------------------------------------------------------------
    # Физические методы (вызываются шиной по абсолютным адресам)
    # --------------------------------------------------------------------------
    def read_phys(self, address: int) -> int:
        """Чтение по абсолютному физическому адресу шины."""
        idx = address - self.start
        if 0 <= idx < self.size:
            self._last_accessed_offset = idx
            return self.read(idx) & 0xFF
        return 0

    def write_phys(self, address: int, value: int):
        """Запись по абсолютному физическому адресу шины."""
        if self.readonly:
            return
        idx = address - self.start
        if 0 <= idx < self.size:
            self._last_accessed_offset = idx
            self.write(idx, value & 0xFF)

    read_physical = read_phys
    write_physical = write_phys

    # --------------------------------------------------------------------------
    # Хуки жизненного цикла и сигналов
    # --------------------------------------------------------------------------
    def on_attach(self, bus: Any):
        """Вызывается при подключении устройства к шине."""
        self.bus = bus

    def set_latency(self, cycles: int, ready_pin: str = "RF"):
        """
        Устанавливает задержку отклика устройства (отставание памяти в тактах шины)
        и имя ножки готовности данных (по умолчанию 'RF' — Ready Flag).
        """
        self.latency = max(0, cycles)
        self.ready_pin = ready_pin
        return self

    def start_read(self, offset: int) -> int:
        """
        Инициирует операцию чтения с учетом аппаратного отставания (latency).
        Если latency > 0:
          - сбрасывает ножку ready_pin в 0 (сигнал ожидания для процессора)
          - начинает отсчет тактов _wait_counter = latency
        Если latency == 0:
          - немедленно выставляет ready_pin в 1
        """
        if self.latency > 0:
            self._wait_counter = self.latency
            self._pending_op = ("read", offset)
            if self.bus is not None:
                getattr(self.bus.pins, self.ready_pin).set(0)
            return 0
        else:
            if self.bus is not None:
                getattr(self.bus.pins, self.ready_pin).set(1)
            return self.read(offset)

    def start_write(self, offset: int, value: int):
        """
        Инициирует операцию записи с учетом задержки.
        """
        val8 = value & 0xFF
        if self.readonly:
            return
        if self.latency > 0:
            self._wait_counter = self.latency
            self._pending_op = ("write", offset, val8)
            if self.bus is not None:
                getattr(self.bus.pins, self.ready_pin).set(0)
        else:
            self.write(offset, val8)
            if self.bus is not None:
                getattr(self.bus.pins, self.ready_pin).set(1)

    def is_ready(self) -> bool:
        """Проверяет, завершена ли операция (ножка RF поднята в 1)."""
        return self._wait_counter == 0

    def on_step(self):
        """
        Вызывается на каждом такте выполнения процессора / тике шины.
        Обрабатывает такты задержки памяти и поднимает ножку RF при готовности.
        """
        if self._wait_counter > 0:
            self._wait_counter -= 1
            if self._wait_counter == 0:
                if self._pending_op is not None:
                    op = self._pending_op
                    if op[0] == "write":
                        self.write(op[1], op[2])
                    self._pending_op = None
                if self.bus is not None:
                    getattr(self.bus.pins, self.ready_pin).set(1)

    def on_tick(self):
        """Псевдоним для on_step."""
        self.on_step()

    def on_pin_change(self, pin_name: str, new_val: int):
        """Реакция на изменение ножки шины (CS, IRQ, RESET, ALE и т.д.)."""
        pass

    # --------------------------------------------------------------------------
    # Вспомогательные методы работы с буфером
    # --------------------------------------------------------------------------
    def load_data(self, data: Union[bytes, bytearray, List[int], str], offset: int = 0):
        """
        Универсальная загрузка начальных данных в буфер устройства:
          - bytes / bytearray / list[int]: прямая запись байтов
          - str:
              * если файл существует на диске — читает бинарные данные из файла (.bin, .hex)
              * если строка из hex байтов (напр: '08 66 F8 00') — парсит hex
              * иначе — записывает строку символов в кодировке ASCII
        """
        import os
        if isinstance(data, (bytes, bytearray, list)):
            self.flash(data, offset=offset)
        elif isinstance(data, str):
            if os.path.exists(data):
                with open(data, "rb") as f:
                    self.flash(f.read(), offset=offset)
            else:
                toks = data.strip().split()
                if toks and all(re.match(r'^(?:0x)?[0-9a-fA-F]{1,4}$', t) for t in toks):
                    self.flash([int(t, 16) & 0xFF for t in toks], offset=offset)
                else:
                    self.flash([ord(c) for c in data], offset=offset)

    def flash(self, data: Union[List[int], bytes, bytearray], offset: int = 0):
        """Записывает массив байтов в память устройства напрямую."""
        for i, val in enumerate(data):
            target = offset + i
            if target < self.size:
                self._raw[target] = val & 0xFF

    def dump(self) -> bytes:
        return bytes(self._raw)

    def __getitem__(self, offset: int) -> int:
        return self.read(offset)

    def __setitem__(self, offset: int, value: int):
        self.write(offset, value)

    def __len__(self) -> int:
        return self.size

    # --------------------------------------------------------------------------
    # Отрисовка графических панелей в UI
    # --------------------------------------------------------------------------
    def render_panel(self) -> Optional[str]:
        """
        Пользовательский виджет для дашборда симулятора.
        Возвращает многострочный текст или None, если панель не требуется.
        """
        return None

    def render_screen(self) -> str:
        """Отрисовка физического видеомонитора в рамке (если is_video=True)."""
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
        """Форматирует окно памяти со стабильным числом строк для UI."""
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

        lines = []
        if start_row > 0:
            lines.append(f"... [пропущено 0x{self.start:04X}..0x{self.start + start_row * 16 - 1:04X}] ...")
        else:
            lines.append(f"... [0x{self.start:04X} начало памяти] ...")

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
            lines.append(f"0x{self.start + row_start:04X}: {h_l}  {h_r}  |{a_s}|")

        if end_row < total_dev_rows:
            lines.append(f"... [пропущено 0x{self.start + end_row * 16:04X}..0x{self.end:04X}] ...")
        else:
            lines.append(f"... [0x{self.end:04X} конец памяти] ...")
        return "\n".join(lines)


# ==============================================================================
# Готовые стандартные устройства
# ==============================================================================

class RAMDevice(BaseDevice):
    """Блок оперативной памяти (Read/Write RAM) с настраиваемым временем доступа и начальными данными."""
    def __init__(
        self,
        start: int,
        end: Optional[int] = None,
        size: Optional[int] = None,
        name: str = "RAM",
        latency: int = 0,
        ready_pin: str = "RF",
        default_data: Optional[Union[bytes, bytearray, List[int], str]] = None,
        default_offset: int = 0
    ):
        super().__init__(
            start=start,
            end=end,
            size=size,
            name=name,
            readonly=False,
            latency=latency,
            ready_pin=ready_pin,
            default_data=default_data,
            default_offset=default_offset
        )


class ROMDevice(BaseDevice):
    """Блок постоянной памяти (Read-Only ROM) с поддержкой времени выборки и начальных данных."""
    def __init__(
        self,
        start: int,
        end: Optional[int] = None,
        size: Optional[int] = None,
        data: Optional[Union[bytes, List[int], str]] = None,
        name: str = "ROM",
        latency: int = 0,
        ready_pin: str = "RF",
        default_data: Optional[Union[bytes, bytearray, List[int], str]] = None,
        default_offset: int = 0
    ):
        init_data = default_data if default_data is not None else data
        super().__init__(
            start=start,
            end=end,
            size=size,
            name=name,
            readonly=True,
            latency=latency,
            ready_pin=ready_pin,
            default_data=init_data,
            default_offset=default_offset
        )


class TextScreenDevice(BaseDevice):
    """
    Текстовый терминал / монитор с авто-рендерингом в интерфейсе симулятора.
    Каждый байт видеопамяти соответствует символу на экране.
    """
    def __init__(
        self,
        start: int,
        width: int = 20,
        height: int = 4,
        name: str = "MONITOR",
        default_data: Optional[Union[bytes, bytearray, List[int], str]] = None,
        default_offset: int = 0
    ):
        super().__init__(
            start=start,
            size=width * height,
            name=name,
            readonly=False,
            is_video=True,
            width=width,
            height=height,
            default_data=default_data,
            default_offset=default_offset
        )

    def print_text(self, text: str, offset: int = 0):
        """Быстрый вывод ASCII строки в видеопамять."""
        for i, ch in enumerate(text):
            if offset + i < self.size:
                self.write(offset + i, ord(ch))

    def clear(self):
        """Очистка экрана (заполнение пробелами)."""
        for i in range(self.size):
            self.write(i, ord(' '))


class UARTDevice(BaseDevice):
    """
    Последовательный контроллер UART:
      - Offset 0 (0x00): DATA_REG (Запись = передача TX, Чтение = прием RX)
      - Offset 1 (0x01): STATUS_REG (Бит 0: TX_READY=1, Бит 1: RX_AVAIL=0/1)
      - Offset 2 (0x02): CONTROL_REG (Бит 0: TX_INT_EN, Бит 1: RX_INT_EN)
    """
    def __init__(self, start: int, name: str = "UART0"):
        super().__init__(start=start, size=4, name=name)
        self.tx_history: List[str] = []
        self.rx_buffer: List[int] = []
        self._raw[1] = 0x01  # TX_READY по умолчанию

    def write(self, offset: int, value: int):
        val8 = value & 0xFF
        if offset == 0:  # DATA TX
            char = chr(val8) if 32 <= val8 <= 126 else ("\n" if val8 == 10 else f"\\x{val8:02X}")
            self.tx_history.append(char)
            # Ограничиваем историю
            if len(self.tx_history) > 200:
                self.tx_history = self.tx_history[-100:]
            self._raw[0] = val8
        elif offset == 2:  # CONTROL
            self._raw[2] = val8

    def read(self, offset: int) -> int:
        if offset == 0:  # DATA RX
            if self.rx_buffer:
                val = self.rx_buffer.pop(0)
                if not self.rx_buffer:
                    self._raw[1] &= ~0x02  # RX_AVAIL = 0
                return val
            return 0
        elif offset == 1:  # STATUS
            return self._raw[1]
        return self._raw[offset]

    def queue_input(self, text: str):
        """Помещает строку в приемный буфер RX."""
        for ch in text:
            self.rx_buffer.append(ord(ch))
        if self.rx_buffer:
            self._raw[1] |= 0x02  # RX_AVAIL = 1

    def render_panel(self) -> Optional[str]:
        """Виджет консоли UART."""
        w = 80
        title = f"{self.name} SERIAL CONSOLE @ 0x{self.start:04X}"
        recent = "".join(self.tx_history)[-60:].replace("\n", " ")
        lines = [
            f"┌── [{title}] " + ("─" * max(0, w - 8 - len(title))) + "┐",
            f"│  STATUS: 0x{self._raw[1]:02X} (TX_READY={'1' if self._raw[1] & 1 else '0'}, RX_AVAIL={'1' if self._raw[1] & 2 else '0'}) │".ljust(w - 1) + "│",
            f"│  TX LOG: \"{recent}\"".ljust(w - 1) + "│",
            "└" + ("─" * (w - 2)) + "┘"
        ]
        return "\n".join(lines)


class TimerDevice(BaseDevice):
    """
    Аппаратный таймер / счетчик:
      - Offset 0: COUNTER_LO
      - Offset 1: COUNTER_HI
      - Offset 2: RELOAD_VAL
      - Offset 3: CONTROL (Бит 0: ENABLE, Бит 1: IRQ_ENABLE)
    При достижении нуля выставляет сигнал на ножке IRQ шины.
    """
    def __init__(self, start: int, name: str = "TIMER0", irq_pin: str = "IRQ"):
        super().__init__(start=start, size=4, name=name)
        self.irq_pin = irq_pin
        self.counter = 100
        self.reload = 100
        self.enabled = True
        self.irq_enabled = True
        self.fired_count = 0
        self._raw[2] = 100
        self._raw[3] = 0x03  # Enabled + IRQ Enabled

    def on_step(self):
        """Срабатывает на каждом такте процессора."""
        if self.enabled:
            self.counter -= 1
            if self.counter <= 0:
                self.counter = self.reload
                self.fired_count += 1
                if self.irq_enabled and self.bus is not None:
                    getattr(self.bus.pins, self.irq_pin).set(1)

    def write(self, offset: int, value: int):
        val8 = value & 0xFF
        self._raw[offset] = val8
        if offset == 0:
            self.counter = (self.counter & 0xFF00) | val8
        elif offset == 1:
            self.counter = (self.counter & 0x00FF) | (val8 << 8)
        elif offset == 2:
            self.reload = max(1, val8)
        elif offset == 3:
            self.enabled = bool(val8 & 0x01)
            self.irq_enabled = bool(val8 & 0x02)

    def read(self, offset: int) -> int:
        if offset == 0:
            return self.counter & 0xFF
        elif offset == 1:
            return (self.counter >> 8) & 0xFF
        return self._raw[offset]


class CustomDevice(BaseDevice):
    """
    Шаблон для создания собственного устройства.
    Любой пользователь может унаследовать или скопировать этот класс
    и описать собственную логику регистров и портов.
    """
    def __init__(self, start: int, size: int = 16, name: str = "MY_DEV"):
        super().__init__(start=start, size=size, name=name)
        # Пользовательские переменные состояния:
        self.state_var = 0

    def read(self, offset: int) -> int:
        # Например, регистр 0 возвращает состояние, остальные — память
        if offset == 0:
            return self.state_var & 0xFF
        return self._raw[offset]

    def write(self, offset: int, value: int):
        val8 = value & 0xFF
        self._raw[offset] = val8
        if offset == 0:
            self.state_var = val8
            # Можно проверить ножки шины или послать прерывание:
            # if self.bus: self.bus.pins.IRQ.pulse()
