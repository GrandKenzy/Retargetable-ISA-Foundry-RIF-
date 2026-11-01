"""Declarative generic ``@block`` syntax for RIF."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gram import combinators as cmb
from gram import lexer


@dataclass(frozen=True)
class RawBlock:
    """A generic block whose body is preserved for semantic processing."""

    block_name: str
    lines: tuple[tuple[lexer.TokenType, ...], ...]
    start: lexer.TokenType | None = None

    @property
    def name(self) -> str:
        return "BLOCK"


_END = cmb.Seq(
    cmb.MatchToken(lexer.Token.AT),
    cmb.MatchKeyword("end"),
    cmb.MatchToken(lexer.Token.NEWLINE),
)


def _split_lines(tokens: tuple[lexer.TokenType, ...]) -> tuple[tuple[lexer.TokenType, ...], ...]:
    lines: list[tuple[lexer.TokenType, ...]] = []
    line: list[lexer.TokenType] = []
    for token in tokens:
        line.append(token)
        if token.token == lexer.Token.NEWLINE:
            lines.append(tuple(line))
            line = []
    if line:
        lines.append(tuple(line))
    return tuple(lines)


def _token(node: Any) -> lexer.TokenType | None:
    if isinstance(node, lexer.TokenType):
        return node
    value = getattr(node, "token", None)
    return value if isinstance(value, lexer.TokenType) else None


def normalize_block(nodes: Any) -> RawBlock:
    """Convert the declarative Gram result into the semantic RawBlock shape."""

    if isinstance(nodes, RawBlock):
        return nodes
    if not isinstance(nodes, (list, tuple)):
        raise RuntimeError("El bloque declarativo tiene una forma inválida.")
    raw = next((node for node in nodes if isinstance(node, cmb.RawNode)), None)
    if raw is None:
        raise RuntimeError("El bloque declarativo no contiene CaptureRaw.")
    prefix = tuple(token for node in nodes if (token := _token(node)) is not None)
    if len(prefix) < 3:
        raise RuntimeError("La cabecera de @block está incompleta.")
    captured = tuple(raw.tokens)
    if len(captured) < 3:
        raise RuntimeError("El bloque no contiene un terminador @end válido.")
    body_tokens = captured[:-3]
    if body_tokens and body_tokens[-1].token != lexer.Token.NEWLINE:
        raise RuntimeError("@end debe comenzar en una línea nueva.")
    return RawBlock(
        block_name=str(prefix[2].value),
        lines=_split_lines(body_tokens),
        start=prefix[0],
    )


_BLOCK_NAME = cmb.Alt(
    cmb.MatchToken(lexer.Token.IDENT),
    cmb.MatchGroup("keywords"),
)


class BLOCK(cmb.RuleItem):
    nodeable = True
    description = "Captura un bloque genérico mediante CaptureRaw."
    entrypoint = cmb.Seq(
        cmb.MatchToken(lexer.Token.AT),
        cmb.MatchKeyword("block"),
        _BLOCK_NAME,
        cmb.MatchToken(lexer.Token.COLON),
        cmb.MatchToken(lexer.Token.NEWLINE),
        cmb.CaptureRaw(_END, consume_target=True),
    )


__all__ = ["BLOCK", "RawBlock", "normalize_block"]
