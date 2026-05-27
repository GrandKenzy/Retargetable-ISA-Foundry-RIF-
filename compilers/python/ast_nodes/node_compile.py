from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from ..errors import (
    NeedSyntaxError,
    NeedTargetError,
    RuleInstructionError,
    UnknownNeedTypeError,
)
from ..lexer import Lexer, Token

from .node_constants import (
    CONDITION_NAMES,
    EMIT_MODES,
    HEX_BYTE_RE,
    IDENT_RE,
    KNOWN_NEED_TYPES,
    NEED_NORMALIZE,
)
from .node_macros import expand_macro_instructions
from .node_syntax import (
    AssignNode,
    CalcdistNode,
    CallNode,
    CaseNode,
    CheckNode,
    ConditionNode,
    EmitNode,
    ErrorNode,
    IntNode,
    LiteralNeedNode,
    MarkNode,
    MemskipNode,
    MultipleNode,
    NeedNode,
    NonsfamilyNode,
    OffNode,
    OnNode,
    PendingNode,
    RefNode,
    StrictNode,
    StringNode,
    SwitchNode,
    InstructionNode,
    MacroNode,
)
from .node_utils import split_token_groups, token_raw


def compile_need_instruction(instruction: InstructionNode) -> NeedNode | LiteralNeedNode:
    tokens = instruction.args
    line = instruction.line
    if not tokens:
        raise NeedSyntaxError("empty need instruction", line)
    if len(tokens) == 1 and tokens[0].kind == "STRING":
        return LiteralNeedNode(tokens[0].value, line)
    groups = split_token_groups(tokens, "COMMA")
    if len(groups) < 2:
        raise NeedTargetError("need instruction requires a target operand", line)
    target_group = groups[-1]
    if len(target_group) != 1 or target_group[0].kind != "IDENT":
        raise NeedTargetError("invalid need target", line)
    target = target_group[0].value
    if target.upper() in KNOWN_NEED_TYPES:
        raise NeedTargetError(f"need target cannot be a type name {target!r}", line, target_group[0].col)
    if not IDENT_RE.fullmatch(target):
        raise NeedTargetError(f"invalid need target {target!r}", line, target_group[0].col)
    accepts: list[str] = []
    for group in groups[:-1]:
        if len(group) != 1 or group[0].kind != "IDENT":
            raise NeedSyntaxError("invalid need type", line)
        kind = group[0].value.upper()
        if kind not in KNOWN_NEED_TYPES:
            raise UnknownNeedTypeError(f"unknown need type {group[0].value!r}", line, group[0].col)
        normalized = NEED_NORMALIZE.get(kind, kind)
        if normalized not in accepts:
            accepts.append(normalized)
    return NeedNode(target, tuple(accepts), line)


def compile_rule_body(instructions: Sequence[InstructionNode], macros: Mapping[str, MacroNode] | None = None) -> tuple[Any, ...]:
    if macros:
        instructions = expand_macro_instructions(instructions, macros)
    out: list[Any] = []
    i = 0
    while i < len(instructions):
        instruction = instructions[i]
        if instruction.kind == "off":
            i += 1
            continue
        if instruction.kind == "switch":
            cases: list[InstructionNode] = []
            i += 1
            while i < len(instructions):
                candidate = instructions[i]
                if candidate.kind == "off":
                    i += 1
                    continue
                if candidate.kind != "case":
                    break
                cases.append(candidate)
                i += 1
            out.append(compile_switch(instruction, cases))
            continue
        out.append(compile_rule_instruction(instruction, None))
        i += 1
    return tuple(out)


