#!/usr/bin/env python3
# ==============================================================================
# LIM2 / compiler / compiler.py — Точка входа в компилятор ассемблера LIM M2
# ==============================================================================
import sys
from pathlib import Path

# Добавляем директорию этого скрипта в sys.path
_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from limasm import main

if __name__ == "__main__":
    sys.exit(main())
