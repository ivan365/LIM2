#!/usr/bin/env python3
# ==============================================================================
# LIM2 / sim / ui.py — Полноэкранный TUI интерфейс первого симулятора LIMSIM
# ==============================================================================
# Включает:
#   1. Интегральные микросхемы регистров (Circuit IC / Chips style)
#   2. Регистр состояния и флагов (STATUS) с подробными бейджами [ZF:1] [CF:0]
#   3. Дизассемблер потока команд со светлым инверсным курсором текущего PC
#   4. Окна памяти устройств с защитой от тряски и подсветкой изменений
#   5. Графическую карту адресного пространства шины (Windows Disk Management style)
#   6. Терминальные видеоэкраны / мониторы с рамками
# ==============================================================================
import re
import shutil
from typing import Any, Dict, List, Optional, Tuple, Set

BOX_WIDTH = 80
ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    """Удаляет ANSI-escape последовательности для точного расчета видимой ширины."""
    return ANSI_RE.sub("", text)


def pad_ansi(text: str, width: int) -> str:
    """Дополняет строку пробелами до заданной видимой ширины с учётом ANSI-последовательностей."""
    clean = strip_ansi(text)
    pad = " " * max(0, width - len(clean))
    return f"{text}{pad}"


def pad_visible(text: str, width: int, align: str = "left", fillchar: str = " ") -> str:
    vis_len = len(strip_ansi(text))
    pad_needed = max(0, width - vis_len)
    if align == "right":
        return fillchar * pad_needed + text
    elif align == "center":
        left_pad = pad_needed // 2
        right_pad = pad_needed - left_pad
        return (fillchar * left_pad) + text + (fillchar * right_pad)
    else:
        return text + fillchar * pad_needed


def fit_cell(text: str, width: int, align: str = "center") -> str:
    vis = strip_ansi(text)
    if len(vis) > width:
        text = vis[:width]
    return pad_visible(text, width, align=align)


def box_top(title: str = "", width: int = BOX_WIDTH) -> str:
    if title:
        max_t = width - 8
        clean_t = strip_ansi(title)
        if len(clean_t) > max_t:
            title = clean_t[:max_t - 3] + "..."
            clean_t = strip_ansi(title)
        t = f" [{title}] "
        vis_len = len(clean_t) + 4
        bar_len = max(0, width - 4 - vis_len)
        bar = "─" * bar_len
        return f"┌──{t}{bar}┐"
    bar = "─" * (width - 2)
    return f"┌{bar}┐"


def box_divider(title: str = "", width: int = BOX_WIDTH) -> str:
    if title:
        max_t = width - 8
        clean_t = strip_ansi(title)
        if len(clean_t) > max_t:
            title = clean_t[:max_t - 3] + "..."
            clean_t = strip_ansi(title)
        t = f" [{title}] "
        vis_len = len(clean_t) + 4
        bar_len = max(0, width - 4 - vis_len)
        bar = "─" * bar_len
        return f"├──{t}{bar}┤"
    bar = "─" * (width - 2)
    return f"├{bar}┤"


def box_bottom(width: int = BOX_WIDTH) -> str:
    bar = "─" * (width - 2)
    return f"└{bar}┘"


def box_row(content: str, width: int = BOX_WIDTH) -> str:
    clean = strip_ansi(content)
    avail = width - 4
    if len(clean) > avail:
        content = content[:avail - 3] + "..."
        clean = strip_ansi(content)
    pad = " " * max(0, avail - len(clean))
    return f"│ {content}{pad} │"


def format_bytes_smart(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} Б"
    elif num_bytes < 1024 * 1024:
        kb = num_bytes / 1024.0
        return f"{kb:.1f} КБ" if kb < 10 else f"{int(round(kb))} КБ"
    else:
        mb = num_bytes / (1024.0 * 1024.0)
        return f"{mb:.1f} МБ"


