#!/usr/bin/env python3
# ==============================================================================
# LIM2 / sim / limasm.py — Прокси для обратной совместимости
# ==============================================================================
# Основной компилятор ассемблера вынесен в отдельную папку:
#     LIM2/compiler/limasm.py (и удобный алиас LIM2/compiler/compiler.py)
# ==============================================================================
import sys
from pathlib import Path

_COMPILER_DIR = Path(__file__).resolve().parent.parent / "compiler"
if str(_COMPILER_DIR) not in sys.path:
    sys.path.insert(0, str(_COMPILER_DIR))

import importlib.util
_backend_path = _COMPILER_DIR / "limasm.py"
_spec = importlib.util.spec_from_file_location("lim_compiler_backend", _backend_path)
_backend = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_backend)

LimAssembler = _backend.LimAssembler
AssemblerError = _backend.AssemblerError
disassemble_one = _backend.disassemble_one
OPCODES = _backend.OPCODES
GPR_MAP = _backend.GPR_MAP
SPEC_REG_MAP = _backend.SPEC_REG_MAP
MSP_LOGIC_OPS = _backend.MSP_LOGIC_OPS
MSP_ARITH_OPS = _backend.MSP_ARITH_OPS
main = _backend.main

__all__ = [
    "LimAssembler",
    "AssemblerError",
    "disassemble_one",
    "OPCODES",
    "GPR_MAP",
    "SPEC_REG_MAP",
    "MSP_LOGIC_OPS",
    "MSP_ARITH_OPS",
    "main",
]

if __name__ == "__main__":
    sys.exit(main())
