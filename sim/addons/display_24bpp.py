#!/usr/bin/env python3
# ==============================================================================
# LIM2 / sim / addons / display_24bpp.py — Графический TrueColor дисплей (16M цветов)
# ==============================================================================
"""
Внешнее дополнение для симулятора LIM M2:
Высокопроизводительный графический TrueColor дисплей на 16.7 миллионов цветов
(24 бита на пиксель — 3 байта: R, G, B).

ПОДКЛЮЧЕНИЕ ПРЯМО В КОД (например, в sim.py или LIM2.py):
    from addons.display_24bpp import Display24bppDevice
    bus.attach(Display24bppDevice(start=0x00010000, width=64, height=64, scale=6, gui=True))

После этого запускайте симулятор как обычно БЕЗ ВСЯКИХ ФЛАГОВ:
    python3 sim.py demo.asm
    python3 sim.py demo.hex -i

Окно Tkinter открывается автоматически в отдельном изолированном процессе и не
блокирует выполнение симулятора. Обмен видеопамятью идет через быстрый mmap-буфер.
"""

import sys
import os
import time
import mmap
import atexit
import tempfile
import subprocess
from typing import Optional, Tuple, Dict, Any
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
SIM_DIR = CURRENT_DIR.parent
if str(SIM_DIR) not in sys.path:
    sys.path.insert(0, str(SIM_DIR))

try:
    from devices import BaseDevice
except ImportError:
    try:
        from ..devices import BaseDevice
    except Exception:
        # Автономный fallback для переноса в любой другой проект
        class BaseDevice:
            def __init__(self, start=0, size=0, name="DEV", **kwargs):
                self.start = start
                self.size = size
                self.end = start + size - 1
                self.name = name
                self.is_video = kwargs.get("is_video", False)
                self.width = kwargs.get("width", 0)
                self.height = kwargs.get("height", 0)


