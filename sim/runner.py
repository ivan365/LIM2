#!/usr/bin/env python3
# ==============================================================================
# LIM2 / sim / runner.py — Интерактивный TUI дашборд и CLI раннер
# ==============================================================================
import argparse
import os
import sys
import time
from typing import Type, Optional, Union, Callable, Any
try:
    from .bus import MemoryBus
    from .core import BaseCPU
except (ImportError, ValueError):
    from bus import MemoryBus
    from core import BaseCPU


try:
    from .ui import render_full_simulator_screen, UIConfig
except (ImportError, ValueError):
    from ui import render_full_simulator_screen, UIConfig


class SimulationRunner:
    """Интерактивный раннер с красивой графикой в терминале."""

    def __init__(self, cpu: BaseCPU, ui_config: Optional[UIConfig] = None, long_term_file: Optional[str] = None):
        self.cpu = cpu
        self.bus = cpu.bus
        self.cfg = ui_config if ui_config is not None else UIConfig(layout_mode="auto")
        self.loaded_file: Optional[str] = None
        self.entry_point: int = 0x0000
        self.long_term_file: Optional[str] = long_term_file

    def save_state(self, path: Optional[str] = None) -> str:
        """Сохраняет полный снимок памяти и регистров в файл дампа."""
        target = path or self.long_term_file or "lim2_state.dump"
        res = self.cpu.save_state(target)
        return target

    def load_state(self, path: Optional[str] = None) -> bool:
        """Загружает полный снимок памяти и регистров из файла дампа."""
        target = path or self.long_term_file or "lim2_state.dump"
        return self.cpu.load_state(target)

    def load(self, file_path: str, at: Optional[int] = None) -> int:
        self.loaded_file = file_path
        count = self.cpu.load(file_path, at=at)
        self.entry_point = self.cpu.pc
        return count

    def render_dashboard(self, clear_screen: bool = False) -> str:
        """Отрисовывает полноценный экран симулятора со всеми блоками первого симулятора."""
        prefix = "\033[H\033[J" if clear_screen else ""
        return prefix + render_full_simulator_screen(self.cpu, step_count=self.cpu.step_count, cfg=self.cfg)

    def render_help(self) -> str:
        """Справка по командам меню отладчика."""
        lines = [
            "┌── [СПРАВКА ПО КОМАНДАМ МЕНЮ СИМУЛЯТОРА] ──────────────────────────────────────┐",
            "│ УПРАВЛЕНИЕ ВЫПОЛНЕНИЕМ:                                                      │",
            "│   <Enter> / s / step     — выполнить 1 такт/команду                          │",
            "│   do <N>                 — выполнить N тактов (напр: do 10)                  │",
            "│   r / run / cont         — запуск до останова или Ctrl+C                     │",
            "│   delay <ms>             — задержка между шагами в мс (delay 50)             │",
            "│   b <addr>               — установить/снять точку останова (breakpoint)      │",
            "│                                                                              │",
            "│ УПРАВЛЕНИЕ РЕГИСТРАМИ И ПАМЯТЬЮ:                                             │",
            "│   r0=0x42 / r1=100       — прямое присваивание значению регистру             │",
            "│   set <addr> <val...>    — записать байты в память по адресу                 │",
            "│   write <dev> <off> <val>— записать данные/текст в устройство                │",
            "│   d / dump [addr] [len]  — вывести дамп памяти шины                          │",
            "│   mem [addr | auto]      — переключить фокус просмотра памяти                │",
            "│   goto / g <addr>        — перейти к просмотру памяти по адресу              │",
            "│                                                                              │",
            "│ НАСТРОЙКИ ОТОБРАЖЕНИЯ И МЕНЮ:                                                │",
            "│   menu / help / ?        — открыть эту справку меню                          │",
            "│   layout [auto|1..3col]  — переключить режим раскладки экрана                │",
            "│   move / cols            — показать распределение блоков по колонкам         │",
            "│   move <блок> <1|2|3>    — перенести блок в колонку (напр: move screen 2)    │",
            "│   move <блок> next/prev  — сдвинуть блок в следующую/предыдущую колонку      │",
            "│   wrap [on|off]          — автоперенос блоков при нехватке высоты экрана     │",
            "│   height [N|auto]        — ограничить высоту колонок (в строках)             │",
            "│   view [cpu|code|mem|..] — включить/выключить панели интерфейса              │",
            "│   view dev [all|VID1]    — фильтр отображения памяти устройств               │",
            "│   screen / v [ID]        — принудительно показать видеомониторы              │",
            "│   map / busmap           — показать карту распределения памяти шины          │",
            "│   mode [16bit|24bit]     — переключить режим адресации шины                  │",
            "│   save [file] / load [..]— сохранить/загрузить полный снимок машины          │",
            "│   q / quit / exit        — выход из симулятора                               │",
            "└──────────────────────────────────────────────────────────────────────────────┘"
        ]
        return "\n".join(lines)

    def run_interactive(self):
        """Интерактивный пошаговый режим с полным меню команд."""
        print(self.render_dashboard(clear_screen=True))
        print("Команды: [Enter] Шаг | [r] Пуск | [do N] | [view] Меню | [layout] Раскладка | [help] Справка | [q] Выход")

        sim_delay = 0.0

        while not self.cpu.is_halted:
            try:
                cmd_raw = input(f"({self.cpu.name.lower()}) > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n[СИМУЛЯТОР] Прервано пользователем.")
                break

            if not cmd_raw:
                self.cpu.step()
                print(self.render_dashboard(clear_screen=True))
                continue

            # Проверка на присваивание регистру: r0=0x42 или r1=10
            if "=" in cmd_raw:
                parts = cmd_raw.split("=", 1)
                r_name = parts[0].strip().lower()
                try:
                    val = int(parts[1].strip(), 0)
                    self.cpu.set_reg(r_name, val)
                    print(f"Регистр {r_name.upper()} = 0x{val:X} ({val})")
                    print(self.render_dashboard(clear_screen=True))
                    continue
                except Exception as e:
                    print(f"Ошибка присваивания: {e}")
                    continue

            cmd_parts = cmd_raw.split()
            cmd = cmd_parts[0].lower()

            if cmd in ("s", "step"):
                self.cpu.step()
                print(self.render_dashboard(clear_screen=True))

            elif cmd in ("do",):
                count = int(cmd_parts[1], 0) if len(cmd_parts) > 1 else 1
                for _ in range(count):
                    if not self.cpu.step():
                        break
                    if sim_delay > 0:
                        time.sleep(sim_delay)
                print(self.render_dashboard(clear_screen=True))
                print(f"Выполнено {count} шагов.")

            elif cmd in ("delay",):
                if len(cmd_parts) > 1:
                    ms = float(cmd_parts[1])
                    sim_delay = max(0.0, ms / 1000.0)
                    print(f"Задержка между тактами: {ms:.1f} мс")
                else:
                    print(f"Текущая задержка: {sim_delay * 1000.0:.1f} мс. Использование: delay <мс>")

            elif cmd in ("r", "c", "run", "cont"):
                print("Выполнение (Ctrl+C для паузы)...")
                try:
                    start_t = time.time()
                    steps = 0
                    while not self.cpu.is_halted:
                        if not self.cpu.step():
                            break
                        steps += 1
                        if sim_delay > 0:
                            time.sleep(sim_delay)
                    el = time.time() - start_t
                    print(self.render_dashboard(clear_screen=True))
                    print(f"Выполнено {steps} тактов за {el:.4f} сек.")
                    if self.cpu.is_halted:
                        print("[СИМУЛЯЦИЯ ЗАВЕРШЕНА] Процессор остановлен.")
                except KeyboardInterrupt:
                    print(self.render_dashboard(clear_screen=True))
                    print(f"\n[ПАУЗА] Выполнение приостановлено пользователем.")

            elif cmd in ("layout", "l"):
                if len(cmd_parts) > 1:
                    lm = cmd_parts[1].lower()
                    if lm in ("auto", "1col", "2col", "3col"):
                        self.cfg.layout_mode = lm
                        print(f"Раскладка переключена на '{lm}'")
                    else:
                        print("Допустимые раскладки: auto, 1col, 2col, 3col")
                else:
                    modes = ["auto", "1col", "2col", "3col"]
                    cur_idx = modes.index(self.cfg.layout_mode) if self.cfg.layout_mode in modes else 0
                    self.cfg.layout_mode = modes[(cur_idx + 1) % len(modes)]
                    print(f"Раскладка переключена на '{self.cfg.layout_mode}'")
                print(self.render_dashboard(clear_screen=True))

            elif cmd in ("view", "ui"):
                if len(cmd_parts) == 1:
                    v_info = [
                        "[НАСТРОЙКИ ОТОБРАЖЕНИЯ ПАНЕЛЕЙ (VIEW)]:",
                        f"  view cpu     : {'ВКЛ' if self.cfg.show_cpu else 'ВЫКЛ'}",
                        f"  view code    : {'ВКЛ' if self.cfg.show_code else 'ВЫКЛ'}",
                        f"  view mem     : {'ВКЛ' if self.cfg.show_mem else 'ВЫКЛ'} (строк: {self.cfg.mem_rows})",
                        f"  view screen  : {'ВКЛ' if self.cfg.show_screen else 'ВЫКЛ'}",
                        f"  view map     : {'ВКЛ' if self.cfg.show_map else 'ВЫКЛ'}",
                        f"  view rows <N>: задать число строк памяти",
                        f"  view all / view none"
                    ]
                    print("\n".join(v_info))
                else:
                    sub = cmd_parts[1].lower()
                    if sub == "cpu": self.cfg.show_cpu = not self.cfg.show_cpu
                    elif sub == "code": self.cfg.show_code = not self.cfg.show_code
                    elif sub == "mem": self.cfg.show_mem = not self.cfg.show_mem
                    elif sub == "screen": self.cfg.show_screen = not self.cfg.show_screen
                    elif sub == "map": self.cfg.show_map = not self.cfg.show_map
                    elif sub == "all":
                        self.cfg.show_cpu = self.cfg.show_code = self.cfg.show_mem = self.cfg.show_screen = self.cfg.show_map = True
                    elif sub == "none":
                        self.cfg.show_cpu = self.cfg.show_code = self.cfg.show_mem = self.cfg.show_screen = self.cfg.show_map = False
                    elif sub in ("rows", "memrows") and len(cmd_parts) > 2:
                        self.cfg.mem_rows = max(1, int(cmd_parts[2], 0))
                    print(self.render_dashboard(clear_screen=True))

            elif cmd in ("move", "col", "cols"):
                if len(cmd_parts) == 1:
                    info = [
                        "┌── [РАСПРЕДЕЛЕНИЕ БЛОКОВ ПО КОЛОНКАМ] ────────────────────────────────────────┐",
                        f"│  Режим раскладки: {self.cfg.layout_mode.upper():<6}  Автоперенос по высоте: {'ВКЛ' if self.cfg.auto_height_wrap else 'ВЫКЛ':<4}                   │",
                        "│                                                                              │",
                    ]
                    names_map = {
                        "cpu": "Регистры процессора (Circuit Chips)",
                        "code": "Дизассемблер потока инструкций",
                        "screen": "Видеомониторы / Текстовые терминалы",
                        "mem": "Память устройств (Hexdump)",
                        "map": "Карта памяти шины (Diskmgmt)"
                    }
                    for b_name, b_desc in names_map.items():
                        col = self.cfg.get_block_column(b_name)
                        info.append(f"│    [{b_name:<6}] -> Колонка {col:<2} ({b_desc:<36}) │")
                    info.extend([
                        "│                                                                              │",
                        "│  Команды:                                                                    │",
                        "│    move <блок> <1|2|3>    — перенести блок в колонку (напр: move screen 2)   │",
                        "│    move <блок> next / +   — сдвинуть блок в следующую колонку                │",
                        "│    move <блок> prev / -   — сдвинуть блок в предыдущую колонку               │",
                        "│    wrap on / off          — вкл/выкл автоперенос по высоте экрана            │",
                        "│    height <N|auto>        — ограничить высоту колонок (в строках)            │",
                        "└──────────────────────────────────────────────────────────────────────────────┘"
                    ])
                    print("\n".join(info))
                elif len(cmd_parts) == 2:
                    sub = cmd_parts[1].lower()
                    nxt = self.cfg.move_block_next(sub)
                    if nxt is not None:
                        print(f"Блок '{sub}' перемещен в колонку {nxt}")
                        print(self.render_dashboard(clear_screen=True))
                    else:
                        print(f"Неизвестный блок '{sub}'. Доступны: cpu, code, screen, mem, map")
                else:
                    b_target = cmd_parts[1].lower()
                    action = cmd_parts[2].lower()
                    if action in ("next", "+"):
                        nxt = self.cfg.move_block_next(b_target)
                        if nxt is not None:
                            print(f"Блок '{b_target}' перемещен в колонку {nxt}")
                        else:
                            print(f"Неизвестный блок '{b_target}'. Доступны: cpu, code, screen, mem, map")
                    elif action in ("prev", "-"):
                        prev = self.cfg.move_block_prev(b_target)
                        if prev is not None:
                            print(f"Блок '{b_target}' перемещен в колонку {prev}")
                        else:
                            print(f"Неизвестный блок '{b_target}'. Доступны: cpu, code, screen, mem, map")
                    else:
                        try:
                            c_num = int(action, 0)
                            ok = self.cfg.set_block_column(b_target, c_num)
                            if ok:
                                print(f"Блок '{b_target}' назначен в колонку {c_num}")
                            else:
                                print(f"Неизвестный блок '{b_target}'. Доступны: cpu, code, screen, mem, map")
                        except ValueError:
                            print(f"Неверный номер колонки '{action}'. Используйте 1, 2 или 3.")
                    print(self.render_dashboard(clear_screen=True))

            elif cmd in ("wrap", "autowrap"):
                if len(cmd_parts) > 1:
                    sub = cmd_parts[1].lower()
                    if sub in ("on", "1", "true", "yes"):
                        self.cfg.auto_height_wrap = True
                        print("Автоперенос блоков по высоте: ВКЛЮЧЕН")
                    elif sub in ("off", "0", "false", "no"):
                        self.cfg.auto_height_wrap = False
                        print("Автоперенос блоков по высоте: ВЫКЛЮЧЕН")
                    else:
                        print("Использование: wrap on / wrap off")
                else:
                    self.cfg.auto_height_wrap = not self.cfg.auto_height_wrap
                    st = "ВКЛЮЧЕН" if self.cfg.auto_height_wrap else "ВЫКЛЮЧЕН"
                    print(f"Автоперенос блоков по высоте: {st}")
                print(self.render_dashboard(clear_screen=True))

            elif cmd in ("height", "fit"):
                import shutil
                if len(cmd_parts) > 1:
                    sub = cmd_parts[1].lower()
                    if sub in ("auto", "reset"):
                        self.cfg.max_col_height = None
                        print("Высота колонок: АВТО (по высоте терминала)")
                    else:
                        try:
                            h_val = int(sub, 0)
                            self.cfg.max_col_height = max(5, h_val)
                            print(f"Максимальная высота колонки установлена: {self.cfg.max_col_height} строк")
                        except ValueError:
                            print("Использование: height <число> или height auto")
                else:
                    cur_t = shutil.get_terminal_size((80, 24)).lines
                    h_info = f"Пользовательская ({self.cfg.max_col_height})" if self.cfg.max_col_height else f"Автоматическая (~{max(15, cur_t - 3)} строк)"
                    print(f"Текущая высота колонок: {h_info}. Использование: height <число> или height auto")
                print(self.render_dashboard(clear_screen=True))

            elif cmd in ("screen", "v", "video"):
                scrs = []
                for dev in getattr(self.bus, "_devices_list", []):
                    if getattr(dev, "is_video", False) and hasattr(dev, "render_screen"):
                        scr = dev.render_screen()
                        if scr: scrs.append(scr)
                if scrs:
                    print("\n".join(scrs))
                else:
                    print("[СИМУЛЯТОР] Нет подключенных видеомониторов (используйте флаг -v).")

            elif cmd in ("map", "busmap"):
                from ui import render_full_memory_map
                print(render_full_memory_map(self.bus))

            elif cmd in ("mode",):
                if len(cmd_parts) > 1:
                    m = cmd_parts[1].lower()
                    if hasattr(self.bus, "set_mode"):
                        self.bus.set_mode(m)
                        print(f"Режим шины переключен на {self.bus.mode.upper()}")
                        print(self.render_dashboard(clear_screen=True))
                else:
                    print(f"Текущий режим шины: {getattr(self.bus, 'mode', '16bit')}. Использование: mode [16bit|24bit]")

            elif cmd.startswith("b"):
                if len(cmd_parts) > 1:
                    try:
                        b_addr = int(cmd_parts[1], 0)
                        if b_addr in self.cpu.breakpoints:
                            self.cpu.breakpoints.remove(b_addr)
                            print(f"Точка останова 0x{b_addr:04X} удалена.")
                        else:
                            self.cpu.breakpoints.add(b_addr)
                            print(f"Точка останова установлена на 0x{b_addr:04X}")
                    except Exception as e:
                        print(f"Ошибка: {e}")
                else:
                    bps = ", ".join(f"0x{b:04X}" for b in self.cpu.breakpoints) if self.cpu.breakpoints else "нет"
                    print(f"Точки останова: {bps}. Использование: b <адрес>")

            elif cmd in ("d", "dump"):
                try:
                    d_addr = int(cmd_parts[1], 0) if len(cmd_parts) > 1 else self.cpu.pc
                    d_len = int(cmd_parts[2], 0) if len(cmd_parts) > 2 else 32
                    print(self.bus.dump(d_addr, d_len))
                except Exception as e:
                    print(f"Ошибка дампа: {e}")

            elif cmd in ("set", "poke"):
                if len(cmd_parts) >= 3:
                    try:
                        addr = int(cmd_parts[1], 0)
                        for idx, tok in enumerate(cmd_parts[2:]):
                            val = int(tok, 0) & 0xFF
                            self.bus.write8(addr + idx, val)
                        print(f"Записано {len(cmd_parts)-2} байт по адресу 0x{addr:04X}")
                        print(self.render_dashboard(clear_screen=True))
                    except Exception as e:
                        print(f"Ошибка записи: {e}")
                else:
                    print("Использование: set <адрес> <байт1> [байт2...]")

            elif cmd == "write":
                if len(cmd_parts) >= 4:
                    d_name = cmd_parts[1]
                    try:
                        off = int(cmd_parts[2], 0)
                        raw_data = cmd_raw.split(None, 3)[3]
                        if (raw_data.startswith('"') and raw_data.endswith('"')) or (raw_data.startswith("'") and raw_data.endswith("'")):
                            data_bytes = [ord(c) & 0xFF for c in raw_data[1:-1]]
                        else:
                            data_bytes = [int(x, 0) & 0xFF for x in raw_data.split()]

                        found = False
                        for dev in getattr(self.bus, "_devices_list", []):
                            if dev.name.lower() == d_name.lower():
                                for i, b in enumerate(data_bytes):
                                    dev.write_phys(dev.start + off + i, b)
                                found = True
                                break
                        if found:
                            print(f"Записано {len(data_bytes)} байт в устройство [{d_name.upper()}].")
                            print(self.render_dashboard(clear_screen=True))
                        else:
                            print(f"Устройство [{d_name}] не найдено.")
                    except Exception as e:
                        print(f"Ошибка write: {e}")
                else:
                    print('Использование: write <устройство> <смещение> <"текст"|байты>')

            elif cmd in ("goto", "g", "mem"):
                if len(cmd_parts) > 1:
                    try:
                        g_addr = int(cmd_parts[1], 0)
                        print(self.bus.dump(g_addr, 32))
                    except Exception as e:
                        print(f"Ошибка адреса: {e}")
                else:
                    print("Использование: goto <адрес>")

            elif cmd in ("save",):
                tgt = cmd_parts[1] if len(cmd_parts) > 1 else (self.long_term_file or "lim2_state.dump")
                self.save_state(tgt)
                print(f"[DUMP] Состояние успешно сохранено в '{tgt}'.")

            elif cmd in ("load",):
                tgt = cmd_parts[1] if len(cmd_parts) > 1 else (self.long_term_file or "lim2_state.dump")
                if self.load_state(tgt):
                    print(f"[DUMP] Состояние успешно загружено из '{tgt}'.")
                    print(self.render_dashboard(clear_screen=True))
                else:
                    print(f"[DUMP] Не удалось загрузить состояние из '{tgt}'.")

            elif cmd in ("help", "h", "?", "menu"):
                print(self.render_help())

            elif cmd in ("q", "quit", "exit"):
                print("Выход из симулятора.")
                break
            else:
                print(f"Неизвестная команда '{cmd}'. Введите 'help' или 'menu' для справки.")

        # Авто-сохранение в режиме долговременной работы (Long-Term Work)
        if self.long_term_file:
            self.save_state(self.long_term_file)
            print(f"[LONG-TERM] Состояние сессии сохранено в '{self.long_term_file}'.")

    def run_batch(self, max_steps: int = 100000, verbose: bool = False) -> int:
        """Быстрый пакетный запуск."""
        start_time = time.time()
        steps = self.cpu.run(max_steps=max_steps)
        elapsed = time.time() - start_time
        if self.long_term_file:
            self.save_state(self.long_term_file)
            if verbose:
                print(f"[LONG-TERM] Состояние сессии сохранено в '{self.long_term_file}'")
        if verbose:
            speed = steps / (elapsed + 1e-9)
            print(f"[PROCESS] Завершено за {elapsed:.4f} сек ({steps} тактов, {speed:.0f} тактов/сек)")
        return steps