def compile_rule_instruction(instruction: InstructionNode, parent: str | None) -> Any:
    kind = instruction.kind
    if kind in CONDITION_NAMES or kind == "not":
        ensure_no_children(instruction)
        return CheckNode(parse_condition(tokens_with_head(kind, instruction.args, instruction.line), instruction.line), instruction.line)
    if kind == "emmit":
        ensure_no_children(instruction)
        return compile_emit(instruction)
    if kind == "switch":
        return compile_switch(instruction)
    if kind == "case":
        if parent != "switch":
            raise RuleInstructionError("case outside switch", instruction.line)
        return compile_case(instruction)
    if kind == "on":
        return compile_on(instruction)
    if kind == "call":
        ensure_no_children(instruction)
        if not instruction.args:
            raise RuleInstructionError("empty call instruction", instruction.line)
        rule_token = instruction.args[0]
        if rule_token.kind != "IDENT":
            raise RuleInstructionError("call instruction expects a rule name identifier as the first argument", instruction.line)
        rule_name = rule_token.value
        
        # Parse the comma-separated arguments
        arg_tokens = instruction.args[1:]
        args = []
        if arg_tokens:
            groups = split_token_groups(arg_tokens, "COMMA")
            for group in groups:
                args.append(parse_expr(group, instruction.line))
        return CallNode(rule_name, tuple(args), instruction.line)
    if kind == "nonsfamily":
        ensure_no_children(instruction)
        groups = split_token_groups(instruction.args, "COMMA")
        if len(groups) != 2:
            raise RuleInstructionError(f"{kind} requires exactly two operands", instruction.line)
        left = parse_expr(groups[0], instruction.line)
        right = parse_expr(groups[1], instruction.line)
        return NonsfamilyNode(left, right, instruction.line)
    if kind == "memskip":
        ensure_no_children(instruction)
        if len(instruction.args) != 1:
            raise RuleInstructionError("memskip requires exactly one argument", instruction.line)
        arg = parse_expr(instruction.args, instruction.line)
        return MemskipNode(arg, instruction.line)
    if kind == "mark":
        ensure_no_children(instruction)
        if len(instruction.args) == 0:
            raise RuleInstructionError("empty mark instruction", instruction.line)
        expr = parse_expr(instruction.args, instruction.line)
        if not isinstance(expr, RefNode) or expr.attr not in {"bottom", "top"}:
            raise RuleInstructionError("mark instruction expects an operand attribute like op.bottom or op.top", instruction.line)
        return MarkNode(expr, instruction.line)
    if kind == "multiple":
        ensure_no_children(instruction)
        groups = split_token_groups(instruction.args, "COMMA")
        if len(groups) != 2:
            raise RuleInstructionError("multiple requires exactly two arguments", instruction.line)
        left = parse_expr(groups[0], instruction.line)
        right = parse_expr(groups[1], instruction.line)
        return MultipleNode(left, right, instruction.line)
    if kind == "strict":
        ensure_no_children(instruction)
        groups = split_token_groups(instruction.args, "COMMA")
        if len(groups) != 2:
            raise RuleInstructionError("strict requires exactly two arguments", instruction.line)
        val = parse_expr(groups[0], instruction.line)
        type_tokens = groups[1]
        if len(type_tokens) != 1 or type_tokens[0].kind != "IDENT":
            raise RuleInstructionError("strict type specifier must be a single identifier", instruction.line)
        type_spec = type_tokens[0].value
        return StrictNode(val, type_spec, instruction.line)
    if kind == "off":
        ensure_no_children(instruction)
        ensure_no_args(instruction)
        return OffNode(instruction.line)
    if kind == "error":
        ensure_no_children(instruction)
        return compile_error(instruction)
    if kind == "pending":
        ensure_no_children(instruction)
        ensure_no_args(instruction)
        return PendingNode(instruction.line)
    if len(instruction.args) >= 1 and instruction.args[0].kind == "EQUAL":
        ensure_no_children(instruction)
        expr = parse_expr(instruction.args[1:], instruction.line)
        return AssignNode(kind, expr, instruction.line)
    raise RuleInstructionError(f"unknown rule instruction {kind!r}", instruction.line)


def compile_switch(instruction: InstructionNode, sibling_cases: Sequence[InstructionNode] | None = None) -> SwitchNode:
    args = strip_trailing_colon(instruction.args, instruction.line, "switch")
    expr = parse_expr(args, instruction.line)
    case_source = list(sibling_cases or [])
    for child in instruction.children:
        if child.kind == "off":
            continue
        if child.kind != "case":
            raise RuleInstructionError("switch only accepts case blocks", child.line)
        case_source.append(child)
    cases = [compile_rule_instruction(child, "switch") for child in case_source]
    return SwitchNode(expr, tuple(cases), instruction.line)


def compile_case(instruction: InstructionNode) -> CaseNode:
    args = strip_trailing_colon(instruction.args, instruction.line, "case")
    value = parse_case_value(args, instruction.line)
    body = compile_rule_body(instruction.children)
    return CaseNode(value, body, instruction.line)


def compile_on(instruction: InstructionNode) -> OnNode:
    args = strip_trailing_colon(instruction.args, instruction.line, "ON")
    if not args:
        raise RuleInstructionError("ON requires exactly one condition", instruction.line)
    condition = parse_condition(args, instruction.line)
    body = compile_rule_body(instruction.children)
    return OnNode(condition, body, instruction.line)


