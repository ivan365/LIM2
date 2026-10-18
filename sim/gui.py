#!/usr/bin/env python3
# ==============================================================================
# LIM2 / sim / gui.py — Графический интерфейс симулятора процессора LIM M2
# ==============================================================================
"""
Полнофункциональное графическое окно (GUI) для симулятора архитектуры LIM M2:
  - Пошаговая отладка и свободный запуск настраиваемой скорости
  - Визуальные микросхемы РОН (R0..R7), аккумуляторов, 32-битных SREG и PTREG
  - Интерактивные цветные бейджи регистра флагов FREG (STATUS)
  - Дизассемблер с подсветкой текущей инструкции PC и точками останова (Breakpoints)
  - Обозреватель памяти устройств (NVM1, RAM1) в формате Hexdump с навигацией
  - Индикация аппаратных ножек шины (RD, WR, MREQ, IORQ, CS, IRQ, RESET, HALT, RF)
"""

import sys
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set

import tkinter as tk
from tkinter import ttk, messagebox
import tkinter.font as tkfont

CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent
COMPILER_DIR = ROOT_DIR / "compiler"
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(COMPILER_DIR) not in sys.path:
    sys.path.insert(0, str(COMPILER_DIR))

try:
    import limasm
    disassemble_one = limasm.disassemble_one
except Exception:
    def disassemble_one(read_fn, addr):
        b0 = read_fn(addr)
        return f"BYTE 0x{b0:02X}", 1, [b0]


class DarkButton(tk.Frame):
    """
    Кроссплатформенная темная кнопка (исправляет проблему белых кнопок standard tk.Button на macOS Cocoa
    и артефактов/полос отрисовки highlightthickness в Tk 9.0).
    Использует чистую двухслойную модель Frame (рамка) + Label (текст),
    что гарантирует 100% идеальный рендеринг без полос и срезов на любой ОС.
    """
    def __init__(
        self,
        master,
        text="",
        command=None,
        bg="#313244",
        fg="#cdd6f4",
        hover_bg=None,
        active_bg=None,
        border_color="#45475a",
        font=None,
        padx=10,
        pady=4,
        cursor="hand2",
        **kwargs
    ):
        self.command = command
        self._bg_normal = bg
        self._fg_normal = fg
        self._border_color = border_color
        self._bg_hover = hover_bg or self._calc_hover(bg)
        self._bg_active = active_bg or "#585b70"
        self._is_hovered = False

        super().__init__(
            master,
            bg=self._border_color,
            bd=0,
            highlightthickness=0,
            cursor=cursor
        )

        self._lbl = tk.Label(
            self,
            text=text,
            bg=self._bg_normal,
            fg=self._fg_normal,
            font=font,
            padx=padx,
            pady=pady,
            bd=0,
            highlightthickness=0,
            relief="flat",
            cursor=cursor,
            **kwargs
        )
        self._lbl.pack(fill="both", expand=True, padx=1, pady=1)

        for w in (self, self._lbl):
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
            w.bind("<ButtonPress-1>", self._on_press)
            w.bind("<ButtonRelease-1>", self._on_release)

    @staticmethod
    def _calc_hover(hex_color: str) -> str:
        if not hex_color.startswith("#") or len(hex_color) != 7:
            return "#45475a"
        try:
            r = min(255, int(int(hex_color[1:3], 16) * 1.25 + 14))
            g = min(255, int(int(hex_color[3:5], 16) * 1.25 + 14))
            b = min(255, int(int(hex_color[5:7], 16) * 1.25 + 14))
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return "#45475a"

    def _on_enter(self, e):
        self._is_hovered = True
        self._lbl.configure(bg=self._bg_hover)

    def _on_leave(self, e):
        self._is_hovered = False
        self._lbl.configure(bg=self._bg_normal)

    def _on_press(self, e):
        self._lbl.configure(bg=self._bg_active)

    def _on_release(self, e):
        if self._is_hovered:
            self._lbl.configure(bg=self._bg_hover)
            if self.command:
                self.command()
        else:
            self._lbl.configure(bg=self._bg_normal)

    def invoke(self):
        if self.command:
            return self.command()

    def cget(self, key):
        if key in ("text", "fg", "font"):
            return self._lbl.cget(key)
        if key == "bg":
            return self._bg_normal
        if key == "border_color":
            return self._border_color
        return super().cget(key)

    __getitem__ = cget

    def configure(self, **kwargs):
        if "command" in kwargs:
            self.command = kwargs.pop("command")
        if "bg" in kwargs:
            self._bg_normal = kwargs["bg"]
            if "hover_bg" not in kwargs:
                self._bg_hover = self._calc_hover(self._bg_normal)
            self._lbl.configure(bg=self._bg_normal)
        if "fg" in kwargs:
            self._fg_normal = kwargs["fg"]
            self._lbl.configure(fg=self._fg_normal)
        if "hover_bg" in kwargs:
            self._bg_hover = kwargs.pop("hover_bg")
        if "active_bg" in kwargs:
            self._bg_active = kwargs.pop("active_bg")
        if "border_color" in kwargs:
            self._border_color = kwargs.pop("border_color")
            super().configure(bg=self._border_color)
        if "text" in kwargs:
            self._lbl.configure(text=kwargs.pop("text"))
        if kwargs:
            self._lbl.configure(**kwargs)

    config = configure


class AutoScrollbar(tk.Scrollbar):
    """
    Скроллбар, который автоматически скрывается, когда всё содержимое помещается на экране,
    и появляется только тогда, когда содержимое превышает видимую область.
    """
    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)
        self._target_widget = None
        self._pack_kwargs = {"side": "right", "fill": "y"}

    def set_target(self, widget, **pack_kwargs):
        self._target_widget = widget
        if pack_kwargs:
            self._pack_kwargs = pack_kwargs

    def set(self, lo, hi):
        if float(lo) <= 0.0 and float(hi) >= 1.0:
            if self.winfo_ismapped():
                self.pack_forget()
        else:
            if not self.winfo_ismapped():
                kw = dict(self._pack_kwargs)
                if self._target_widget and self._target_widget.winfo_ismapped():
                    kw["before"] = self._target_widget
                self.pack(**kw)
        super().set(lo, hi)



