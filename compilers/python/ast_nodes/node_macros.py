from __future__ import annotations

from dataclasses import replace
from typing import Mapping, Sequence

from ..errors import RuleInstructionError
from ..lexer import Token

from .node_syntax import InstructionNode, MacroNode
from .node_utils import split_token_groups


def expand_macro_instructions(
    instructions: Sequence[InstructionNode],
    macros: Mapping[str, MacroNode],
    call_stack: tuple[str, ...] = (),
) -> list[InstructionNode]:
    """Return instructions with generic macro calls expanded.

    This is a pure syntax transformation. The compiler does not interpret the
    macro name or body semantically; it only substitutes argument tokens for
    parameter tokens and recursively expands the resulting instruction stream.
    """
    if not macros:
        return [clone_instruction(instruction) for instruction in instructions]
    out: list[InstructionNode] = []
    for instruction in instructions:
        macro = macros.get(instruction.kind)
        if macro is None:
            children = expand_macro_instructions(instruction.children, macros, call_stack)
            out.append(replace(instruction, children=children))
            continue
        out.extend(expand_macro_call(instruction, macro, macros, call_stack))
    return out


def expand_macro_call(
    instruction: InstructionNode,
    macro: MacroNode,
    macros: Mapping[str, MacroNode],
    call_stack: tuple[str, ...],
) -> list[InstructionNode]:
    if macro.name in call_stack:
        chain = " -> ".join((*call_stack, macro.name))
        raise RuleInstructionError(f"recursive macro expansion: {chain}", instruction.line)
    arg_groups = parse_macro_call_args(instruction.args, instruction.line)
    if len(arg_groups) != len(macro.params):
        raise RuleInstructionError(
            f"macro {macro.name!r} expects {len(macro.params)} argument(s), got {len(arg_groups)}",
            instruction.line,
        )
    mapping = dict(zip(macro.params, arg_groups))
    substituted = [substitute_instruction(child, mapping) for child in macro.instructions]
    return expand_macro_instructions(substituted, macros, (*call_stack, macro.name))


def parse_macro_call_args(tokens: Sequence[Token], line: int) -> list[tuple[Token, ...]]:
    tokens = tuple(tokens)
    if not tokens:
        return []
    groups = split_token_groups(tokens, "COMMA")
    return [tuple(group) for group in groups]


def substitute_instruction(instruction: InstructionNode, mapping: Mapping[str, tuple[Token, ...]]) -> InstructionNode:
    args = substitute_tokens(instruction.args, mapping)
    children = [substitute_instruction(child, mapping) for child in instruction.children]
    raw = instruction_source(instruction.kind, args)
    return InstructionNode(instruction.kind, args, instruction.line, instruction.indent, raw, children)


def substitute_tokens(tokens: Sequence[Token], mapping: Mapping[str, tuple[Token, ...]]) -> tuple[Token, ...]:
    out: list[Token] = []
    for token in tokens:
        if token.kind == "IDENT" and token.value in mapping:
            out.extend(mapping[token.value])
        else:
            out.append(token)
    return tuple(out)


def clone_instruction(instruction: InstructionNode) -> InstructionNode:
    return replace(instruction, children=[clone_instruction(child) for child in instruction.children])


def instruction_source(kind: str, args: Sequence[Token]) -> str:
    args_source = tokens_to_source(args)
    return kind if not args_source else f"{kind} {args_source}"


def tokens_to_source(tokens: Sequence[Token]) -> str:
    parts: list[str] = []
    previous: Token | None = None
    for token in tokens:
        piece = token_to_source(token)
        if parts and needs_space(previous, token):
            parts.append(" ")
        parts.append(piece)
        previous = token
    return "".join(parts)


def token_to_source(token: Token) -> str:
    if token.kind == "STRING":
        escaped = token.value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        return f'"{escaped}"'
    return token.value


def needs_space(previous: Token | None, current: Token) -> bool:
    if previous is None:
        return False
    no_space_before = {"DOT", "COMMA", "COLON", "RPAREN", "RBRACKET"}
    no_space_after = {"DOT", "LPAREN", "LBRACKET"}
    return current.kind not in no_space_before and previous.kind not in no_space_after