# ==============================================================================
# Отрисовка микросхем регистров (Circuit IC / Chips)
# ==============================================================================
def make_single_chip(spec: Any, val: int) -> List[str]:
    """Генерирует микросхему одного регистра с ножками D, Q, WE."""
    title_raw = spec.title if spec.title else spec.name.upper()
    title_fmt = title_raw[:7]
    r_label = (spec.block or "REG")[:3].upper() if hasattr(spec, "block") else "REG"

    if spec.bits > 16:
        # 24-битный или 32-битный чип
        val_mask = val & spec.mask
        chip = [
            f"┌──[{title_fmt:^7}]────┐",
            f"│  HEX: 0x{val_mask:06X}│",
            f"│  DEC: {val_mask:7d} │",
            f"│ D           Q │",
            f"│ 24-BIT ADDR   │",
            f"│ >         {r_label:>3} │",
            f"└───────────────┘"
        ]
    elif spec.bits > 8:
        val16 = val & 0xFFFF
        hi = (val16 >> 8) & 0xFF
        lo = val16 & 0xFF
        chip = [
            f"┌──[{title_fmt:^7}]────┐",
            f"│  HEX: 0x{val16:04X}  │",
            f"│  DEC: {val16:5d}   │",
            f"│ D           Q │",
            f"│ H:0x{hi:02X} L:0x{lo:02X} │",
            f"│ >         {r_label:>3} │",
            f"└───────────────┘"
        ]
    else:
        val8 = val & 0xFF
        bin_val = f"{val8:08b}"
        chip = [
            f"┌──[{title_fmt:^7}]────┐",
            f"│   HEX: 0x{val8:02X}   │",
            f"│   DEC: {val8:4d}   │",
            f"│ D           Q │",
            f"│ WE   {bin_val} │",
            f"│ >         {r_label:>3} │",
            f"└───────────────┘"
        ]
    return chip


def make_flag_chip(spec: Any, val: int, width: int = 74) -> List[str]:
    """Генерирует расширенный чип регистра флагов со статусами битов."""
    W = width
    inner_w = W - 2
    title = f" {spec.title or 'FREG'} / STATUS "
    prefix = f"┌──[{title}]"
    bar_len = max(0, W - 1 - len(prefix))
    top = prefix + ("─" * bar_len) + "┐"

    def wrap_line(content: str) -> str:
        c_vis = len(strip_ansi(content))
        pad = max(0, inner_w - c_vis)
        return "│" + content + (" " * pad) + "│"

    val_hex = f"0x{val:0{spec.hex_len}X}" if hasattr(spec, "hex_len") else f"0x{val:04X}"
    bin_str = f"{val:0{spec.bits}b}"
    left_info = f" HEX: {val_hex} ({val:d})    BIN: [{bin_str}]"
    right_info = f"WIDTH: {spec.bits}-BIT "
    space1 = inner_w - len(left_info) - len(right_info)
    r1 = wrap_line(left_info + (" " * max(1, space1)) + right_info)
    r2 = wrap_line(" D" + (" " * (inner_w - 4)) + "Q ")

    layout = spec.flag_layout or [
        ("ZF", "Zero", 0), ("CF", "Carry", 1), ("OF", "Overflow", 2), ("EM", "ErrMath", 3),
        ("PIE", "ProgInt", 8), ("MIE", "MasterInt", 9), ("DWR", "NoWait", 10), ("M24", "24-bit Mode", 11)
    ]

    flag_rows = []
    for chunk_idx in range(0, len(layout), 4):
        chunk = layout[chunk_idx:chunk_idx + 4]
        items = []
        for fname, fdesc, bit_pos in chunk:
            bval = 1 if (val & (1 << bit_pos)) else 0
            badge = f"\033[1;32m[{fname}:1]\033[0m" if bval else f"\033[90m[{fname}:0]\033[0m"
            items.append(pad_ansi(f"{badge} {fdesc[:10]}", 17))
        row_inner = "  " + "".join(items)
        flag_rows.append(wrap_line(row_inner))

    row_last = wrap_line(" >" + (" " * (inner_w - 11)) + "STATUS ")
    bot = "└" + ("─" * inner_w) + "┘"
    return [top, r1, r2] + flag_rows + [row_last, bot]


