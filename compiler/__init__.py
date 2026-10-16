#!/usr/bin/env python3
# ==============================================================================
# LIM2 / compiler / __init__.py — Пакет компилятора ассемблера LIM M2
# ==============================================================================
from .limasm import (
    LimAssembler,
    AssemblerError,
    disassemble_one,
    OPCODES,
    GPR_MAP,
    SPEC_REG_MAP,
)

__all__ = [
    "LimAssembler",
    "AssemblerError",
    "disassemble_one",
    "OPCODES",
    "GPR_MAP",
    "SPEC_REG_MAP",
]
