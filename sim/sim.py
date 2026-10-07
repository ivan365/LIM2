#!/usr/bin/env python3
# ==============================================================================
# LIM2 / sim / sim.py — Главная точка запуска симулятора архитектуры LIM M2
# ==============================================================================
"""
Вся конфигурация материнской платы, устройств и карты памяти задается ПРЯМО В КОДЕ!
Вам больше НЕ нужно вводить длинные флаги командной строки (-m, -v) каждый раз.

Просто запустите:
    python3 sim.py demo.hex -i
"""

import sys
from pathlib import Path

# Автоматически настраиваем sys.path, чтобы запуск работал из любой директории
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from bus import MemoryBus
from core import BaseCPU
from exampcpu import create_lim2_cpu
from runner import run_cli
from devices import (
    BaseDevice,
    RAMDevice,
    ROMDevice,
    TextScreenDevice,
    UARTDevice,
    TimerDevice,
    CustomDevice
)


# ==============================================================================
# КОНФИГУРАЦИЯ ПЛАТФОРМЫ И РАСПРЕДЕЛЕНИЕ ПАМЯТИ В КОДЕ
# ==============================================================================
def setup_platform(bus: MemoryBus):
    """
    Здесь вы можете свободно создавать, настраивать адреса и логику любых устройств.
    Они автоматически подключаются к шине и отображаются в TUI-интерфейсе.
    """
    # 1. Системное ОЗУ (0x0000 .. 0x3FFF = 16 КБ)
    bus.attach(RAMDevice(start=0x0000, end=0x3FFF, name="RAM"))

    # 2. Текстовый видеомонитор 20x4 (0x8000 .. 0x804F)
    #    При записи байта в этот диапазон процессор напрямую выводит символ на экран
    bus.attach(TextScreenDevice(start=0x8000, width=20, height=4, name="MONITOR"))

    # 3. Последовательный порт UART (0xF000 .. 0xF003)
    #    Регистры: 0=DATA, 1=STATUS (TX/RX ready), 2=CONTROL
    bus.attach(UARTDevice(start=0xF000, name="UART0"))

    # 4. Аппаратный таймер (0xF010 .. 0xF013)
    #    Считает такты и выставляет логическую 1 на ножке bus.pins.IRQ
    bus.attach(TimerDevice(start=0xF010, name="TIMER0", irq_pin="IRQ"))

    # --------------------------------------------------------------------------
    # ПРИМЕР: Создание собственного устройства в 10 строк прямо здесь:
    # --------------------------------------------------------------------------
    # class SoundBuzzer(BaseDevice):
    #     def write(self, offset: int, value: int):
    #         print(f"[BUZZER] Частота звука установлена в {value} Гц")
    # bus.attach(SoundBuzzer(start=0xF020, size=4, name="BUZZER"))


def main():
    """Запуск симулятора через CLI."""
    run_cli(create_lim2_cpu, configure_platform=setup_platform)


if __name__ == "__main__":
    main()
