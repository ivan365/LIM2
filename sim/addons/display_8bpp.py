#!/usr/bin/env python3
# ==============================================================================
# LIM2 / sim / addons / display_8bpp.py — Графический 256-цветовой дисплей (8-bit)
# ==============================================================================
"""
Внешнее дополнение для симулятора LIM M2:
Энергоэффективный и быстрый графический дисплей на 256 цветов (8 бит на пиксель).

Цветовые форматы:
  - '3-2-3' (по умолчанию): 3 бита Red [7:5], 2 бита Green [4:3], 3 бита Blue [2:0] (3+2+3 = 8 бит);
  - '3-3-2': 3 бита Red [7:5], 3 бита Green [4:2], 2 бита Blue [1:0].

ПОДКЛЮЧЕНИЕ ПРЯМО В КОД (например, в sim.py или LIM2.py):
    from addons.display_8bpp import Display8bppDevice
    bus.attach(Display8bppDevice(start=0x00008000, width=64, height=64, scale=6, format="3-2-3", gui=True))

После этого запускайте симулятор как обычно БЕЗ ВСЯКИХ ФЛАГОВ:
    python3 sim.py demo.asm
    python3 sim.py demo.hex -i
"""

import sys
import os
import time
import mmap
import atexit
import tempfile
import subprocess
from typing import Optional, Tuple, Dict, Any, List
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


def _build_palette_323() -> List[Tuple[int, int, int]]:
    lut = []
    for val in range(256):
        r3 = (val >> 5) & 0x07
        g2 = (val >> 3) & 0x03
        b3 = val & 0x07
        r = r3 * 255 // 7
        g = g2 * 255 // 3
        b = b3 * 255 // 7
        lut.append((r, g, b))
    return lut


def _build_palette_332() -> List[Tuple[int, int, int]]:
    lut = []
    for val in range(256):
        r3 = (val >> 5) & 0x07
        g3 = (val >> 2) & 0x07
        b2 = val & 0x03
        r = r3 * 255 // 7
        g = g3 * 255 // 7
        b = b2 * 255 // 3
        lut.append((r, g, b))
    return lut


