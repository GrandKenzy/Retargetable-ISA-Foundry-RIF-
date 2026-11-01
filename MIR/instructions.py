"""Internal representation of compiled RIF Rules.

This module does not define the user-facing/external MIR input. Its public
names are :class:`CompiledRule` and :class:`CompiledRuleSet`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from Frontend import globals


@dataclass(frozen=True)
class SourceSpan:
    path: str | None
    line: int | None
    column: int | None


@dataclass(frozen=True)
class Operand:
    kind: str
    value: Any
    raw: str | None = None
    width: int | None = None
    resolved: Any = None


@dataclass(frozen=True)
class Instruction:
    opcode: str
    operands: tuple[Operand, ...]
    span: SourceSpan
    source_node: Any = None


@dataclass(frozen=True)
class CompiledRule:
    name: str
    instructions: tuple[Instruction, ...]
    source_path: str | None = None


@dataclass(frozen=True)
class CompiledRuleSet:
    """Resolved Rules produced from a ``.rif`` definition or ``.pack``."""

    rules: dict[str, CompiledRule]
    context: globals.TargetContext = field(default_factory=globals.TargetContext)


__all__ = [
    "SourceSpan",
    "Operand",
    "Instruction",
    "CompiledRule",
    "CompiledRuleSet",
]
