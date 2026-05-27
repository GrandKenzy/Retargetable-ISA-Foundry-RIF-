from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..lexer import Token


@dataclass
class InstructionNode:
    kind: str
    args: tuple[Token, ...]
    line: int
    indent: int
    raw: str
    children: list[InstructionNode] = field(default_factory=list)


@dataclass
class MacroNode:
    name: str
    params: tuple[str, ...]
    line: int
    instructions: list[InstructionNode]


@dataclass
class NeedNode:
    name: str
    accepts: tuple[str, ...]
    line: int


@dataclass
class LiteralNeedNode:
    value: str
    line: int


@dataclass
class OperandNode:
    name: str
    kind: str
    raw: str
    value: Any
    bits: int | None
    line: int | None = None


@dataclass
class RefNode:
    root: str
    attr: str | None
    raw: str
    line: int


@dataclass
class IntNode:
    value: int
    raw: str
    line: int


@dataclass
class StringNode:
    value: str
    line: int


@dataclass
class ConditionNode:
    kind: str
    args: tuple[Any, ...]
    line: int


@dataclass
class CheckNode:
    condition: ConditionNode
    line: int


@dataclass
class EmitNode:
    mode: str
    args: tuple[Any, ...]
    line: int


@dataclass
class ErrorNode:
    message: str
    line: int


@dataclass
class OffNode:
    line: int


@dataclass
class OnNode:
    condition: ConditionNode
    body: tuple[Any, ...]
    line: int


@dataclass
class CaseNode:
    value: Any
    body: tuple[Any, ...]
    line: int


@dataclass
class SwitchNode:
    expr: Any
    cases: tuple[CaseNode, ...]
    line: int


@dataclass
class CallNode:
    rule_name: str
    args: tuple[Any, ...]
    line: int


@dataclass
class NonsfamilyNode:
    left: Any
    right: Any
    line: int


@dataclass
class MemskipNode:
    arg: Any
    line: int


@dataclass
class MarkNode:
    ref: RefNode
    line: int


@dataclass
class MultipleNode:
    left: Any
    right: Any
    line: int


@dataclass
class StrictNode:
    val: Any
    type_spec: str
    line: int


@dataclass
class CalcdistNode:
    left: Any
    right: Any
    line: int


@dataclass
class AssignNode:
    name: str
    expr: Any
    line: int


@dataclass
class PendingNode:
    line: int
