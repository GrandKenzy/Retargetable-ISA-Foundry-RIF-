from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from Frontend import globals
from Frontend.session import CompilationSession


_LITERAL_KINDS = {"NUMBER", "DECIMAL", "IDENT", "STRING", "BOOL"}
_NAME_KINDS = {"IDENT", "KEYWORD"}


@dataclass(frozen=True)
class _DerivedHeader:
    """A column populated by joining the current row with another table."""

    selector: str
    source_table: str
    source_column: str

    @property
    def name(self) -> str:
        return self.source_column


@dataclass(frozen=True)
class _TableLookup:
    """A cell value copied from one uniquely selected source row."""

    source_table: str
    selector: str
    key: Any
    source_column: str


@dataclass(frozen=True)
class _TableSpec:
    name: str
    headers: tuple[str | _DerivedHeader, ...]
    rows: tuple[tuple[Any, ...], ...]


def _children(node: Any) -> tuple[Any, ...]:
    if isinstance(node, (list, tuple)):
        return tuple(node)
    items = getattr(node, "items", None)
    if items is not None:
        return tuple(items)
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


def _operation_tokens(operation: Any) -> tuple[tuple[str, Any], ...]:
    return tuple(
        (kind, _token_value(current))
        for current in _walk(operation)
        if (kind := _token_kind(current)) is not None
    )


def _parse_operation(operation: Any) -> _DerivedHeader | _TableLookup:
    tokens = _operation_tokens(operation)
    kinds = tuple(kind for kind, _ in tokens)

    if (
        len(tokens) == 9
        and kinds[0] == "PERCENT"
        and kinds[1] == "LBRACKET"
        and kinds[2] in _NAME_KINDS
        and kinds[3] == "RBRACKET"
        and kinds[4] == "ASSIGN"
        and kinds[5] in _NAME_KINDS
        and kinds[6] == "DOT"
        and kinds[7] in _NAME_KINDS
        and kinds[8] == "PERCENT"
    ):
        return _DerivedHeader(
            selector=tokens[2][1],
            source_table=tokens[5][1],
            source_column=tokens[7][1],
        )

    if (
        len(tokens) == 10
        and kinds[0] == "PERCENT"
        and kinds[1] in _NAME_KINDS
        and kinds[2] == "DOT"
        and kinds[3] in _NAME_KINDS
        and kinds[4] == "LBRACKET"
        and kinds[5] in _LITERAL_KINDS
        and kinds[6] == "RBRACKET"
        and kinds[7] == "DOT"
        and kinds[8] in _NAME_KINDS
        and kinds[9] == "PERCENT"
    ):
        return _TableLookup(
            source_table=tokens[1][1],
            selector=tokens[3][1],
            key=tokens[5][1],
            source_column=tokens[8][1],
        )

    raise RuntimeError(
        "La operación de tabla debe ser %[selector]=tabla.columna% "
        "o %tabla.selector[clave].columna%."
    )


def _header_items(header: Any) -> tuple[Any, ...]:
    """Return the payload of each ``| value`` group in HEADER."""

    items: list[Any] = []
    for child in _children(header):
        if not isinstance(child, (list, tuple)):
            continue
        for group in child:
            group_children = _children(group)
            if len(group_children) >= 2 and _token_kind(group_children[0]) == "OR":
                items.append(group_children[1])
    return tuple(items)


def _headers(header: Any) -> tuple[str | _DerivedHeader, ...]:
    headers: list[str | _DerivedHeader] = []
    for item in _header_items(header):
        if getattr(item, "name", None) == "TABLE_OPERATION":
            parsed = _parse_operation(item)
            if not isinstance(parsed, _DerivedHeader):
                raise RuntimeError("Una operación de consulta no puede ser una cabecera.")
            headers.append(parsed)
            continue

        kind = _token_kind(item)
        value = _token_value(item)
        if kind not in _NAME_KINDS or not isinstance(value, str) or not value:
            raise RuntimeError("La cabecera de @table debe contener nombres de columna.")
        headers.append(value)

    if not headers:
        raise RuntimeError("La tabla debe declarar al menos una columna.")

    names = tuple(header if isinstance(header, str) else header.name for header in headers)
    if len(set(names)) != len(names):
        raise RuntimeError("Una tabla no puede repetir nombres de columna.")
    return tuple(headers)


def _cell_value(cell: Any) -> Any:
    operations = tuple(_named(cell, "TABLE_OPERATION"))
    if operations:
        if len(operations) != 1:
            raise RuntimeError("La celda de una tabla debe contener una única operación.")
        return _parse_operation(operations[0])

    value_refs = tuple(_named(cell, "VALUE"))
    if len(value_refs) != 1:
        raise RuntimeError("La celda de una tabla debe contener un único valor.")

    leaves = tuple(
        current
        for current in _walk(value_refs[0])
        if _token_kind(current) in _LITERAL_KINDS
    )
    if len(leaves) != 1:
        raise RuntimeError(
            "Las tablas solo pueden contener valores literales NUMBER, DECIMAL, IDENT, "
            "STRING o BOOL, u operaciones de tabla."
        )
    return _token_value(leaves[0])


