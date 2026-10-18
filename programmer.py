#!/usr/bin/env python3
# ==============================================================================
# LIM M2 — Автономный программатор образов памяти и дисков (Programmer)
# ==============================================================================
"""
Полностью автономный программатор прошивок (.bin / .hex) в файлы образов
памяти и дисков (ПЗУ / Flash / Hard Drive).

Принцип работы:
  1. Начало образа — всегда 0x0000.
  2. Указывается смещение (откуда начать заливать, по умолчанию 0x0000).
  3. Для нового файла обязательно указывается размер устройства (-s 8K, 0x2000, 8192).
  4. Положение и адреса внутри HEX-файла полностью игнорируются — байты
     считываются подряд и заливаются строго начиная со смещения.
  5. Если код вылазит за пределы размера устройства (offset + len > size),
     программатор выводит ошибку и НЕ выполняет прошивку.

Примеры использования:
  # Залить в начало образа drive.bin размером 8 КБ:
  python3 programmer.py firmware.bin drive.bin 0x0000 8K

  # Залить с флагами -o (откуда начать) и -s (размер):
  python3 programmer.py firmware.hex drive.bin -o 0x0100 -s 0x2000

  # Залить в уже существующий образ диска:
  python3 programmer.py firmware.bin drive.bin
"""

import os
import sys
import argparse
import re
from typing import Tuple, Optional


