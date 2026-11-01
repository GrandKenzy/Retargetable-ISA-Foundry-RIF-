"""Declarative line-oriented instruction syntax for RIF rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gram import combinators as cmb
from gram import lexer

from ..keywords import INSTRUCTION_OPCODES


@dataclass(frozen=True)
class RawInstruction:
    """One logical RIF instruction preserved for semantic processing."""

    opcode: str
    lines: tuple[tuple[lexer.TokenType, ...], ...]

    @property
    def tokens(self) -> tuple[lexer.TokenType, ...]:
        return tuple(token for line in self.lines for token in line)

    @property
    def start(self) -> lexer.TokenType | None:
        return self.tokens[0] if self.tokens else None


_FRAME_END = cmb.Seq(
    cmb.MatchToken(lexer.Token.DOT),
    cmb.MatchSeqSymbol(symbols=["frameend"], case_sensitive=True),
    cmb.MatchToken(lexer.Token.NEWLINE),
)

# A fixed MatchSeqSymbol is part of Gram's C/AOT subset. Literal is not
# suitable here because it intentionally rejects KEYWORD tokens.
_MARK_OPCODE = cmb.MatchSeqSymbol(symbols=["mark"], case_sensitive=True)


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
    if isinstance(node, (list, tuple)) and len(node) == 1:
        return _token(node[0])
    value = getattr(node, "token", None)
    return value if isinstance(value, lexer.TokenType) else None


def _opcode(lines: tuple[tuple[lexer.TokenType, ...], ...]) -> str:
    if not lines or len(lines[0]) < 2:
        raise RuntimeError("Una instrucción RIF requiere un opcode.")
    body = lines[0][1:]
    if body and body[-1].token == lexer.Token.NEWLINE:
        body = body[:-1]
    if not body:
        raise RuntimeError("Una instrucción RIF requiere un opcode.")

    first = body[0]
    if first.token == lexer.Token.DOLLAR:
        return "table_matcher"
    if first.token == lexer.Token.LBRACKET:
        return "store"
    opcode = INSTRUCTION_OPCODES.get(str(first.value))
    if opcode is not None:
        return opcode
    if first.token == lexer.Token.KEYWORD:
        if lexer.Token.from_string(str(first.value)) is not None:
            return "consumer"
    elif first.token in {lexer.Token.NUMBER, lexer.Token.DECIMAL, lexer.Token.IDENT}:
        return "consumer"
    raise RuntimeError(f"Opcode de instrucción no reconocido: {first.value!r}.")


def normalize_instruction(nodes: Any) -> RawInstruction:
    """Convert the declarative Gram result into the semantic RawInstruction."""

    if isinstance(nodes, RawInstruction):
        return nodes
    if not isinstance(nodes, (list, tuple)):
        raise RuntimeError("La instrucción declarativa tiene una forma inválida.")

    raw = next((node for node in nodes if isinstance(node, cmb.RawNode)), None)
    if raw is None:
        raise RuntimeError("La instrucción declarativa no contiene CaptureRaw.")
    prefix = tuple(token for node in nodes if (token := _token(node)) is not None)
    lines = _split_lines(prefix + tuple(raw.tokens))
    if not lines:
        raise RuntimeError("La instrucción declarativa está vacía.")

    if len(prefix) > 1 and prefix[1].value == "frame":
        captured = tuple(raw.tokens)
        if captured[:-3] and captured[-4].token != lexer.Token.NEWLINE:
            raise RuntimeError("frameend debe comenzar en una línea nueva.")
        if any(
            len(line) == 1 and line[0].token == lexer.Token.NEWLINE
            for line in lines[1:-1]
        ):
            raise RuntimeError("frame no admite líneas vacías en el frame.")

    return RawInstruction(opcode=_opcode(lines), lines=lines)


_INSTRUCTION_START = cmb.Alt(
    cmb.MatchToken(lexer.Token.DOLLAR),
    cmb.MatchToken(lexer.Token.LBRACKET),
    cmb.MatchGroup("keywords"),
    cmb.MatchGroup("token_names"),
    cmb.MatchToken(lexer.Token.NUMBER),
    cmb.MatchToken(lexer.Token.DECIMAL),
    cmb.MatchToken(lexer.Token.IDENT),
)


class INSTRUCTION(cmb.RuleItem):
    nodeable = False
    description = "Captura una instrucción RIF mediante CaptureRaw."
    entrypoint = cmb.Alt(
        cmb.Seq(
            cmb.MatchToken(lexer.Token.DOT),
            cmb.MatchSeqSymbol(symbols=["frame"], case_sensitive=True),
            cmb.CaptureRaw(_FRAME_END, consume_target=True),
        ),
        cmb.Seq(
            cmb.MatchToken(lexer.Token.DOT),
            _MARK_OPCODE,
            cmb.CaptureRaw(cmb.MatchToken(lexer.Token.NEWLINE), consume_target=True),
        ),
        cmb.Seq(
            cmb.MatchToken(lexer.Token.DOT),
            _INSTRUCTION_START,
            cmb.CaptureRaw(cmb.MatchToken(lexer.Token.NEWLINE), consume_target=True),
        ),
    )


__all__ = ["RawInstruction", "INSTRUCTION", "normalize_instruction"]