class SimulatorGUI:
    """Главное графическое окно симулятора процессора."""

    def __init__(self, cpu: Any, max_steps: int = 100000, initial_speed_ms: Optional[int] = None):
        self.cpu = cpu
        self.max_steps = max_steps
        self.bus = getattr(cpu, "bus", None)

        self.is_running = False
        self.initial_speed_ms = initial_speed_ms if initial_speed_ms is not None else 50
        self.run_speed_ms = self.initial_speed_ms
        self.batch_size = 1     # Сколько шагов за один тик таймера

        self.mem_view_addr = cpu.pc
        self.selected_device_name = ""

        # Создаем окно Tkinter
        self.root = tk.Tk()
        self.root.title("LIM M2 Processor Simulator — GUI")
        self.root.geometry("1280x800")
        self.root.minsize(1050, 680)

        # Темная тема
        self.c_bg = "#1e1e2e"       # Основной фон
        self.c_panel = "#252538"    # Фон панелей
        self.c_panel_border = "#3e3e5c"
        self.c_fg = "#cdd6f4"       # Основной текст
        self.c_fg_muted = "#7f849c" # Тусклый текст
        self.c_accent = "#89b4fa"   # Синий акцент
        self.c_green = "#a6e3a1"    # Зеленый (активен)
        self.c_red = "#f38ba8"      # Красный (останов / ошибка)
        self.c_yellow = "#f9e2af"   # Желтый (PC / пауза)
        self.c_hl = "#313244"       # Подсветка строки

        self.root.configure(bg=self.c_bg)

        # Моноширинный шрифт
        available_fonts = set(tkfont.names())
        system_families = set(tkfont.families())
        if "Menlo" in system_families:
            font_family = "Menlo"
        elif "Consolas" in system_families:
            font_family = "Consolas"
        elif "DejaVu Sans Mono" in system_families:
            font_family = "DejaVu Sans Mono"
        else:
            font_family = "Courier"

        self.font_mono = (font_family, 11)
        self.font_mono_bold = (font_family, 11, "bold")
        self.font_mono_small = (font_family, 9)
        self.font_ui = ("Segoe UI" if "Segoe UI" in system_families else "Helvetica", 10)
        self.font_ui_bold = ("Segoe UI" if "Segoe UI" in system_families else "Helvetica", 10, "bold")

        # Применяем стили ttk
        self._init_ttk_styles()

        # Построение интерфейса
        self._build_toolbar()
        self._build_main_layout()
        self._build_statusbar()

        # Привязка горячих клавиш
        self.root.bind("<space>", lambda e: self.step())
        self.root.bind("<F7>", lambda e: self.step())
        self.root.bind("<F5>", lambda e: self.toggle_run())
        self.root.bind("<F9>", lambda e: self.reset_cpu())
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Глобальная обработка прокрутки колесиком мыши и тачпада (поддержка Tk 9.0 TIP 684)
        self.root.bind_all("<MouseWheel>", self._on_global_mousewheel)
        try:
            self.root.bind_all("<TouchpadScroll>", self._on_touchpad_scroll)
        except Exception:
            pass
        self.root.bind_all("<Button-4>", lambda e: self._on_global_mousewheel(e, button_direction=-1))
        self.root.bind_all("<Button-5>", lambda e: self._on_global_mousewheel(e, button_direction=1))

        # Запуск внешнего окна только если явно запрошено (dev.standalone_window = True).
        # По умолчанию все дисплеи отображаются прямо во встроенной панели GUI.
        if self.bus:
            for dev in getattr(self.bus, "_devices_list", []):
                if getattr(dev, "standalone_window", False) and hasattr(dev, "launch_gui"):
                    try:
                        dev.launch_gui()
                    except Exception as ex:
                        print(f"[GUI] Не удалось открыть окно устройства {dev.name}: {ex}")

        # Первичное обновление состояния
        self.update_all()

    def _init_ttk_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(".", background=self.c_bg, foreground=self.c_fg)
        style.configure("TFrame", background=self.c_bg)
        style.configure("Panel.TFrame", background=self.c_panel, relief="flat")
        style.configure("TLabel", background=self.c_bg, foreground=self.c_fg, font=self.font_ui)
        style.configure("Panel.TLabel", background=self.c_panel, foreground=self.c_fg, font=self.font_ui)
        style.configure("Header.TLabel", background=self.c_panel, foreground=self.c_accent, font=self.font_ui_bold)
        
        # Стили для Combobox (выбор устройства памяти)
        style.configure("TCombobox",
            fieldbackground="#181825",
            background="#313244",
            foreground=self.c_fg,
            darkcolor="#313244",
            lightcolor="#313244",
            arrowcolor=self.c_accent,
            bordercolor="#45475a",
            relief="solid",
            padding=3
        )
        style.map("TCombobox",
            fieldbackground=[("readonly", "#181825"), ("disabled", "#252538")],
            selectbackground=[("readonly", "#181825")],
            selectforeground=[("readonly", self.c_fg)],
            foreground=[("readonly", self.c_fg), ("disabled", self.c_fg_muted)]
        )

        try:
            self.root.option_add("*TCombobox*Listbox.background", "#1e1e2e")
            self.root.option_add("*TCombobox*Listbox.foreground", self.c_fg)
            self.root.option_add("*TCombobox*Listbox.selectBackground", "#45475a")
            self.root.option_add("*TCombobox*Listbox.selectForeground", self.c_fg)
        except Exception:
            pass

    @staticmethod
    def _is_child_of(widget, ancestor) -> bool:
        """Проверяет, является ли widget или любой из его предков равным ancestor."""
        curr = widget
        while curr is not None:
            if curr == ancestor:
                return True
            curr = getattr(curr, "master", None)
        return False

    def _is_pointer_inside(self, widget, x: int, y: int) -> bool:
        """Проверяет, попадают ли экранные координаты (x, y) внутрь прямоугольника виджета."""
        try:
            if not widget.winfo_ismapped():
                return False
            rx = widget.winfo_rootx()
            ry = widget.winfo_rooty()
            rw = widget.winfo_width()
            rh = widget.winfo_height()
            return (rx <= x <= rx + rw) and (ry <= y <= ry + rh)
        except Exception:
            return False

    def _dispatch_scroll(self, delta_units: int, event=None):
        if delta_units == 0:
            return

        # Получаем экранные координаты курсора мыши
        x, y = 0, 0
        if event is not None:
            x = getattr(event, "x_root", 0)
            y = getattr(event, "y_root", 0)
        if x == 0 and y == 0:
            try:
                x, y = self.root.winfo_pointerxy()
            except Exception:
                pass

        hovered = None
        if event is not None:
            hovered = getattr(event, "widget", None)
        if hovered is None and x != 0 and y != 0:
            try:
                hovered = self.root.winfo_containing(x, y)
            except Exception:
                hovered = None

        # 1. Колонка регистров
        if hasattr(self, "col_regs") and (
            self._is_pointer_inside(self.col_regs, x, y) or
            (hovered and self._is_child_of(hovered, self.col_regs))
        ):
            if hasattr(self, "canvas_regs"):
                self.canvas_regs.yview_scroll(delta_units, "units")
            return "break"

        # 2. Колонка дизассемблера (кода)
        if hasattr(self, "col_code") and (
            self._is_pointer_inside(self.col_code, x, y) or
            (hovered and self._is_child_of(hovered, self.col_code))
        ):
            if hasattr(self, "txt_code"):
                self.txt_code.yview_scroll(delta_units, "units")
            return "break"

        # 3. Колонка памяти (листает дамп по 16 байт)
        if hasattr(self, "col_mem") and (
            self._is_pointer_inside(self.col_mem, x, y) or
            (hovered and self._is_child_of(hovered, self.col_mem))
        ):
            step = 16 if delta_units > 0 else -16
            self._page_mem(step)
            return "break"

    def _on_global_mousewheel(self, event, button_direction=None):
        """
        Глобальный обработчик физического колесика мыши.
        """
        if button_direction is not None:
            delta = button_direction * 2
        elif sys.platform == "darwin":
            if event.delta != 0:
                raw_dir = -1 if event.delta > 0 else 1
                delta = raw_dir * max(2, abs(int(event.delta)))
            else:
                delta = 0
        elif sys.platform.startswith("win"):
            delta = -1 * int(event.delta / 120) * 2 if event.delta != 0 else 0
        else:
            delta = -2 if getattr(event, "num", None) == 4 else 2

        return self._dispatch_scroll(delta, event)

    def _on_touchpad_scroll(self, event):
        """
        Обработка жестов тачпада двумя пальцами в Tk 9.0 (Aqua/macOS TIP 684).
        """
        raw = getattr(event, "delta", 0) & 0xFFFFFFFF
        delta_y = raw & 0xFFFF
        if delta_y >= 0x8000:
            delta_y -= 0x10000

        units = -1 * delta_y
        if units == 0 and delta_y != 0:
            units = -1 if delta_y > 0 else 1
        return self._dispatch_scroll(units, event)


    # --------------------------------------------------------------------------
    # Верхняя панель управления (Toolbar)
    # --------------------------------------------------------------------------
    def _build_toolbar(self):
        tb = tk.Frame(self.root, bg=self.c_panel, bd=1, relief="solid", highlightbackground=self.c_panel_border)
        tb.pack(fill="x", padx=8, pady=(8, 4))

        # Левая часть — кнопки управления
        btn_frame = tk.Frame(tb, bg=self.c_panel)
        btn_frame.pack(side="left", padx=8, pady=6)

        self.btn_step = DarkButton(
            btn_frame, text="▶ Шаг (F7 / Space)", font=self.font_ui_bold,
            bg="#243b2a", fg=self.c_green, hover_bg="#2e4d35", active_bg="#3d6647",
            border_color="#345e3c", padx=10, pady=4, command=self.step
        )
        self.btn_step.pack(side="left", padx=4)

        self.btn_run = DarkButton(
            btn_frame, text="⏩ Пуск (F5)", font=self.font_ui_bold,
            bg="#25364d", fg=self.c_accent, hover_bg="#304663", active_bg="#3e5a80",
            border_color="#3b557a", padx=10, pady=4, command=self.toggle_run
        )
        self.btn_run.pack(side="left", padx=4)

        self.btn_100 = DarkButton(
            btn_frame, text="⏭ +100", font=self.font_ui,
            bg="#313244", fg=self.c_fg, hover_bg="#45475a", active_bg="#585b70",
            border_color="#45475a", padx=8, pady=4, command=lambda: self.step_n(100)
        )
        self.btn_100.pack(side="left", padx=4)

        self.btn_reset = DarkButton(
            btn_frame, text="🔄 Сброс (F9)", font=self.font_ui,
            bg="#3a2228", fg=self.c_red, hover_bg="#4c2a32", active_bg="#61343f",
            border_color="#5e2a35", padx=8, pady=4, command=self.reset_cpu
        )
        self.btn_reset.pack(side="left", padx=4)

        # Разделитель
        sep = tk.Frame(tb, width=2, bg=self.c_panel_border)
        sep.pack(side="left", fill="y", padx=10, pady=6)

        # Регулятор скорости
        spd_frame = tk.Frame(tb, bg=self.c_panel)
        spd_frame.pack(side="left", padx=4, pady=6)

        tk.Label(spd_frame, text="Скорость:", font=self.font_ui, bg=self.c_panel, fg=self.c_fg_muted).pack(side="left", padx=4)
        self.speed_scale = tk.Scale(
            spd_frame, from_=0, to=200, orient="horizontal", length=140,
            bg=self.c_panel, fg=self.c_fg, troughcolor="#313244", highlightthickness=0,
            showvalue=False, command=self._on_speed_change
        )
        init_val = min(200, max(0, self.initial_speed_ms))
        self.speed_scale.set(init_val)
        self.speed_scale.pack(side="left", padx=4)

        self.lbl_speed_val = tk.Label(spd_frame, text="20 шаг/сек", font=self.font_mono_small, bg=self.c_panel, fg=self.c_fg)
        self.lbl_speed_val.pack(side="left", padx=4)
        self._on_speed_change(init_val)

        # Правая часть — индикатор статуса
        status_frame = tk.Frame(tb, bg=self.c_panel)
        status_frame.pack(side="right", padx=12, pady=6)

        self.lbl_status_badge = tk.Label(
            status_frame, text=" [ ПАУЗА ] ", font=self.font_ui_bold,
            bg="#45475a", fg=self.c_yellow, padx=8, pady=2
        )
        self.lbl_status_badge.pack(side="right", padx=6)

        self.lbl_pc_quick = tk.Label(status_frame, text="PC: 0x00000000", font=self.font_mono_bold, bg=self.c_panel, fg=self.c_fg)
        self.lbl_pc_quick.pack(side="right", padx=10)

        self.lbl_steps_quick = tk.Label(status_frame, text="Такт #0", font=self.font_mono, bg=self.c_panel, fg=self.c_fg_muted)
        self.lbl_steps_quick.pack(side="right", padx=10)

    # --------------------------------------------------------------------------
    # --------------------------------------------------------------------------
    # Основная сетка окон
    # --------------------------------------------------------------------------
    def _build_main_layout(self):
        main_paned = tk.PanedWindow(self.root, orient="horizontal", bg=self.c_bg, sashwidth=4, bd=0)
        main_paned.pack(fill="both", expand=True, padx=8, pady=4)

        # 1. Левая колонка: Регистры и микросхемы (ширина 480 для полного отображения без срезов)
        self.col_regs = tk.Frame(main_paned, bg=self.c_panel, bd=1, relief="solid", highlightbackground=self.c_panel_border)
        main_paned.add(self.col_regs, minsize=420, width=480)

        # 2. Центральная колонка: Дизассемблер
        self.col_code = tk.Frame(main_paned, bg=self.c_panel, bd=1, relief="solid", highlightbackground=self.c_panel_border)
        main_paned.add(self.col_code, minsize=350, width=410)

        # 3. Правая колонка: Память устройств
        self.col_mem = tk.Frame(main_paned, bg=self.c_panel, bd=1, relief="solid", highlightbackground=self.c_panel_border)
        main_paned.add(self.col_mem, minsize=350, width=390)

        self._build_registers_view(self.col_regs)
        self._build_code_view(self.col_code)
        self._build_memory_view(self.col_mem)

    # --------------------------------------------------------------------------
    # Универсальные методы чтения / записи состояния процессора
    # --------------------------------------------------------------------------
    def get_cpu_reg(self, name: str) -> int:
        name_l = name.lower()
        if name_l == "pc":
            return getattr(self.cpu, "pc", 0)
        if hasattr(self.cpu, "get_reg"):
            return self.cpu.get_reg(name_l)
        if hasattr(self.cpu, "regs") and hasattr(self.cpu.regs, "get"):
            return self.cpu.regs.get(name_l)
        return getattr(self.cpu, name_l, 0)

    def set_cpu_reg(self, name: str, val: int):
        name_l = name.lower()
        if name_l == "pc":
            self.cpu.pc = val
            self.mem_view_addr = val
            return
        if hasattr(self.cpu, "set_reg"):
            self.cpu.set_reg(name_l, val)
            return
        if hasattr(self.cpu, "regs") and hasattr(self.cpu.regs, "set"):
            self.cpu.regs.set(name_l, val)
            return
        if hasattr(self.cpu, name_l):
            setattr(self.cpu, name_l, val)

    def _on_reg_entry_commit(self, rname: str, bits: int, ent: tk.Entry):
        """Применяет введённое значение регистра при нажатии Enter или потере фокуса (только во время паузы)."""
        if self.is_running:
            self.lbl_sb_left.configure(text="⚠️ Изменение регистров разрешено только во время паузы.")
            self._refresh_single_reg_entry(rname, bits, ent)
            return

        text = ent.get().strip()
        mask = (1 << bits) - 1
        try:
            val = int(text, 0) & mask
            self.set_cpu_reg(rname, val)
            hex_digits = max(2, (bits + 3) // 4)
            self.lbl_sb_left.configure(text=f"Регистр {rname.upper()} изменен: 0x{val:0{hex_digits}X} ({val})")
            self.update_all()
        except ValueError:
            self._refresh_single_reg_entry(rname, bits, ent)

    def _refresh_single_reg_entry(self, rname: str, bits: int, ent: tk.Entry):
        val = self.get_cpu_reg(rname)
        hex_digits = max(2, (bits + 3) // 4)
        ent.delete(0, "end")
        ent.insert(0, f"0x{val:0{hex_digits}X}")

    def _on_flag_click(self, fname: str, bit_pos: int):
        """Интерактивное переключение бита флага FREG по клику (только на паузе)."""
        if self.is_running:
            self.lbl_sb_left.configure(text="⚠️ Переключение флагов разрешено только во время паузы.")
            return

        freg_val = self.get_cpu_reg("freg")
        new_freg = freg_val ^ (1 << bit_pos)
        self.set_cpu_reg("freg", new_freg)
        self.update_all()
        new_val = (new_freg >> bit_pos) & 1
        self.lbl_sb_left.configure(text=f"Флаг {fname} переключен в {new_val} (FREG = 0x{new_freg:04X})")

    # --------------------------------------------------------------------------
    # Левая панель: Регистры, Флаги, Ножки (динамически подстраивается под CPU)
    # --------------------------------------------------------------------------
    def _build_registers_view(self, parent: tk.Frame):
        # Заголовок
        h_frame = tk.Frame(parent, bg=self.c_panel)
        h_frame.pack(fill="x", padx=8, pady=(8, 4))
        tk.Label(h_frame, text="МИКРОСХЕМЫ РЕГИСТРОВ (CIRCUIT IC)", font=self.font_ui_bold, bg=self.c_panel, fg=self.c_accent).pack(side="left")

        # Scrollable container for registers
        canvas = tk.Canvas(parent, bg=self.c_panel, bd=0, highlightthickness=0, yscrollincrement=16)
        scrollbar = AutoScrollbar(parent, orient="vertical", command=canvas.yview)
        scrollbar.set_target(canvas, side="right", fill="y", padx=(0, 4), pady=4)
        self.canvas_regs = canvas
        scroll_frame = tk.Frame(canvas, bg=self.c_panel)

        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas_win = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.yview_moveto(0)

        # Автоматическое растягивание содержимого по ширине канвы без срезания текста
        def _on_canvas_configure(e):
            canvas.itemconfig(canvas_win, width=e.width)
        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.bind("<MouseWheel>", self._on_global_mousewheel)
        scroll_frame.bind("<MouseWheel>", self._on_global_mousewheel)
        try:
            canvas.bind("<TouchpadScroll>", self._on_touchpad_scroll)
            scroll_frame.bind("<TouchpadScroll>", self._on_touchpad_scroll)
        except Exception:
            pass

        scrollbar.pack(side="right", fill="y", padx=(0, 4), pady=4)
        canvas.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=4)

        # Динамический сбор регистров из структуры процессора (без изменения кода CPU)
        regs_obj = getattr(self.cpu, "regs", None)
        specs = getattr(regs_obj, "_specs", {})
        indexed_names = list(getattr(regs_obj, "_indexed_names", []))
        if not indexed_names:
            import re
            indexed_names = [k for k in specs.keys() if re.match(r"^r\d+$", k)]
        if not indexed_names:
            indexed_names = [f"r{i}" for i in range(8)]

        first_gpr_spec = specs.get(indexed_names[0]) if indexed_names and specs else None
        gpr_bits = first_gpr_spec.bits if first_gpr_spec else 16

        self.reg_entries: Dict[str, tk.Entry] = {}
        self.reg_labels: Dict[str, Tuple[tk.Label, Optional[tk.Label], int]] = {}

        def _make_reg_row(parent_box, rname, title, bits, fg_color):
            row_f = tk.Frame(parent_box, bg=self.c_panel)
            row_f.pack(fill="x", padx=6, pady=2)

            w_hex = max(6, (bits // 4) + 2)
            title_w = 6 if rname.startswith("ir") or rname.startswith("pv") else (13 if bits > 16 or len(title) > 4 else 5)
            name_lbl = tk.Label(row_f, text=title, font=self.font_mono_bold, bg=self.c_panel, fg=self.c_accent if rname != "pc" else self.c_yellow, width=title_w, anchor="w")
            name_lbl.pack(side="left")

            # Интерактивное поле ввода HEX (редактируемое во время паузы)
            ent_hex = tk.Entry(
                row_f, font=self.font_mono, bg="#181825", fg=fg_color,
                insertbackground=self.c_fg, width=w_hex + 2, relief="solid", bd=1,
                highlightbackground=self.c_panel_border, highlightcolor=self.c_accent,
                highlightthickness=1, justify="center"
            )
            ent_hex.pack(side="left", padx=4)

            # Биндинги редактирования
            ent_hex.bind("<Return>", lambda e, rn=rname, b=bits, ent=ent_hex: self._on_reg_entry_commit(rn, b, ent))
            ent_hex.bind("<FocusOut>", lambda e, rn=rname, b=bits, ent=ent_hex: self._on_reg_entry_commit(rn, b, ent))
            ent_hex.bind("<FocusIn>", lambda e, ent=ent_hex: ent.select_range(0, "end"))

            # Подсветка рамки при наведении
            ent_hex.bind("<Enter>", lambda e, ent=ent_hex: ent.configure(highlightbackground="#89b4fa" if not self.is_running else self.c_panel_border))
            ent_hex.bind("<Leave>", lambda e, ent=ent_hex: ent.configure(highlightbackground=self.c_panel_border))

            # Десятичное значение (без искусственного среза ширины!)
            dec_lbl = tk.Label(row_f, text="DEC: 0", font=self.font_mono, bg=self.c_panel, fg=self.c_fg, anchor="w")
            dec_lbl.pack(side="left", padx=6)

            # Двоичное значение (для регистров до 16 бит)
            bin_lbl = None
            if bits <= 16:
                bin_lbl = tk.Label(row_f, text="0000 0000 0000 0000", font=self.font_mono_small, bg=self.c_panel, fg=self.c_fg_muted, anchor="w")
                bin_lbl.pack(side="left", padx=4)

            self.reg_entries[rname] = ent_hex
            self.reg_labels[rname] = (dec_lbl, bin_lbl, bits)
            return row_f

        # 1. Блок РОН (R0..R7)
        gpr_title = f" Регистры общего назначения ({indexed_names[0].upper()}..{indexed_names[-1].upper()}, {gpr_bits}-bit) "
        gpr_box = tk.LabelFrame(scroll_frame, text=gpr_title, font=self.font_ui_bold, bg=self.c_panel, fg=self.c_fg, bd=1)
        gpr_box.pack(fill="x", padx=4, pady=4)

        for rname in indexed_names:
            spec = specs.get(rname)
            bits = spec.bits if spec else gpr_bits
            _make_reg_row(gpr_box, rname, f"{rname.upper()}:", bits, self.c_green)

        # 2. Системные регистры, ALU и Указатели
        sys_regs = []
        ivt_regs = []
        prot_regs = []
        compact_other_regs = []
        for name, spec in specs.items():
            if name in indexed_names:
                continue
            if getattr(spec, "is_flag", False) or getattr(spec, "flag_layout", None) or name == "freg":
                continue
            if name == "pc":
                continue
            title_name = spec.title or name.upper()
            blk = getattr(spec, "block", "")
            is_comp = getattr(spec, "is_compact", False)
            if blk == "IVT" or name.startswith("ir"):
                ivt_regs.append((name, f"{title_name}:", spec.bits))
            elif blk == "PROT" or name.startswith("pv"):
                prot_regs.append((name, f"{title_name}:", spec.bits))
            elif is_comp:
                compact_other_regs.append((name, f"{title_name}:", spec.bits))
            else:
                sys_regs.append((name, f"{title_name} ({spec.bits}b):", spec.bits))

        if not sys_regs:
            sys_regs = [("acca", "ACCA (16b):", 16), ("accb", "ACCB (16b):", 16), ("sreg", "SREG (32b):", 32), ("ptreg", "PTREG(32b):", 32)]

        pc_spec = specs.get("pc")
        pc_bits = pc_spec.bits if pc_spec else 32
        sys_regs.append(("pc", f"PC   ({pc_bits}b):", pc_bits))

        sys_box = tk.LabelFrame(scroll_frame, text=" ALU, Системный стек и Указатели ", font=self.font_ui_bold, bg=self.c_panel, fg=self.c_fg, bd=1)
        sys_box.pack(fill="x", padx=4, pady=6)

        for rname, title, bits in sys_regs:
            _make_reg_row(sys_box, rname, title, bits, self.c_yellow if rname == "pc" else self.c_green)

        # 3. Регистр флагов FREG (STATUS) с интерактивным переключением битов
        flags_box = tk.LabelFrame(scroll_frame, text=" Регистр флагов (FREG / STATUS — кликните для изменения) ", font=self.font_ui_bold, bg=self.c_panel, fg=self.c_fg, bd=1)
        flags_box.pack(fill="x", padx=4, pady=6)

        freg_spec = specs.get("freg")
        flag_layout = getattr(freg_spec, "flag_layout", None) or [
            ("ZF", "Zero", 0), ("CF", "Carry", 1), ("OF", "Overflow", 2), ("EM", "ErrMath", 3),
            ("CMP0", "CmpBit0", 4), ("CMP1", "CmpBit1", 5), ("PIE", "ProgInt", 8), ("MIE", "MasterInt", 9),
            ("DWR", "NoWait", 10), ("PRV", "Superv", 11), ("AIP", "AutoInc", 12), ("DBIT", "DispBit", 13),
            ("SMOD", "ShiftMod", 14), ("INTR", "InIntr", 15)
        ]

        self.flag_badges: Dict[str, Tuple[tk.Label, int]] = {}
        grid_frame = tk.Frame(flags_box, bg=self.c_panel)
        grid_frame.pack(fill="x", padx=6, pady=4)

        for idx, (fname, fdesc, bit_pos) in enumerate(flag_layout):
            r = idx // 4
            c = idx % 4
            b_lbl = tk.Label(
                grid_frame, text=f"[{fname}: 0]", font=self.font_mono_small,
                bg="#313244", fg=self.c_fg_muted, padx=6, pady=3, relief="solid", bd=1,
                highlightbackground="#45475a", highlightthickness=1, width=9, cursor="hand2"
            )
            b_lbl.grid(row=r, column=c, padx=3, pady=3, sticky="ew")
            b_lbl.bind("<Button-1>", lambda e, fn=fname, bp=bit_pos: self._on_flag_click(fn, bp))
            b_lbl.bind("<Enter>", lambda e, lbl=b_lbl: lbl.configure(highlightbackground="#89b4fa" if not self.is_running else "#45475a"))
            b_lbl.bind("<Leave>", lambda e, lbl=b_lbl: lbl.configure(highlightbackground="#45475a"))
            self.flag_badges[fname] = (b_lbl, bit_pos)

        for c in range(4):
            grid_frame.columnconfigure(c, weight=1)

        # 4. Таблица векторов прерываний (IVT: IR0..IR15, 32-bit) — в одну аккуратную колонку
        if ivt_regs:
            ivt_box = tk.LabelFrame(scroll_frame, text=" Векторы прерываний (IVT: IR0..IR15, 32-bit) ", font=self.font_ui_bold, bg=self.c_panel, fg=self.c_fg, bd=1)
            ivt_box.pack(fill="x", padx=4, pady=6)
            for rname, title, bits in ivt_regs:
                _make_reg_row(ivt_box, rname, title, bits, self.c_green)

        # 5. Зоны защиты привилегий (PROT: PV0..PV15, 32-bit) — в одну аккуратную колонку
        if prot_regs:
            prot_box = tk.LabelFrame(scroll_frame, text=" Зоны защиты привилегий (PROT: PV0..PV15, 32-bit) ", font=self.font_ui_bold, bg=self.c_panel, fg=self.c_fg, bd=1)
            prot_box.pack(fill="x", padx=4, pady=6)
            for rname, title, bits in prot_regs:
                _make_reg_row(prot_box, rname, title, bits, self.c_green)

        # Дополнительные табличные/компактные регистры
        if compact_other_regs:
            comp_box = tk.LabelFrame(scroll_frame, text=" Дополнительные табличные регистры ", font=self.font_ui_bold, bg=self.c_panel, fg=self.c_fg, bd=1)
            comp_box.pack(fill="x", padx=4, pady=6)
            for rname, title, bits in compact_other_regs:
                _make_reg_row(comp_box, rname, title, bits, self.c_green)

        # 6. Ножки процессора / шины
        pins_box = tk.LabelFrame(scroll_frame, text=" Ножки процессора / PINS ", font=self.font_ui_bold, bg=self.c_panel, fg=self.c_fg, bd=1)
        pins_box.pack(fill="x", padx=4, pady=6)

        pins_frame = tk.Frame(pins_box, bg=self.c_panel)
        pins_frame.pack(fill="x", padx=6, pady=4)

        self.pin_badges: Dict[str, tk.Label] = {}
        key_order = ["RD", "WR", "MREQ", "IORQ", "CS", "IRQ", "IA", "RESET", "HALT", "RF"]
        for idx, pname in enumerate(key_order):
            r = idx // 5
            c = idx % 5
            p_lbl = tk.Label(
                pins_frame, text=f"{pname}:0", font=self.font_mono_small,
                bg="#313244", fg=self.c_fg_muted, padx=4, pady=2, relief="solid", bd=1,
                highlightbackground="#45475a", highlightthickness=1, width=7, cursor="hand2"
            )
            p_lbl.grid(row=r, column=c, padx=2, pady=2, sticky="ew")
            p_lbl.bind("<Button-1>", lambda e, pn=pname: self._toggle_pin(pn))
            self.pin_badges[pname] = p_lbl

        for c in range(5):
            pins_frame.columnconfigure(c, weight=1)

        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

    # --------------------------------------------------------------------------
    # Центральная панель: Дизассемблер
    # --------------------------------------------------------------------------
    def _build_code_view(self, parent: tk.Frame):
        h_frame = tk.Frame(parent, bg=self.c_panel)
        h_frame.pack(fill="x", padx=8, pady=(8, 4))

        btn_pc_jump = DarkButton(
            h_frame, text="К PC", font=self.font_ui, bg="#313244", fg=self.c_yellow,
            hover_bg="#45475a", active_bg="#585b70", border_color="#45475a",
            padx=8, pady=2, command=self.update_code_view
        )
        btn_pc_jump.pack(side="right")

        # Текстовое поле дизассемблера с тегами стилей
        c_frame = tk.Frame(parent, bg=self.c_panel)
        c_frame.pack(fill="both", expand=True, padx=8, pady=(4, 8))

        self.txt_code = tk.Text(
            c_frame, font=self.font_mono, bg="#181825", fg=self.c_fg,
            insertbackground=self.c_fg, selectbackground="#45475a",
            wrap="none", bd=0, highlightthickness=1, highlightbackground=self.c_panel_border,
            cursor="arrow"
        )
        scroll_code = AutoScrollbar(c_frame, orient="vertical", command=self.txt_code.yview)
        scroll_code.set_target(self.txt_code, side="right", fill="y")
        self.txt_code.configure(yscrollcommand=scroll_code.set)

        scroll_code.pack(side="right", fill="y")
        self.txt_code.pack(side="left", fill="both", expand=True)

        # Настройка тегов стилей
        self.txt_code.tag_configure("pc_curr", background="#f9e2af", foreground="#11111b", font=self.font_mono_bold)
        self.txt_code.tag_configure("addr", foreground=self.c_accent)
        self.txt_code.tag_configure("hex", foreground=self.c_fg_muted)
        self.txt_code.tag_configure("mnem", foreground=self.c_fg)
        self.txt_code.tag_configure("bpoint", background="#f38ba8", foreground="#11111b")

        # Двойной клик — установить/снять точку останова
        self.txt_code.bind("<Double-Button-1>", self._on_code_double_click)

        # Прокрутка колесиком мыши по дизассемблеру
        def _on_code_mousewheel(event):
            if sys.platform == "darwin":
                delta = -1 * event.delta
            elif sys.platform.startswith("win"):
                delta = -1 * int(event.delta / 120)
            else:
                delta = -1 if event.num == 4 else 1
            self.txt_code.yview_scroll(delta, "units")
            return "break"

        self.txt_code.bind("<MouseWheel>", _on_code_mousewheel)
        try:
            self.txt_code.bind("<TouchpadScroll>", self._on_touchpad_scroll)
        except Exception:
            pass
        self.txt_code.bind("<Button-4>", lambda e: (self.txt_code.yview_scroll(-2, "units"), "break")[1])
        self.txt_code.bind("<Button-5>", lambda e: (self.txt_code.yview_scroll(2, "units"), "break")[1])

    # --------------------------------------------------------------------------
    # Правая панель: Память устройств (Hexdump)
    # --------------------------------------------------------------------------
    def _build_memory_view(self, parent: tk.Frame):
        h_frame = tk.Frame(parent, bg=self.c_panel)
        h_frame.pack(fill="x", padx=8, pady=(8, 4))

        tk.Label(h_frame, text="ПАМЯТЬ УСТРОЙСТВ (HEXDUMP)", font=self.font_ui_bold, bg=self.c_panel, fg=self.c_accent).pack(side="left")

        # Выбор устройства и навигация
        ctrl_frame = tk.Frame(parent, bg=self.c_panel)
        ctrl_frame.pack(fill="x", padx=8, pady=4)

        dev_names = [d.name for d in getattr(self.bus, "_devices_list", [])] or ["RAM"]
        self.cb_dev = ttk.Combobox(ctrl_frame, values=dev_names, state="readonly", width=10)
        if dev_names:
            self.cb_dev.current(0)
            self.selected_device_name = dev_names[0]
        self.cb_dev.pack(side="left", padx=(0, 4))
        self.cb_dev.bind("<<ComboboxSelected>>", self._on_dev_selected)

        tk.Label(ctrl_frame, text="0x", font=self.font_mono, bg=self.c_panel, fg=self.c_fg_muted).pack(side="left")
        self.ent_addr = tk.Entry(
            ctrl_frame, font=self.font_mono, bg="#181825", fg=self.c_fg,
            insertbackground=self.c_fg, width=8, bd=1, relief="solid",
            highlightbackground="#45475a", highlightthickness=1
        )
        self.ent_addr.insert(0, f"{self.cpu.pc:X}")
        self.ent_addr.pack(side="left", padx=2)
        self.ent_addr.bind("<Return>", lambda e: self._on_goto_addr())

        btn_go = DarkButton(
            ctrl_frame, text="Перейти", font=self.font_ui, bg="#313244", fg=self.c_accent,
            hover_bg="#45475a", active_bg="#585b70", border_color="#45475a",
            padx=8, pady=2, command=self._on_goto_addr
        )
        btn_go.pack(side="left", padx=2)

        btn_prev = DarkButton(
            ctrl_frame, text="▲ -256", font=self.font_ui, bg="#313244", fg=self.c_fg,
            hover_bg="#45475a", active_bg="#585b70", border_color="#45475a",
            padx=6, pady=2, command=lambda: self._page_mem(-256)
        )
        btn_prev.pack(side="left", padx=2)

        btn_next = DarkButton(
            ctrl_frame, text="▼ +256", font=self.font_ui, bg="#313244", fg=self.c_fg,
            hover_bg="#45475a", active_bg="#585b70", border_color="#45475a",
            padx=6, pady=2, command=lambda: self._page_mem(256)
        )
        btn_next.pack(side="left", padx=2)

        # Текстовое окно Hexdump (компактно 16 строк для страницы 256 байт)
        m_frame = tk.Frame(parent, bg=self.c_panel)
        m_frame.pack(fill="x", padx=8, pady=(4, 2))

        self.txt_mem = tk.Text(
            m_frame, font=self.font_mono, bg="#181825", fg=self.c_fg,
            insertbackground=self.c_fg, selectbackground="#45475a",
            wrap="none", bd=0, highlightthickness=1, highlightbackground=self.c_panel_border,
            cursor="hand2", height=16
        )
        scroll_mem = AutoScrollbar(m_frame, orient="vertical", command=self.txt_mem.yview)
        scroll_mem.set_target(self.txt_mem, side="right", fill="y")
        self.txt_mem.configure(yscrollcommand=scroll_mem.set)

        scroll_mem.pack(side="right", fill="y")
        self.txt_mem.pack(side="left", fill="both", expand=True)

        self.txt_mem.tag_configure("pc_byte", background="#f9e2af", foreground="#11111b", font=self.font_mono_bold)
        self.txt_mem.tag_configure("addr", foreground=self.c_accent)
        self.txt_mem.tag_configure("ascii", foreground=self.c_green)

        # Интерактивное редактирование по двойному клику и подсказка по одинарному
        self.txt_mem.bind("<Button-1>", self._on_mem_click)
        self.txt_mem.bind("<Double-Button-1>", self._on_mem_double_click)

        # Прокрутка колесиком мыши по памяти: листает память строками по 16 байт
        def _on_mem_mousewheel(event):
            if sys.platform == "darwin":
                delta = -1 * event.delta
            elif sys.platform.startswith("win"):
                delta = -1 * int(event.delta / 120)
            else:
                delta = -1 if event.num == 4 else 1
            step = 16 if delta > 0 else -16
            self._page_mem(step)
            return "break"

        self.txt_mem.bind("<MouseWheel>", _on_mem_mousewheel)
        try:
            self.txt_mem.bind("<TouchpadScroll>", self._on_touchpad_scroll)
        except Exception:
            pass
        self.txt_mem.bind("<Button-4>", lambda e: (self._page_mem(-16), "break")[1])
        self.txt_mem.bind("<Button-5>", lambda e: (self._page_mem(16), "break")[1])

        # Встраиваем экран / терминал прямо под дамп памяти
        self._build_screen_view(parent)

    # --------------------------------------------------------------------------
    # Встроенный монитор / терминал (Display & Terminal Subsystem)
    # --------------------------------------------------------------------------
    @classmethod
    def _get_cached_palette_323(cls):
        if not hasattr(cls, "_palette_323_cache"):
            cls._palette_323_cache = [
                bytes(( ((i >> 5) & 7) * 255 // 7, ((i >> 3) & 3) * 255 // 3, (i & 7) * 255 // 7 ))
                for i in range(256)
            ]
        return cls._palette_323_cache

    @classmethod
    def _get_cached_palette_332(cls):
        if not hasattr(cls, "_palette_332_cache"):
            cls._palette_332_cache = [
                bytes(( ((i >> 5) & 7) * 255 // 7, ((i >> 2) & 7) * 255 // 7, (i & 3) * 255 // 3 ))
                for i in range(256)
            ]
        return cls._palette_332_cache

    def _build_screen_view(self, parent: tk.Frame):
        div = tk.Frame(parent, height=1, bg=self.c_panel_border)
        div.pack(fill="x", padx=8, pady=(4, 4))

        # Заголовок секции экрана
        s_header = tk.Frame(parent, bg=self.c_panel)
        s_header.pack(fill="x", padx=8, pady=(0, 2))

        tk.Label(
            s_header, text="ЭКРАН / ТЕРМИНАЛ", font=self.font_ui_bold,
            bg=self.c_panel, fg=self.c_accent
        ).pack(side="left")

        self._display_map: Dict[str, Any] = {}
        self.cb_monitor = ttk.Combobox(s_header, state="readonly", width=16)
        self.cb_monitor.pack(side="left", padx=6)
        self.cb_monitor.bind("<<ComboboxSelected>>", lambda e: self._on_monitor_selected())

        btn_popout = DarkButton(
            s_header, text="В окно ↗", font=self.font_ui, bg="#313244", fg=self.c_accent,
            hover_bg="#45475a", active_bg="#585b70", border_color="#45475a",
            padx=6, pady=2, command=self._on_popout_screen
        )
        btn_popout.pack(side="right", padx=(2, 0))

        btn_clr = DarkButton(
            s_header, text="Очистить", font=self.font_ui, bg="#313244", fg=self.c_fg,
            hover_bg="#45475a", active_bg="#585b70", border_color="#45475a",
            padx=6, pady=2, command=self._on_clear_screen
        )
        btn_clr.pack(side="right", padx=2)

        self.lbl_screen_info = tk.Label(
            s_header, text="", font=self.font_mono_small,
            bg=self.c_panel, fg=self.c_yellow
        )
        self.lbl_screen_info.pack(side="right", padx=4)

        # Контейнер для отображения экранов
        self.screen_container = tk.Frame(
            parent, bg="#11111b", bd=1, relief="solid", highlightbackground=self.c_panel_border
        )
        self.screen_container.pack(fill="both", expand=True, padx=8, pady=(2, 6))

        # 1. Подпредставление: Пусто (нет мониторов)
        self.subview_empty = tk.Frame(self.screen_container, bg="#181825")
        tk.Label(
            self.subview_empty, text="📺 ВСТРОЕННЫЙ МОНИТОР / ТЕРМИНАЛ",
            font=self.font_ui_bold, bg="#181825", fg=self.c_accent
        ).pack(pady=(10, 4))

        tk.Label(
            self.subview_empty,
            text="Монитор пока не подключен к шине процессора.\nПодключите его в Python коде:",
            font=self.font_ui, bg="#181825", fg=self.c_fg_muted, justify="center"
        ).pack(pady=2)

        code_sample = (
            "from sim.devices import TextScreen, Display256, Display16M\n"
            "bus.attach(TextScreen(0x020000, width=40, height=12))\n"
            "bus.attach(Display256(0x030000, width=64, height=64))"
        )
        lbl_code = tk.Label(
            self.subview_empty, text=code_sample, font=self.font_mono_small,
            bg="#11111b", fg=self.c_yellow, padx=10, pady=6, bd=1, relief="solid",
            highlightbackground="#313244", justify="left"
        )
        lbl_code.pack(pady=4)

        btn_bar = tk.Frame(self.subview_empty, bg="#181825")
        btn_bar.pack(pady=(4, 10))

        DarkButton(
            btn_bar, text="+ TextScreen", font=self.font_ui,
            bg="#25364d", fg=self.c_accent, hover_bg="#304663", active_bg="#3e5a80",
            border_color="#3b557a", padx=6, pady=3,
            command=self._add_default_text_screen
        ).pack(side="left", padx=3)

        DarkButton(
            btn_bar, text="+ Display256", font=self.font_ui,
            bg="#313244", fg=self.c_green, hover_bg="#45475a", active_bg="#585b70",
            border_color="#45475a", padx=6, pady=3,
            command=lambda: self._add_default_pixel_screen(is_16m=False)
        ).pack(side="left", padx=3)

        DarkButton(
            btn_bar, text="+ Display16M", font=self.font_ui,
            bg="#313244", fg=self.c_yellow, hover_bg="#45475a", active_bg="#585b70",
            border_color="#45475a", padx=6, pady=3,
            command=lambda: self._add_default_pixel_screen(is_16m=True)
        ).pack(side="left", padx=3)

        # 2. Подпредставление: Текстовый экран CRT
        self.subview_text = tk.Frame(self.screen_container, bg="#0d1117")
        self.txt_screen = tk.Text(
            self.subview_text, bg="#0d1117", fg="#a6e3a1", font=self.font_mono,
            insertbackground="#a6e3a1", selectbackground="#313244",
            wrap="none", bd=0, highlightthickness=0, state="disabled", cursor="arrow"
        )
        self.txt_screen.pack(fill="both", expand=True, padx=8, pady=(6, 2))

        self.lbl_text_status = tk.Label(
            self.subview_text, text="CRT TERMINAL • ASCII MMIO",
            font=self.font_mono_small, bg="#161b22", fg="#7f849c", anchor="w", padx=6, pady=2
        )
        self.lbl_text_status.pack(fill="x", side="bottom")

        # 3. Подпредставление: Графический пиксельный экран
        self.subview_pixel = tk.Frame(self.screen_container, bg="#11111b")
        self.canvas_pixel = tk.Canvas(
            self.subview_pixel, bg="#11111b", bd=0, highlightthickness=0
        )
        self.canvas_pixel.pack(fill="both", expand=True, padx=4, pady=4)
        self.canvas_pixel.bind("<Configure>", lambda e: self.update_screen_view())

        self.lbl_pixel_status = tk.Label(
            self.subview_pixel, text="PIXEL VRAM",
            font=self.font_mono_small, bg="#181825", fg="#7f849c", anchor="w", padx=6, pady=2
        )
        self.lbl_pixel_status.pack(fill="x", side="bottom")

        # 4. Подпредставление: UART консоль
        self.subview_uart = tk.Frame(self.screen_container, bg="#181825")
        self.txt_uart = tk.Text(
            self.subview_uart, bg="#11111b", fg=self.c_fg, font=self.font_mono_small,
            bd=0, highlightthickness=1, highlightbackground=self.c_panel_border,
            state="disabled", wrap="word"
        )
        self.txt_uart.pack(fill="both", expand=True, padx=6, pady=(6, 4))

        uart_input_bar = tk.Frame(self.subview_uart, bg="#181825")
        uart_input_bar.pack(fill="x", padx=6, pady=(0, 6))

        tk.Label(uart_input_bar, text="TX >", font=self.font_mono_bold, bg="#181825", fg=self.c_accent).pack(side="left", padx=2)
        self.ent_uart = tk.Entry(
            uart_input_bar, font=self.font_mono_small, bg="#11111b", fg=self.c_fg,
            insertbackground=self.c_fg, bd=1, relief="solid", highlightbackground="#45475a", highlightthickness=1
        )
        self.ent_uart.pack(side="left", fill="x", expand=True, padx=4)
        self.ent_uart.bind("<Return>", lambda e: self._on_uart_send())

        DarkButton(
            uart_input_bar, text="Отправить", font=self.font_ui, bg="#313244", fg=self.c_accent,
            hover_bg="#45475a", active_bg="#585b70", border_color="#45475a",
            padx=8, pady=2, command=self._on_uart_send
        ).pack(side="right")

        self._refresh_monitors_list()

    def _get_display_devices(self) -> List[Any]:
        if not self.bus or not hasattr(self.bus, "_devices_list"):
            return []
        displays = []
        for dev in self.bus._devices_list:
            if getattr(dev, "is_video", False) or hasattr(dev, "tx_history") or hasattr(dev, "print_text") or hasattr(dev, "_palette"):
                displays.append(dev)
        return displays

    def _format_display_label(self, dev: Any) -> str:
        name = getattr(dev, "name", "DEV")
        w = getattr(dev, "width", 0)
        h = getattr(dev, "height", 0)
        if hasattr(dev, "tx_history"):
            return f"{name} [UART]"
        is_text = hasattr(dev, "print_text") or (getattr(dev, "is_video", False) and w <= 80 and h <= 35 and getattr(dev, "size", 0) < 4000)
        if is_text and w > 0 and h > 0:
            return f"{name} [Текст {w}x{h}]"
        if getattr(dev, "size", 0) >= w * h * 3 and w > 0:
            return f"{name} [16M {w}x{h}]"
        if w > 0 and h > 0:
            return f"{name} [256ц {w}x{h}]"
        return f"{name} [Экран]"

    def _refresh_monitors_list(self):
        displays = self._get_display_devices()
        values = []
        self._display_map = {}
        for d in displays:
            label = self._format_display_label(d)
            values.append(label)
            self._display_map[label] = d

        if hasattr(self, "cb_monitor"):
            if values:
                self.cb_monitor.configure(values=values)
                cur = self.cb_monitor.get()
                if cur not in values:
                    self.cb_monitor.current(0)
                self._on_monitor_selected()
            else:
                self.cb_monitor.configure(values=["Нет устройств"])
                self.cb_monitor.set("Нет устройств")
                if hasattr(self, "lbl_screen_info"):
                    self.lbl_screen_info.configure(text="")
                self._show_screen_subview("empty")

    def _on_monitor_selected(self):
        dev = self._get_current_selected_monitor()
        if not dev:
            self._show_screen_subview("empty")
            if hasattr(self, "lbl_screen_info"):
                self.lbl_screen_info.configure(text="")
            return

        w = getattr(dev, "width", 0)
        h = getattr(dev, "height", 0)
        addr_str = f"0x{dev.start:06X}" if hasattr(dev, "start") else ""

        if hasattr(dev, "tx_history"):
            self._show_screen_subview("uart")
            self.lbl_screen_info.configure(text=f"UART • {addr_str}")
        elif hasattr(dev, "print_text") or (getattr(dev, "is_video", False) and w <= 80 and h <= 35 and getattr(dev, "size", 0) < 4000):
            self._show_screen_subview("text")
            self.lbl_screen_info.configure(text=f"Текст {w}x{h} • {addr_str}")
        else:
            self._show_screen_subview("pixel")
            is_16m = getattr(dev, "size", 0) >= w * h * 3
            c_mode = "16M" if is_16m else "256ц"
            self.lbl_screen_info.configure(text=f"{c_mode} {w}x{h} • {addr_str}")

        self.update_screen_view()

    def _show_screen_subview(self, mode: str):
        for sub in (getattr(self, "subview_empty", None), getattr(self, "subview_text", None), getattr(self, "subview_pixel", None), getattr(self, "subview_uart", None)):
            if sub:
                sub.pack_forget()

        if mode == "text" and hasattr(self, "subview_text"):
            self.subview_text.pack(fill="both", expand=True)
        elif mode == "pixel" and hasattr(self, "subview_pixel"):
            self.subview_pixel.pack(fill="both", expand=True)
        elif mode == "uart" and hasattr(self, "subview_uart"):
            self.subview_uart.pack(fill="both", expand=True)
        elif hasattr(self, "subview_empty"):
            self.subview_empty.pack(fill="both", expand=True)

    def _get_current_selected_monitor(self) -> Optional[Any]:
        if not hasattr(self, "cb_monitor") or not hasattr(self, "_display_map"):
            return None
        return self._display_map.get(self.cb_monitor.get())

    def _on_clear_screen(self):
        dev = self._get_current_selected_monitor()
        if not dev:
            return
        if hasattr(dev, "clear"):
            dev.clear()
        elif hasattr(dev, "tx_history"):
            dev.tx_history.clear()
        elif hasattr(dev, "_raw"):
            vlen = getattr(dev, "vram_size", getattr(dev, "size", 0))
            dev._raw[:vlen] = bytes(vlen)
        self.update_screen_view()
        self.lbl_sb_left.configure(text=f"Экран устройства '{dev.name}' очищен.")

    def _on_popout_screen(self):
        dev = self._get_current_selected_monitor()
        if not dev:
            return
        if hasattr(dev, "launch_gui"):
            try:
                dev.launch_gui()
                self.lbl_sb_left.configure(text=f"Монитор '{dev.name}' запущен в отдельном окне.")
            except Exception as ex:
                self.lbl_sb_left.configure(text=f"Ошибка открытия внешнего окна: {ex}")
        else:
            self.lbl_sb_left.configure(text=f"Устройство '{dev.name}' отображается во встроенном режиме.")

    def _on_uart_send(self):
        if not hasattr(self, "ent_uart"):
            return
        text = self.ent_uart.get()
        if not text:
            return
        dev = self._get_current_selected_monitor()
        if dev and hasattr(dev, "queue_input"):
            dev.queue_input(text + "\n")
            self.ent_uart.delete(0, "end")
            self.lbl_sb_left.configure(text=f"Отправлено в UART '{dev.name}': {text}")

    def _add_default_text_screen(self):
        if not self.bus:
            return
        start_addr = 0x00020000
        if hasattr(self.bus, "_devices_list"):
            for d in self.bus._devices_list:
                if d.start <= start_addr <= d.end:
                    start_addr = (d.end + 0x1000) & ~0xFFF
        try:
            from devices import TextScreenDevice
        except Exception:
            try:
                from .devices import TextScreenDevice
            except Exception:
                from LIM2.sim.devices import TextScreenDevice

        dev = TextScreenDevice(start=start_addr, width=40, height=12, name="SCREEN")
        dev.print_text("LIM M2 RETRO TERMINAL READY.", offset=0)
        dev.print_text("MMIO VIDEO MEMORY 40x12 OK.", offset=40)
        self.bus.attach(dev)

        self._refresh_dev_combobox()
        self._refresh_monitors_list()
        self._select_monitor_by_device(dev)
        self.update_all()
        self.lbl_sb_left.configure(text=f"📺 Подключен текстовый терминал '{dev.name}' [40x12] по адресу 0x{start_addr:06X}")

    def _add_default_pixel_screen(self, is_16m: bool = False):
        if not self.bus:
            return
        start_addr = 0x00040000 if not is_16m else 0x00080000
        if hasattr(self.bus, "_devices_list"):
            for d in self.bus._devices_list:
                if d.start <= start_addr <= d.end:
                    start_addr = (d.end + 0x1000) & ~0xFFF

        if is_16m:
            try:
                from devices import Display16MDevice
            except Exception:
                try:
                    from .devices import Display16MDevice
                except Exception:
                    from LIM2.sim.devices import Display16MDevice
            dev = Display16MDevice(start=start_addr, width=64, height=64, name="GPU_16M", gui=False)
        else:
            try:
                from devices import Display256Device
            except Exception:
                try:
                    from .devices import Display256Device
                except Exception:
                    from LIM2.sim.devices import Display256Device
            dev = Display256Device(start=start_addr, width=64, height=64, name="GPU_256", gui=False)

        self.bus.attach(dev)
        self._refresh_dev_combobox()
        self._refresh_monitors_list()
        self._select_monitor_by_device(dev)
        self.update_all()
        mode_name = "16.7M TrueColor" if is_16m else "256 цветов"
        self.lbl_sb_left.configure(text=f"📺 Подключен графический экран '{dev.name}' [64x64, {mode_name}] по адресу 0x{start_addr:06X}")

    def _select_monitor_by_device(self, target_dev: Any):
        if not hasattr(self, "cb_monitor") or not hasattr(self, "_display_map"):
            return
        for label, dev in self._display_map.items():
            if dev == target_dev:
                self.cb_monitor.set(label)
                self._on_monitor_selected()
                break

    def _refresh_dev_combobox(self):
        if hasattr(self, "cb_dev") and self.bus:
            dev_names = [d.name for d in getattr(self.bus, "_devices_list", [])] or ["RAM"]
            self.cb_dev.configure(values=dev_names)

    def update_screen_view(self):
        """Обновляет текущий активный встроенный монитор/терминал."""
        if not hasattr(self, "cb_monitor") or not hasattr(self, "_display_map"):
            return

        label = self.cb_monitor.get()
        dev = self._display_map.get(label)
        if not dev:
            self._show_screen_subview("empty")
            return

        dev_version = getattr(dev, "_vram_version", 0)

        # 1. UART терминал
        if hasattr(dev, "tx_history"):
            self._show_screen_subview("uart")
            if getattr(self, "_last_uart_dev", None) is dev and getattr(self, "_last_uart_version", None) == dev_version:
                return
            history_text = "".join(getattr(dev, "tx_history", []))
            self.txt_uart.configure(state="normal")
            cur_txt = self.txt_uart.get("1.0", "end-1c")
            if cur_txt != history_text:
                self.txt_uart.delete("1.0", "end")
                self.txt_uart.insert("end", history_text)
                self.txt_uart.see("end")
            self.txt_uart.configure(state="disabled")
            self._last_uart_dev = dev
            self._last_uart_version = dev_version
            return

        # 2. Текстовый экран CRT
        w = getattr(dev, "width", 0)
        h = getattr(dev, "height", 0)
        is_text = hasattr(dev, "print_text") or (getattr(dev, "is_video", False) and w <= 80 and h <= 35 and getattr(dev, "size", 0) < 4000)
        if is_text and w > 0 and h > 0:
            self._show_screen_subview("text")
            if getattr(self, "_last_text_dev", None) is dev and getattr(self, "_last_text_version", None) == dev_version:
                return
            raw = getattr(dev, "_raw", None)
            if raw is not None:
                lines = []
                for r in range(h):
                    row_bytes = raw[r * w : (r + 1) * w]
                    line_chars = "".join(chr(b) if 32 <= b <= 126 else (" " if b == 0 else "·") for b in row_bytes)
                    lines.append(line_chars)
                text_content = "\n".join(lines)
                self.txt_screen.configure(state="normal")
                if self.txt_screen.get("1.0", "end-1c") != text_content:
                    self.txt_screen.delete("1.0", "end")
                    self.txt_screen.insert("1.0", text_content)
                self.txt_screen.configure(state="disabled")
            self._last_text_dev = dev
            self._last_text_version = dev_version
            self.lbl_text_status.configure(text=f"CRT TERMINAL • {w}x{h} ({w*h} B) • MMIO 0x{dev.start:06X}")
            return

        # 3. Графический пиксельный экран (8bpp или 24bpp)
        if w > 0 and h > 0:
            self._show_screen_subview("pixel")
            raw = getattr(dev, "_raw", None)
            if raw is None:
                return

            cw = max(64, self.canvas_pixel.winfo_width())
            ch = max(64, self.canvas_pixel.winfo_height())
            scale = max(1, min(cw // w, ch // h, 8))

            last_dev = getattr(self, "_last_pixel_dev", None)
            last_version = getattr(self, "_last_pixel_version", None)
            last_scale = getattr(self, "_last_pixel_scale", None)

            # Если VRAM не менялась и масштаб холста тот же — выходим мгновенно без единой аллокации (0 мс)
            if last_dev is dev and last_version == dev_version and last_scale == scale:
                return

            vram_len = len(raw)
            is_24bpp = (vram_len >= w * h * 3) and getattr(dev, "size", 0) >= w * h * 3

            if is_24bpp:
                rgb_bytes = bytes(raw[:w * h * 3])
                mode_str = "16.7M TrueColor (24bpp)"
            else:
                palette = getattr(dev, "_palette_bytes", None)
                if not palette:
                    fmt = getattr(dev, "format", getattr(dev, "mode", "3-2-3"))
                    if str(fmt).lower() in ("3-3-2", "332", "rgb332"):
                        palette = self._get_cached_palette_332()
                    else:
                        palette = self._get_cached_palette_323()
                vram_data = raw[:w * h]
                rgb_bytes = b"".join(palette[b] for b in vram_data)
                mode_str = f"256 цветов ({getattr(dev, 'format', '3-2-3')})"

            ppm_header = f"P6\n{w} {h}\n255\n".encode("ascii")
            if not hasattr(self, "_base_pixel_img") or getattr(self, "_base_pixel_w", 0) != w or getattr(self, "_base_pixel_h", 0) != h:
                self._base_pixel_img = tk.PhotoImage(width=w, height=h)
                self._base_pixel_w = w
                self._base_pixel_h = h

            self._base_pixel_img.put(ppm_header + rgb_bytes)

            scaled_w = w * scale
            scaled_h = h * scale
            if (not hasattr(self, "_scaled_pixel_img") or
                getattr(self, "_scaled_pixel_w", 0) != scaled_w or
                getattr(self, "_scaled_pixel_h", 0) != scaled_h):
                if hasattr(self, "_scaled_pixel_img") and self._scaled_pixel_img:
                    try:
                        self.root.tk.call("image", "delete", self._scaled_pixel_img)
                    except Exception:
                        pass
                self._scaled_pixel_img = tk.PhotoImage(width=scaled_w, height=scaled_h)
                self._scaled_pixel_w = scaled_w
                self._scaled_pixel_h = scaled_h

            if scale > 1:
                self.root.tk.call(self._scaled_pixel_img, "copy", self._base_pixel_img, "-zoom", scale, scale)
            else:
                self.root.tk.call(self._scaled_pixel_img, "copy", self._base_pixel_img)

            cx = cw // 2
            cy = ch // 2
            if not hasattr(self, "_canvas_img_id") or not self._canvas_img_id:
                self._canvas_img_id = self.canvas_pixel.create_image(cx, cy, anchor="center", image=self._scaled_pixel_img)
            else:
                self.canvas_pixel.coords(self._canvas_img_id, cx, cy)
                self.canvas_pixel.itemconfig(self._canvas_img_id, image=self._scaled_pixel_img)

            self._last_pixel_dev = dev
            self._last_pixel_version = dev_version
            self._last_pixel_scale = scale

            self.lbl_pixel_status.configure(
                text=f"PIXEL VRAM • {w}x{h} • Масштаб {scale}x • {mode_str} • MMIO 0x{dev.start:06X}"
            )
            return

    # --------------------------------------------------------------------------
    # Нижний статусбар
    # --------------------------------------------------------------------------
    def _build_statusbar(self):
        sb = tk.Frame(self.root, bg=self.c_panel, bd=1, relief="solid", highlightbackground=self.c_panel_border)
        sb.pack(fill="x", side="bottom", padx=8, pady=(0, 8))

        self.lbl_sb_left = tk.Label(sb, text=" Готов к работе | Нажмите F7/Space для шага, F5 для запуска", font=self.font_ui, bg=self.c_panel, fg=self.c_fg_muted)
        self.lbl_sb_left.pack(side="left", padx=6, pady=3)

        bus_mode = getattr(self.bus, "mode", "32bit").upper()
        self.lbl_sb_right = tk.Label(sb, text=f"Режим шины: {bus_mode} │ Память: 4 ГБ ", font=self.font_ui, bg=self.c_panel, fg=self.c_accent)
        self.lbl_sb_right.pack(side="right", padx=6, pady=3)

        if hasattr(self.bus, "on_collision"):
            self.bus.on_collision = self._handle_bus_collision

    def _handle_bus_collision(self, warning_msg: str):
        try:
            self.lbl_sb_left.configure(text=warning_msg, fg="#ff5555")
        except Exception:
            pass

    # --------------------------------------------------------------------------
    # Обновление представлений
    # --------------------------------------------------------------------------
    def update_all(self):
        self.update_registers_view()
        self.update_code_view()
        self.update_memory_view()
        self.update_screen_view()
        self.update_toolbar_and_status()

    def update_toolbar_and_status(self):
        pc = getattr(self.cpu, "pc", 0)
        steps = getattr(self.cpu, "step_count", 0)

        self.lbl_pc_quick.configure(text=f"PC: 0x{pc:08X}")
        self.lbl_steps_quick.configure(text=f"Такт #{steps}")

        if self.cpu.is_halted:
            self.lbl_status_badge.configure(text=" [ HALT / ОСТАНОВ ] ", bg=self.c_red, fg="#11111b")
            self.btn_run.configure(
                text="⏩ Пуск (F5)", fg=self.c_accent,
                bg="#25364d", hover_bg="#304663", border_color="#3b557a"
            )
            self.is_running = False
        elif self.is_running:
            self.lbl_status_badge.configure(text=" [ ИСПОЛНЕНИЕ ] ", bg=self.c_green, fg="#11111b")
            self.btn_run.configure(
                text="⏸ Пауза (F5)", fg=self.c_yellow,
                bg="#38301e", hover_bg="#4a4027", border_color="#5e502b"
            )
        else:
            self.lbl_status_badge.configure(text=" [ ПАУЗА ] ", bg="#45475a", fg=self.c_yellow)
            self.btn_run.configure(
                text="⏩ Пуск (F5)", fg=self.c_accent,
                bg="#25364d", hover_bg="#304663", border_color="#3b557a"
            )

        # Блокировка полей ввода регистров во время исполнения (защита от сбоев)
        # Разблокировка только во время паузы
        target_state = "readonly" if self.is_running else "normal"
        for ent in getattr(self, "reg_entries", {}).values():
            if str(ent.cget("state")) != target_state:
                ent.configure(state=target_state)

    def update_registers_view(self):
        focused_widget = self.root.focus_get()

        # 1. Динамическое обновление всех зарегистрированных регистров (РОН + Системные + PC)
        for rname, ent in getattr(self, "reg_entries", {}).items():
            dec_lbl, bin_lbl, bits = self.reg_labels[rname]
            val = self.get_cpu_reg(rname)
            hex_digits = max(2, (bits + 3) // 4)

            # Если пользователь прямо сейчас печатает в этом поле — не перезаписывать его ввод
            if focused_widget != ent:
                curr_txt = ent.get()
                new_txt = f"0x{val:0{hex_digits}X}"
                if curr_txt != new_txt:
                    was_readonly = (str(ent.cget("state")) == "readonly")
                    if was_readonly:
                        ent.configure(state="normal")
                    ent.delete(0, "end")
                    ent.insert(0, new_txt)
                    if was_readonly:
                        ent.configure(state="readonly")

            # Десятичное значение (без искусственного срезания)
            dec_lbl.configure(text=f"DEC: {val}")

            # Двоичное значение (по тетрадам)
            if bin_lbl is not None:
                b_str = f"{val:0{bits}b}"
                parts = [b_str[i:i+4] for i in range(0, len(b_str), 4)]
                bin_lbl.configure(text=" ".join(parts))

        # 2. Флаги FREG
        freg_val = self.get_cpu_reg("freg")
        for fname, (b_lbl, bit_pos) in getattr(self, "flag_badges", {}).items():
            bval = 1 if (freg_val & (1 << bit_pos)) else 0
            if bval:
                b_lbl.configure(
                    text=f"[{fname}: 1]", bg=self.c_green, fg="#11111b",
                    font=self.font_mono_bold, highlightbackground="#5bb86e"
                )
            else:
                b_lbl.configure(
                    text=f"[{fname}: 0]", bg="#313244", fg=self.c_fg_muted,
                    font=self.font_mono_small, highlightbackground="#45475a"
                )

        # 3. Ножки процессора / шины
        if self.bus and hasattr(self.bus, "pins"):
            for pname, p_lbl in getattr(self, "pin_badges", {}).items():
                val = int(getattr(self.bus.pins, pname)) if hasattr(self.bus.pins, pname) else 0
                if val:
                    p_lbl.configure(text=f"{pname}:1", bg=self.c_green, fg="#11111b", font=self.font_mono_bold)
                else:
                    p_lbl.configure(text=f"{pname}:0", bg="#313244", fg=self.c_fg_muted, font=self.font_mono_small)

    def update_code_view(self):
        curr_pc = self.cpu.pc
        bus = self.bus
        mask = getattr(bus, "mask", 0xFFFFFFFF)

        self.txt_code.configure(state="normal")
        self.txt_code.delete("1.0", "end")

        # Считываем инструкции вокруг PC: 2 до PC (если возможно) и 20 после
        start_addr = max(0, curr_pc - 4) if curr_pc >= 4 else curr_pc
        addr = start_addr

        # Накопим 24 инструкции
        instructions = []
        for _ in range(24):
            mnem, length, raw_bytes = disassemble_one(lambda a: (bus.peek(a & mask) if hasattr(bus, "peek") else bus.read8(a & mask)), addr)
            hex_bytes = " ".join(f"{b:02X}" for b in raw_bytes[:length])
            instructions.append((addr, hex_bytes, mnem, length))
            addr = (addr + max(1, length)) & mask

        curr_line_idx = None
        for i, (i_addr, i_hex, i_mnem, i_len) in enumerate(instructions):
            is_pc = (i_addr == curr_pc)
            is_bp = i_addr in getattr(self.cpu, "breakpoints", set())

            line_start = self.txt_code.index("end-1c")

            prefix = " ● " if is_bp else (" ▶ " if is_pc else "   ")
            line_str = f"{prefix}0x{i_addr:06X}:  {i_hex:<10}  {i_mnem:<32}\n"
            self.txt_code.insert("end", line_str)

            line_end = self.txt_code.index("end-1c")

            if is_bp:
                self.txt_code.tag_add("bpoint", line_start, line_end)
            elif is_pc:
                self.txt_code.tag_add("pc_curr", line_start, line_end)
                curr_line_idx = line_start

        if curr_line_idx:
            self.txt_code.see(curr_line_idx)

        self.txt_code.configure(state="disabled")

    def update_memory_view(self):
        bus = self.bus
        if not bus:
            return

        addr = self.mem_view_addr & 0xFFFFFFFF
        curr_pc = self.cpu.pc

        self.txt_mem.configure(state="normal")
        self.txt_mem.delete("1.0", "end")

        # Отображаем 16 строк по 16 байт = 256 байт
        for row in range(16):
            row_addr = (addr + row * 16) & 0xFFFFFFFF
            chunk = [(bus.peek(row_addr + col) if hasattr(bus, "peek") else bus.read8(row_addr + col)) for col in range(16)]

            line_start = self.txt_mem.index("end-1c")

            addr_str = f" 0x{row_addr:06X}: "
            self.txt_mem.insert("end", addr_str, "addr")

            for col in range(16):
                byte_addr = row_addr + col
                b_val = chunk[col]
                b_str = f"{b_val:02X} "
                if col == 8:
                    self.txt_mem.insert("end", " ")

                if byte_addr == curr_pc:
                    self.txt_mem.insert("end", b_str, "pc_byte")
                else:
                    self.txt_mem.insert("end", b_str)

            # ASCII представление
            ascii_chars = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
            self.txt_mem.insert("end", f" |{ascii_chars}|\n", "ascii")

        self.txt_mem.configure(state="disabled")

    # --------------------------------------------------------------------------
    # Обработчики событий и навигации
    # --------------------------------------------------------------------------
    def _on_code_double_click(self, event):
        """Устанавливает или снимает точку останова по клику на строке кода."""
        try:
            line_str = self.txt_code.get("insert linestart", "insert lineend")
            parts = line_str.split(":")
            if parts and "0x" in parts[0]:
                addr_hex = parts[0].strip().split()[-1]
                addr = int(addr_hex, 16)
                bps = getattr(self.cpu, "breakpoints", set())
                if addr in bps:
                    bps.remove(addr)
                    self.lbl_sb_left.configure(text=f"Снята точка останова с 0x{addr:06X}")
                else:
                    bps.add(addr)
                    self.lbl_sb_left.configure(text=f"Установлена точка останова на 0x{addr:06X}")
                self.update_code_view()
        except Exception:
            pass

    def _on_dev_selected(self, event=None):
        name = self.cb_dev.get()
        self.selected_device_name = name
        if self.bus:
            for dev in getattr(self.bus, "_devices_list", []):
                if dev.name == name:
                    self.mem_view_addr = dev.start
                    self.ent_addr.delete(0, "end")
                    self.ent_addr.insert(0, f"{dev.start:X}")
                    self.update_memory_view()
                    break

    def _on_goto_addr(self):
        val = self.ent_addr.get().strip()
        try:
            addr = int(val, 16) if val.startswith("0x") or val.startswith("0X") else int(val, 16)
            self.mem_view_addr = addr
            self.update_memory_view()
        except ValueError:
            messagebox.showerror("Ошибка", f"Некорректный шестнадцатеричный адрес: {val}")

    def _page_mem(self, delta: int):
        self.mem_view_addr = max(0, self.mem_view_addr + delta)
        self.ent_addr.delete(0, "end")
        self.ent_addr.insert(0, f"{self.mem_view_addr:X}")
        self.update_memory_view()

    def _calc_mem_click_addr(self, event) -> Optional[Tuple[int, int, str]]:
        """
        По координатам клика в txt_mem определяет:
        (target_addr, cur_val, tag_pos)
        """
        if not self.bus:
            return None

        idx = self.txt_mem.index(f"@{event.x},{event.y}")
        parts = idx.split(".")
        if len(parts) != 2:
            return None
        line_no = int(parts[0])
        char_col = int(parts[1])

        row = line_no - 1
        if not (0 <= row < 16):
            return None

        col = None
        if 11 <= char_col <= 34:
            col = (char_col - 11) // 3
        elif char_col == 35:
            col = 7
        elif 36 <= char_col <= 59:
            col = 8 + (char_col - 36) // 3
        elif 62 <= char_col <= 77:
            col = char_col - 62

        if col is None or not (0 <= col < 16):
            return None

        row_addr = (self.mem_view_addr + row * 16) & 0xFFFFFFFF
        target_addr = (row_addr + col) & 0xFFFFFFFF
        cur_val = self.bus.peek(target_addr) if hasattr(self.bus, "peek") else self.bus.read8(target_addr)

        if col < 8:
            start_col = 11 + col * 3
        else:
            start_col = 36 + (col - 8) * 3
        tag_pos = f"{line_no}.{start_col}"

        return target_addr, cur_val, tag_pos

    def _on_mem_click(self, event):
        info = self._calc_mem_click_addr(event)
        if info:
            addr, val, _ = info
            dev_name = ""
            if hasattr(self.bus, "_devices_list"):
                for d in self.bus._devices_list:
                    if d.start <= addr <= d.end:
                        dev_name = f" [{d.name}]"
                        break
            ch = chr(val) if 32 <= val <= 126 else "."
            self.lbl_sb_left.configure(
                text=f"Память 0x{addr:06X}{dev_name} = 0x{val:02X} ({val}, '{ch}') │ Двойной клик для изменения байта"
            )

    def _on_mem_double_click(self, event):
        if self.is_running:
            self.lbl_sb_left.configure(text="⚠️ Редактирование памяти разрешено только во время паузы.")
            return "break"

        info = self._calc_mem_click_addr(event)
        if not info:
            return "break"
        addr, val, tag_pos = info
        self._show_inplace_byte_editor(addr, val, tag_pos)
        return "break"

    def _show_inplace_byte_editor(self, target_addr: int, cur_val: int, tag_pos: str):
        if hasattr(self, "_active_mem_entry") and self._active_mem_entry:
            try:
                self._active_mem_entry.destroy()
            except Exception:
                pass
            self._active_mem_entry = None

        bbox = self.txt_mem.bbox(tag_pos)
        if not bbox:
            from tkinter import simpledialog
            res = simpledialog.askstring(
                "Изменение байта памяти",
                f"Адрес: 0x{target_addr:06X}\nТекущее: 0x{cur_val:02X} ({cur_val})\n\nНовое значение (HEX):",
                initialvalue=f"{cur_val:02X}",
                parent=self.root
            )
            if res is not None:
                self._commit_mem_edit(target_addr, cur_val, res)
            return

        x, y, w, h = bbox
        entry_w = max(32, w * 3)

        ent = tk.Entry(
            self.txt_mem,
            font=self.font_mono_bold,
            bg="#313244",
            fg="#a6e3a1",
            insertbackground="#ffffff",
            bd=1,
            relief="solid",
            highlightthickness=1,
            highlightbackground="#89b4fa",
            highlightcolor="#89b4fa",
            justify="center"
        )
        ent.place(x=max(0, x - 2), y=max(0, y - 1), width=entry_w, height=h + 2)
        ent.insert(0, f"{cur_val:02X}")
        ent.select_range(0, "end")
        ent.focus_set()
        self._active_mem_entry = ent

        def _commit():
            if not self._active_mem_entry:
                return
            val_text = ent.get().strip()
            ent.destroy()
            self._active_mem_entry = None
            self._commit_mem_edit(target_addr, cur_val, val_text)

        def _cancel(e=None):
            if hasattr(self, "_active_mem_entry") and self._active_mem_entry:
                try:
                    self._active_mem_entry.destroy()
                except Exception:
                    pass
                self._active_mem_entry = None

        ent.bind("<Return>", lambda e: _commit())
        ent.bind("<KP_Enter>", lambda e: _commit())
        ent.bind("<Escape>", _cancel)
        ent.bind("<FocusOut>", lambda e: _commit())

    def _commit_mem_edit(self, target_addr: int, cur_val: int, val_text: str):
        if not val_text:
            return
        t = val_text.strip()
        try:
            if (len(t) == 3 and t[0] in ("'", '"') and t[2] in ("'", '"')) or (len(t) == 1 and not t.isdigit() and t not in "abcdefABCDEF"):
                new_val = ord(t[1] if len(t) == 3 else t[0]) & 0xFF
            elif t.lower().startswith("0x"):
                new_val = int(t, 16) & 0xFF
            elif any(c in "abcdefABCDEF" for c in t):
                new_val = int(t, 16) & 0xFF
            elif len(t) <= 2:
                new_val = int(t, 16) & 0xFF
            else:
                new_val = int(t, 10) & 0xFF

            if hasattr(self.bus, "poke"):
                self.bus.poke(target_addr, new_val)
            elif hasattr(self.bus, "write8"):
                self.bus.write8(target_addr, new_val)

            dev_name = ""
            if hasattr(self.bus, "_devices_list"):
                for d in self.bus._devices_list:
                    if d.start <= target_addr <= d.end:
                        dev_name = f" ({d.name})"
                        break

            self.lbl_sb_left.configure(
                text=f"Память [0x{target_addr:06X}]{dev_name} изменена: 0x{cur_val:02X} -> 0x{new_val:02X} ({new_val})"
            )
            self.update_memory_view()
            self.update_code_view()
        except Exception as ex:
            self.lbl_sb_left.configure(text=f"⚠️ Ошибка записи в память: {ex}")

    def _on_speed_change(self, val):
        spd = int(val)
        if spd == 0:
            self.run_speed_ms = 0
            self.batch_size = 500  # Максимальная скорость
            self.lbl_speed_val.configure(text="MAX (пакет)")
        elif spd < 30:
            self.run_speed_ms = int(300 - spd * 8)
            self.batch_size = 1
            hz = int(1000 / self.run_speed_ms)
            self.lbl_speed_val.configure(text=f"{hz} шаг/сек")
        elif spd < 100:
            self.run_speed_ms = max(5, int(100 - spd))
            self.batch_size = 1
            hz = int(1000 / self.run_speed_ms)
            self.lbl_speed_val.configure(text=f"{hz} шаг/сек")
        else:
            self.run_speed_ms = 1
            self.batch_size = max(2, (spd - 90) * 5)
            self.lbl_speed_val.configure(text=f"~{self.batch_size * 50} шаг/сек")

    # --------------------------------------------------------------------------
    # Логика исполнения процессора (Step, Run, Reset)
    # --------------------------------------------------------------------------
    def step(self):
        if self.cpu.is_halted:
            self.lbl_sb_left.configure(text="[CPU] Процессор остановлен (HALT). Нажмите 'Сброс' для перезапуска.")
            return

        self.cpu.step()
        self.update_all()

    def step_n(self, count: int):
        for _ in range(count):
            if self.cpu.is_halted or self.cpu.pc in getattr(self.cpu, "breakpoints", set()):
                break
            self.cpu.step()
        self.update_all()

    def toggle_run(self):
        if self.is_running:
            self.is_running = False
            self.update_toolbar_and_status()
            self.lbl_sb_left.configure(text="Исполнение приостановлено пользователем.")
        else:
            if self.cpu.is_halted:
                self.lbl_sb_left.configure(text="[CPU] Невозможно запустить: процессор остановлен (HALT). Нажмите 'Сброс'.")
                return
            self.is_running = True
            self.update_toolbar_and_status()
            self.lbl_sb_left.configure(text="Исполнение инструкций...")
            self._run_loop()

    def trigger_irq_click(self):
        """Эмуляция нажатия кнопки аппаратного прерывания IRQ."""
        if self.bus and hasattr(self.bus, "pins"):
            self.bus.pins.IRQ.set(1)

        success = False
        if hasattr(self.cpu, "trigger_irq"):
            success = self.cpu.trigger_irq(0, force=True)
        elif self.bus and hasattr(self.bus, "pins"):
            self.bus.pins.IRQ.pulse()
            success = True

        if success:
            self.lbl_sb_left.configure(text=f"⚡ КНОПКА ПРЕРЫВАНИЯ: Вызван IRQ0! PC перешел на 0x{self.cpu.pc:06X}")
        else:
            self.lbl_sb_left.configure(text="⚡ Ножка IRQ установлена в 1")
        self.update_all()

    def _toggle_pin(self, pin_name: str):
        if self.bus and hasattr(self.bus, "pins") and hasattr(self.bus.pins, pin_name):
            pin = getattr(self.bus.pins, pin_name)
            new_val = 0 if pin.get() else 1
            pin.set(new_val)
            if pin_name == "IRQ" and new_val == 1 and hasattr(self.cpu, "trigger_irq"):
                self.cpu.trigger_irq(0, force=True)
            self.lbl_sb_left.configure(text=f"Ножка {pin_name} переключена в {new_val}")
            self.update_all()

    def _run_loop(self):
        if not self.is_running:
            return

        bps = getattr(self.cpu, "breakpoints", set())
        for _ in range(self.batch_size):
            if self.cpu.is_halted:
                self.is_running = False
                break
            if self.cpu.pc in bps and self.cpu.step_count > 0:
                self.is_running = False
                self.lbl_sb_left.configure(text=f"Точка останова достигнута на PC = 0x{self.cpu.pc:06X}")
                break

            self.cpu.step()

        # Обновление экрана в реальном времени:
        # При непрерывном беге (run) обновляем графику не чаще 30 FPS (каждые 33 мс),
        # чтобы процессор не захлебывался в перерисовке GUI
        now = time.time()
        if (now - getattr(self, "_last_gui_update", 0.0)) >= 0.033:
            self.update_all()
            self._last_gui_update = now

        if self.is_running:
            delay = max(1, self.run_speed_ms)
            self.root.after(delay, self._run_loop)
        else:
            self.update_all()
            self.update_toolbar_and_status()

    def reset_cpu(self):
        self.is_running = False
        if hasattr(self.cpu, "reset"):
            self.cpu.reset()
        self.lbl_sb_left.configure(text="Процессор сброшен к начальному состоянию.")
        self.update_all()

    def on_close(self):
        self.is_running = False
        if self.bus and hasattr(self.bus, "save_persistent_devices"):
            saved = self.bus.save_persistent_devices()
            if saved:
                for s in saved:
                    print(f"[PERSIST] Образ памяти сохранен на диск: {s}")
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def launch_simulator_gui(cpu: Any, max_steps: int = 100000, initial_speed_ms: Optional[int] = None):
    """Точка входа для запуска GUI окна симулятора."""
    app = SimulatorGUI(cpu, max_steps=max_steps, initial_speed_ms=initial_speed_ms)
    app.run()


if __name__ == "__main__":
    from cpu import LIM2CPU
    from bus import MemoryBus, RAMDevice
    bus = MemoryBus()
    bus.attach(RAMDevice(start=0x000000, end=0x0FFFFF, name="NVM1"))
    bus.attach(RAMDevice(start=0x100000, end=0x1FFFFF, name="RAM1"))
    cpu = LIM2CPU(bus=bus)
    launch_simulator_gui(cpu)
