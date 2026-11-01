from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from Frontend import globals


_VALUE_KINDS = {"NUMBER", "DECIMAL", "IDENT", "STRING", "BOOL"}


def _children(node: Any) -> tuple[Any, ...]:
    if isinstance(node, (list, tuple)):
        return tuple(node)
    return tuple(getattr(node, "nodes", ()) or ())


def _walk(node: Any) -> Iterator[Any]:
    yield node
    for child in _children(node):
        yield from _walk(child)


def _named(node: Any, name: str) -> Iterator[Any]:
    for current in _walk(node):
        if getattr(current, "name", None) == name:
            yield current


def _token_kind(node: Any) -> str | None:
    token = getattr(node, "token", None)
    return getattr(getattr(token, "token", None), "name", None)


def _token_value(node: Any) -> Any:
    token = getattr(node, "token", None)
    return getattr(token, "value", None)


def _table_name(node: Any) -> str:
    # TABLE: AT, keyword, IDENT, NEWLINE, COLUMNS, AT, keyword.
    children = _children(node)
    if len(children) < 3:
        raise RuntimeError("La declaración @table está incompleta.")

    name = _token_value(children[2])
    if not isinstance(name, str) or not name:
        raise RuntimeError("El nombre de @table no es válido.")
    return name


def _headers(header: Any) -> tuple[str, ...]:
    names = tuple(
        value
        for current in _walk(header)
        if _token_kind(current) in {"IDENT", "KEYWORD"}
        for value in (_token_value(current),)
    )
    if not names:
        raise RuntimeError("La tabla debe declarar al menos una columna.")
    if len(set(names)) != len(names):
        raise RuntimeError("Una tabla no puede repetir nombres de columna.")
    return names


def _cell_value(cell: Any) -> Any:
    value_refs = tuple(_named(cell, "VALUE"))
    if len(value_refs) != 1:
        raise RuntimeError("La celda de una tabla debe contener un único valor.")

    leaves = tuple(
        current
        for current in _walk(value_refs[0])
        if _token_kind(current) in _VALUE_KINDS
    )
    if len(leaves) != 1:
        raise RuntimeError(
            "Las tablas solo pueden contener valores literales NUMBER, DECIMAL, IDENT, "
            "STRING o BOOL."
        )
    return _token_value(leaves[0])


def _rows(table: Any, width: int) -> list[tuple[Any, ...]]:
    materialized: list[tuple[Any, ...]] = []
    for row in _named(table, "ROW"):
        cells = tuple(_named(row, "CELL"))
        if len(cells) != width:
            raise RuntimeError(
                f"Una fila de @table debe tener {width} celdas; "
                f"se encontraron {len(cells)}."
            )
        materialized.append(tuple(_cell_value(cell) for cell in cells))
    if not materialized:
        raise RuntimeError("La tabla debe contener al menos una fila.")
    return materialized


def visit(node: Any) -> None:
    """Materializa una declaración TABLE y registra sus índices."""
    name = _table_name(node)
    if name in globals.TABLES:
        raise RuntimeError(f"La tabla '{name}' ya fue declarada.")

    header_refs = tuple(_named(node, "HEADER"))
    if len(header_refs) != 1:
        raise RuntimeError("La tabla debe contener exactamente un encabezado.")

    headers = _headers(header_refs[0])
    matrix = _rows(node, len(headers))
    columns = {column: index for index, column in enumerate(headers)}
    globals.TABLES[name] = globals.TableData(
        name=name,
        headers=headers,
        matrix=matrix,
        columns=columns,
    )


__all__ = ["visit"]
