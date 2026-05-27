from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping, Sequence, Any

from ..errors import (
    LiteralMismatchError,
    OperandCountError,
    OperandTypeError,
    SymbolPendingError,
)

from .node_compile import compile_need_instruction, compile_rule_body
from .node_info import RegisterInfo, StackInfo, SubRegisterInfo, SymbolInfo, TypeInfo, WordInfo
from .node_macros import expand_macro_instructions
from .node_syntax import InstructionNode, LiteralNeedNode, MacroNode, NeedNode, OperandNode
from .node_utils import signed_int_bits, unsigned_int_bits


class CompiledRule:
    name: str
    pattern: tuple[NeedNode | LiteralNeedNode, ...]
    needs: tuple[NeedNode, ...]
    ast: tuple[InstructionNode, ...]
    body: tuple[Any, ...]

    def parse(self, operands: Sequence[str], program: Program, symbols: dict[str, SymbolInfo] | None = None) -> dict[str, OperandNode]:
        symbols = symbols or {}
        if len(operands) != len(self.pattern):
            raise OperandCountError(f"rule {self.name!r} expects {len(self.pattern)} fields, got {len(operands)}")
        out: dict[str, OperandNode] = {}
        for index, item in enumerate(self.pattern):
            raw = operands[index]
            if isinstance(item, LiteralNeedNode):
                if raw != item.value:
                    raise LiteralMismatchError(f"rule {self.name!r} expects literal {item.value!r} at field {index + 1}, got {raw!r}", item.line)
                continue
            out[item.name] = self._parse_operand(item, raw, program, symbols)
        return out

    def emit(self, operands: Sequence[str], program: Program, symbols: dict[str, SymbolInfo] | None = None) -> bytes:
        parsed = self.parse(operands, program, symbols)
        context = RuleContext(program, parsed, symbols or {})
        execute_nodes(self.body, context)
        return bytes(context.output)

    def _parse_operand(self, need: NeedNode, raw: str, program: Program, symbols: dict[str, SymbolInfo]) -> OperandNode:
        for kind in need.accepts:
            if kind == "TYPE" and raw in program.types:
                t = program.types[raw]
                return OperandNode(need.name, "TYPE", raw, t, t.bits, need.line)
            if kind == "REG" and raw in program.registers:
                r = program.registers[raw]
                return OperandNode(need.name, "REG", raw, r, r.bits, need.line)
            if kind == "SREG":
                sreg = program.find_sreg(raw)
                if sreg is not None:
                    return OperandNode(need.name, "SREG", raw, sreg, sreg.bits, need.line)
            if kind == "SYMBOL" and raw in symbols:
                s = symbols[raw]
                return OperandNode(need.name, "SYMBOL", raw, s, s.bits, need.line)
            if kind == "LABEL" and raw in symbols:
                s = symbols[raw]
                return OperandNode(need.name, "LABEL", raw, s, s.bits, need.line)
            if kind == "INT" and re.fullmatch(r"[+-]?[0-9]+", raw):
                n = int(raw)
                bits = signed_int_bits(n) if n < 0 else unsigned_int_bits(n)
                return OperandNode(need.name, "INT", raw, n, bits, need.line)
            if kind == "IDENT" and not re.fullmatch(r"[+-]?[0-9]+", raw) and raw not in program.types and raw not in program.registers and program.find_sreg(raw) is None:
                return OperandNode(need.name, "IDENT", raw, raw, None, need.line)
            if kind == "STACK" and raw in symbols and isinstance(symbols[raw], StackInfo):
                s = symbols[raw]
                return OperandNode(need.name, "STACK", raw, s, s.reserve, need.line)
        if ("SYMBOL" in need.accepts or "LABEL" in need.accepts) and raw not in program.types and raw not in program.registers and program.find_sreg(raw) is None and not re.fullmatch(r"[+-]?[0-9]+", raw):
            raise SymbolPendingError(f"SYMBOL resolution is pending for {raw!r}", need.line)
        raise OperandTypeError(f"field {need.name!r} expected {', '.join(need.accepts)}, got {raw!r}", need.line)


class RuleNode:
    name: str
    line: int
    instructions: list[InstructionNode]

    def compile(self, macros: Mapping[str, MacroNode] | None = None) -> CompiledRule:
        pattern: list[NeedNode | LiteralNeedNode] = []
        needs: list[NeedNode] = []
        body_source: list[InstructionNode] = []
        for instruction in self.instructions:
            if instruction.kind == "need":
                item = compile_need_instruction(instruction)
                pattern.append(item)
                if isinstance(item, NeedNode):
                    needs.append(item)
            else:
                body_source.append(instruction)
        expanded_body_source = expand_macro_instructions(body_source, macros or {})
        body = compile_rule_body(expanded_body_source, macros or {})
        return CompiledRule(self.name, tuple(pattern), tuple(needs), tuple(expanded_body_source), body)


class Program:
    world: dict[str, str | list[str]]
    types: dict[str, TypeInfo]
    words: dict[str, WordInfo]
    registers: dict[str, RegisterInfo]
    sregs: dict[str, SubRegisterInfo]
    rules: dict[str, RuleNode]
    macros: dict[str, MacroNode] = field(default_factory=dict)

    def compile_rules(self) -> dict[str, CompiledRule]:
        return {name: rule.compile(self.macros) for name, rule in self.rules.items()}

    def find_sreg(self, raw: str) -> SubRegisterInfo | None:
        if raw in self.sregs:
            return self.sregs[raw]
        m = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z]+)", raw)
        if m:
            return self.sregs.get(f"{m.group(1)}[{m.group(2)}]")
        m = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\[([A-Za-z]+)\]", raw)
        if m:
            return self.sregs.get(f"{m.group(1)}[{m.group(2)}]")
        return None
