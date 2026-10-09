#!/usr/bin/env python3
# ==============================================================================
# LIM2 / sim / core.py — Низкоуровневое ядро процессора, регистры и декодер битов
# ==============================================================================
import re
from typing import Dict, List, Optional, Tuple, Union, Callable, Any
try:
    from .bus import MemoryBus
except (ImportError, ValueError):
    from bus import MemoryBus


class ParseResult(tuple):
    """
    Результат работы битового парсера.
    Одновременно ведет себя как кортеж для распаковки:
        op, cfg, rd = parse("[15-11] [10-8] [7-5]")
        (op,) = parse("[15-11]")
    и как полноценное целое число (int), если распарсено одно поле или 1 бит:
        opcode = parse("[15-11]")
        bit = parse("[15]")
        if opcode == 1: ...
        if opcode < 10: ...
        val = opcode + 2
    """

    def __int__(self) -> int:
        return self[0] if self else 0

    def __index__(self) -> int:
        return self[0] if self else 0

    def __bool__(self) -> bool:
        if len(self) == 1:
            return bool(self[0])
        return super().__bool__()

    def __hash__(self) -> int:
        if len(self) == 1:
            return hash(self[0])
        return super().__hash__()

    def __eq__(self, other: Any) -> bool:
        if len(self) == 1 and isinstance(other, int):
            return self[0] == other
        return super().__eq__(other)

    def __ne__(self, other: Any) -> bool:
        if len(self) == 1 and isinstance(other, int):
            return self[0] != other
        return super().__ne__(other)

    def __lt__(self, other: Any) -> bool:
        if len(self) == 1 and isinstance(other, (int, float)):
            return self[0] < other
        return super().__lt__(other)

    def __le__(self, other: Any) -> bool:
        if len(self) == 1 and isinstance(other, (int, float)):
            return self[0] <= other
        return super().__le__(other)

    def __gt__(self, other: Any) -> bool:
        if len(self) == 1 and isinstance(other, (int, float)):
            return self[0] > other
        return super().__gt__(other)

    def __ge__(self, other: Any) -> bool:
        if len(self) == 1 and isinstance(other, (int, float)):
            return self[0] >= other
        return super().__ge__(other)

    def __add__(self, other: Any) -> Any:
        if len(self) == 1 and isinstance(other, int):
            return self[0] + other
        return super().__add__(other)

    def __radd__(self, other: Any) -> Any:
        if len(self) == 1 and isinstance(other, int):
            return other + self[0]
        return other + tuple(self)

    def __sub__(self, other: Any) -> int:
        return self[0] - int(other) if len(self) == 1 else NotImplemented

    def __rsub__(self, other: Any) -> int:
        return int(other) - self[0] if len(self) == 1 else NotImplemented

    def __mul__(self, other: Any) -> Any:
        if len(self) == 1 and isinstance(other, int):
            return self[0] * other
        return super().__mul__(other)

    def __rmul__(self, other: Any) -> Any:
        if len(self) == 1 and isinstance(other, int):
            return other * self[0]
        return super().__rmul__(other)

    def __floordiv__(self, other: Any) -> int:
        return self[0] // int(other) if len(self) == 1 else NotImplemented

    def __rfloordiv__(self, other: Any) -> int:
        return int(other) // self[0] if len(self) == 1 else NotImplemented

    def __and__(self, other: Any) -> int:
        return self[0] & int(other) if len(self) == 1 else NotImplemented

    def __rand__(self, other: Any) -> int:
        return int(other) & self[0] if len(self) == 1 else NotImplemented

    def __or__(self, other: Any) -> int:
        return self[0] | int(other) if len(self) == 1 else NotImplemented

    def __ror__(self, other: Any) -> int:
        return int(other) | self[0] if len(self) == 1 else NotImplemented

    def __xor__(self, other: Any) -> int:
        return self[0] ^ int(other) if len(self) == 1 else NotImplemented

    def __rxor__(self, other: Any) -> int:
        return int(other) ^ self[0] if len(self) == 1 else NotImplemented

    def __invert__(self) -> int:
        return ~self[0] if len(self) == 1 else NotImplemented

    def __str__(self) -> str:
        if len(self) == 1:
            return str(self[0])
        return super().__str__()

    def __repr__(self) -> str:
        if len(self) == 1:
            return f"{self[0]}"
        return super().__repr__()

    def __format__(self, format_spec: str) -> str:
        if len(self) == 1:
            return format(self[0], format_spec)
        return super().__format__(format_spec)


