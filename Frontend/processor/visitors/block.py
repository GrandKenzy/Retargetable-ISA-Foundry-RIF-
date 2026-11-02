"""Normalize and dispatch generic ``@block`` declarations."""

from __future__ import annotations

import json
from typing import Any

from Frontend import globals
from Frontend.session import CompilationSession

from .config import visit as visit_config
from .linker import visit as visit_linker


_VALUE_KINDS = {"KEYWORD", "IDENT", "NUMBER", "DECIMAL", "STRING", "BOOL"}


def _kind(token: Any) -> str:
    return getattr(getattr(token, "token", None), "name", "")


def _value(token: Any) -> Any:
    return getattr(token, "value", None)


def _render_value(token: Any) -> str:
    kind = _kind(token)
    value = _value(token)
    if kind == "STRING":
        return json.dumps(value, ensure_ascii=False)
    if kind == "BOOL":
        return "true" if value else "false"
    return str(value)


def _entries(node: Any) -> tuple[globals.BlockEntryData, ...]:
    result: list[globals.BlockEntryData] = []
    for line in tuple(getattr(node, "lines", ()) or ()):
        tokens = list(line)
        if tokens and _kind(tokens[-1]) == "NEWLINE":
            tokens.pop()
        if not tokens:
            continue
        if _kind(tokens[0]) not in {"IDENT", "KEYWORD"}:
            raise RuntimeError(
                "Un bloque genérico requiere un nombre de entrada sin prefijo."
            )
        if len(tokens) > 3:
            raise RuntimeError(
                "Un bloque genérico acepta un nombre y como máximo dos valores por línea."
            )
        values: list[globals.BlockValueData] = []
        for token in tokens[1:]:
            kind = _kind(token)
            if kind not in _VALUE_KINDS:
                raise RuntimeError(
                    f"El valor de '{_value(tokens[0])}' no es válido en un bloque genérico."
                )
            values.append(
                globals.BlockValueData(kind, _value(token), _render_value(token))
            )
        result.append(globals.BlockEntryData(str(_value(tokens[0])), tuple(values)))
    return tuple(result)


def visit(
    node: Any,
    source_path: str | None = None,
    *,
    session: CompilationSession,
) -> None:
    """Validate, preserve, and dispatch one generic block."""

    block_name = str(getattr(node, "block_name", "")).lower()
    if not block_name:
        raise RuntimeError("Un bloque genérico requiere un nombre.")
    entries = _entries(node)
    block = globals.BlockData(block_name, entries, source_path)
    session.blocks.setdefault(block_name, []).append(block)
    if block_name == "config":
        visit_config(block, session)
    elif block_name == "linker":
        visit_linker(block, session)


__all__ = ["visit"]