def render_circuit_registers(cpu: Any, step_count: int = 0) -> str:
    """Форматирует панель регистров в стиле Circuit IC (микросхем)."""
    specs = getattr(cpu, "get_register_specs", lambda: list(cpu.regs._specs.values()))()
    pc_val = cpu.pc

    core_specs = [s for s in specs if not getattr(s, "is_aux", False) and not getattr(s, "is_flag", False) and s.name != "pc"]
    aux_specs = [s for s in specs if getattr(s, "is_aux", False) and not getattr(s, "is_flag", False)]
    flag_specs = [s for s in specs if getattr(s, "is_flag", False)]

    lines = [box_top("LIM CPU Circuit Registers")]

    def render_chips_rows(spec_list: List[Any]) -> List[str]:
        row_lines = []
        chips = [make_single_chip(s, cpu.get_reg(s.name)) for s in spec_list]
        for chunk_idx in range(0, len(chips), 4):
            chunk = chips[chunk_idx:chunk_idx + 4]
            for r in range(7):
                row_chips = [c[r] for c in chunk]
                row_str = " " + "  ".join(row_chips)
                row_lines.append(box_row(row_str))
        return row_lines

    # 1. Основные регистры
    lines.extend(render_chips_rows(core_specs))
    hdr = f"PC: 0x{pc_val:04X} ({pc_val:5d})    Такты: {step_count:<7d}    Шина: {getattr(cpu.bus, 'mode', '16bit').upper()}"
    lines.append(box_row(hdr))

    # 2. Вспомогательные блоки (ALU / ACCA / ACCB)
    if aux_specs:
        lines.append(box_divider("Вспомогательные блоки (ALU / ACC)"))
        lines.extend(render_chips_rows(aux_specs))

    # 3. Регистр флагов (STATUS)
    if flag_specs:
        lines.append(box_divider("Регистры состояния и флагов (STATUS)"))
        for s in flag_specs:
            val = cpu.get_reg(s.name)
            flag_lines = make_flag_chip(s, val, width=74)
            for fl in flag_lines:
                lines.append(box_row(" " + fl))

    lines.append(box_bottom())
    return "\n".join(lines)


# ==============================================================================
# Дизассемблер потока кода с подсветкой текущего PC
# ==============================================================================
def render_code_stream(cpu: Any, code_rows: int = 6) -> str:
    """
    Отрисовывает окно дизассемблера / потока инструкций.
    Текущий адрес PC выделяется инверсным курсором.
    """
    curr_pc = cpu.pc
    bus = cpu.bus
    title = f"ПОТОК КОМАНД (ДИЗАССЕМБЛЕР) @ PC=0x{curr_pc:04X}"
    lines = [box_top(title)]

    for i in range(code_rows):
        addr = (curr_pc + i * 2) & getattr(bus, "mask", 0xFFFF)
        b0 = bus.read8(addr)
        b1 = bus.read8(addr + 1)
        w = (b0 << 8) | b1

        # Извлекаем опкод для подсказки
        op = (w >> 11) & 0x1F
        rd = (w >> 5) & 0x07
        rs1 = (w >> 2) & 0x07
        rs2 = w & 0x03

        # Описания популярных инструкций
        op_names = {
            0: "NOP", 1: f"ADD R{rd}, R{rs1}, R{rs2}", 2: f"SUB R{rd}, R{rs1}, R{rs2}",
            3: f"MUL R{rd}, R{rs1}, R{rs2}", 4: f"DIV R{rd}, R{rs1}, R{rs2}",
            5: f"MOV R{rd}, R{rs1}", 6: f"MOVI R{rd}, #...", 7: f"LOAD R{rd}, [R{rs1}]",
            8: f"STORE [R{rd}], R{rs1}", 9: f"AND R{rd}, R{rs1}", 10: f"OR R{rd}, R{rs1}",
            11: f"XOR R{rd}, R{rs1}", 12: "JMP target", 13: "JZ target", 14: "JNZ target",
            31: "HALT"
        }
        mnem = op_names.get(op, f"OP_{op:02X} R{rd}, R{rs1}")

        is_current = (i == 0)
        raw_hex = f"{b0:02X} {b1:02X}"
        if is_current:
            raw_text = f" ▶ 0x{addr:04X}:  {raw_hex:<6}  {mnem:<40} <== [PC]"
            lines.append(box_row(f"\033[7;1m{raw_text:<76}\033[0m"))
        else:
            raw_text = f"   0x{addr:04X}:  {raw_hex:<6}  {mnem:<40}"
            lines.append(box_row(raw_text))

    lines.append(box_bottom())
    return "\n".join(lines)


