"""Verifica left <= right."""

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
    if len(pack) != 2 or not all(pack):
        return Err("lte espera dos valores")
    return Expr(["lte", pack[0], pack[1]])


def _start():
    return main()
