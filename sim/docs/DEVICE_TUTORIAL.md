# 🛠️ Практическое руководство по созданию внешних устройств для LIM M2 (Device Developer Guide)

Полный пошаговый туториал по разработке, подключению и программированию любых внешних периферийных устройств (Memory-Mapped I/O, таймеры, прерывания, видеоконтроллеры, DMA, внешние шинные модули) на платформе симулятора **LIM M2** (Pure Python, Zero Dependencies).

---

## 📑 Содержание

1. [Архитектура системной шины LIM M2](#1-архитектура-системной-шины-lim-m2)
2. [Анатомия базового класса BaseDevice](#2-анатомия-базового-класса-basedevice)
3. [Рецепт 1: Простое MMIO-устройство (GPIO контроллер светодиодов и кнопок)](#рецепт-1-простое-mmio-устройство-gpio-контроллер)
4. [Рецепт 2: Устройство с аппаратным прерыванием IRQ (Сенсор / Таймер)](#рецепт-2-устройство-с-аппаратным-прерыванием-irq)
5. [Рецепт 3: Аппаратная задержка (Latency) и протокол готовности RF](#рецепт-3-аппаратная-задержка-latency-и-протокол-готовности-rf)
6. [Рецепт 4: Низкоуровневый физический контроль шины (on_bus_cycle)](#рецепт-4-низкоуровневый-физический-контроль-шины-on_bus_cycle)
7. [Рецепт 5: Видеоконтроллер и графический дисплей с Dirty Tracking](#рецепт-5-видеоконтроллер-и-графический-дисплей)
8. [Рецепт 6: Контроллер прямого доступа к памяти (DMA)](#рецепт-6-контроллер-прямого-доступа-к-памяти-dma)
9. [Рецепт 7: Энергонезависимая память (NVM / ROM с сохранением в файл)](#рецепт-7-энергонезависимая-память-nvm--rom)
10. [Сборка системы, карта памяти и запуск](#10-сборка-системы-карта-памяти-и-запуск)
11. [Написание драйвера на ассемблере LIM M2](#11-написание-драйвера-на-ассемблере-lim-m2)

---

## 1. Архитектура системной шины LIM M2

Системная шина `MemoryBus` соединяет процессор `LIM2CPU` и внешние устройства:

```text
       ┌────────────────────────────────────────────────────────┐
       │                   ПРОЦЕССОР LIM M2                     │
       └────┬───────────┬──────────────┬─────────────▲──────────┘
            │ Address   │ Data         │ Control     │ Interrupt
       A0-A31 (32 бит)  │ D0-D7 (8 бит)│ RD/WR/RF    │ IRQ (ножка)
            ▼           ▼              ▼             │
═════════════════════════════════════════════════════╪═══════════════════ [ШИНА]
     │                 │                  │          │
     ▼                 ▼                  ▼          │
┌───────────┐   ┌─────────────┐   ┌──────────────┐   │
│ ОЗУ / RAM │   │ GPIO / UART │   │  ВИДЕОПАМЯТЬ │───┘ (Генерация IRQ)
│ 0x0000..  │   │  0x000100.. │   │  0x00080000..│
└───────────┘   └─────────────┘   └──────────────┘
```

### Ключевые параметры шины:
* **Адресное пространство:** Линейное 32-битное (`0x00000000` — `0xFFFFFFFF`, 4 ГБ). Любое устройство отображается в свой диапазон адресов (`MMIO`).
* **Разрядность шины данных:** 8 бит (`D0–D7`). Чтение и запись 16-битных слов (`.w`) и 32-битных адресов (`.d`) осуществляются побайтово в порядке **Little-Endian** (младший байт по меньшему адресу).
* **Сигнальные ножки (`PinBank`):**
  * `RD` (Read) — процессор производит чтение из шины.
  * `WR` (Write) — процессор производит запись данных на шину.
  * `MREQ` (Memory Request) — обращение к адресному пространству памяти.
  * `IORQ` (I/O Request) — обращение к пространству портов / периферии.
  * `IRQ` (Interrupt Request) — линия запроса аппаратного прерывания от внешних устройств к процессору.
  * `RF` (Ready Flag) — флаг готовности памяти/периферии (рукопожатие при наличии циклов ожидания `Wait States`).
  * `HALT` — сигнал останова процессора.
  * `RESET` — аппаратный сброс процессора и устройств.
* **Принцип Zero Tri-State:** Отсутствие внутренних неопределенных Z-состояний. Арбитр шины отслеживает конфликты одновременного выставления данных несколькими устройствами по одному адресу (`Bus Contention Detection`).

---

## 2. Анатомия базового класса BaseDevice

Все внешние модули в симуляторе LIM M2 наследуются от класса `BaseDevice` (модуль `LIM2.sim.devices`):

```python
from devices import BaseDevice

class MyDevice(BaseDevice):
    def __init__(self, start: int, size: int, name: str = "MY_DEV"):
        super().__init__(start=start, size=size, name=name)
        # Пользовательская инициализация внутренних регистров
```

### Главные параметры конструктора `super().__init__(...)`:
| Параметр | Тип | Описание |
| :--- | :---: | :--- |
| `start` | `int` | Начальный физический 32-битный адрес на шине (например, `0x00010000`). |
| `size` | `int` | Размер адресного окна устройства в байтах (например, `16`). |
| `end` | `int` | Конечный адрес (альтернатива `size`, вычисляется автоматически). |
| `name` | `str` | Короткое имя устройства для карты памяти и логов (например, `GPIO0`). |
| `readonly`| `bool`| Если `True`, запись в устройство аппаратно блокируется (режим ROM). |
| `latency` | `int` | Задержка отклика в тактах шины (аппаратное отставание памяти, 0 = мгновенно). |
| `ready_pin`| `str`| Имя сигнальной ножки готовности данных (по умолчанию `"RF"`). |
| `is_video`| `bool`| Если `True`, устройство регистрируется как видеодисплей для GUI/TUI. |
| `persist` | `bool`| Автоматическое сохранение/загрузка состояния устройства в файл на диске. |
| `file` | `str` | Путь к файлу образа для сохранения/загрузки. |

### Методы и хуки жизненного цикла:
* `read(offset: int) -> int` — **Обязательный.** Вызывается, когда процессор читает байт по относительному смещению (`0 <= offset < size`). Должен возвращать целое число `0..255`.
* `write(offset: int, value: int)` — **Обязательный.** Вызывается, когда процессор пишет байт `value & 0xFF` по смещению `offset`.
* `on_attach(bus)` — Вызывается один раз в момент подключения устройства к шине (`bus.attach(dev)`). Здесь доступен объект `self.bus`.
* `on_step()` / `on_tick()` — Вызывается **на каждом такте процессора**. Используется для таймеров, внутренних автоматов состояний и автономных контроллеров.
* `on_pin_change(pin_name: str, new_val: int)` — Реакция на изменение уровней сигнальных ножек (`CS`, `RESET`, `IRQ` и др.).
* `on_bus_cycle(bus)` — Низкоуровневый хук физического цикла. Дает прямой доступ к физическим ножкам `bus.rd`, `bus.wr`, `bus.addressbus` и `bus.databus`.

---

## Рецепт 1: Простое MMIO-устройство (GPIO контроллер)

Создадим 8-битный контроллер ввода-вывода общего назначения (`GPIO`).

### Карта регистров (размер 4 байта):
* `Offset 0x00` (`DATA_OUT`): Данные на выход (светодиоды, реле). Запись/чтение.
* `Offset 0x01` (`DATA_IN`): Физическое состояние входных пинов (кнопки, датчики). Только чтение.
* `Offset 0x02` (`DIRECTION`): Направление линий (0 = вход, 1 = выход).
* `Offset 0x03` (`STATUS`): Флаг активности контроллера.

### Реализация на Python:

```python
from devices import BaseDevice

class GPIODevice(BaseDevice):
    def __init__(self, start: int = 0x00010000, name: str = "GPIO"):
        super().__init__(start=start, size=4, name=name)
        self.data_out = 0x00
        self.direction = 0x00
        self._external_inputs = 0x00  # Физические кнопки из внешнего мира

    def set_button(self, pin_index: int, pressed: bool):
        """Внешний метод симулятора: эмуляция нажатия кнопки пользователем."""
        if pressed:
            self._external_inputs |= (1 << pin_index)
        else:
            self._external_inputs &= ~(1 << pin_index)

    def read(self, offset: int) -> int:
        if offset == 0:
            return self.data_out
        elif offset == 1:
            # Читаем входы с учетом маски направления (только те, что настроены на вход)
            return self._external_inputs & (~self.direction & 0xFF)
        elif offset == 2:
            return self.direction
        elif offset == 3:
            return 0x01  # Контроллер готов к работе
        return 0

    def write(self, offset: int, value: int):
        val8 = value & 0xFF
        if offset == 0:
            # При записи на выход обновляем только выводы, настроенные как выходы
            self.data_out = val8 & self.direction
            print(f"[GPIO] Выходное состояние светодиодов: 0b{self.data_out:08b}")
        elif offset == 2:
            self.direction = val8
            print(f"[GPIO] Маска направлений DIR установлена: 0x{self.direction:02X}")
```

---

## Рецепт 2: Устройство с аппаратным прерыванием IRQ

Создадим аппаратный интервальный таймер, который отсчитывает такты процессора и при достижении нуля выставляет сигнал `IRQ` на системной шине.

### Как работает прерывание в процессоре LIM M2:
1. Устройство поднимает ножку: `self.bus.pins.IRQ.set(1)`.
2. Если в `FREG` процессора разрешены прерывания (`MIE=1`, бит 9) и процессор не находится в прерывании (`INTR=0`, бит 15):
   * Текущий 32-битный `PC` сохраняется в вершину аппаратного стека `SP` (`SP -= 4`, Little-Endian).
   * Бит `INTR` (бит 15 `FREG`) устанавливается в `1` (блокировка вложенных прерываний).
   * `PC` загружается из таблицы системных векторов `INT_VEC[i]` (`$ir0..$ir15`).
3. Обработчик прерывания (ISR) выполняет полезную работу, сбрасывает флаг в регистре устройства (квитирование ACK, устройство опускает `IRQ.set(0)`) и выполняет команду `RET`.
4. Инструкция `RET` извлекает `PC` из стека (`SP += 4`) и автоматически сбрасывает `INTR = 0`.

### Реализация таймера:

```python
from devices import BaseDevice

class HardwareTimerDevice(BaseDevice):
    def __init__(self, start: int = 0x00020000, name: str = "TIMER"):
        super().__init__(start=start, size=4, name=name)
        self.reload_value = 100
        self.counter = 100
        self.enabled = False
        self.irq_pending = False

    def on_step(self):
        """Вызывается на каждом такте процессора."""
        if not self.enabled:
            return

        self.counter -= 1
        if self.counter <= 0:
            self.counter = self.reload_value
            self.irq_pending = True
            # Поднимаем ножку IRQ на шине процессора!
            if self.bus is not None:
                self.bus.pins.IRQ.set(1)

    def read(self, offset: int) -> int:
        if offset == 0:
            return self.counter & 0xFF
        elif offset == 1:
            return 1 if self.irq_pending else 0
        elif offset == 2:
            return self.reload_value & 0xFF
        return 0

    def write(self, offset: int, value: int):
        val8 = value & 0xFF
        if offset == 0:
            # Запись в регистр 0 включает/выключает таймер
            self.enabled = bool(val8 & 1)
        elif offset == 1:
            # Квитирование прерывания (ACK): запись 1 очищает IRQ!
            if val8 & 1:
                self.irq_pending = False
                if self.bus is not None:
                    self.bus.pins.IRQ.set(0)
        elif offset == 2:
            self.reload_value = val8
            self.counter = val8
```

---

## Рецепт 3: Аппаратная задержка (Latency) и протокол готовности RF

В реальном кремнии внешняя память (EEPROM, медленные контроллеры, АЦП) не успевают выдать данные за один такт. Симулятор LIM M2 поддерживает точную эмуляцию задержки выборки и аппаратных циклов ожидания (**Wait States**) через ножку `RF` (Ready Flag).

```text
Такты шины:       T1             T2             T3 (Wait)      T4 (Ready)
           ┌──────────────┐┌──────────────┐┌──────────────┐┌──────────────┐
CLK        │              ││              ││              ││              │
           └──────────────┘└──────────────┘└──────────────┘└──────────────┘
RD Strobe  ───────────────────────────────────────────────────────────────
RF (Ready) ───────────────\______________________________/\───────────────
                              [Устройство занято]             [Данные OK]
```

### Как настроить устройство с задержкой:

```python
from devices import BaseDevice

class SlowEEPROMDevice(BaseDevice):
    def __init__(self, start: int = 0x00030000, size: int = 256):
        # Задаем задержку в 3 такта шины
        super().__init__(start=start, size=size, latency=3, ready_pin="RF", name="EEPROM")
        self.storage = bytearray(size)

    def read(self, offset: int) -> int:
        # Этот метод вызовется ровно через 3 такта после того, как ножка RF вернется в 1!
        return self.storage[offset]

    def write(self, offset: int, value: int):
        self.storage[offset] = value & 0xFF
```

### Поведение процессора:
* Если бит `DWR` (Disable Wait Ready, бит 10 `FREG`) равен `0`, процессор при обращении к медленному устройству задерживает такт и ждет поднятия `RF=1`.
* Если программист установил `DWR=1`, процессор игнорирует ножку `RF` и читает шину без ожидания.

---

## Рецепт 4: Низкоуровневый физический контроль шины (on_bus_cycle)

Если вам нужно симулировать поведение реальной микросхемы (например, шинный приемопередатчик, коммутатор, дешифратор адреса или анализатор шины), переопределите метод `on_bus_cycle`:

```python
from devices import BaseDevice

class BusAnalyzerDevice(BaseDevice):
    def __init__(self, name: str = "ANALYZER"):
        super().__init__(start=0x00000000, size=0, name=name)
        self.access_log = []

    def on_bus_cycle(self, bus):
        """Прямой доступ к состоянию ножек и адресной шины."""
        addr = bus.addressbus  # 32-битный адрес на шине
        
        if bus.rd == 1:
            print(f"[ШИНА] Цикл чтения по адресу: 0x{addr:08X}")
        elif bus.wr == 1:
            data = bus.databus  # 8-битные данные, выставленные процессором
            print(f"[ШИНА] Цикл записи: 0x{addr:08X} = 0x{data:02X}")
```

---

## Рецепт 5: Видеоконтроллер и графический дисплей

Симулятор LIM M2 имеет встроенную подсистему высокопроизводительного рендеринга дисплеев как в терминале (TUI), так и в графическом интерфейсе Tkinter (GUI).

### Ключевая концепция: VRAM Dirty Tracking (`_vram_version`)
Чтобы симулятор не тратил 100% CPU на постоянную перерисовку дисплея, базовый класс `BaseDevice` содержит счетчик версии `_vram_version`.
Каждый раз, когда процессор пишет байт в видеопамять, `_vram_version` инкрементируется. Если процессор не пишет в дисплей, проверка пропускает перерисовку всего за **0.008 мс**!

### Создание кастомного видеодисплея (Матрица 32x16 символов):

```python
from devices import BaseDevice

class MiniScreenDevice(BaseDevice):
    def __init__(self, start: int = 0x00080000):
        width = 32
        height = 16
        size = width * height
        super().__init__(
            start=start,
            size=size,
            name="SCREEN",
            is_video=True,
            width=width,
            height=height
        )
        self.vram = bytearray([32] * size)  # Пробелы

    def read(self, offset: int) -> int:
        return self.vram[offset]

    def write(self, offset: int, value: int):
        val8 = value & 0xFF
        if self.vram[offset] != val8:
            self.vram[offset] = val8
            # Сигнализируем GUI и TUI, что видеопамять обновилась:
            self._vram_version += 1

    def render_screen(self) -> str:
        """Отрисовка текстового дисплея для терминального режима (TUI)."""
        lines = []
        lines.append("┌" + "─" * self.width + "┐")
        for y in range(self.height):
            row = self.vram[y * self.width : (y + 1) * self.width]
            row_str = "".join(chr(b) if 32 <= b <= 126 else "." for b in row)
            lines.append(f"│{row_str}│")
        lines.append("└" + "─" * self.width + "┘")
        return "\n".join(lines)
```

---

## Рецепт 6: Контроллер прямого доступа к памяти (DMA)

DMA контроллер позволяет передавать блоки данных из одного диапазона памяти в другой без загрузки регистров процессора:

```python
from devices import BaseDevice

class DMACounterDevice(BaseDevice):
    """
    Регистры (смещение 0x00..0x0A):
      0x00..0x03: Source Address (32 бит, Little-Endian)
      0x04..0x07: Destination Address (32 бит, Little-Endian)
      0x08..0x09: Block Length (16 бит)
      0x0A:       Control (бит 0 = START, бит 1 = BUSY)
    """
    def __init__(self, start: int = 0x00040000):
        super().__init__(start=start, size=16, name="DMA")
        self.regs = bytearray(16)
        self.active = False
        self.src = 0
        self.dst = 0
        self.len = 0

    def read(self, offset: int) -> int:
        return self.regs[offset]

    def write(self, offset: int, value: int):
        self.regs[offset] = value & 0xFF
        if offset == 0x0A and (value & 1):
            # Запуск DMA передачи
            self.src = int.from_bytes(self.regs[0:4], "little")
            self.dst = int.from_bytes(self.regs[4:8], "little")
            self.len = int.from_bytes(self.regs[8:10], "little")
            self.active = True
            self.regs[0x0A] = 0x02  # BUSY = 1

    def on_step(self):
        """Каждый такт DMA пересылает 1 байт напрямую по шине."""
        if not self.active or self.len == 0 or self.bus is None:
            return

        byte_val = self.bus.read8(self.src)
        self.bus.write8(self.dst, byte_val)

        self.src += 1
        self.dst += 1
        self.len -= 1

        if self.len == 0:
            self.active = False
            self.regs[0x0A] = 0x00  # Готово!
            # При необходимости можно выставить прерывание: self.bus.pins.IRQ.set(1)
```

---

## Рецепт 7: Энергонезависимая память (NVM / ROM)

Если ваше устройство должно сохранять свое состояние между перезапусками симулятора:

```python
from devices import BaseDevice

class FlashStorageDevice(BaseDevice):
    def __init__(self, start: int = 0x00050000, size: int = 1024, filename: str = "flash.bin"):
        # Флаг persist=True автоматически сохраняет файл при выходе из симулятора
        super().__init__(start=start, size=size, file=filename, persist=True, name="FLASH")

    def read(self, offset: int) -> int:
        return self._raw[offset]

    def write(self, offset: int, value: int):
        self._raw[offset] = value & 0xFF
```

---

## 10. Сборка системы, карта памяти и запуск

Все устройства объединяются на шине в вашей главной точке входа (например, `main_system.py`):

```python
#!/usr/bin/env python3
from bus import MemoryBus
from devices import RAMDevice, ROMDevice
from cpu import LIM2CPU
from ui import run_sim

# Импортируем наши собственные устройства:
from my_gpio import GPIODevice
from my_timer import HardwareTimerDevice
from my_screen import MiniScreenDevice

def build_system():
    # 1. Создаем физическую шину:
    bus = MemoryBus()

    # 2. Подключаем базовую память:
    # 0x00000000 .. 0x0000FFFF: ROM начальной загрузки (64 КБ)
    bus.attach(ROMDevice(start=0x00000000, size=0x10000, file="firmware.bin", name="BOOT_ROM"))

    # 0x00010000 .. 0x0007FFFF: Оперативная память ОЗУ (448 КБ)
    bus.attach(RAMDevice(start=0x00010000, size=0x70000, name="MAIN_RAM"))

    # 3. Подключаем собственные периферийные модули:
    bus.attach(GPIODevice(start=0x00080000, name="GPIO0"))
    bus.attach(HardwareTimerDevice(start=0x00080100, name="TIMER0"))
    bus.attach(MiniScreenDevice(start=0x00082000))

    # 4. Инициализируем процессор LIM M2:
    cpu = LIM2CPU(bus=bus)
    return cpu

if __name__ == "__main__":
    cpu = build_system()
    # Запуск в графическом интерфейсе GUI (или interactive=True для терминала TUI):
    run_sim(cpu, gui=True)
```

---

## 11. Написание драйвера на ассемблере LIM M2

Напишем программу на ассемблере LIM M2 (`driver.asm`), которая взаимодействует с нашими устройствами:
1. Настраивает аппаратный стек `SP` и вектор прерываний таймера `INT_VEC0`.
2. Конфигурирует `GPIO` на вывод и включает светодиод `0xAA`.
3. Запускает аппаратный таймер на 50 тактов.
4. Выводит символы `'H'`, `'E'`, `'L'`, `'L'`, `'O'` на экран дисплея по базовому указателю `PTREG` с автоинкрементом `AIP`.
5. Ожидает прерывания от таймера.

```assembly
; ==============================================================================
; ДРАЙВЕР УСТРОЙСТВ ДЛЯ ПРОЦЕССОРА LIM M2
; ==============================================================================
.org 0x00000000

Entry:
    ; 1. Инициализация аппаратного стека SP на вершину RAM:
    MSP.ld      $sp, 0x0007FFFC

    ; 2. Регистрация вектора прерывания IR0 (INT_VEC0 = TimerIsr):
    MSP.ld      $ir0, TimerIsr

    ; 3. Конфигурация FREG: AIP=1 (автоинкремент PT), MIE=1 (разрешить прерывания)
    MSP.ld      $freg, 0x1200

    ; 4. Настройка GPIO (базовый адрес 0x00080000):
    ; Направление (DIR, offset 2) = 0xFF (все пины на выход)
    LMR.b       $0, 0xFF
    LRM.b       $0, [0x00080002]

    ; Данные (DATA_OUT, offset 0) = 0xAA (зажечь чередующиеся светодиоды)
    LMR.b       $0, 0xAA
    LRM.b       $0, [0x00080000]

    ; 5. Вывод строки "HELLO" на видеоэкран (адрес 0x00082000):
    ; Загружаем базовый адрес экрана в 32-битный регистр PTREG:
    MSP.ld      $ptreg, 0x00082000

    ; Последовательная потоковая запись (PTREG увеличивается на +1 при каждом шаге):
    LMR.b       $1, 'H'
    LRM.b       $1, [$ptreg]            ; *0x00082000 = 'H', PTREG = 0x00082001
    LMR.b       $1, 'E'
    LRM.b       $1, [$ptreg]            ; *0x00082001 = 'E', PTREG = 0x00082002
    LMR.b       $1, 'L'
    LRM.b       $1, [$ptreg]            ; *0x00082002 = 'L', PTREG = 0x00082003
    LRM.b       $1, [$ptreg]            ; *0x00082003 = 'L', PTREG = 0x00082004
    LMR.b       $1, 'O'
    LRM.b       $1, [$ptreg]            ; *0x00082004 = 'O', PTREG = 0x00082005

    ; 6. Запуск аппаратного таймера (адрес 0x00080100):
    ; Устанавливаем период 50 тактов (offset 2):
    LMR.b       $2, 50
    LRM.b       $2, [0x00080102]
    ; Включаем таймер (offset 0, бит 0 = 1):
    LMR.b       $2, 0x01
    LRM.b       $2, [0x00080100]

MainLoop:
    ; Фоновый рабочий цикл: ожидаем срабатывания аппаратного таймера
    NOP
    JMP         MainLoop

; ==============================================================================
; ОБРАБОТЧИК АППАРАТНОГО ПРЕРЫВАНИЯ ТАЙМЕРА (ISR ДЛЯ INT_VEC0)
; ==============================================================================
TimerIsr:
    PUSH        $0                      ; Сохраняем рабочий регистр в стек
    PUSH        $1

    ; Инвертируем светодиоды на GPIO при каждом тике таймера:
    LMR.b       $0, [0x00080000]
    NOT         $0, $0                  ; $0 = ~$0
    LRM.b       $0, [0x00080000]

    ; Квитируем прерывание (ACK) в контроллере таймера (offset 1, запись 1):
    LMR.b       $1, 0x01
    LRM.b       $1, [0x00080101]

    POP         $1                      ; Восстанавливаем регистры
    POP         $0
    RET                                 ; Возврат в MainLoop (автоматически INTR = 0)
```

### Компиляция и запуск:
```bash
# 1. Компилируем прошивку:
python3 LIM2/compiler/compiler.py driver.asm -o firmware.bin -x firmware.hex -l

# 2. Запускаем нашу систему:
python3 main_system.py
```

Готово! Теперь вы полностью вооружены знаниями для создания абсолютно любого аппаратного контроллера, сенсора, звукового генератора, сетевого адаптера или графической карты под процессор **LIM M2**!