# ==============================================================================
# Карта адресного пространства шины (Windows Disk Management Style)
# ==============================================================================
def collect_memory_segments(bus: Any):
    bus_bits = getattr(bus, "busbits", 16)
    max_bus_addr = (1 << bus_bits) - 1
    total_bus_space = 1 << bus_bits

    devs = list(getattr(bus, "_devices_list", []))
    if not devs:
        # Если устройств нет, создаем дефолтный сегмент RAM
        devs = [type("DummyRAM", (), {
            "start": 0x0000,
            "end": min(max_bus_addr, len(bus.ram) - 1 if bus.ram else 0xFFFF),
            "name": "RAM",
            "size": min(total_bus_space, len(bus.ram) if bus.ram else 0x10000),
            "is_video": False,
            "readonly": False
        })()]

    sorted_devs = sorted(devs, key=lambda d: d.start)
    segments = []
    curr_addr = 0
    orphaned_devs = []

    for dev in sorted_devs:
        if dev.start > max_bus_addr:
            orphaned_devs.append((dev, dev.start, dev.end, dev.size))
            continue

        if dev.start > curr_addr:
            gap_size = dev.start - curr_addr
            segments.append({
                "type": "free",
                "name": "[Свободно]",
                "dev": None,
                "start": curr_addr,
                "end": dev.start - 1,
                "size": gap_size
            })

        in_bus_end = min(dev.end, max_bus_addr)
        in_bus_size = in_bus_end - dev.start + 1
        segments.append({
            "type": "device",
            "name": dev.name,
            "dev": dev,
            "start": dev.start,
            "end": in_bus_end,
            "size": in_bus_size
        })
        curr_addr = in_bus_end + 1

    if curr_addr <= max_bus_addr:
        segments.append({
            "type": "free",
            "name": "[Свободно]",
            "dev": None,
            "start": curr_addr,
            "end": max_bus_addr,
            "size": max_bus_addr - curr_addr + 1
        })

    return segments, orphaned_devs, total_bus_space, max_bus_addr


def render_diskmgmt_bar(segments: list, total_bus_space: int, max_inner_width: int = 76) -> List[str]:
    K = len(segments)
    if K == 0:
        return []

    avail = max_inner_width - (K + 1)
    widths = []
    for seg in segments:
        share = seg["size"] / total_bus_space
        w = max(4, int(round(share * avail)))
        widths.append(w)

    while sum(widths) > avail:
        idx = widths.index(max(widths))
        widths[idx] -= 1
    while sum(widths) < avail:
        idx = widths.index(min(widths))
        widths[idx] += 1

    top_parts = ["─" * w for w in widths]
    div_parts = ["─" * w for w in widths]
    bot_parts = ["─" * w for w in widths]

    top_line = "┌" + "┬".join(top_parts) + "┐"
    div_line = "├" + "┼".join(div_parts) + "┤"
    bot_line = "└" + "┴".join(bot_parts) + "┘"

    title_cells = []
    addr_cells = []
    pct_cells = []

    for seg, w in zip(segments, widths):
        pct = (seg["size"] / total_bus_space) * 100.0
        if seg["type"] == "free":
            t_str = fit_cell("[Свободно]" if w >= 10 else "░░", w)
            a_str = fit_cell(f"0x{seg['start']:04X}..0x{seg['end']:04X}" if w >= 14 else f"{seg['start']:04X}", w)
            p_str = fit_cell(f"{pct:.1f}%", w)
        else:
            dev = seg["dev"]
            color = "\033[1;36m" if getattr(dev, "is_video", False) else "\033[1;32m"
            t_str = fit_cell(f"{color}{seg['name']}\033[0m", w)
            a_str = fit_cell(f"0x{seg['start']:04X}..0x{seg['end']:04X}" if w >= 14 else f"{seg['start']:04X}", w)
            p_str = fit_cell(f"{format_bytes_smart(seg['size'])} ({pct:.0f}%)" if w >= 12 else f"{pct:.0f}%", w)

        title_cells.append(t_str)
        addr_cells.append(a_str)
        pct_cells.append(p_str)

    row_title = "│" + "│".join(title_cells) + "│"
    row_addr = "│" + "│".join(addr_cells) + "│"
    row_pct = "│" + "│".join(pct_cells) + "│"

    return [top_line, row_title, div_line, row_addr, row_pct, bot_line]