class Display8bppDevice(BaseDevice):
    """
    8-битный графический дисплей на 256 цветов (формат по умолчанию: 3-2-3 RGB).

    Параметры:
      start:   Базовый адрес VRAM в памяти процессора (по умолчанию: 0x00008000)
      width:   Ширина экрана в пикселях (по умолчанию: 64)
      height:  Высота экрана в пикселях (по умолчанию: 64)
      scale:   Масштаб окна Tkinter (по умолчанию: 6x)
      format:  Цветовой формат ("3-2-3" или "3-3-2", по умолчанию: "3-2-3")
      gui:     Автоматически открыть окно Tkinter (True/False, по умолчанию: True)
      name:    Имя устройства на шине (по умолчанию: "GPU_8BPP")
      title:   Заголовок окна
    """

    def __init__(
        self,
        start: int = 0x00008000,
        width: int = 64,
        height: int = 64,
        scale: int = 6,
        format: str = "3-2-3",
        gui: bool = False,
        standalone: bool = False,
        name: str = "GPU_8BPP",
        title: str = "LIM M2 256-Color Display (8-bit / 3-2-3 RGB)"
    ):
        self.width = max(1, int(width))
        self.height = max(1, int(height))
        self.scale = max(1, int(scale))
        self.format = format.lower().strip()
        self.title = title
        self.standalone_window = bool(standalone or gui)
        self.gui = self.standalone_window

        self.vram_size = self.width * self.height
        self.ctrl_size = 16
        total_size = self.vram_size + self.ctrl_size
        self.ctrl_offset = self.vram_size

        if self.format in ("3-3-2", "332", "rgb332"):
            self._palette = _build_palette_332()
            format_code = 1
        else:
            self._palette = _build_palette_323()
            format_code = 0

        self._palette_bytes = [bytes(rgb) for rgb in self._palette]

        # Создаем временный файл для быстрой разделяемой памяти mmap с окном GUI
        self._temp_file = tempfile.NamedTemporaryFile(prefix="lim2_gpu8_", delete=False)
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
        self._raw[self.ctrl_offset + 1] = 0x00  # CLEAR_COLOR
        self._raw[self.ctrl_offset + 2] = 0x00  # VSYNC
        self._raw[self.ctrl_offset + 3] = self.width & 0xFF
        self._raw[self.ctrl_offset + 4] = (self.width >> 8) & 0xFF
        self._raw[self.ctrl_offset + 5] = self.height & 0xFF
        self._raw[self.ctrl_offset + 6] = (self.height >> 8) & 0xFF
        self._raw[self.ctrl_offset + 7] = format_code
        self._raw[self.ctrl_offset + 8] = 8     # 8 bits per pixel

        self._frame_count = 0
        self._last_vsync_time = time.time()
        self._proc: Optional[subprocess.Popen] = None

        atexit.register(self.close)

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
                f"{self.title} [{self.width}x{self.height} @ 0x{self.start:08X}]",
                self.format
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
        elif offset == self.ctrl_offset + 2:
            return self._frame_count & 0xFF
        elif offset < self.size:
            return self._raw[offset]
        return 0

    def write(self, offset: int, value: int):
        val8 = value & 0xFF
        self._vram_version = getattr(self, "_vram_version", 0) + 1
        if offset < self.vram_size:
            self._raw[offset] = val8
        elif offset == self.ctrl_offset + 1:
            # Запись в CLEAR_COLOR мгновенно заливает весь экран
            self._raw[offset] = val8
            self.clear(val8)
        elif offset < self.size:
            self._raw[offset] = val8

    # --------------------------------------------------------------------------
    # Вспомогательные методы
    # --------------------------------------------------------------------------
    def rgb_to_color(self, r: int, g: int, b: int) -> int:
        if self.format in ("3-3-2", "332"):
            r3 = min(7, (r * 7 + 127) // 255)
            g3 = min(7, (g * 7 + 127) // 255)
            b2 = min(3, (b * 3 + 127) // 255)
            return (r3 << 5) | (g3 << 2) | b2
        else:
            r3 = min(7, (r * 7 + 127) // 255)
            g2 = min(3, (g * 3 + 127) // 255)
            b3 = min(7, (b * 7 + 127) // 255)
            return (r3 << 5) | (g2 << 3) | b3

    def color_to_rgb(self, color_idx: int) -> Tuple[int, int, int]:
        return self._palette[color_idx & 0xFF]

    def set_pixel(self, x: int, y: int, color: int):
        if 0 <= x < self.width and 0 <= y < self.height:
            self._raw[y * self.width + x] = color & 0xFF
            self._vram_version = getattr(self, "_vram_version", 0) + 1

    def get_pixel(self, x: int, y: int) -> int:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self._raw[y * self.width + x]
        return 0

    def clear(self, color: int = 0):
        val8 = color & 0xFF
        self._raw[:self.vram_size] = bytes([val8]) * self.vram_size
        self._vram_version = getattr(self, "_vram_version", 0) + 1

    def on_step(self):
        now = time.time()
        if now - self._last_vsync_time >= 0.016:
            self._last_vsync_time = now
            self._frame_count = (self._frame_count + 1) & 0xFFFF
            self._raw[self.ctrl_offset + 2] = self._frame_count & 0xFF

    # --------------------------------------------------------------------------
    # Отрисовка в терминале для встроенного TUI дашборда
    # --------------------------------------------------------------------------
    def render_screen(self) -> str:
        return self.render_panel()

    def render_panel(self) -> str:
        w = 80
        title = f"{self.name} 256-COLOR 8-BIT ({self.width}x{self.height}, MODE {self.format.upper()})"
        gui_active = self._proc is not None and self._proc.poll() is None
        status = "\033[1;32mGUI OKHO\033[0m" if gui_active else "\033[90mGUI OFF\033[0m"
        vram_info = f"0x{self.start:08X}..0x{self.start + self.vram_size - 1:08X} ({self.vram_size} B)"
        ctrl_info = f"CTRL: 0x{self.start + self.ctrl_offset:08X} (VSYNC: {self._frame_count})"

        lines = [
            f"┌── [{title}] " + ("─" * max(0, w - 8 - len(title))) + "┐",
            f"│  VRAM: {vram_info:<36} Статус: {status:<22} │",
            f"│  Управление: {ctrl_info:<30} Режим: 1 байт/пикс ({self.format.upper()})    │",
        ]

        preview_h = min(8, max(2, self.height // 4))
        preview_w = min(40, self.width)
        step_x = max(1, self.width // preview_w)
        step_y = max(1, self.height // (preview_h * 2))

        lines.append(f"│  МИНИ-ПРЕВЬЮ ЭКРАНА В ТЕРМИНАЛЕ (ANSI TrueColor 8bpp):                       │")
        for py in range(preview_h):
            y_top = py * 2 * step_y
            y_bot = y_top + step_y
            tokens = []
            for px in range(preview_w):
                x = px * step_x
                t_val = self.get_pixel(x, y_top)
                b_val = self.get_pixel(x, y_bot) if y_bot < self.height else 0
                tr, tg, tb = self.color_to_rgb(t_val)
                br, bg, bb = self.color_to_rgb(b_val)
                token = f"\033[38;2;{tr};{tg};{tb}m\033[48;2;{br};{bg};{bb}m▀\033[0m"
                tokens.append(token)
            pad = " " * max(0, w - 6 - preview_w)
            lines.append(f"│  {''.join(tokens)}{pad} │")

        lines.append("└" + ("─" * (w - 2)) + "┘")
        return "\n".join(lines)


# ==============================================================================
# Независимый просмотрщик Tkinter (запускается как дочерний процесс)
# ==============================================================================
def _run_tk_viewer(fpath: str, width: int, height: int, scale: int, title: str, fmt: str):
    try:
        import tkinter as tk
    except ImportError:
        return

    vram_size = width * height
    ppm_header = f"P6\n{width} {height}\n255\n".encode("ascii")

    if fmt in ("3-3-2", "332"):
        palette = _build_palette_332()
    else:
        palette = _build_palette_323()

    palette_bytes = [bytes(rgb) for rgb in palette]

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
            text=f"Resolution: {width}x{height} | Mode: 8bpp ({fmt.upper()}) | VRAM: {vram_size} B",
            font=("Consolas", 10),
            fg="#cccccc",
            bg="#1e1e1e",
            anchor="w",
            padx=8,
            height=1
        )
        status_lbl.pack(side=tk.BOTTOM, fill=tk.X)

        raw_slice = mm[:vram_size]
        base_img = tk.PhotoImage(width=width, height=height)
        scaled_img = tk.PhotoImage(width=width * scale, height=height * scale) if scale > 1 else base_img
        ppm_data = ppm_header + b"".join(palette_bytes[b] for b in raw_slice)
        base_img.put(ppm_data)
        if scale > 1:
            root.tk.call(scaled_img, "copy", base_img, "-zoom", scale, scale)
        img_id = canvas.create_image(0, 0, image=scaled_img, anchor="nw")
        canvas.image = scaled_img
        last_vram_hash = hash(bytes(raw_slice))

        def on_mouse_move(event):
            px = event.x // scale
            py = event.y // scale
            if 0 <= px < width and 0 <= py < height:
                val8 = mm[py * width + px]
                r, g, b = palette[val8]
                if fmt in ("3-3-2", "332"):
                    r_raw = (val8 >> 5) & 7
                    g_raw = (val8 >> 2) & 7
                    b_raw = val8 & 3
                    spec = f"R:{r_raw}/7 G:{g_raw}/7 B:{b_raw}/3"
                else:
                    r_raw = (val8 >> 5) & 7
                    g_raw = (val8 >> 3) & 3
                    b_raw = val8 & 7
                    spec = f"R:{r_raw}/7 G:{g_raw}/3 B:{b_raw}/7"
                hex_col = f"#{r:02X}{g:02X}{b:02X}"
                status_lbl.config(
                    text=f"X:{px:3d} Y:{py:3d} | Byte: 0x{val8:02X} | {spec} | RGB: ({r:3d},{g:3d},{b:3d}) | HEX: {hex_col}"
                )

        canvas.bind("<Motion>", on_mouse_move)

        def poll_refresh():
            nonlocal last_vram_hash
            try:
                raw_slice = mm[:vram_size]
                cur_hash = hash(bytes(raw_slice))
                if cur_hash != last_vram_hash:
                    last_vram_hash = cur_hash
                    ppm_data = ppm_header + b"".join(palette_bytes[b] for b in raw_slice)
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


Display256Device = Display8bppDevice

if __name__ == "__main__":
    if len(sys.argv) >= 6 and sys.argv[1] == "--viewer":
        _run_tk_viewer(
            fpath=sys.argv[2],
            width=int(sys.argv[3]),
            height=int(sys.argv[4]),
            scale=int(sys.argv[5]),
            title=sys.argv[6] if len(sys.argv) > 6 else "LIM M2 Display",
            fmt=sys.argv[7] if len(sys.argv) > 7 else "3-2-3"
        )
