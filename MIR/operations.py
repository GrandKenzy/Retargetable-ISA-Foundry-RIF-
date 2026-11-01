"""Versioned primitive operation ABI shared by Rules and a future C runtime.

This is intentionally narrower than an assembler API.  It exposes only
target-neutral arithmetic/bit/relocation primitives; the Rule compiler still
decides which operation appears in a target's declarative program.  No Python
callback is serialized into a ``.pack`` or accepted by the AOT path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from rif_limits import resolve_limits


RULE_OPERATION_ABI_VERSION = "1.0"
MAX_OPERATION_WIDTH = 64 << 20


class OperationError(ValueError):
    """A primitive Rule operation received invalid values."""


@dataclass(frozen=True)
class OperationSpec:
    name: str
    arity: int
    result: str
    c_symbol: str
    deterministic: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "arity": self.arity,
            "result": self.result,
            "c_symbol": self.c_symbol,
            "deterministic": self.deterministic,
        }


def _width(width: int) -> int:
    if isinstance(width, bool) or not isinstance(width, int) or width <= 0:
        raise OperationError("El ancho de una operación debe ser un entero positivo.")
    if width > resolve_limits().cap(MAX_OPERATION_WIDTH):
        raise OperationError("El ancho de una operación excede el límite configurado.")
    return width


def _integer(value: int, name: str = "valor") -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise OperationError(f"{name} debe ser un entero.")
    return value


def _fit_unsigned(value: int, width: int, truncate: bool) -> int:
    value = _integer(value)
    width = _width(width)
    if not isinstance(truncate, bool):
        raise OperationError("truncate debe ser booleano.")
    limit = 1 << width
    if not truncate and not 0 <= value < limit:
        raise OperationError(f"El inmediato {value} no cabe en {width} bits.")
    return value & (limit - 1)


def _fit_signed(value: int, width: int, truncate: bool) -> int:
    value = _integer(value)
    width = _width(width)
    if not isinstance(truncate, bool):
        raise OperationError("truncate debe ser booleano.")
    limit = 1 << (width - 1)
    if not truncate and not -limit <= value < limit:
        raise OperationError(f"El inmediato signed {value} no cabe en {width} bits.")
    return value & ((1 << width) - 1)


def _encode_relocation(value: int, width: int, mode: str) -> int:
    value = _integer(value)
    width = _width(width)
    mode = str(mode).casefold()
    if mode in {"relative", "pcrel", "pc"}:
        limit = 1 << (width - 1)
        if not -limit <= value < limit:
            raise OperationError(f"El desplazamiento {value} no cabe en pc{width}.")
        return value & ((1 << width) - 1)
    if mode not in {"absolute", "abs"}:
        raise OperationError(f"Modo de relocación desconocido: {mode!r}.")
    if not 0 <= value < (1 << width):
        raise OperationError(f"La dirección {value} no cabe en abs{width}.")
    return value


_OPERATIONS: dict[str, tuple[OperationSpec, Callable[..., Any]]] = {
    "fit_unsigned": (
        OperationSpec("fit_unsigned", 3, "uinteger", "rif_op_fit_unsigned"),
        _fit_unsigned,
    ),
    "fit_signed": (
        OperationSpec("fit_signed", 3, "uinteger", "rif_op_fit_signed"),
        _fit_signed,
    ),
    "encode_relocation": (
        OperationSpec("encode_relocation", 3, "uinteger", "rif_op_encode_relocation"),
        _encode_relocation,
    ),
}


def execute_operation(name: str, *args: Any) -> Any:
    """Execute one closed primitive from the Rule operation table."""

    try:
        spec, function = _OPERATIONS[name]
    except KeyError as exc:
        raise OperationError(f"Operación Rule desconocida: {name!r}.") from exc
    if len(args) != spec.arity:
        raise OperationError(
            f"La operación {name} requiere {spec.arity} argumentos; recibió {len(args)}."
        )
    return function(*args)


def operation_specs() -> tuple[OperationSpec, ...]:
    """Return the stable operation descriptors consumed by AOT/C tooling."""

    return tuple(_OPERATIONS[name][0] for name in sorted(_OPERATIONS))


def operation_abi() -> dict[str, Any]:
    return {
        "format": "RIF_RULE_OPERATION_ABI",
        "version": RULE_OPERATION_ABI_VERSION,
        "operations": [spec.as_dict() for spec in operation_specs()],
    }


def operation_abi_json() -> bytes:
    return json.dumps(operation_abi(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def operation_c_header() -> str:
    """Return the small C header that mirrors the closed primitive table."""

    return """#ifndef RIF_RULE_OPERATION_ABI_H
#define RIF_RULE_OPERATION_ABI_H

#include <stdint.h>

#define RIF_RULE_OPERATION_ABI_VERSION \"1.0\"

/* Return 0 on success and a non-zero validation error otherwise. */
int rif_op_fit_unsigned(uint64_t value, uint32_t width, uint8_t truncate, uint64_t *out);
int rif_op_fit_signed(int64_t value, uint32_t width, uint8_t truncate, uint64_t *out);
int rif_op_encode_relocation(int64_t value, uint32_t width, uint8_t relative, uint64_t *out);

#endif
"""


def operation_c_source() -> str:
    """Return the portable C implementation for the scalar operation ABI.

    Python remains the reference for arbitrarily wide dynamic fields. This C
    surface is deliberately scalar and returns an error for widths above 64;
    a future byte-span ABI can be added with a new version.
    """

    return r'''#include "rif_rule_operation_abi.h"

static int rif_valid_width(uint32_t width) {
    return width > 0 && width <= 64;
}

int rif_op_fit_unsigned(uint64_t value, uint32_t width, uint8_t truncate, uint64_t *out) {
    uint64_t mask;
    if (!out || !rif_valid_width(width)) return -1;
    mask = width == 64 ? UINT64_MAX : ((UINT64_C(1) << width) - UINT64_C(1));
    if (!truncate && value > mask) return -2;
    *out = value & mask;
    return 0;
}

int rif_op_fit_signed(int64_t value, uint32_t width, uint8_t truncate, uint64_t *out) {
    int64_t minimum;
    int64_t maximum;
    uint64_t mask;
    if (!out || !rif_valid_width(width)) return -1;
    if (width == 64) {
        minimum = INT64_MIN;
        maximum = INT64_MAX;
        mask = UINT64_MAX;
    } else {
        minimum = -(INT64_C(1) << (width - 1));
        maximum = (INT64_C(1) << (width - 1)) - INT64_C(1);
        mask = (UINT64_C(1) << width) - UINT64_C(1);
    }
    if (!truncate && (value < minimum || value > maximum)) return -2;
    *out = ((uint64_t)value) & mask;
    return 0;
}

int rif_op_encode_relocation(int64_t value, uint32_t width, uint8_t relative, uint64_t *out) {
    if (!out || !rif_valid_width(width)) return -1;
    if (relative) return rif_op_fit_signed(value, width, 0, out);
    if (value < 0) return -2;
    return rif_op_fit_unsigned((uint64_t)value, width, 0, out);
}
'''


__all__ = [
    "MAX_OPERATION_WIDTH",
    "OperationError",
    "OperationSpec",
    "RULE_OPERATION_ABI_VERSION",
    "execute_operation",
    "operation_abi",
    "operation_abi_json",
    "operation_c_header",
    "operation_c_source",
    "operation_specs",
]