def render_full_memory_map(bus: Any) -> str:
    bus_bits = getattr(bus, "busbits", 16)
    segments, orphaned_devs, total_bus_space, max_bus_addr = collect_memory_segments(bus)

    lines = [box_top(f"КАРТА АДРЕСНОГО ПРОСТРАНСТВА ШИНЫ (0x0000..0x{max_bus_addr:04X}, {bus_bits} бит)")]
    lines.append(box_row("РАСПРЕДЕЛЕНИЕ ПАМЯТИ УСТРОЙСТВ (DISKMGMT.MSC STYLE):"))

    bar_lines = render_diskmgmt_bar(segments, total_bus_space, max_inner_width=76)
    for bl in bar_lines:
        lines.append(box_row(bl))

    used_bytes = sum(s["size"] for s in segments if s["type"] == "device")
    free_bytes = sum(s["size"] for s in segments if s["type"] == "free")
    used_pct = (used_bytes / total_bus_space) * 100.0
    free_pct = (free_bytes / total_bus_space) * 100.0

    stat_line = f"Занято: {format_bytes_smart(used_bytes)} ({used_pct:.1f}%) │ Свободно: {format_bytes_smart(free_bytes)} ({free_pct:.1f}%) │ Объем шины: {format_bytes_smart(total_bus_space)}"
    lines.append(box_row(stat_line))
    lines.append(box_bottom())
    return "\n".join(lines)


# ==============================================================================
# Окна памяти устройств (Device memory hexdump)
# ==============================================================================
def render_devices_memory(bus: Any, cpu: Any, step_count: int = 0) -> str:
    devs = list(getattr(bus, "_devices_list", []))
    lines = [box_top(f"СОСТОЯНИЕ ПАМЯТИ УСТРОЙСТВ (Такт #{step_count})")]

    if not devs:
        # Дамп начального диапазона ОЗУ
        lines.append(box_row(" ► [RAM] (0x0000..0x003F) | PC:0x{:04X}".format(cpu.pc)))
        for off in range(0, 64, 16):
            chunk = [bus.read8(off + i) for i in range(16)]
            h_l = " ".join(f"{b:02X}" for b in chunk[:8])
            h_r = " ".join(f"{b:02X}" for b in chunk[8:])
            a_s = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
            lines.append(box_row(f"0x{off:04X}: {h_l}  {h_r}  |{a_s}|"))
    else:
        for dev_idx, dev in enumerate(devs[:3]):
            if dev_idx > 0:
                lines.append(box_divider())
            lines.append(box_row(f" ► [{dev.name}] (0x{dev.start:04X}..0x{dev.end:04X})"))
            dump_str = dev.format_windowed_hexdump(current_step=step_count, pc_addr=cpu.pc)
            for dl in dump_str.splitlines():
                lines.append(box_row(dl))

    lines.append(box_bottom())
    return "\n".join(lines)


def join_columns(blocks: List[str], gap: int = 2) -> str:
    """
    Объединяет N многострочных текстовых блоков бок о бок с учётом ANSI-последовательностей.
    """
    valid_blocks = [b for b in blocks if b and b.strip()]
    if not valid_blocks:
        return ""
    if len(valid_blocks) == 1:
        return valid_blocks[0]

    lines_per_block = [b.splitlines() for b in valid_blocks]
    widths = [max((len(strip_ansi(l)) for l in lines), default=0) for lines in lines_per_block]
    max_lines = max(len(lines) for lines in lines_per_block)
    gap_str = " " * gap

    result = []
    for i in range(max_lines):
        row_parts = []
        for b_idx, lines in enumerate(lines_per_block):
            w = widths[b_idx]
            is_last = (b_idx == len(lines_per_block) - 1)
            if i < len(lines):
                line = lines[i]
                vis_len = len(strip_ansi(line))
                pad = " " * max(0, w - vis_len)
                if is_last:
                    row_parts.append(line)
                else:
                    row_parts.append(f"{line}{pad}")
            else:
                if not is_last:
                    row_parts.append(" " * w)
        result.append(gap_str.join(row_parts))

    return "\n".join(result)


def join_side_by_side(left_block: str, right_block: str, gap: int = 2) -> str:
    """Объединяет два многострочных текстовых блока бок о бок."""
    return join_columns([left_block, right_block], gap=gap)


