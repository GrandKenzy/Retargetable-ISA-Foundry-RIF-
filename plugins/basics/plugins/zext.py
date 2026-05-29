"""Zero-extend de un valor a n bits."""

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
        return Err("zext espera valor, tamano o destino, valor, tamano")

    target = None
    if len(pack) == 3:
        target, value, width_text = pack
    else:
        value, width_text = pack

    return Expr(["zext", target, value, width_text])


def _start():
    return main()
