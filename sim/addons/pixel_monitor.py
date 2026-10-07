#!/usr/bin/env python3
# ==============================================================================
# LIM2 / sim / addons / pixel_monitor.py — Внешний графический пиксельный монитор
# ==============================================================================
"""
Внешнее расширение для симулятора LIM2:
Полноценный графический пиксельный монитор с реальным окном (Tkinter GUI),
буфером видеопамяти (VRAM), поддержкой палитр, цветовых режимов RGB332 / Palette
и возможностью рисования прямо из процессора через MMIO.

Модуль спроектирован как отдельное дополнение:
  - Не навязывается базовому ядру симулятора;
  - Легко подключается одной строкой при необходимости:
      from addons.pixel_monitor import PixelMonitorDevice
      bus.attach(PixelMonitorDevice(start=0x4000, width=64, height=64, scale=6))
"""

import sys
import time
import threading
from typing import Optional, List, Tuple, Dict, Any
from pathlib import Path

# Добавляем родительскую папку для импорта BaseDevice
CURRENT_DIR = Path(__file__).resolve().parent
PARENT_DIR = CURRENT_DIR.parent
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

try:
    from devices import BaseDevice
except ImportError:
    from ..devices import BaseDevice


# Стандартная палитра 16 цветов (CGA/EGA/VGA)
STANDARD_PALETTE_16 = [
    (0x00, 0x00, 0x00),  # 0: Черный
    (0x00, 0x00, 0xAA),  # 1: Синий
    (0x00, 0xAA, 0x00),  # 2: Зеленый
    (0x00, 0xAA, 0xAA),  # 3: Циан
    (0xAA, 0x00, 0x00),  # 4: Красный
    (0xAA, 0x00, 0xAA),  # 5: Пурпурный
    (0xAA, 0x55, 0x00),  # 6: Коричневый
    (0xAA, 0xAA, 0xAA),  # 7: Светло-серый
    (0x55, 0x55, 0x55),  # 8: Темно-серый
    (0x55, 0x55, 0xFF),  # 9: Ярко-синий
    (0x55, 0xFF, 0x55),  # 10: Ярко-зеленый
    (0x55, 0xFF, 0xFF),  # 11: Ярко-циан
    (0xFF, 0x55, 0x55),  # 12: Ярко-красный
    (0xFF, 0x55, 0xFF),  # 13: Ярко-пурпурный
    (0xFF, 0xFF, 0x55),  # 14: Желтый
    (0xFF, 0xFF, 0xFF),  # 15: Белый
]


def rgb332_to_rgb888(val: int) -> Tuple[int, int, int]:
    """Преобразует 8-битный цвет RGB332 в RGB (0..255)."""
    r = ((val >> 5) & 0x07) * 255 // 7
    g = ((val >> 2) & 0x07) * 255 // 7
    b = (val & 0x03) * 255 // 3
    return (r, g, b)