class Display24bppDevice(BaseDevice):
    """
    24-битный TrueColor графический дисплей (16 777 216 цветов).

    Параметры:
      start:   Базовый адрес VRAM в памяти процессора (по умолчанию: 0x00010000)
      width:   Ширина экрана в пикселях (по умолчанию: 64)
      height:  Высота экрана в пикселях (по умолчанию: 64)
      scale:   Масштаб окна Tkinter (по умолчанию: 6x)
      gui:     Автоматически открыть окно Tkinter (True/False, по умолчанию: True)
      name:    Имя устройства на шине (по умолчанию: "GPU_24BPP")
      title:   Заголовок окна

    Формат видеопамяти: 3 байта на пиксель (R, G, B):
      offset = (y * width + x) * 3
      [offset + 0] = Red   (0..255)
      [offset + 1] = Green (0..255)
      [offset + 2] = Blue  (0..255)

    Служебные регистры (по смещению = vram_size):
      + 0: CONTROL (бит 0: включен, бит 1: авто-обновление)
      + 1: CLEAR_R
      + 2: CLEAR_G
      + 3: CLEAR_B (запись сюда запускает аппаратную заливку цветом CLEAR_R:G:B)
      + 4: VSYNC (счетчик кадров)
      + 5..8: WIDTH, HEIGHT
      + 9: BPP (24)
    """

    def __init__(
        self,
        start: int = 0x00010000,
        width: int = 64,
        height: int = 64,
        scale: int = 6,
        gui: bool = False,
        standalone: bool = False,
        name: str = "GPU_24BPP",
        title: str = "LIM M2 TrueColor 24-bit Display (16M Colors)"
    ):
        self.width = max(1, int(width))
        self.height = max(1, int(height))
        self.scale = max(1, int(scale))
        self.title = title
        self.standalone_window = bool(standalone or gui)
        self.gui = self.standalone_window

        self.vram_size = self.width * self.height * 3
        self.ctrl_size = 16
        total_size = self.vram_size + self.ctrl_size
        self.ctrl_offset = self.vram_size

        # Создаем временный файл для быстрой разделяемой памяти mmap с окном GUI
        self._temp_file = tempfile.NamedTemporaryFile(prefix="lim2_gpu24_", delete=False)
        self._temp_file.truncate(total_size)
        self._temp_file.close()
        self._fpath = self._temp_file.name

        self._f = open(self._fpath, "r+b")
        self._raw = mmap.mmap(self._f.fileno(), total_size)

        super().__init__(
            start=start,
            size=total_size,
            name=name,
            readonly=False,
            is_video=True,
            width=self.width,
            height=self.height
        )

        # Инициализируем служебные регистры
        self._raw[self.ctrl_offset + 0] = 0x03  # ENABLE + AUTO_REFRESH
        self._raw[self.ctrl_offset + 4] = 0x00  # VSYNC
        self._raw[self.ctrl_offset + 5] = self.width & 0xFF
        self._raw[self.ctrl_offset + 6] = (self.width >> 8) & 0xFF
        self._raw[self.ctrl_offset + 7] = self.height & 0xFF
        self._raw[self.ctrl_offset + 8] = (self.height >> 8) & 0xFF
        self._raw[self.ctrl_offset + 9] = 24

        self._frame_count = 0
        self._last_vsync_time = time.time()
        self._proc: Optional[subprocess.Popen] = None

        # Регистрируем автоматическую очистку при завершении работы симулятора
        atexit.register(self.close)

        # Автоматический запуск окна GUI в отдельном независимом процессе
        if self.gui:
            self.launch_gui()

    def launch_gui(self):
        """Запускает графическое окно Tkinter в отдельном процессе."""
        if self._proc is not None and self._proc.poll() is None:
            return

        try:
            cmd = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--viewer",
                self._fpath,
                str(self.width),
                str(self.height),
                str(self.scale),
                f"{self.title} [{self.width}x{self.height} @ 0x{self.start:08X}]"
            ]
            self._proc = subprocess.Popen(cmd)
        except Exception as e:
            print(f"[{self.name}] Предупреждение: Не удалось запустить графическое окно ({e}). Доступен консольный TUI вывод.")

    def close(self):
        """Закрывает окно и освобождает ресурсы."""
        if self._proc is not None:
            try:
                if self._proc.poll() is None:
                    self._proc.terminate()
            except Exception:
                pass
            self._proc = None

        try:
            if hasattr(self, "_raw") and self._raw:
                self._raw.close()
        except Exception:
            pass

        try:
            if hasattr(self, "_f") and self._f:
                self._f.close()
        except Exception:
            pass

        try:
            if hasattr(self, "_fpath") and os.path.exists(self._fpath):
                os.unlink(self._fpath)
        except Exception:
            pass

    def __del__(self):
        self.close()

    # --------------------------------------------------------------------------
    # Чтение и запись со стороны процессора (MMIO)
    # --------------------------------------------------------------------------
    def read(self, offset: int) -> int:
        if offset < self.vram_size:
            return self._raw[offset]
        elif offset == self.ctrl_offset + 4:
            return self._frame_count & 0xFF
        elif offset < self.size:
            return self._raw[offset]
        return 0

    def write(self, offset: int, value: int):
        val8 = value & 0xFF
        self._vram_version = getattr(self, "_vram_version", 0) + 1
        if offset < self.vram_size:
            self._raw[offset] = val8
        elif offset == self.ctrl_offset + 3:
            # Запись в CLEAR_B запускает быструю заливку
            self._raw[offset] = val8
            cr = self._raw[self.ctrl_offset + 1]
            cg = self._raw[self.ctrl_offset + 2]
            cb = val8
            self.clear(cr, cg, cb)
        elif offset < self.size:
            self._raw[offset] = val8

    # --------------------------------------------------------------------------
    # Вспомогательные методы
    # --------------------------------------------------------------------------
    def set_pixel(self, x: int, y: int, r: int, g: int, b: int):
        if 0 <= x < self.width and 0 <= y < self.height:
            off = (y * self.width + x) * 3
            self._raw[off + 0] = r & 0xFF
            self._raw[off + 1] = g & 0xFF
            self._raw[off + 2] = b & 0xFF
            self._vram_version = getattr(self, "_vram_version", 0) + 1

    def get_pixel(self, x: int, y: int) -> Tuple[int, int, int]:
        if 0 <= x < self.width and 0 <= y < self.height:
            off = (y * self.width + x) * 3
            return (self._raw[off], self._raw[off + 1], self._raw[off + 2])
        return (0, 0, 0)

    def clear(self, r: int = 0, g: int = 0, b: int = 0):
        pixel_3b = bytes([r & 0xFF, g & 0xFF, b & 0xFF])
        self._raw[:self.vram_size] = pixel_3b * (self.width * self.height)
        self._vram_version = getattr(self, "_vram_version", 0) + 1

    def on_step(self):
        now = time.time()
        if now - self._last_vsync_time >= 0.016:
            self._last_vsync_time = now
            self._frame_count = (self._frame_count + 1) & 0xFFFF
            self._raw[self.ctrl_offset + 4] = self._frame_count & 0xFF

    # --------------------------------------------------------------------------
    # Отрисовка в терминале для встроенного TUI дашборда симулятора
    # --------------------------------------------------------------------------
    def render_screen(self) -> str:
        return self.render_panel()

    def render_panel(self) -> str:
        w = 80
        title = f"{self.name} TRUECOLOR 24-BIT ({self.width}x{self.height}, 16M COLORS)"
        gui_active = self._proc is not None and self._proc.poll() is None
        status = "\033[1;32mGUI OKHO\033[0m" if gui_active else "\033[90mGUI OFF\033[0m"
        vram_info = f"0x{self.start:08X}..0x{self.start + self.vram_size - 1:08X} ({self.vram_size} B)"
        ctrl_info = f"CTRL: 0x{self.start + self.ctrl_offset:08X} (VSYNC: {self._frame_count})"

        lines = [
            f"┌── [{title}] " + ("─" * max(0, w - 8 - len(title))) + "┐",
            f"│  VRAM: {vram_info:<36} Статус: {status:<22} │",
            f"│  Управление: {ctrl_info:<30} Режим: 3 байта/пикс (RGB24) │",
        ]

        preview_h = min(8, max(2, self.height // 4))
        preview_w = min(40, self.width)
        step_x = max(1, self.width // preview_w)
        step_y = max(1, self.height // (preview_h * 2))

        lines.append(f"│  МИНИ-ПРЕВЬЮ ЭКРАНА В ТЕРМИНАЛЕ (ANSI TrueColor 24-bit):                     │")
        for py in range(preview_h):
            y_top = py * 2 * step_y
            y_bot = y_top + step_y
            tokens = []
            for px in range(preview_w):
                x = px * step_x
                tr, tg, tb = self.get_pixel(x, y_top)
                br, bg, bb = self.get_pixel(x, y_bot) if y_bot < self.height else (0, 0, 0)
                token = f"\033[38;2;{tr};{tg};{tb}m\033[48;2;{br};{bg};{bb}m▀\033[0m"
                tokens.append(token)
            pad = " " * max(0, w - 6 - preview_w)
            lines.append(f"│  {''.join(tokens)}{pad} │")

        lines.append("└" + ("─" * (w - 2)) + "┘")
        return "\n".join(lines)


# ==============================================================================
# Независимый просмотрщик Tkinter (запускается как дочерний процесс)
# ==============================================================================
def _run_tk_viewer(fpath: str, width: int, height: int, scale: int, title: str):
    try:
        import tkinter as tk
    except ImportError:
        return

    vram_size = width * height * 3
    ppm_header = f"P6\n{width} {height}\n255\n".encode("ascii")

    if not os.path.exists(fpath):
        return

    with open(fpath, "r+b") as f:
        mm = mmap.mmap(f.fileno(), vram_size + 16)

        root = tk.Tk()
        win_w = width * scale
        win_h = height * scale

        root.title(title)
        root.geometry(f"{win_w}x{win_h + 26}")
        root.resizable(False, False)

        canvas = tk.Canvas(root, width=win_w, height=win_h, bg="#000000", highlightthickness=0)
        canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=False)

        status_lbl = tk.Label(
            root,
            text=f"Resolution: {width}x{height} | Mode: 24bpp TrueColor (16M) | VRAM: {vram_size} B",
            font=("Consolas", 10),
            fg="#cccccc",
            bg="#1e1e1e",
            anchor="w",
            padx=8,
            height=1
        )
        status_lbl.pack(side=tk.BOTTOM, fill=tk.X)

        ppm_data = ppm_header + bytes(mm[:vram_size])
        base_img = tk.PhotoImage(width=width, height=height)
        scaled_img = tk.PhotoImage(width=width * scale, height=height * scale) if scale > 1 else base_img
        base_img.put(ppm_data)
        if scale > 1:
            root.tk.call(scaled_img, "copy", base_img, "-zoom", scale, scale)
        img_id = canvas.create_image(0, 0, image=scaled_img, anchor="nw")
        canvas.image = scaled_img
        last_vram_hash = hash(bytes(mm[:vram_size]))

        def on_mouse_move(event):
            px = event.x // scale
            py = event.y // scale
            if 0 <= px < width and 0 <= py < height:
                off = (py * width + px) * 3
                r, g, b = mm[off], mm[off + 1], mm[off + 2]
                hex_col = f"#{r:02X}{g:02X}{b:02X}"
                status_lbl.config(
                    text=f"X:{px:3d} Y:{py:3d} | RGB: ({r:3d}, {g:3d}, {b:3d}) | HEX: {hex_col}"
                )

        canvas.bind("<Motion>", on_mouse_move)

        def poll_refresh():
            nonlocal last_vram_hash
            try:
                raw_bytes = bytes(mm[:vram_size])
                cur_hash = hash(raw_bytes)
                if cur_hash != last_vram_hash:
                    last_vram_hash = cur_hash
                    ppm_data = ppm_header + raw_bytes
                    base_img.put(ppm_data)
                    if scale > 1:
                        root.tk.call(scaled_img, "copy", base_img, "-zoom", scale, scale)
                root.after(33, poll_refresh)
            except Exception:
                root.destroy()

        root.after(33, poll_refresh)
        try:
            root.mainloop()
        except Exception:
            pass


Display16MDevice = Display24bppDevice

if __name__ == "__main__":
    if len(sys.argv) >= 6 and sys.argv[1] == "--viewer":
        _run_tk_viewer(
            fpath=sys.argv[2],
            width=int(sys.argv[3]),
            height=int(sys.argv[4]),
            scale=int(sys.argv[5]),
            title=sys.argv[6] if len(sys.argv) > 6 else "LIM M2 Display"
        )