def _rows(table: Any, headers: tuple[str | _DerivedHeader, ...]) -> tuple[tuple[Any, ...], ...]:
    literal_columns = tuple(
        index for index, header in enumerate(headers) if isinstance(header, str)
    )
    materialized: list[tuple[Any, ...]] = []
    for row in _named(table, "ROW"):
        cells = tuple(_named(row, "CELL"))
        if len(cells) != len(literal_columns):
            expected = len(literal_columns)
            if expected == len(headers):
                detail = f"{expected} celdas"
            else:
                detail = f"{expected} celdas literales; las columnas calculadas se omiten"
            raise RuntimeError(
                f"Una fila de @table debe tener {detail}; se encontraron {len(cells)}."
            )

        values: list[Any] = [None] * len(headers)
        for column, cell in zip(literal_columns, cells):
            values[column] = _cell_value(cell)
        materialized.append(tuple(values))

    if not materialized:
        raise RuntimeError("La tabla debe contener al menos una fila.")
    return tuple(materialized)


def _dependencies(spec: _TableSpec) -> tuple[str, ...]:
    names: list[str] = []
    for header in spec.headers:
        if isinstance(header, _DerivedHeader):
            names.append(header.source_table)
    for row in spec.rows:
        for value in row:
            if isinstance(value, _TableLookup):
                names.append(value.source_table)
    return tuple(dict.fromkeys(names))


def _source_table(
    spec_name: str,
    source_name: str,
    session: CompilationSession,
) -> globals.TableData:
    table = session.tables.get(source_name)
    if table is None:
        if source_name in session.pending_tables:
            raise RuntimeError(
                f"La tabla '{spec_name}' depende de '{source_name}', "
                "pero todavía no ha sido materializada."
            )
        raise RuntimeError(f"La tabla '{source_name}' no existe.")
    return table


def _lookup(
    spec_name: str,
    reference: _TableLookup,
    session: CompilationSession,
) -> Any:
    source = _source_table(spec_name, reference.source_table, session)
    if reference.selector not in source.columns:
        raise RuntimeError(
            f"La columna selectora '{reference.selector}' no existe en "
            f"la tabla '{reference.source_table}'."
        )
    if reference.source_column not in source.columns:
        raise RuntimeError(
            f"La columna '{reference.source_column}' no existe en "
            f"la tabla '{reference.source_table}'."
        )
    source.require_unique(reference.selector)
    row_index = source.lookup_unique(reference.selector, reference.key)
    if row_index is None:
        raise RuntimeError(
            f"La clave {reference.key!r} no existe en "
            f"{reference.source_table}.{reference.selector}."
        )
    return source.matrix[row_index][source.columns[reference.source_column]]


def _materialize(spec: _TableSpec, session: CompilationSession) -> globals.TableData:
    names = tuple(header if isinstance(header, str) else header.name for header in spec.headers)
    columns = {name: index for index, name in enumerate(names)}
    matrix: list[tuple[Any, ...]] = []

    for row in spec.rows:
        values = list(row)
        for index, header in enumerate(spec.headers):
            if not isinstance(header, _DerivedHeader):
                if isinstance(values[index], _TableLookup):
                    values[index] = _lookup(spec.name, values[index], session)
                continue

            if header.selector not in columns:
                raise RuntimeError(
                    f"La columna selectora '{header.selector}' no existe en "
                    f"la tabla '{spec.name}'."
                )
            source = _source_table(spec.name, header.source_table, session)
            if header.selector not in source.columns:
                raise RuntimeError(
                    f"La columna selectora '{header.selector}' no existe en "
                    f"la tabla '{header.source_table}'."
                )
            if header.source_column not in source.columns:
                raise RuntimeError(
                    f"La columna '{header.source_column}' no existe en "
                    f"la tabla '{header.source_table}'."
                )
            source.require_unique(header.selector)
            key = values[columns[header.selector]]
            row_index = source.lookup_unique(header.selector, key)
            if row_index is None:
                raise RuntimeError(
                    f"La clave {key!r} de '{spec.name}.{header.selector}' no existe en "
                    f"{header.source_table}.{header.selector}."
                )
            values[index] = source.matrix[row_index][source.columns[header.source_column]]
        matrix.append(tuple(values))

    return globals.TableData(
        name=spec.name,
        headers=names,
        matrix=tuple(matrix),
        columns=columns,
    )


def _resolve(
    name: str,
    stack: tuple[str, ...],
    session: CompilationSession,
) -> globals.TableData:
    existing = session.tables.get(name)
    if existing is not None:
        return existing
    spec = session.pending_tables.get(name)
    if spec is None:
        raise RuntimeError(f"La tabla '{name}' no existe.")
    if name in stack:
        cycle = " -> ".join((*stack, name))
        raise RuntimeError(f"Ciclo de operaciones de tabla detectado: {cycle}")

    for dependency in _dependencies(spec):
        _resolve(dependency, (*stack, name), session)
    table = _materialize(spec, session)
    session.tables[name] = table
    return table


def resolve_pending_tables(session: CompilationSession) -> None:
    """Resolve all table joins after the complete source graph is loaded."""

    try:
        for name in tuple(session.pending_tables):
            _resolve(name, (), session)
    finally:
        session.pending_tables.clear()


def clear_pending_tables(session: CompilationSession) -> None:
    """Discard pending declarations after a failed frontend pass."""

    session.pending_tables.clear()


def visit(node: Any, session: CompilationSession) -> None:
    """Register a table declaration for dependency-aware materialization."""

    name = _table_name(node)
    if name in session.tables or name in session.pending_tables:
        raise RuntimeError(f"La tabla '{name}' ya fue declarada.")

    header_refs = tuple(_named(node, "HEADER"))
    if len(header_refs) != 1:
        raise RuntimeError("La tabla debe contener exactamente un encabezado.")

    headers = _headers(header_refs[0])
    session.pending_tables[name] = _TableSpec(
        name=name,
        headers=headers,
        rows=_rows(node, headers),
    )


__all__ = ["clear_pending_tables", "resolve_pending_tables", "visit"]
