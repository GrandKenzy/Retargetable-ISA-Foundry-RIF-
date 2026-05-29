"""Evita movimientos entre operandos con tamaños incompatibles."""

from __future__ import annotations

from rif import Line, Err, Expr, Operators, RuleIndicator


def _clean(value: str):
    if hasattr(value, "value"):
        value = value.value
    return str(value).strip()


def resolve(op: str):
    return Operators.Load(op, RuleIndicator.current)


def main():
    Line.Advance()  # consumir "fits"
    pack = [_clean(item) for item in Line.Unpack(",")]

    if len(pack) != 2 or not all(pack):
        return Err("Se esperaban solamente dos elementos")

    op1_name, op2_name = pack
    op1, op2 = resolve(op1_name), resolve(op2_name)

    bits1 = op1.type.get("bits")
    bits2 = op2.type.get("bits")

    # Si una parte es una captura de regla, la comparación se deja como
    # restricción para la fase que resuelva operandos reales.
    if bits1 is None or bits2 is None:
        return Expr(["fits", op1_name, op2_name])

    if bits1 != bits2:
        return Err("El operador origen no cabe en el operador destino")

    return 0


def _start():
    return main()