def load_firmware_bytes(path: str) -> bytearray:
    """
    Загружает байты прошивки из файла .bin или .hex.
    Полностью игнорирует адреса и смещения внутри .hex — считывает чистые данные подряд.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Файл прошивки '{path}' не найден.")

    is_hex = path.lower().endswith(".hex")
    if not is_hex:
        with open(path, "rb") as f:
            head = f.read(128)
            if all(b < 128 for b in head) and any(b in b":0123456789abcdefABCDEF" for b in head):
                try:
                    head_str = head.decode("ascii")
                    if any(line.strip().startswith(":") or ":" in line for line in head_str.splitlines()):
                        is_hex = True
                except Exception:
                    pass

    if is_hex:
        raw_bytes = bytearray()
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith(";") or line.startswith("#"):
                    continue
                # Intel HEX: :count:addr:rtype:data...
                # Игнорируем адрес (байты 3..7), берем ТОЛЬКО данные payload (rtype == 0x00)
                if line.startswith(":"):
                    try:
                        count = int(line[1:3], 16)
                        rtype = int(line[7:9], 16)
                        data_hex = line[9:9 + count * 2]
                        if rtype == 0x00:
                            for i in range(count):
                                raw_bytes.append(int(data_hex[i * 2:(i + 1) * 2], 16))
                        elif rtype == 0x01:  # Конец файла Intel HEX
                            break
                    except Exception:
                        pass
                    continue

                # Текстовый дамп hex (например "0x2000: 12 34 56" или "2000: 12 34")
                # Игнорируем адрес до двоеточия, считываем только байты данных подряд:
                if ":" in line:
                    line = line.split(":", 1)[1]
                for tok in line.split():
                    clean = tok.strip().lower()
                    if clean.startswith("0x"):
                        clean = clean[2:]
                    if re.match(r'^[0-9a-f]{1,2}$', clean):
                        raw_bytes.append(int(clean, 16))
        return raw_bytes
    else:
        with open(path, "rb") as f:
            return bytearray(f.read())


def parse_size_str(val: str) -> int:
    """Парсит строковый размер устройства: '8K', '16KB', '1M', '0x2000', '8192'."""
    val = val.strip()
    m = re.match(r'^(\d+)\s*([kKmMgG]?)(?:[bB])?$', val)
    if m:
        num = int(m.group(1))
        unit = m.group(2).upper()
        if unit == 'K':
            return num * 1024
        elif unit == 'M':
            return num * 1024 * 1024
        elif unit == 'G':
            return num * 1024 * 1024 * 1024
        return num
    return int(val, 0)


def program_image(
    firmware_path: str,
    image_path: str,
    offset: int = 0x0000,
    size: Optional[int] = None,
    fill_byte: int = 0x00
) -> Tuple[int, int, int]:
    """
    Записывает прошивку firmware_path в образ image_path со смещением offset.

    - Начало образа всегда 0x0000.
    - offset: откуда начать заливать данные (по умолчанию 0x0000).
    - size: размер устройства (обязателен для нового файла).
    - Адреса внутри HEX-файла полностью игнорируются, байты пишутся подряд с offset.
    - Если код вылазит за пределы size (offset + len > size), выдается ошибка и прошивка НЕ выполняется.

    Возвращает: (размер_прошивки, смещение, итоговый_размер_образа).
    """
    fw_bytes = load_firmware_bytes(firmware_path)
    fw_len = len(fw_bytes)
    if fw_len == 0:
        raise ValueError(f"Файл прошивки '{firmware_path}' пуст. Прошивка отменена.")

    file_exists = os.path.exists(image_path) and os.path.getsize(image_path) > 0

    # 1. Если файл новый — размер устройства обязателен!
    if not file_exists and size is None:
        raise ValueError(
            f"Файл нового образа '{image_path}' еще не существует на диске.\n"
            f"Для создания нового файла необходимо указать размер устройства:\n"
            f"  - Через флаг: -s 8K (или -s 0x2000)\n"
            f"  - Либо позиционно: python3 programmer.py {os.path.basename(firmware_path)} {os.path.basename(image_path)} 0x0000 8K\n"
            f"Прошивка не выполнена."
        )

    offset = max(0, offset)

    # Если образ уже существует и размер не передан явно — берем размер существующего файла
    if file_exists and size is None:
        size = os.path.getsize(image_path)

    # 2. Проверка выхода за пределы устройства:
    required_len = offset + fw_len
    if size is not None and required_len > size:
        overflow_bytes = required_len - size
        raise ValueError(
            f"КОД ВЫЛАЗИТ ЗА ПРЕДЕЛЫ УСТРОЙСТВА!\n"
            f"  Размер устройства   : {size} байт (0x{size:04X})\n"
            f"  Смещение записи     : 0x{offset:04X}\n"
            f"  Размер прошивки     : {fw_len} байт (0x{fw_len:04X})\n"
            f"  Требуемый размер    : {required_len} байт (0x{required_len:04X})\n"
            f"  Переполнение на     : {overflow_bytes} байт (0x{overflow_bytes:04X})\n"
            f"Прошивка НЕ выполнена, образ остался без изменений!"
        )

    # 3. Загружаем существующий образ или создаем новый буфер ровно под размер устройства
    if file_exists:
        with open(image_path, "rb") as f:
            img = bytearray(f.read())
    else:
        img = bytearray([fill_byte & 0xFF] * size)

    # Если существующий файл меньше заданного размера устройства — расширяем до size
    if size is not None and len(img) < size:
        img.extend([fill_byte & 0xFF] * (size - len(img)))

    # 4. Записываем байты прошивки подряд, начиная с offset
    img[offset:offset + fw_len] = fw_bytes

    # 5. Сохраняем на диск
    dirname = os.path.dirname(os.path.abspath(image_path))
    if dirname and not os.path.exists(dirname):
        os.makedirs(dirname, exist_ok=True)

    with open(image_path, "wb") as f:
        f.write(img)

    return fw_len, offset, len(img)


def main():
    parser = argparse.ArgumentParser(
        prog="python3 programmer.py",
        description="Автономный программатор образов памяти (LIM M2 Flash Tool)"
    )
    parser.add_argument("firmware", help="Файл прошивки (.bin или .hex)")
    parser.add_argument("image", help="Целевой файл образа (например: drive.bin)")
    parser.add_argument(
        "pos_offset",
        nargs="?",
        default=None,
        help="Смещение записи (откуда начать, по умолчанию 0x0000)"
    )
    parser.add_argument(
        "pos_size",
        nargs="?",
        default=None,
        help="Размер устройства (например: 8K, 16KB, 0x2000, 8192)"
    )
    parser.add_argument(
        "-o", "--offset",
        type=lambda x: int(x, 0),
        default=None,
        help="Смещение записи в образе (откуда начать, по умолчанию 0x0000)"
    )
    parser.add_argument(
        "-s", "--size",
        type=str,
        default=None,
        help="Размер устройства (например: 8K, 16KB, 0x2000, 8192)"
    )
    parser.add_argument(
        "-f", "--fill",
        type=lambda x: int(x, 0),
        default=0x00,
        help="Байт заполнения пустого пространства (по умолчанию 0x00)"
    )

    args = parser.parse_args()

    offset = args.offset if args.offset is not None else 0x0000
    if args.pos_offset is not None:
        try:
            offset = int(args.pos_offset, 0)
        except ValueError:
            # Если пользователь передал размер вторым аргументом вместо смещения (например 8K)
            if args.pos_size is None:
                args.pos_size = args.pos_offset

    size = None
    if args.size:
        size = parse_size_str(args.size)
    elif args.pos_size:
        size = parse_size_str(args.pos_size)

    try:
        fw_len, off, total_size = program_image(
            firmware_path=args.firmware,
            image_path=args.image,
            offset=offset,
            size=size,
            fill_byte=args.fill
        )

        end_addr = off + fw_len - 1
        print("┌────────────────────────────────────────────────────────────────────────┐")
        print("│            ПРОГРАММАТОР ОБРАЗОВ ПАМЯТИ (LIM M2 FLASH TOOL)             │")
        print("├────────────────────────────────────────────────────────────────────────┤")
        print(f"│  Входная прошивка  : {os.path.basename(args.firmware):<48} │")
        print(f"│  Размер прошивки   : {fw_len:<10} байт (0x{fw_len:04X})                        │")
        print(f"│  Целевой образ     : {os.path.basename(args.image):<48} │")
        print(f"│  Смещение (откуда) : 0x{off:04X} (с {off}-го байта образа)                       │")
        print(f"│  Диапазон записи   : 0x{off:04X} .. 0x{end_addr:04X} ({fw_len} байт)                     │")
        print(f"│  Размер устройства : {total_size:<10} байт (0x{total_size:04X})                       │")
        print("├────────────────────────────────────────────────────────────────────────┤")
        print("│  СТАТУС            : \033[1;32mУСПЕШНО ПРОШИТО В ОБРАЗ\033[0m                           │")
        print("└────────────────────────────────────────────────────────────────────────┘")

    except Exception as e:
        print(f"\033[1;31m[ОШИБКА ПРОГРАММАТОРА]\033[0m {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
