"""Emite padding derecho automatico de n bytes."""

from __future__ import annotations

from rif import Err, Expr, Line


def main():
    if Line.elements < 2:
        return Err("pad espera un numero")

    Line.Advance()
    value = " ".join(str(item).strip() for item in Line.toks).strip()
    Line.toks.clear()
    Line.expects(" ", "\n")

    if not value:
        return Err("pad espera un numero")

    return Expr(["pad", value])


def _start():
    return main()
