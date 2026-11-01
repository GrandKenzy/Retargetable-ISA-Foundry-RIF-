"""Preprocessing of closed RIF metaprogramming directives in external MIR."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from gram import lexer


RIF_META_DIRECTIVES = frozenset(
    {
        "RIF_PCPI",
        "RIF_STORE",
        "RIF_REQSTS",
        "RIF_BUFFER",
        "RIF_INSERT",
        "RIF_PATCH",
        "RIF_SECTION",
    }
)

RIF_META_OPERATIONS = {
    "RIF_BUFFER": ("SET", "CLEAN", "EXTRACT"),
    "RIF_INSERT": ("BYTES", "BINARY", "FILE"),
    "RIF_PATCH": ("PATCH",),
        "RIF_PCPI": ("SET", "PIT", "FILL"),
    "RIF_REQSTS": ("REQSTS",),
    "RIF_SECTION": ("SECTION",),
    "RIF_STORE": ("STORE",),
}


@dataclass(frozen=True)
class RIFMetaDirective:
    """A closed metaprogramming directive removed from Rule dispatch."""

    name: str
    operation: str | None = None
    path: str | None = None
    label: str | None = None
    endianness: int | None = None
    bitorder: int | None = None
    index: int | None = None
    section: str | None = None
    payload: tuple[lexer.TokenType, ...] = ()
    line: int | None = None


MIRLine = tuple[lexer.TokenType, ...] | RIFMetaDirective


def _line_number(line: tuple[lexer.TokenType, ...]) -> int | None:
    return getattr(line[0], "line", None) if line else None


def _directive(line: tuple[lexer.TokenType, ...]) -> RIFMetaDirective | None:
    if len(line) < 3:
        return None
    if (
        line[0].token != lexer.Token.COLON
        or line[1].token != lexer.Token.COLON
        or line[2].token != lexer.Token.IDENT
    ):
        return None
    name = str(line[2].value)
    if name not in RIF_META_DIRECTIVES:
        return None
    line_number = _line_number(line)
    if name == "RIF_PCPI":
        if len(line) < 4 or line[3].token not in {lexer.Token.IDENT, lexer.Token.KEYWORD}:
            raise ValueError("::RIF_PCPI requiere SET o PIT.")
        operation = str(line[3].value)
        if operation == "SET":
            if len(line) != 5 or line[4].token != lexer.Token.STRING:
                raise ValueError('::RIF_PCPI SET requiere la ruta de un archivo .pcic.')
            return RIFMetaDirective(
                name,
                operation=operation,
                path=str(line[4].value),
                line=line_number,
            )
        if operation == "PIT":
            if len(line) not in {5, 7} or line[4].token != lexer.Token.NUMBER:
                raise ValueError("::RIF_PCPI PIT requiere un índice y SECTION opcional.")
            index = int(line[4].value)
            if index < 0:
                raise ValueError("El índice de ::RIF_PCPI PIT no puede ser negativo.")
            section = None
            if len(line) == 7:
                if (
                    line[5].token not in {lexer.Token.IDENT, lexer.Token.KEYWORD}
                    or str(line[5].value) != "SECTION"
                    or line[6].token not in {lexer.Token.IDENT, lexer.Token.KEYWORD}
                ):
                    raise ValueError("::RIF_PCPI PIT usa SECTION nombre.")
                section = str(line[6].value)
            return RIFMetaDirective(
                name,
                operation=operation,
                index=index,
                section=section,
                line=line_number,
            )
        if operation == "FILL":
            if (
                len(line) != 6
                or line[4].token != lexer.Token.NUMBER
                or line[5].token != lexer.Token.STRING
            ):
                raise ValueError(
                    '::RIF_PCPI FILL requiere un índice y un string hexadecimal.'
                )
            index = int(line[4].value)
            if index < 0:
                raise ValueError("El índice de ::RIF_PCPI FILL no puede ser negativo.")
            return RIFMetaDirective(
                name,
                operation=operation,
                index=index,
                payload=(line[5],),
                line=line_number,
            )
        raise ValueError("::RIF_PCPI solo acepta SET, PIT o FILL.")
    if name == "RIF_REQSTS":
        if len(line) != 4 or line[3].token != lexer.Token.STRING:
            raise ValueError('::RIF_REQSTS requiere una ruta GitHub entre comillas.')
        return RIFMetaDirective(
            name,
            operation="REQSTS",
            path=str(line[3].value),
            line=line_number,
        )
    if name == "RIF_BUFFER":
        if len(line) < 4 or line[3].token not in {lexer.Token.IDENT, lexer.Token.KEYWORD}:
            raise ValueError("::RIF_BUFFER requiere SET, CLEAN o EXTRACT.")
        operation = str(line[3].value).upper()
        if operation == "SET":
            if len(line) != 5 or line[4].token != lexer.Token.NUMBER:
                raise ValueError("::RIF_BUFFER SET requiere capacidad en KiB.")
            return RIFMetaDirective(
                name,
                operation=operation,
                index=int(line[4].value),
                line=line_number,
            )
        if operation == "CLEAN":
            if len(line) != 4:
                raise ValueError("::RIF_BUFFER CLEAN no recibe argumentos.")
            return RIFMetaDirective(name, operation=operation, line=line_number)
        if operation == "EXTRACT":
            if (
                len(line) != 6
                or line[4].token != lexer.Token.NUMBER
                or line[5].token != lexer.Token.NUMBER
            ):
                raise ValueError("::RIF_BUFFER EXTRACT requiere inicio y fin en bytes.")
            return RIFMetaDirective(
                name,
                operation=operation,
                index=int(line[4].value),
                section=str(line[5].value),
                line=line_number,
            )
        raise ValueError("::RIF_BUFFER solo acepta SET, CLEAN o EXTRACT.")
    if name == "RIF_INSERT":
        if len(line) < 5 or line[3].token not in {lexer.Token.IDENT, lexer.Token.KEYWORD}:
            raise ValueError("::RIF_INSERT requiere BYTES, BINARY o FILE.")
        operation = str(line[3].value).upper()
        if operation not in {"BYTES", "BINARY", "FILE"}:
            raise ValueError("::RIF_INSERT solo acepta BYTES, BINARY o FILE.")
        if line[4].token != lexer.Token.STRING:
            raise ValueError(f"::RIF_INSERT {operation} requiere un string.")
        section = None
        if len(line) == 7:
            if (
                line[5].token not in {lexer.Token.IDENT, lexer.Token.KEYWORD}
                or str(line[5].value).upper() != "SECTION"
                or line[6].token not in {lexer.Token.IDENT, lexer.Token.KEYWORD}
            ):
                raise ValueError("::RIF_INSERT usa SECTION nombre.")
            section = str(line[6].value)
        elif len(line) != 5:
            raise ValueError("::RIF_INSERT acepta SECTION opcional.")
        return RIFMetaDirective(
            name,
            operation=operation,
            path=str(line[4].value) if operation == "FILE" else None,
            section=section,
            payload=(line[4],) if operation != "FILE" else (),
            line=line_number,
        )
    if name == "RIF_PATCH":
        if len(line) < 4:
            raise ValueError("::RIF_PATCH requiere offset, ancho opcional y expresión.")
        return RIFMetaDirective(
            name,
            operation="PATCH",
            payload=tuple(line[3:]),
            line=line_number,
        )
    if name == "RIF_SECTION":
        if len(line) != 4 or line[3].token not in {lexer.Token.IDENT, lexer.Token.KEYWORD}:
            raise ValueError("::RIF_SECTION requiere el nombre de una sección.")
        return RIFMetaDirective(
            name,
            operation="SECTION",
            section=str(line[3].value),
            line=line_number,
        )
    if (
        len(line) != 7
        or line[3].token != lexer.Token.STRING
        or line[4].token not in {lexer.Token.IDENT, lexer.Token.KEYWORD}
        or line[5].token != lexer.Token.NUMBER
        or line[6].token != lexer.Token.NUMBER
    ):
        raise ValueError(
            '::RIF_STORE requiere "ruta.storage.bin", un label, ENDIANNESS y BITORDER.'
        )
    endianness = int(line[5].value)
    bitorder = int(line[6].value)
    if endianness not in {1, 2}:
        raise ValueError("::RIF_STORE usa ENDIANNESS 1 (little) o 2 (big).")
    if bitorder not in {0, 1}:
        raise ValueError("::RIF_STORE usa BITORDER 0 (LSB) o 1 (MSB).")
    return RIFMetaDirective(
        name,
        operation="STORE",
        path=str(line[3].value),
        label=str(line[4].value),
        endianness=endianness,
        bitorder=bitorder,
        line=line_number,
    )


def preprocess_mir_lines(
    lines: Iterable[tuple[lexer.TokenType, ...]],
) -> tuple[MIRLine, ...]:
    """Extract recognized metaprogramming lines before Rule dispatch.

    ``RIF_PCPI SET`` must be the first non-empty MIR line. The other closed
    directives are consumed here and never reach Rule dispatch. The external
    compiler applies stateful directives such as ``RIF_SECTION`` in source
    order; patches remain deferred until the final layout exists.
    """

    result: list[MIRLine] = []
    for line in lines:
        directive = _directive(line)
        if directive is not None and directive.name == "RIF_PCPI" and directive.operation == "SET":
            if result:
                raise ValueError("::RIF_PCPI SET debe ser la primera línea del MIR.")
        result.append(directive if directive is not None else line)
    return tuple(result)


__all__ = [
    "MIRLine",
    "RIFMetaDirective",
    "RIF_META_DIRECTIVES",
    "RIF_META_OPERATIONS",
    "preprocess_mir_lines",
]
