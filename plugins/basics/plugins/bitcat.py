"""Concatena varios valores de bits.

Formas:

    bitcat A, B
    bitcat OUT, A, B

Con destino, OUT queda disponible como valor temporal para `emit OUT` dentro
de la misma ejecucion de regla.
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

    if len(pack) < 2 or not all(pack):
        return Err("bitcat espera al menos dos valores")

    target = None
    args = pack
    if len(pack) >= 3:
        target = pack[0]
        args = pack[1:]

    return Expr(["bitcat", target, *args])


def _start():
    return main()