def compile_emit(instruction: InstructionNode) -> EmitNode:
    args = instruction.args
    if not args:
        raise RuleInstructionError("empty emmit instruction", instruction.line)
    first = args[0]
    if first.kind == "IDENT" and first.value.lower() in EMIT_MODES:
        mode = first.value.lower()
        rest = args[1:]
        if mode == "cbits":
            parts = instruction.raw.split(None, 2)
            if len(parts) != 3 or not parts[2].strip():
                raise RuleInstructionError("emmit cbits requires a bit flow", instruction.line)
            items: list[Any] = []
            for part in parts[2].split():
                part_tokens = tuple(t for t in Lexer(part).lex() if t.kind not in {"EOF", "NEWLINE", "COMMENT"})
                items.append(parse_cbits_part(part_tokens, instruction.line))
            return EmitNode("cbits", tuple(items), instruction.line)
        if mode == "lit":
            groups = split_token_groups(rest, "COMMA")
            if len(groups) != 2:
                raise RuleInstructionError("emmit lit requires value and size", instruction.line)
            return EmitNode("lit", (parse_expr(groups[0], instruction.line), parse_bit_size(groups[1], instruction.line)), instruction.line)
        if mode == "addr":
            groups = split_token_groups(rest, "COMMA")
            if len(groups) != 2:
                raise RuleInstructionError("emmit addr requires value and size", instruction.line)
            return EmitNode("addr", (parse_expr(groups[0], instruction.line), parse_bit_size(groups[1], instruction.line)), instruction.line)
        if mode == "jaddr":
            groups = split_token_groups(rest, "COMMA")
            if len(groups) != 2:
                raise RuleInstructionError("emmit jaddr requires value and size", instruction.line)
            return EmitNode("jaddr", (parse_expr(groups[0], instruction.line), parse_bit_size(groups[1], instruction.line)), instruction.line)
        if mode == "fill":
            groups = split_token_groups(rest, "COMMA")
            if len(groups) != 2:
                raise RuleInstructionError("emmit fill requires byte value and count", instruction.line)
            return EmitNode("fill", (parse_expr(groups[0], instruction.line), parse_expr(groups[1], instruction.line)), instruction.line)
    if len(args) == 1 and token_raw(args[0]).upper() in {"66", "C7", "B4", "B5", "B6", "B7"} | set():
        raw = token_raw(args[0])
        if not HEX_BYTE_RE.fullmatch(raw):
            raise RuleInstructionError("invalid emmit hex literal", instruction.line)
        return EmitNode("hex", (raw.upper(),), instruction.line)
    if len(args) == 1:
        raw = token_raw(args[0])
        if HEX_BYTE_RE.fullmatch(raw):
            return EmitNode("hex", (raw.upper(),), instruction.line)
        if args[0].kind == "IDENT":
            return EmitNode("word", (RefNode(args[0].value, None, args[0].value, args[0].line),), instruction.line)
    raise RuleInstructionError("invalid emmit instruction", instruction.line)


def compile_error(instruction: InstructionNode) -> ErrorNode:
    args = instruction.args
    if len(args) != 1 or args[0].kind != "STRING":
        raise RuleInstructionError("error requires one string", instruction.line)
    return ErrorNode(args[0].value, instruction.line)


def parse_condition(tokens: Sequence[Token], line: int) -> ConditionNode:
    tokens = tuple(tokens)
    if not tokens:
        raise RuleInstructionError("empty condition", line)

    or_groups = split_condition_operator(tokens, "or")
    if len(or_groups) > 1:
        return ConditionNode("or", tuple(parse_condition(group, line) for group in or_groups), line)

    and_groups = split_condition_operator(tokens, "and")
    if len(and_groups) > 1:
        return ConditionNode("and", tuple(parse_condition(group, line) for group in and_groups), line)

    if tokens[0].kind == "IDENT" and tokens[0].value.lower() == "not":
        if len(tokens) == 1:
            raise RuleInstructionError("not requires one condition", line)
        return ConditionNode("not", (parse_condition(tokens[1:], line),), line)
    if tokens[0].kind == "IDENT" and tokens[0].value.lower() in CONDITION_NAMES:
        name = tokens[0].value.lower()
        groups = split_token_groups(tokens[1:], "COMMA") if len(tokens) > 1 else []
        if name in {"exists", "this"}:
            if len(groups) != 1:
                raise RuleInstructionError(f"{name} requires one operand", line)
            return ConditionNode(name, (parse_expr(groups[0], line),), line)
        if name in {"has_subset", "fits", "unbsize"}:
            if len(groups) != 2:
                raise RuleInstructionError(f"{name} requires two operands", line)
            return ConditionNode(name, (parse_expr(groups[0], line), parse_expr(groups[1], line)), line)
        if name in {"iarch", "narch"}:
            args = [parse_expr(g, line) for g in groups]
            return ConditionNode(name, tuple(args), line)
    return ConditionNode("truthy", (parse_expr(tokens, line),), line)