class PixelMonitorDevice(BaseDevice):
    """
    Аппаратный пиксельный графический монитор (Memory-Mapped Framebuffer).

    Характеристики:
      - Разрешение: width x height пикселей (по умолчанию 64x64 = 4096 байт VRAM).
      - Масштаб отображения: scale (размер пикселя в экранных точках, напр. 6x).
      - Режимы цвета:
          * 'rgb332': 8 бит на пиксель (256 цветов R:3, G:3, B:2) — без палитры!
          * 'palette16': 4/8 бит на пиксель по 16-цветовой аппаратной палитре.
          * 'mono': монохромный режим (0=черный, !=0=белый).
      - Графический интерфейс Tkinter:
          * Работает в отдельном потоке;
          * Поддерживает живое обновление и перерисовку.
    """

    def __init__(
        self,
        start: int = 0x4000,
        width: int = 64,
        height: int = 64,
        scale: int = 6,
        mode: str = "rgb332",
        name: str = "PIXEL_GPU",
        show_gui: bool = False,
        title: str = "LIM2 Hardware Pixel Display"
    ):
        vram_size = width * height
        # Добавляем 4 байта служебных регистров управления в конец:
        #   offset + 0: CONTROL (бит 0: включен, бит 1: авто-обновление)
        #   offset + 1: CLEAR_COLOR (запись заливает экран указанным цветом)
        #   offset + 2: VSYNC_COUNTER (счетчик кадров)
        #   offset + 3: BRIGHTNESS / MODE
        total_size = vram_size + 4

        super().__init__(
            start=start,
            size=total_size,
            name=name,
            readonly=False,
            is_video=False  # это графический монитор, а не консольный текст
        )

        self.width = width
        self.height = height
        self.scale = max(1, scale)
        self.mode = mode.lower()
        self.vram_size = vram_size
        self.ctrl_offset = vram_size
        self.title = title

        # Состояние графического окна
        self._gui_enabled = show_gui
        self._gui_thread: Optional[threading.Thread] = None
        self._gui_running = False
        self._tk_root: Any = None
        self._tk_canvas: Any = None
        self._dirty_pixels: Dict[Tuple[int, int], int] = {}
        self._frame_count = 0
        self._last_draw_time = 0.0

        # Регистры управления
        self._raw[self.ctrl_offset + 0] = 0x03  # Enabled + AutoRefresh
        self._raw[self.ctrl_offset + 1] = 0x00  # Clear color

        if self._gui_enabled:
            self.launch_gui()

    # --------------------------------------------------------------------------
    # Чтение и запись процессора (MMIO)
    # --------------------------------------------------------------------------
    def read(self, offset: int) -> int:
        if offset < self.vram_size:
            return self._raw[offset]
        elif offset == self.ctrl_offset + 2:
            # Чтение VSYNC / счетчика кадров
            return self._frame_count & 0xFF
        elif offset < self.size:
            return self._raw[offset]
        return 0

    def write(self, offset: int, value: int):
        val8 = value & 0xFF

        # Запись в область пикселей видеопамяти (VRAM)
        if offset < self.vram_size:
            prev = self._raw[offset]
            if prev != val8:
                self._raw[offset] = val8
                x = offset % self.width
                y = offset // self.width
                self._dirty_pixels[(x, y)] = val8

        # Запись в регистры управления
        elif offset == self.ctrl_offset + 0:
            self._raw[offset] = val8
        elif offset == self.ctrl_offset + 1:
            # Команда быстрой заливки экрана цветом val8
            self.clear(val8)
        elif offset < self.size:
            self._raw[offset] = val8

    # --------------------------------------------------------------------------
    # Вспомогательные методы рисования (для ассемблера / Python)
    # --------------------------------------------------------------------------
    def set_pixel(self, x: int, y: int, color: int):
        """Устанавливает цвет пикселя по координатам (x, y)."""
        if 0 <= x < self.width and 0 <= y < self.height:
            offset = y * self.width + x
            self.write(offset, color)

    def get_pixel(self, x: int, y: int) -> int:
        """Возвращает цвет пикселя по координатам (x, y)."""
        if 0 <= x < self.width and 0 <= y < self.height:
            offset = y * self.width + x
            return self._raw[offset]
        return 0

    def clear(self, color: int = 0):
        """Заливает весь буфер видеопамяти одним цветом."""
        col8 = color & 0xFF
        for i in range(self.vram_size):
            self._raw[i] = col8
            x = i % self.width
            y = i // self.width
            self._dirty_pixels[(x, y)] = col8

    def draw_rect(self, x: int, y: int, w: int, h: int, color: int, fill: bool = True):
        """Рисует прямоугольник в VRAM."""
        col8 = color & 0xFF
        for dy in range(h):
            for dx in range(w):
                if fill or (dx == 0 or dx == w - 1 or dy == 0 or dy == h - 1):
                    self.set_pixel(x + dx, y + dy, col8)

    def draw_line(self, x0: int, y0: int, x1: int, y1: int, color: int):
        """Алгоритм Брезенхэма для рисования отрезка в VRAM."""
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy

        while True:
            self.set_pixel(x0, y0, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    # --------------------------------------------------------------------------
    # Преобразование цветов
    # --------------------------------------------------------------------------
    def get_rgb_color(self, val: int) -> Tuple[int, int, int]:
        """Возвращает RGB кортеж для значения пикселя в зависимости от режима."""
        if self.mode == "rgb332":
            return rgb332_to_rgb888(val)
        elif self.mode in ("palette16", "palette", "cga", "vga"):
            idx = val & 0x0F
            return STANDARD_PALETTE_16[idx]
        elif self.mode in ("mono", "monochrome"):
            return (255, 255, 255) if val else (0, 0, 0)
        return (val, val, val)

    def get_hex_color(self, val: int) -> str:
        """Возвращает строку вида '#RRGGBB'."""
        r, g, b = self.get_rgb_color(val)
        return f"#{r:02x}{g:02x}{b:02x}"

    # --------------------------------------------------------------------------
    # Графический интерфейс Tkinter (GUI Window)
    # --------------------------------------------------------------------------
    def launch_gui(self):
        """Запускает настоящее графическое окно дисплея в отдельном потоке."""
        if self._gui_running:
            return

        self._gui_running = True
        self._gui_thread = threading.Thread(target=self._run_tk_app, daemon=True)
        self._gui_thread.start()

    def close_gui(self):
        """Закрывает графическое окно."""
        self._gui_running = False
        if self._tk_root:
            try:
                self._tk_root.quit()
            except Exception:
                pass

    def _run_tk_app(self):
        """Тело фонового потока GUI."""
        try:
            import tkinter as tk
        except ImportError:
            print("[PIXEL_MONITOR] Модуль tkinter недоступен. Графическое окно отключено.")
            self._gui_running = False
            return

        root = tk.Tk()
        self._tk_root = root
        win_w = self.width * self.scale
        win_h = self.height * self.scale
        root.title(f"{self.title} [{self.width}x{self.height} @ 0x{self.start:04X}]")
        root.geometry(f"{win_w}x{win_h}")
        root.resizable(False, False)

        canvas = tk.Canvas(root, width=win_w, height=win_h, bg="#000000", highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        self._tk_canvas = canvas

        # Начальная отрисовка всех пикселей
        self._redraw_full_canvas()

        def on_timer():
            if not self._gui_running:
                root.destroy()
                return
            self._flush_dirty_pixels_to_canvas()
            root.after(30, on_timer)  # ~33 FPS

        root.after(30, on_timer)
        try:
            root.mainloop()
        except Exception:
            pass
        finally:
            self._gui_running = False

    def _redraw_full_canvas(self):
        if not self._tk_canvas:
            return
        self._tk_canvas.delete("all")
        for y in range(self.height):
            for x in range(self.width):
                val = self._raw[y * self.width + x]
                col_hex = self.get_hex_color(val)
                x0 = x * self.scale
                y0 = y * self.scale
                x1 = x0 + self.scale
                y1 = y0 + self.scale
                self._tk_canvas.create_rectangle(x0, y0, x1, y1, fill=col_hex, outline="", tags=f"p_{x}_{y}")
        self._dirty_pixels.clear()

    def _flush_dirty_pixels_to_canvas(self):
        if not self._tk_canvas or not self._dirty_pixels:
            return

        # Обновляем только изменившиеся пиксели для максимальной скорости
        batch = list(self._dirty_pixels.items())
        self._dirty_pixels.clear()

        for (x, y), val in batch:
            col_hex = self.get_hex_color(val)
            x0 = x * self.scale
            y0 = y * self.scale
            x1 = x0 + self.scale
            y1 = y0 + self.scale
            # Ищем и перекрашиваем
            tag = f"p_{x}_{y}"
            items = self._tk_canvas.find_withtag(tag)
            if items:
                self._tk_canvas.itemconfig(items[0], fill=col_hex)
            else:
                self._tk_canvas.create_rectangle(x0, y0, x1, y1, fill=col_hex, outline="", tags=tag)

        self._frame_count += 1

    # --------------------------------------------------------------------------
    # Хук такта процессора
    # --------------------------------------------------------------------------
    def on_step(self):
        """Вызывается на каждом такте выполнения процессора."""
        # Обновляем VSYNC в регистрах управления
        now = time.time()
        if now - self._last_draw_time > 0.05:  # 20 FPS
            self._last_draw_time = now
            self._frame_count = (self._frame_count + 1) & 0xFFFF

    # --------------------------------------------------------------------------
    # Текстовый виджет для терминала (TUI Dashboard)
    # --------------------------------------------------------------------------
    def render_panel(self) -> Optional[str]:
        """
        Компактная информационная карточка устройства и ANSI-превью для TUI дашборда.
        """
        w = 80
        title = f"{self.name} PIXEL FRAMEBUFFER ({self.width}x{self.height}, {self.mode.upper()})"
        gui_status = "\033[1;32mGUI ОКНО АКТИВНО\033[0m" if self._gui_running else "\033[90mGUI ОКНО ВЫКЛ\033[0m"
        vram_info = f"0x{self.start:04X}..0x{self.start + self.vram_size - 1:04X} ({self.vram_size} байт)"
        ctrl_info = f"CTRL: 0x{self.start + self.ctrl_offset:04X} (Frames: {self._frame_count})"

        lines = [
            f"┌── [{title}] " + ("─" * max(0, w - 8 - len(title))) + "┐",
            f"│  VRAM: {vram_info:<35} Статус: {gui_status:<22} │",
            f"│  Управление: {ctrl_info:<30} Режим: {self.mode:<12} Масштаб: {self.scale}x  │",
        ]

        # Добавляем мини-превью в терминале (8 строк через двойные полублоки '▀')
        preview_h = min(6, self.height // 4)
        preview_w = min(32, self.width)
        step_x = max(1, self.width // preview_w)
        step_y = max(1, self.height // (preview_h * 2))

        lines.append(f"│  МИНИ-ПРЕВЬЮ ЭКРАНА В ТЕРМИНАЛЕ (ANSI TrueColor):                            │")
        for py in range(0, preview_h):
            y_top = py * 2 * step_y
            y_bot = y_top + step_y
            row_tokens = []
            for px in range(0, preview_w):
                x = px * step_x
                top_val = self.get_pixel(x, y_top)
                bot_val = self.get_pixel(x, y_bot) if y_bot < self.height else 0

                tr, tg, tb = self.get_rgb_color(top_val)
                br, bg, bb = self.get_rgb_color(bot_val)
                # Верхний цвет = fg, нижний цвет = bg, символ '▀'
                token = f"\033[38;2;{tr};{tg};{tb}m\033[48;2;{br};{bg};{bb}m▀\033[0m"
                row_tokens.append(token)

            preview_line = "".join(row_tokens)
            pad = " " * max(0, w - 6 - preview_w)
            lines.append(f"│  {preview_line}{pad} │")

        lines.append("└" + ("─" * (w - 2)) + "┘")
        return "\n".join(lines)


# ==============================================================================
# Демонстрационный автономный запуск
# ==============================================================================
if __name__ == "__main__":
    print("[PIXEL_MONITOR] Запуск автономного демо пиксельного дисплея...")
    gpu = PixelMonitorDevice(start=0x4000, width=64, height=64, scale=6, mode="rgb332", show_gui=True)

    # Рисуем градиент и рамку в VRAM
    for y in range(64):
        for x in range(64):
            # RGB332: R(3 бита: x), G(3 бита: y), B(2 бита: (x+y))
            r = (x * 8 // 64) & 0x07
            g = (y * 8 // 64) & 0x07
            b = ((x + y) * 4 // 128) & 0x03
            color = (r << 5) | (g << 2) | b
            gpu.set_pixel(x, y, color)

    gpu.draw_rect(10, 10, 44, 44, color=0xFF, fill=False)  # Белая рамка
    gpu.draw_line(10, 10, 54, 54, color=0xE0)               # Красная диагональ
    gpu.draw_line(10, 54, 54, 10, color=0x1C)               # Зеленая диагональ

    print(gpu.render_panel())
    print("\n[OK] Дисплей активен. Окно закроется через 3 секунды...")
    time.sleep(3)
    gpu.close_gui()
    print("[OK] Завершено.")
