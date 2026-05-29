"""Emite padding automatico hasta alinear a n bytes."""

from __future__ import annotations

from rif import Err, Expr, Line


def main():
    if Line.elements < 2:
        return Err("align espera un numero")

    Line.Advance()
    value = " ".join(str(item).strip() for item in Line.toks).strip()
    Line.toks.clear()
    Line.expects(" ", "\n")

    if not value:
        return Err("align espera un numero")

    return Expr(["align", value])


def _start():
    return main()
