"""Calcula distancia relativa entre dos puntos de memoria."""

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

    if len(pack) not in (2, 3) or not all(pack):
        return Err("reldis espera origen, destino y tamano opcional")

    width = pack[2] if len(pack) == 3 else None
    return Expr(["reldis", pack[0], pack[1], width])


def _start():
    return main()