def parse_bits(pattern: str, value: int) -> ParseResult:
    """
    Универсальный битовый декодер опкода.
    Парсит диапазоны битов вида:
      parse_bits("[15-11] [10-8] [7-5] [4-2] [1-0]", value)
      parse_bits("[opcode:15-11] [cfg:10-8]", value)
      parse_bits("[7] [6-0]", value)

    Возвращает ParseResult, который можно сразу распаковать:
      op, cfg, rd, rs1, rs2 = parse_bits("[15-11] [10-8] [7-5] [4-2] [1-0]", inst)
    """
    matches = re.findall(r"\[(?:[a-zA-Z_]\w*\s*:\s*)?(\d+)(?:-(\d+))?\]", pattern)
    if not matches:
        raise ValueError(f"Не найдены битовые поля в шаблоне: '{pattern}'. Ожидался формат '[15-11] [10-8]'")

    results = []
    for h_str, l_str in matches:
        high = int(h_str)
        low = int(l_str) if l_str else high
        if low > high:
            high, low = low, high

        width = high - low + 1
        mask = (1 << width) - 1
        extracted = (value >> low) & mask
        results.append(extracted)

    return ParseResult(results)


class RegisterSpec:
    """Спецификация регистра с настраиваемой разрядностью, маской и параметрами отображения."""

    def __init__(
        self,
        name: str,
        bits: int = 16,
        default: int = 0,
        aliases: Optional[List[str]] = None,
        title: Optional[str] = None,
        role: str = "",
        block: str = "core",
        is_pc: bool = False,
        is_acc: bool = False,
        is_aux: bool = False,
        is_flag: bool = False,
        is_virtual: bool = False,
        flag_layout: Optional[List[Tuple[str, str, int]]] = None
    ):
        self.name = name.lower()
        self.bits = bits
        self.bitwidth = bits
        self.mask = (1 << bits) - 1
        self.default = default & self.mask
        self.aliases = [a.lower() for a in (aliases or [])]
        self.title = title or name.upper()
        self.role = role
        self.block = block
        self.is_pc = is_pc
        self.is_acc = is_acc
        self.is_aux = is_aux
        self.is_flag = is_flag
        self.is_virtual = is_virtual
        self.flag_layout = flag_layout
        self.hex_len = max(2, (bits + 3) // 4)


class RegisterBank:
    """
    Банк регистров с полной свободой настройки:
      - Произвольное имя и разрядность (1, 8, 16, 24, 32, 64 бит)
      - Автоматическое маскирование переполнений
      - Доступ по имени (regs.r0), индексу (regs[0]), словарю (regs['r0'])
    """

    def __init__(self, owner: Any = None):
        self._owner = owner
        self._specs: Dict[str, RegisterSpec] = {}
        self._values: Dict[str, int] = {}
        self._alias_map: Dict[str, str] = {}
        self._indexed_names: List[str] = []

    def define(
        self,
        name: str,
        bits: int = 16,
        default: int = 0,
        aliases: Optional[List[str]] = None,
        indexed: bool = False,
        title: Optional[str] = None,
        role: str = "",
        block: str = "core",
        is_pc: bool = False,
        is_acc: bool = False,
        is_aux: bool = False,
        is_flag: bool = False,
        is_virtual: bool = False,
        flag_layout: Optional[List[Tuple[str, str, int]]] = None
    ):
        """Объявляет регистр заданной разрядности."""
        spec = RegisterSpec(
            name=name,
            bits=bits,
            default=default,
            aliases=aliases,
            title=title,
            role=role,
            block=block,
            is_pc=is_pc,
            is_acc=is_acc,
            is_aux=is_aux,
            is_flag=is_flag,
            is_virtual=is_virtual,
            flag_layout=flag_layout
        )
        norm = spec.name
        self._specs[norm] = spec
        self._values[norm] = spec.default
        self._alias_map[norm] = norm

        for a in spec.aliases:
            self._alias_map[a] = norm

        if indexed and norm not in self._indexed_names:
            self._indexed_names.append(norm)
        return spec

    def get(self, key: Union[str, int]) -> int:
        """Получить значение регистра."""
        if hasattr(key, "__index__") and not isinstance(key, (str, bool)):
            key = int(key)
        if isinstance(key, int):
            if 0 <= key < len(self._indexed_names):
                return self.get(self._indexed_names[key])
            # Фоллбэк: берем по порядку объявления (исключая pc) или по имени r{key}
            all_names = [n for n in self._specs.keys() if n != "pc"]
            if 0 <= key < len(all_names):
                return self.get(all_names[key])
            return 0

        norm = self._alias_map.get(str(key).lower(), str(key).lower())
        spec = self._specs.get(norm)
        mask = spec.mask if spec else 0xFFFF
        return self._values.get(norm, 0) & mask

    def set(self, key: Union[str, int], value: int):
        """Записать значение в регистр (автоматически маскируется)."""
        if hasattr(key, "__index__") and not isinstance(key, (str, bool)):
            key = int(key)
        if isinstance(key, int):
            if 0 <= key < len(self._indexed_names):
                self.set(self._indexed_names[key], value)
                return
            all_names = [n for n in self._specs.keys() if n != "pc"]
            if 0 <= key < len(all_names):
                self.set(all_names[key], value)
                return
            return

        norm = self._alias_map.get(str(key).lower(), str(key).lower())
        spec = self._specs.get(norm)
        mask = spec.mask if spec else 0xFFFF
        self._values[norm] = value & mask

    def reset(self):
        """Сброс всех регистров к значениям по умолчанию."""
        for name, spec in self._specs.items():
            self._values[name] = spec.default

    def __getitem__(self, key: Union[str, int]) -> int:
        return self.get(key)

    def __setitem__(self, key: Union[str, int], value: int):
        self.set(key, value)

    def __getattr__(self, name: str) -> int:
        if name.startswith("_"):
            raise AttributeError(name)
        norm = self._alias_map.get(name.lower(), name.lower())
        if norm in self._specs:
            return self.get(norm)
        raise AttributeError(f"Регистр '{name}' не найден")

    def __setattr__(self, name: str, value: Any):
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            norm = self._alias_map.get(name.lower(), name.lower())
            if norm in self._specs:
                self.set(norm, value)
            else:
                super().__setattr__(name, value)


class BaseCPU:
    """
    Низкоуровневый базовый процессор.
    Максимум свободы, минимум магии:
      - Свободная настройка регистров (cpu.reg("R0", bits=16))
      - Считывание байтов (fetch8) и сборка в инструкцию
      - Переменная databus (текущая инструкция/байткод)
      - Битовый декодер parse("[15-11] [10-8] [7-5] [4-2] [1-0]")
      - Пользовательские функции on_start() и on_step()
    """

    def __init__(self, name: str = "CPU", bus: Optional[MemoryBus] = None, pc_bits: int = 16):
        self.name = name
        self.bus = bus if bus is not None else MemoryBus()
        self.regs = RegisterBank(owner=self)

        # Системные шины и счетчики
        self.databus: int = 0
        self.addressbus: int = 0
        self.step_count: int = 0
        self.is_halted: bool = False
        self.breakpoints: set[int] = set()

        # Регистрируем PC
        self.reg("pc", bits=pc_bits, default=0x0000)

        # Вызываем начальную настройку
        self._init_done = False
        self.setup()
        self.reset()

    # --------------------------------------------------------------------------
    # Пользовательские методы переопределения (Hooks)
    # --------------------------------------------------------------------------
    def setup(self):
        """Здесь пользователь настраивает свои регистры."""
        pass

    def on_start(self):
        """Что процессор делает сразу при старте (сброс регистров, установка PC)."""
        pass

    def onStart(self):
        """Алиас в стиле camelCase."""
        self.on_start()

    def on_step(self):
        """
        Логика одного такта/инструкции процессора.
        Пользователь сам считывает байты (fetch8), собирает опкод в databus,
        декодирует через parse() и меняет регистры/память.
        """
        raise NotImplementedError("Переопределите on_step(self) в вашем классе процессора!")

    def onStep(self):
        """Алиас в стиле camelCase."""
        self.on_step()

    def reg(
        self,
        name: str,
        bits: int = 16,
        default: int = 0,
        aliases: Optional[List[str]] = None,
        indexed: bool = False,
        title: Optional[str] = None,
        role: str = "",
        block: str = "core",
        is_pc: bool = False,
        is_acc: bool = False,
        is_aux: bool = False,
        is_flag: bool = False,
        is_virtual: bool = False,
        flag_layout: Optional[List[Tuple[str, str, int]]] = None
    ):
        """Объявляет регистр с заданной разрядностью и параметрами отображения."""
        return self.regs.define(
            name=name,
            bits=bits,
            default=default,
            aliases=aliases,
            indexed=indexed,
            title=title,
            role=role,
            block=block,
            is_pc=is_pc,
            is_acc=is_acc,
            is_aux=is_aux,
            is_flag=is_flag,
            is_virtual=is_virtual,
            flag_layout=flag_layout
        )

    def get_register_specs(self) -> List[RegisterSpec]:
        """Возвращает список всех зарегистрированных спецификаций регистров для UI."""
        return list(self.regs._specs.values())

    def get_register_value(self, name: str) -> int:
        return self.regs.get(name)

    def get_reg(self, key: Union[str, int]) -> int:
        return self.regs.get(key)

    def set_reg(self, key: Union[str, int], val: int):
        self.regs.set(key, val)

    # Доступ как к атрибутам: cpu.r0, cpu.acca, cpu.pc
    def __getattr__(self, name: str) -> Any:
        if name in ("regs", "bus") or not hasattr(self, "regs"):
            raise AttributeError(name)
        norm = self.regs._alias_map.get(name.lower(), name.lower())
        if norm in self.regs._specs:
            return self.regs.get(norm)
        if hasattr(self, "bus") and hasattr(self.bus, "devices_by_name") and name in self.bus.devices_by_name:
            return self.bus.devices_by_name[name]
        raise AttributeError(f"'{self.__class__.__name__}' не имеет регистра или атрибута '{name}'")

    def __setattr__(self, name: str, value: Any):
        if name.startswith("_") or name in (
            "name", "bus", "regs", "databus", "addressbus", "step_count", "is_halted", "breakpoints"
        ):
            super().__setattr__(name, value)
            return

        if hasattr(self, "regs"):
            norm = self.regs._alias_map.get(name.lower(), name.lower())
            if norm in self.regs._specs:
                self.regs.set(norm, value)
                return

        super().__setattr__(name, value)

    def __getitem__(self, key: Union[str, int]) -> int:
        return self.regs.get(key)

    def __setitem__(self, key: Union[str, int], val: int):
        self.regs.set(key, val)

    # --------------------------------------------------------------------------
    # Program Counter и выборка байтов (Fetch)
    # --------------------------------------------------------------------------
    @property
    def pc(self) -> int:
        return self.regs.get("pc")

    @pc.setter
    def pc(self, val: int):
        self.regs.set("pc", val)

    def fetch8(self) -> int:
        """
        Считывает следующий 8-битный байт по текущему PC
        и увеличивает PC на 1.
        """
        self.addressbus = self.pc
        val = self.bus.read8(self.pc)
        self.pc = (self.pc + 1) & self.regs._specs["pc"].mask
        return val

    def fetch16(self, little_endian: bool = False) -> int:
        """
        Считывает 16-битное число из памяти по текущему PC
        и увеличивает PC на 2.
        """
        b0 = self.fetch8()
        b1 = self.fetch8()
        if little_endian:
            return (b1 << 8) | b0
        return (b0 << 8) | b1

    def jump(self, target: int):
        """Безусловный переход по адресу."""
        self.pc = target & self.regs._specs["pc"].mask

    def relative_jump(self, offset: int):
        """Относительный переход."""
        self.pc = (self.pc + offset) & self.regs._specs["pc"].mask

    # --------------------------------------------------------------------------
    # Битовый парсер / декодер
    # --------------------------------------------------------------------------
    def parse(self, pattern: str, value: Optional[int] = None) -> ParseResult:
        """
        Парсит битовые поля из value (или текущего databus, если value не передан).
        Формат: parse("[15-11] [10-8] [7-5] [4-2] [1-0]")
        """
        val = self.databus if value is None else value
        return parse_bits(pattern, val)

    # --------------------------------------------------------------------------
    # Управление флагами по именам (ZF, CF, OF, etc.)
    # --------------------------------------------------------------------------
    def get_flag(self, flag_name: str) -> int:
        """Возвращает значение бита флага по его имени (например: 'ZF', 'CF')."""
        spec = self.regs._specs.get("freg")
        if spec and spec.flag_layout:
            for fname, _, bit_pos in spec.flag_layout:
                if fname.upper() == flag_name.upper():
                    return (self.freg >> bit_pos) & 1
        return 0

    def set_flag(self, flag_name: str, val: int):
        """Устанавливает значение бита флага по имени (0 или 1)."""
        spec = self.regs._specs.get("freg")
        if spec and spec.flag_layout:
            for fname, _, bit_pos in spec.flag_layout:
                if fname.upper() == flag_name.upper():
                    mask = 1 << bit_pos
                    if val:
                        self.freg |= mask
                    else:
                        self.freg &= ~mask
                    return

    # --------------------------------------------------------------------------
    # Аппаратное рукопожатие и ожидание сигналов ножек (Handshake / Wait States)
    # --------------------------------------------------------------------------
    def read_handshake(self, addr: int, timeout: int = 100) -> int:
        """
        Чтение из памяти с аппаратным ожиданием ножки готовности RF (Ready Flag).
        Возвращает считанный байт.
        """
        if hasattr(self.bus, "read_handshake"):
            data, _ = self.bus.read_handshake(addr, timeout=timeout)
            return data
        return self.bus.read8(addr)

    def write_handshake(self, addr: int, val: int, timeout: int = 100) -> int:
        """
        Запись в память с аппаратным ожиданием ножки готовности RF (Ready Flag).
        Возвращает количество тактов задержки (wait cycles).
        """
        if hasattr(self.bus, "write_handshake"):
            return self.bus.write_handshake(addr, val, timeout=timeout)
        self.bus.write8(addr, val)
        return 0

    def wait_for_pin(self, pin_name: str = "RF", timeout: int = 100) -> int:
        """
        Удерживает процессор в состоянии ожидания (Wait State),
        пока указанная ножка не станет равной 1.
        Возвращает количество затраченных тактов.
        """
        waited = 0
        pin = getattr(self.bus.pins, pin_name)
        while not pin.get() and waited < timeout:
            if hasattr(self.bus, "tick"):
                self.bus.tick()
            waited += 1
        return waited

    # --------------------------------------------------------------------------
    # Цикл выполнения и останов
    # --------------------------------------------------------------------------
    def halt(self):
        """Останавливает процессор."""
        self.is_halted = True

    def reset(self, start_pc: Optional[int] = None):
        """Сброс процессора и вызов on_start()."""
        self.regs.reset()
        if start_pc is not None:
            self.pc = start_pc
        self.databus = 0
        self.addressbus = 0
        self.step_count = 0
        self.is_halted = False

        # Вызываем пользовательский хук старта
        if hasattr(self, "on_start"):
            self.on_start()
        elif hasattr(self, "onStart"):
            self.onStart()

    def step(self) -> bool:
        """Выполняет один шаг/инструкцию."""
        if self.is_halted or self.pc in self.breakpoints:
            return False

        # Вызываем пользовательский обработчик шага
        if hasattr(self, "on_step"):
            res = self.on_step()
        elif hasattr(self, "onStep"):
            res = self.onStep()
        else:
            raise NotImplementedError("Не определен метод on_step(self)")

        self.step_count += 1
        if hasattr(self.bus, "tick"):
            self.bus.tick(self.step_count)

        if res is False:
            self.is_halted = True
            return False
        return True

    def run(self, max_steps: int = 100000) -> int:
        """Запуск процессора до останова или лимита шагов."""
        initial = self.step_count
        while (self.step_count - initial) < max_steps:
            if not self.step():
                break
        return self.step_count - initial

    # --------------------------------------------------------------------------
    # Загрузка и дамп памяти
    # --------------------------------------------------------------------------
    def load(self, file_path: str, at: Optional[int] = None) -> int:
        count = self.bus.load(file_path, at=at)
        target = at if at is not None else 0x0000
        self.pc = target
        return count

    def load_bin(self, source: Union[str, bytes, bytearray], at: int = 0x0000) -> int:
        count = self.bus.load_bin(source, at=at)
        self.pc = at
        return count

    def load_hex(self, source: str, at: Optional[int] = None) -> int:
        count = self.bus.load_hex(source, at=at)
        if at is not None:
            self.pc = at
        return count

    def dump(self, start: int = 0x0000, length: int = 32, bytes_per_line: int = 16) -> str:
        return self.bus.dump(start=start, length=length, bytes_per_line=bytes_per_line)

    def save_state(self, path: str) -> str:
        """Сохраняет полный снимок состояния процессора, регистров и памяти."""
        regs_state = {spec.name: self.regs.get(spec.name) for spec in self.get_register_specs()}
        extra = {
            "pc": self.pc,
            "step_count": self.step_count,
            "is_halted": self.is_halted,
            "regs": regs_state
        }
        return self.bus.save_dump(path, extra_state=extra)

    def load_state(self, path: str) -> bool:
        """Загружает полный снимок состояния процессора, регистров и памяти."""
        extra = self.bus.load_dump(path)
        if extra and isinstance(extra, dict) and "regs" in extra:
            for rname, rval in extra["regs"].items():
                if rname in self.regs._specs:
                    self.regs.set(rname, rval)
            if "pc" in extra:
                self.pc = extra["pc"]
            if "step_count" in extra:
                self.step_count = extra["step_count"]
            if "is_halted" in extra:
                self.is_halted = extra["is_halted"]
            return True
        return False
