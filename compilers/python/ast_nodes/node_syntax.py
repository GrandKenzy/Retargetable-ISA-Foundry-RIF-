from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..lexer import Token


class InstructionNode:
    kind: str
    args: tuple[Token, ...]
    line: int
    indent: int
    raw: str
    children: list[InstructionNode] = field(default_factory=list)


class MacroNode:
    name: str
    params: tuple[str, ...]
    line: int
    instructions: list[InstructionNode]


class NeedNode:
    name: str
    accepts: tuple[str, ...]
    line: int


class LiteralNeedNode:
    value: str
    line: int


class OperandNode:
    name: str
    kind: str
    raw: str
    value: Any
    bits: int | None
    line: int | None = None


class RefNode:
    root: str
    attr: str | None
    raw: str
    line: int


class IntNode:
    value: int
    raw: str
    line: int


class StringNode:
    value: str
    line: int


class ConditionNode:
    kind: str
    args: tuple[Any, ...]
    line: int


class CheckNode:
    condition: ConditionNode
    line: int


class EmitNode:
    mode: str
    args: tuple[Any, ...]
    line: int


class ErrorNode:
    message: str
    line: int


class OffNode:
    line: int


class OnNode:
    condition: ConditionNode
    body: tuple[Any, ...]
    line: int


class CaseNode:
    value: Any
    body: tuple[Any, ...]
    line: int


class SwitchNode:
    expr: Any
    cases: tuple[CaseNode, ...]
    line: int


class CallNode:
    rule_name: str
    args: tuple[Any, ...]
    line: int


class NonsfamilyNode:
    left: Any
    right: Any
    line: int


class MemskipNode:
    arg: Any
    line: int


class MarkNode:
    ref: RefNode
    line: int


class MultipleNode:
    left: Any
    right: Any
    line: int


class StrictNode:
    val: Any
    type_spec: str
    line: int


class CalcdistNode:
    left: Any
    right: Any
    line: int


class AssignNode:
    name: str
    expr: Any
    line: int


class PendingNode:
    line: int
