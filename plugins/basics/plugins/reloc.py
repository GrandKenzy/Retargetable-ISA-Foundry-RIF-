"""Reserva un campo relocatable generico.

Sintaxis:
    reloc kind, target, width
    reloc kind, target, width, addend
"""

from __future__ import annotations

from typing import Any

from rif import Err, Expr, Line


def _clean(value: Any) -> str:
    if hasattr(value, "value"):
        value = value.value
    return str(value).strip()


def main():
    Line.Advance()
    pack = [_clean(item) for item in Line.Unpack(",")]
    if len(pack) not in (3, 4) or not all(pack):
        return Err("reloc espera tipo, destino, ancho y addend opcional")
    addend = pack[3] if len(pack) == 4 else 0
    return Expr(["reloc", pack[0], pack[1], pack[2], addend])


def _start():
    return main()
