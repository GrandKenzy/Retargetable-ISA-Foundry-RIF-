"""Compara que dos valores tengan exactamente los mismos bits.

Sintaxis:

    eq op1, op2
    eq op1.binary, op2.binary
    eq VAR4_A, VAR4_B

La comparación real se hace en codegen. Si alguna parte no está resuelta,
queda como placeholder semántico.
"""

from __future__ import annotations

from typing import Any

from rif import Err, Expr, Line


def _clean(value: Any) -> str:
    if hasattr(value, "value"):
        value = value.value
    return str(value).strip()


def main():
    Line.Advance()  # consumir "eq"
    pack = [_clean(item) for item in Line.Unpack(",")]

    if len(pack) != 2 or not all(pack):
        return Err("eq espera dos valores")

    return Expr(["eq", pack[0], pack[1]])


def _start():
    return main()