def canonical_block_name(name: str) -> Optional[str]:
    """Приводит пользовательское имя блока к каноническому виду."""
    if not name:
        return None
    clean = name.strip().lower()
    if clean in ("cpu", "regs", "reg", "r", "ic", "chips", "chip"):
        return "cpu"
    if clean in ("code", "disasm", "asm", "disas", "instructions", "c"):
        return "code"
    if clean in ("mem", "memory", "devices", "dev", "devs", "dump", "m"):
        return "mem"
    if clean in ("screen", "video", "vid", "monitor", "mon", "scr", "s", "v"):
        return "screen"
    if clean in ("map", "busmap", "bus"):
        return "map"
    return None


class UIConfig:
    """Конфигурация автоматической и настраиваемой раскладки экрана симулятора."""
    def __init__(
        self,
        layout_mode: str = "auto",  # "auto", "1col", "2col", "3col"
        show_cpu: bool = True,
        show_code: bool = True,
        show_mem: bool = True,
        show_screen: bool = True,
        show_map: bool = True,
        map_pos: str = "auto",
        code_rows: int = 8,
        mem_rows: int = 4,
        block_columns: Optional[Dict[str, int]] = None,
        auto_height_wrap: bool = True,
        max_col_height: Optional[int] = None
    ):
        self.layout_mode = layout_mode
        self.show_cpu = show_cpu
        self.show_code = show_code
        self.show_mem = show_mem
        self.show_screen = show_screen
        self.show_map = show_map
        self.map_pos = map_pos
        self.code_rows = code_rows
        self.mem_rows = mem_rows
        self.auto_height_wrap = auto_height_wrap
        self.max_col_height = max_col_height

        # Привязка блоков к колонкам по умолчанию (1..3)
        self.block_columns: Dict[str, int] = {
            "cpu": 1,
            "screen": 1,
            "code": 2,
            "mem": 3,
            "map": 3,
        }
        if block_columns:
            for k, v in block_columns.items():
                c = canonical_block_name(k)
                if c:
                    self.block_columns[c] = max(1, min(3, int(v)))

    def get_block_column(self, block: str) -> int:
        c = canonical_block_name(block)
        return self.block_columns.get(c or block, 1)

    def set_block_column(self, block: str, col: int) -> bool:
        c = canonical_block_name(block)
        if not c:
            return False
        self.block_columns[c] = max(1, min(3, int(col)))
        return True

    def move_block_next(self, block: str, max_cols: int = 3) -> Optional[int]:
        c = canonical_block_name(block)
        if not c:
            return None
        cur = self.block_columns.get(c, 1)
        nxt = 1 if cur >= max_cols else cur + 1
        self.block_columns[c] = nxt
        return nxt

    def move_block_prev(self, block: str, max_cols: int = 3) -> Optional[int]:
        c = canonical_block_name(block)
        if not c:
            return None
        cur = self.block_columns.get(c, 1)
        prev = max_cols if cur <= 1 else cur - 1
        self.block_columns[c] = prev
        return prev


