#!/usr/bin/env python3
# ==============================================================================
# LIM2 / sim / exampcpu.py — Канонический алиас архитектуры LIM M2 (LIM2.py)
# ==============================================================================
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from LIM2 import *
