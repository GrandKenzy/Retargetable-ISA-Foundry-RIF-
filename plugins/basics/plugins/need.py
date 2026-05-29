"""Define una necesidad especificada."""

from __future__ import annotations

import re
from typing import Any

from rif import TYPES_MAP, Line, Err, Expr, Operator, RuleIndicator

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_:-]*$")
_BUILTIN_TYPES: dict[str, Any] = {
    # SYMBOL es un tipo base del compilador: representa un objeto direccionable
    # que podrá resolverse más adelante con NAME/addrs/bits.
    "SYMBOL": "SYMBOL",
    "LABEL": "LABEL",
    "VALUE": "VALUE",
    "TYPE": "TYPE",
    "STACK": "STACK",
    "HEAP": "HEAP",
    "MEMORY": "MEMORY",
}
_DERIVED_TYPES: dict[str, tuple[str, Any]] = {
    # SREG existe cuando hay registros: representa subregistros generados o
    # declarados desde .regs.
    "SREG": ("REG", ".regs.subs"),
}


def _clean(value: Any) -> str:
    if hasattr(value, "value"):
        value = value.value
    return str(value).strip()


def _sanitize_pack(pack: list[Any]) -> list[str] | Err:
    cleaned = [_clean(item) for item in pack]

    if not cleaned:
        return Err("Se esperaba al menos un tipo, literal u operador")

    for index, item in enumerate(cleaned):
        if item:
            continue
        if index == 0:
            return Err("need no puede iniciar con una coma")
        if index == len(cleaned) - 1:
            return Err("need no puede terminar con una coma")
        return Err("No puede haber dos comas seguidas")

    return cleaned


def _resolve_type(name: str) -> Any | None:
    if name in TYPES_MAP:
        return TYPES_MAP[name]

    if name in _BUILTIN_TYPES:
        return _BUILTIN_TYPES[name]

    derived = _DERIVED_TYPES.get(name)
    if derived is not None:
        dependency, node = derived
        if dependency in TYPES_MAP or node in TYPES_MAP.values():
            return node

    return None


def _is_identifier(name: str) -> bool:
    return bool(_IDENTIFIER_RE.match(name))


def main():
    if Line.elements <= 1:
        return Err("Se esperaba al menos un tipo, literal u operador")

    Line.Advance()  # consumir "need"

    # Caso literal especial: need ",". Al llegar aquí el parser ya perdió la
    # información de que venía de un STRING, así que una sola coma debe tratarse
    # como literal y no como separador de tipos.
    if len(Line.toks) == 1 and _clean(Line.toks[0]) == ",":
        Line.Advance()
        Line.expects(" ", "\n")
        return Expr(["need_literal", ","])

    sanitized = _sanitize_pack(Line.Unpack(","))
    if isinstance(sanitized, Err):
        return sanitized

    # Caso: need "="
    if len(sanitized) == 1:
        item = sanitized[0]
        resolved = _resolve_type(item)
        if resolved is not None:
            return Err("Se esperaba un operador al final")
        Line.expects(" ", "\n")
        return Expr(["need_literal", item])

    valids: list[Any] = []
    seen_types: set[str] = set()
    target: str | None = None

    for index, item in enumerate(sanitized):
        is_last = index == len(sanitized) - 1
        resolved = _resolve_type(item)

        if resolved is not None:
            if item in seen_types:
                return Err(f'Has escrito el mismo tipo dos veces: "{item}"')
            if target is not None:
                return Err("No puede haber tipos después del operador")
            seen_types.add(item)
            valids.append(resolved)
            continue

        if not is_last:
            return Err(f'Tipo desconocido "{item}". El operador debe ir al final')

        if not _is_identifier(item):
            return Err(f'Operador inválido "{item}". Debe ser un identificador')

        target = item

    Line.expects(" ", "\n")

    if not valids:
        return Err("Se esperaba al menos un tipo antes del operador")

    if target is None:
        return Err("Se esperaba un operador al final")

    Operator.Save(target, RuleIndicator.current, valid_types=valids)

    return Expr(["need", valids, target])


def _start():
    return main()