def run_cli(
    cpu_factory: Union[Type[BaseCPU], Callable[..., BaseCPU]],
    configure_platform: Optional[Callable[[MemoryBus], None]] = None
):
    """Стандартный CLI-интерфейс запуска симулятора из командной строки."""
    parser = argparse.ArgumentParser(description="Processor Simulator")
    parser.add_argument("file", nargs="?", default=None, help="Файл программы (.bin, .hex, .asm)")
    parser.add_argument("--org", type=lambda x: int(x, 0), default=0x0000, help="Адрес загрузки (по умолчанию 0x0000)")
    parser.add_argument("--pc", type=lambda x: int(x, 0), default=None, help="Начальный счетчик команд PC")
    parser.add_argument("-i", "--interactive", action="store_true", help="Интерактивный пошаговый режим")
    parser.add_argument("-n", "--max-steps", type=int, default=100000, help="Максимум шагов симуляции")
    parser.add_argument("-d", "--dump", nargs=2, type=lambda x: int(x, 0), metavar=("ADDR", "LEN"), help="Вывести дамп памяти")
    parser.add_argument("-l", "--layout", choices=["auto", "1col", "2col", "3col"], default="auto", help="Режим раскладки колонок (по умолчанию auto)")
    parser.add_argument("--mode", choices=["16bit", "24bit"], default="16bit", help="Режим адресации шины памяти (16bit или 24bit)")
    parser.add_argument("-m", "--memory", action="append", nargs="+", help="Диапазоны памяти RAM (напр: -m 0x0000;0x1000)")
    parser.add_argument("-v", "--video-memory", action="append", nargs="+", help="Видеопамять монитора (напр: -v 0x20;0x04;0x8000)")
    parser.add_argument("-L", "--long-term", nargs="?", const="lim2_state.dump", default=None, metavar="DUMP_FILE", help="Режим долговременной работы (Long-term work): авто-загрузка и сохранение дампа памяти и регистров")
    parser.add_argument("--col-cpu", type=int, default=None, help="Колонка для регистров CPU (1, 2, 3)")
    parser.add_argument("--col-code", type=int, default=None, help="Колонка для дизассемблера (1, 2, 3)")
    parser.add_argument("--col-mem", type=int, default=None, help="Колонка для памяти устройств (1, 2, 3)")
    parser.add_argument("--col-screen", type=int, default=None, help="Колонка для видеоэкранов (1, 2, 3)")
    parser.add_argument("--col-map", type=int, default=None, help="Колонка для карты шины (1, 2, 3)")
    parser.add_argument("--no-wrap", action="store_true", help="Отключить автоматический перенос блоков по высоте экрана")
    parser.add_argument("--max-height", type=int, default=None, help="Максимальная высота колонок в строках")
    parser.add_argument("-q", "--quiet", action="store_true", help="Тихий режим")

    args = parser.parse_args()

    bus = MemoryBus(mode=args.mode)

    # 1. Конфигурация платформы и устройств из кода (если передана функция)
    if configure_platform is not None:
        configure_platform(bus)

    # 2. Подключение кастомных диапазонов RAM (если указаны флагом -m)
    if args.memory:
        flat_mem = []
        for grp in args.memory:
            flat_mem.extend(grp)
        # Собираем все токены
        raw_m = " ".join(flat_mem).replace(";", " ").replace(",", " ").replace(":", " ").replace("-", " ")
        m_toks = [int(p, 0) for p in raw_m.split() if p.strip()]
        dev_idx = 1
        for i in range(0, len(m_toks), 2):
            s = m_toks[i]
            e = m_toks[i + 1] if i + 1 < len(m_toks) else s + 0x1000
            bus.create_dev(start=s, end=e, name=f"MEM{dev_idx}")
            if not args.quiet:
                print(f"[BUS] Подключено ОЗУ: [MEM{dev_idx}] 0x{s:04X}..0x{e:04X} ({e - s + 1} байт)")
            dev_idx += 1

    # 3. Подключение видеомониторов (если указаны флагом -v)
    if args.video_memory:
        flat_v = []
        for grp in args.video_memory:
            flat_v.extend(grp)
        # Каждый монитор может быть задан как '20;4;0x8000' или 3 токенами
        for idx, item in enumerate(flat_v, 1):
            cleaned = item.replace(";", " ").replace(",", " ").replace(":", " ")
            v_toks = [int(p, 0) for p in cleaned.split() if p.strip()]
            if len(v_toks) >= 3:
                w, h, s = v_toks[0], v_toks[1], v_toks[2]
            elif len(v_toks) == 2:
                w, h, s = 20, 4, v_toks[0]
            elif len(v_toks) == 1:
                w, h, s = 20, 4, v_toks[0]
            else:
                w, h, s = 20, 4, 0x8000
            e = s + (w * h) - 1
            bus.create_dev(start=s, end=e, name=f"VID{idx}", is_video=True, width=w, height=h)
            if not args.quiet:
                print(f"[BUS] Подключен видеомонитор: [VID{idx}] {w}x{h} по адресу 0x{s:04X}..0x{e:04X}")

    block_cols = {}
    if args.col_cpu is not None: block_cols["cpu"] = args.col_cpu
    if args.col_code is not None: block_cols["code"] = args.col_code
    if args.col_mem is not None: block_cols["mem"] = args.col_mem
    if args.col_screen is not None: block_cols["screen"] = args.col_screen
    if args.col_map is not None: block_cols["map"] = args.col_map

    cpu = cpu_factory(bus=bus) if callable(cpu_factory) else cpu_factory
    ui_cfg = UIConfig(
        layout_mode=args.layout,
        block_columns=block_cols,
        auto_height_wrap=not args.no_wrap,
        max_col_height=args.max_height
    )
    runner = SimulationRunner(
        cpu,
        ui_config=ui_cfg,
        long_term_file=args.long_term
    )

    # 4. Если указан режим долговременной работы -L и файл дампа существует — грузимся из него!
    if args.long_term and os.path.exists(args.long_term):
        if runner.load_state(args.long_term):
            if not args.quiet:
                print(f"[LONG-TERM] Восстановлено состояние из дампа '{args.long_term}' (PC: 0x{cpu.pc:04X}, тактов: {cpu.step_count})")
    elif args.file:
        loaded = runner.load(args.file, at=args.org)
        if not args.quiet:
            print(f"[RUNNER] Загружено {loaded} байт из '{args.file}' по адресу 0x{args.org:04X}")

    if args.pc is not None:
        cpu.pc = args.pc

    if args.interactive or not args.file:
        runner.run_interactive()
    else:
        runner.run_batch(max_steps=args.max_steps, verbose=not args.quiet)
        if not args.quiet:
            print(runner.render_dashboard(clear_screen=False))

    if args.dump:
        addr, length = args.dump
        print(f"\n[DUMP] 0x{addr:04X}..0x{addr+length-1:04X}:")
        print(bus.dump(addr, length))
