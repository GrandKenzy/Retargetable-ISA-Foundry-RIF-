"""Pure arithmetic used by native RIF artifact expressions.

The public contract deliberately uses primitive values so the same operation
can be mirrored by the future C backend without exposing Python runtime state.
"""

from __future__ import annotations

INT64_MIN = -(1 << 63)
INT64_MAX = (1 << 63) - 1
MAX_WIDTH = (1 << 32) - 1


class CalcError(ValueError):
    """A native ``calc`` operation cannot be evaluated safely."""


def calc(
    operator: str,
    left_value: int,
    left_width: int,
    right_value: int,
    right_width: int,
) -> tuple[int, int]:
    """Apply one supported arithmetic operation and return ``(value, width)``.

    RIF artifact expressions currently define only addition and subtraction.
    Width follows the existing MIR rule: the result uses the widest operand.
    """

    if operator not in {"+", "-"}:
        raise CalcError(f"Operador calc no soportado: {operator!r}.")
    if (
        isinstance(left_value, bool)
        or isinstance(right_value, bool)
        or not isinstance(left_value, int)
        or not isinstance(right_value, int)
    ):
        raise CalcError("calc requiere valores enteros.")
    if (
        isinstance(left_width, bool)
        or isinstance(right_width, bool)
        or not isinstance(left_width, int)
        or not isinstance(right_width, int)
        or left_width <= 0
        or right_width <= 0
        or left_width > MAX_WIDTH
        or right_width > MAX_WIDTH
    ):
        raise CalcError("calc requiere anchos enteros positivos.")

    value = left_value + right_value if operator == "+" else left_value - right_value
    if value < INT64_MIN or value > INT64_MAX:
        raise CalcError("El resultado de calc excede el rango signed int64.")
    return value, max(left_width, right_width)


__all__ = [
    "CalcError",
    "INT64_MIN",
    "INT64_MAX",
    "MAX_WIDTH",
    "calc",
]