def split_condition_operator(tokens: Sequence[Token], operator: str) -> list[tuple[Token, ...]]:
    groups: list[list[Token]] = [[]]
    for token in tokens:
        if token.kind == "IDENT" and token.value.lower() == operator:
            groups.append([])
        else:
            groups[-1].append(token)
    if len(groups) > 1 and any(not group for group in groups):
        line = tokens[0].line if tokens else None
        raise RuleInstructionError(f"empty {operator!r} condition group", line)
    return [tuple(group) for group in groups]


def parse_expr(tokens: Sequence[Token], line: int) -> Any:
    tokens = tuple(tokens)
    if not tokens:
        raise RuleInstructionError("empty expression", line)
    if tokens[0].kind == "IDENT" and tokens[0].value.lower() == "calcdist":
        groups = split_token_groups(tokens[1:], "COMMA")
        if len(groups) != 2:
            raise RuleInstructionError("calcdist requires two arguments", line)
        left = parse_expr(groups[0], line)
        right = parse_expr(groups[1], line)
        return CalcdistNode(left, right, line)
    if len(tokens) == 1:
        t = tokens[0]
        if t.kind == "NUMBER":
            try:
                return IntNode(int(t.value), t.value, t.line)
            except ValueError:
                raise RuleInstructionError(f"invalid integer literal {t.value!r}", t.line)
        if t.kind == "STRING":
            return StringNode(t.value, t.line)
        if t.kind == "IDENT":
            return RefNode(t.value, None, t.value, t.line)
        if t.kind == "DOT":
            return RefNode(".", None, ".", t.line)
        return StringNode(t.value, t.line)
    if len(tokens) == 2 and tokens[0].kind in {"PLUS", "MINUS"} and tokens[1].kind == "NUMBER":
        raw = tokens[0].value + tokens[1].value
        try:
            return IntNode(int(raw), raw, tokens[0].line)
        except ValueError:
            raise RuleInstructionError(f"invalid integer literal {raw!r}", tokens[0].line)
    if len(tokens) == 3 and tokens[0].kind == "IDENT" and tokens[1].kind == "DOT" and tokens[2].kind == "IDENT":
        return RefNode(tokens[0].value, tokens[2].value, f"{tokens[0].value}.{tokens[2].value}", tokens[0].line)
    raise RuleInstructionError("invalid expression", line)


def parse_case_value(tokens: Sequence[Token], line: int) -> Any:
    tokens = tuple(tokens)
    if len(tokens) == 1 and tokens[0].kind in {"IDENT", "NUMBER"}:
        return token_raw(tokens[0])
    expr = parse_expr(tokens, line)
    if isinstance(expr, IntNode):
        return expr.raw
    if isinstance(expr, RefNode) and expr.attr is None:
        return expr.raw
    return expr


def parse_bit_size(tokens: Sequence[Token], line: int) -> Any:
    expr = parse_expr(tokens, line)
    if isinstance(expr, IntNode):
        if expr.value <= 0 or expr.value % 8 != 0:
            raise RuleInstructionError("byte size must be positive and byte aligned", line)
    return expr


def parse_cbits_part(tokens: Sequence[Token], line: int) -> Any:
    if len(tokens) == 1:
        t = tokens[0]
        raw = token_raw(t)
        if re.fullmatch(r"[01]+", raw):
            return StringNode(raw, t.line)
    return parse_expr(tokens, line)


def split_spaces(tokens: Sequence[Token]) -> list[list[Token]]:
    return [[token] for token in tokens]


def tokens_with_head(kind: str, args: Sequence[Token], line: int) -> tuple[Token, ...]:
    return (Token("IDENT", kind, line, 1), *args)


def strip_trailing_colon(tokens: Sequence[Token], line: int, name: str) -> tuple[Token, ...]:
    if not tokens or tokens[-1].kind != "COLON":
        raise RuleInstructionError(f"{name} requires a ':' block", line)
    out = tuple(tokens[:-1])
    if not out:
        raise RuleInstructionError(f"{name} requires a value", line)
    return out


def ensure_no_children(instruction: InstructionNode) -> None:
    if instruction.children:
        raise RuleInstructionError(f"instruction {instruction.kind!r} cannot have a block", instruction.line)


def ensure_no_args(instruction: InstructionNode) -> None:
    if instruction.args:
        raise RuleInstructionError(f"instruction {instruction.kind!r} does not accept arguments", instruction.line)