# ==============================================================================
# Главная функция сборки интерфейса (автоматический адаптивный 1/2/3-колоночный режим)
# ==============================================================================
def render_full_simulator_screen(
    cpu: Any,
    step_count: int = 0,
    cfg: Optional[UIConfig] = None
) -> str:
    """
    Формирует экран симулятора с поддержкой:
    - Настраиваемого распределения блоков по колонкам (1, 2, 3)
    - Автоматического переноса блоков при нехватке высоты экрана (Height Wrap)
    - Адаптивного многоколоночного рендеринга (1col / 2col / 3col)
    """
    if cfg is None:
        cfg = UIConfig()

    cpu_widget = render_circuit_registers(cpu, step_count=step_count) if cfg.show_cpu else ""
    code_widget = render_code_stream(cpu, code_rows=cfg.code_rows) if cfg.show_code else ""
    mem_widget = render_devices_memory(cpu.bus, cpu, step_count=step_count) if cfg.show_mem else ""
    map_widget = render_full_memory_map(cpu.bus) if cfg.show_map else ""

    video_widgets = []
    if cfg.show_screen:
        for dev in getattr(cpu.bus, "_devices_list", []):
            if getattr(dev, "is_video", False) and hasattr(dev, "render_screen"):
                scr = dev.render_screen()
                if scr:
                    video_widgets.append(scr)
            elif hasattr(dev, "render_panel") and callable(dev.render_panel):
                pnl = dev.render_panel()
                if pnl:
                    video_widgets.append(pnl)

    screen_widget = "\n".join(video_widgets) if video_widgets else ""

    term_size = shutil.get_terminal_size((80, 24))
    term_cols = term_size.columns
    term_lines = term_size.lines

    MIN_3COL_WIDTH = 244
    MIN_2COL_WIDTH = 162

    # Определяем количество колонок по ширине терминала или явной настройке
    if cfg.layout_mode == "auto":
        if term_cols >= MIN_3COL_WIDTH:
            num_cols = 3
        elif term_cols >= MIN_2COL_WIDTH:
            num_cols = 2
        else:
            num_cols = 1
    elif cfg.layout_mode == "3col":
        num_cols = 3
    elif cfg.layout_mode == "2col":
        num_cols = 2
    else:
        num_cols = 1

    widget_map = {
        "cpu": cpu_widget,
        "code": code_widget,
        "screen": screen_widget,
        "mem": mem_widget,
        "map": map_widget,
    }

    # Порядок следования блоков по умолчанию внутри колонки
    DEFAULT_BLOCK_ORDER = ["cpu", "code", "screen", "mem", "map"]

    # 1. Если колонка всего одна (узкий терминал или принудительно 1col)
    if num_cols == 1:
        ordered = sorted(
            [b for b in DEFAULT_BLOCK_ORDER if widget_map[b] and widget_map[b].strip()],
            key=lambda b: cfg.get_block_column(b)
        )
        return "\n".join(widget_map[b] for b in ordered)

    # 2. Многоколоночный режим (2 или 3 колонки)
    cols: List[List[Tuple[str, str, int]]] = [[] for _ in range(num_cols)]

    for b_name in DEFAULT_BLOCK_ORDER:
        w_text = widget_map[b_name]
        if not w_text or not w_text.strip():
            continue
        w_lines = len(w_text.splitlines())
        desired_col = cfg.get_block_column(b_name)

        # Дефолтная раскладка для 2 колонок (если пользователь не менял вручную):
        # Левая колонка: cpu, code; Правая колонка: screen, mem, map
        if num_cols == 2 and cfg.block_columns == UIConfig().block_columns:
            target_idx = 0 if b_name in ("cpu", "code") else 1
        else:
            target_idx = min(num_cols - 1, max(0, desired_col - 1))

        cols[target_idx].append((b_name, w_text, w_lines))

    # 3. Автоматический перенос по высоте экрана (Height-Adaptive Overflow Wrap)
    if cfg.auto_height_wrap and num_cols > 1:
        target_h = cfg.max_col_height if cfg.max_col_height is not None else max(15, term_lines - 3)

        # Проход слева направо: если колонка i выше target_h, а в следующей есть место
        for i in range(num_cols - 1):
            while len(cols[i]) > 1:
                cur_h = sum(item[2] for item in cols[i])
                next_h = sum(item[2] for item in cols[i + 1])
                if cur_h > target_h and next_h < cur_h:
                    # Переносим последний блок в следующую колонку
                    block_to_move = cols[i].pop()
                    cols[i + 1].insert(0, block_to_move)
                else:
                    break

        # Проход справа налево (для балансировки последней колонки)
        for i in range(num_cols - 1, 0, -1):
            while len(cols[i]) > 1:
                cur_h = sum(item[2] for item in cols[i])
                prev_h = sum(item[2] for item in cols[i - 1])
                if cur_h > target_h and (prev_h + cols[i][-1][2]) <= target_h:
                    block_to_move = cols[i].pop()
                    cols[i - 1].append(block_to_move)
                else:
                    break

    # Сборка колонок
    col_strings = []
    for c in cols:
        if c:
            col_strings.append("\n".join(item[1] for item in c))
        else:
            col_strings.append("")

    active_cols = [cs for cs in col_strings if cs and cs.strip()]
    if not active_cols:
        return ""
    if len(active_cols) == 1:
        return active_cols[0]
    return join_columns(active_cols, gap=2)

