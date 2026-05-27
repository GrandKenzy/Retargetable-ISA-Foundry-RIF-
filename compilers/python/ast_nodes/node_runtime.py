from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any, Sequence

from ..errors import (
    EmitError,
    LiteralMismatchError,
    OperandCountError,
    OperandTypeError,
    RuleConditionError,
    RuleExecutionError,
    SymbolPendingError,
)

from .node_info import RegisterInfo, StackInfo, SubRegisterInfo, SymbolInfo, TypeInfo, WordInfo
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
    NonsfamilyNode,
    OffNode,
    OnNode,
    OperandNode,
    PendingNode,
    RefNode,
    StrictNode,
    StringNode,
    SwitchNode,
)
from .node_utils import signed_int_bits, unsigned_int_bits


class RuleContext:
    program: Program
    operands: dict[str, OperandNode]
    symbols: dict[str, SymbolInfo]
    output: bytearray = field(default_factory=bytearray)
    pc: int = 0


def execute_nodes(nodes: Sequence[Any], context: RuleContext) -> None:
    for node in nodes:
        execute_node(node, context)


def check_and_wrap_operand(need_name: str, accepts: tuple[str, ...], val: Any, program: Program, line: int) -> OperandNode:
    if isinstance(val, OperandNode):
        if val.kind in accepts:
            return replace(val, name=need_name)
        raise OperandTypeError(f"Call expected operand of type {', '.join(accepts)}, got {val.kind}", line)
    
    if "REG" in accepts and isinstance(val, RegisterInfo):
        return OperandNode(need_name, "REG", val.name, val, val.bits, line)
    if "SREG" in accepts and isinstance(val, SubRegisterInfo):
        return OperandNode(need_name, "SREG", val.name, val, val.bits, line)
    if "TYPE" in accepts and isinstance(val, TypeInfo):
        return OperandNode(need_name, "TYPE", val.name, val, val.bits, line)
    if "SYMBOL" in accepts and isinstance(val, SymbolInfo):
        return OperandNode(need_name, "SYMBOL", val.name, val, val.bits, line)
    if "INT" in accepts and isinstance(val, int):
        bits = signed_int_bits(val) if val < 0 else unsigned_int_bits(val)
        return OperandNode(need_name, "INT", str(val), val, bits, line)
        
    raise OperandTypeError(f"Call expected operand of type {', '.join(accepts)}, got {type(val).__name__}", line)


def register_family(operand: Any) -> str | None:
    if isinstance(operand, OperandNode):
        if operand.kind == "REG":
            return operand.value.name
        if operand.kind == "SREG":
            return operand.value.family
    if isinstance(operand, RegisterInfo):
        return operand.name
    if isinstance(operand, SubRegisterInfo):
        return operand.family
    return None


def execute_node(node: Any, context: RuleContext) -> None:
    if isinstance(node, CheckNode):
        if not eval_condition(node.condition, context):
            raise RuleConditionError(f"condition {node.condition.kind!r} failed", node.line)
        return
    if isinstance(node, EmitNode):
        context.output.extend(eval_emit(node, context))
        return
    if isinstance(node, SwitchNode):
        value = eval_expr(node.expr, context)
        for case in node.cases:
            if case_matches(value, case.value, context):
                execute_nodes(case.body, context)
                return
        return
    if isinstance(node, OnNode):
        if eval_condition(node.condition, context):
            execute_nodes(node.body, context)
        return
    if isinstance(node, ErrorNode):
        raise RuleExecutionError(node.message, node.line)
    if isinstance(node, OffNode):
        return
    if isinstance(node, CallNode):
        rules = context.program.compile_rules()
        if node.rule_name not in rules:
            raise RuleExecutionError(f"unknown rule {node.rule_name!r}", node.line)
        compiled_rule = rules[node.rule_name]
        
        if len(node.args) != len(compiled_rule.pattern):
            raise OperandCountError(f"rule {node.rule_name!r} expects {len(compiled_rule.pattern)} fields, got {len(node.args)}")
            
        called_operands = {}
        for idx, need_node in enumerate(compiled_rule.pattern):
            arg_expr = node.args[idx]
            val = eval_expr(arg_expr, context)
            
            if isinstance(need_node, LiteralNeedNode):
                val_str = val.raw if isinstance(val, OperandNode) else str(val)
                if val_str != need_node.value:
                    raise LiteralMismatchError(f"call to {node.rule_name!r} expected literal {need_node.value!r}, got {val_str!r}", node.line)
                continue
                
            called_operands[need_node.name] = check_and_wrap_operand(
                need_node.name, need_node.accepts, val, context.program, node.line
            )
            
        called_context = RuleContext(context.program, called_operands, context.symbols, pc=context.pc)
        execute_nodes(compiled_rule.body, called_context)
        context.output.extend(called_context.output)
        context.pc = called_context.pc
        return
    if isinstance(node, NonsfamilyNode):
        left_val = eval_expr(node.left, context)
        right_val = eval_expr(node.right, context)
        
        left_family = register_family(left_val)
        right_family = register_family(right_val)
        
        if left_family is not None and right_family is not None:
            if left_family == right_family:
                raise RuleExecutionError(f"registers belong to the same family: {left_family}", node.line)
        return
    if isinstance(node, AssignNode):
        val = eval_expr(node.expr, context)
        context.symbols[node.name] = val
        return
    if isinstance(node, MemskipNode):
        val = int_value(eval_expr(node.arg, context))
        context.pc += val
        return
    if isinstance(node, MarkNode):
        if node.ref.root not in context.operands:
            raise RuleExecutionError(f"unknown operand {node.ref.root!r}", node.line)
        operand = context.operands[node.ref.root]
        if operand.kind not in {"IDENT", "STACK"}:
            raise RuleExecutionError(f"mark instruction expects IDENT or STACK operand, got {operand.kind}", node.line)
        stack_name = operand.raw
        if stack_name not in context.symbols:
            context.symbols[stack_name] = StackInfo(name=stack_name)
        elif not isinstance(context.symbols[stack_name], StackInfo):
            raise RuleExecutionError(f"symbol {stack_name!r} is already defined and is not a STACK", node.line)
        stack_info = context.symbols[stack_name]
        if node.ref.attr == "bottom":
            stack_info.bottom = context.pc
        elif node.ref.attr == "top":
            stack_info.top = context.pc
            stack_info.reserve = stack_info.top - stack_info.bottom
        return
    if isinstance(node, MultipleNode):
        left_val = int_value(eval_expr(node.left, context))
        right_val = int_value(eval_expr(node.right, context))
        if left_val % right_val != 0:
            raise RuleExecutionError(f"value {left_val} is not a multiple of {right_val}", node.line)
        return
    if isinstance(node, StrictNode):
        num = int_value(eval_expr(node.val, context))
        match_u = re.match(r"^u(\d+)$", node.type_spec, re.IGNORECASE)
        match_i = re.match(r"^[is](\d+)$", node.type_spec, re.IGNORECASE)
        if match_u:
            bits = int(match_u.group(1))
            if not (0 <= num <= (1 << bits) - 1):
                raise RuleExecutionError(f"value {num} is not a strict {node.type_spec}", node.line)
        elif match_i:
            bits = int(match_i.group(1))
            limit = 1 << (bits - 1)
            if not (-limit <= num <= limit - 1):
                raise RuleExecutionError(f"value {num} is not a strict {node.type_spec}", node.line)
        else:
            if node.type_spec in context.program.types:
                t = context.program.types[node.type_spec]
                if not (-(1 << (t.bits - 1)) <= num <= (1 << t.bits) - 1):
                    raise RuleExecutionError(f"value {num} does not fit strict type {node.type_spec}", node.line)
            else:
                raise RuleExecutionError(f"unknown strict type specifier {node.type_spec!r}", node.line)
        return
    if isinstance(node, PendingNode):
        raise SymbolPendingError("pending instruction encountered", node.line)
    raise RuleExecutionError(f"unknown compiled node {type(node).__name__}")


def eval_condition(node: ConditionNode, context: RuleContext) -> bool:
    if node.kind == "or":
        return any(eval_condition(arg, context) for arg in node.args)
    if node.kind == "and":
        return all(eval_condition(arg, context) for arg in node.args)
    if node.kind == "not":
        return not eval_condition(node.args[0], context)
    if node.kind == "truthy":
        return bool(eval_expr(node.args[0], context))
    if node.kind in {"exists", "this"}:
        return eval_exists(node.args[0], context, node.line)
    if node.kind == "fits":
        left = eval_expr(node.args[0], context)
        right = eval_expr(node.args[1], context)
        bits = bits_of(right)
        
        # Check if left is a register/subregister
        is_reg_or_sreg = False
        if isinstance(left, OperandNode):
            is_reg_or_sreg = left.kind in {"REG", "SREG"}
        elif isinstance(left, (RegisterInfo, SubRegisterInfo)):
            is_reg_or_sreg = True
            
        if is_reg_or_sreg:
            return bits_of(left) <= bits
            
        value = int_value(left)
        return integer_fits(value, bits)
    if node.kind == "unbsize":
        left = eval_expr(node.args[0], context)
        right = eval_expr(node.args[1], context)
        bits = bits_of(right)
        value = int_value(left)
        return 0 <= value <= (1 << bits) - 1
    if node.kind == "has_subset":
        left = eval_expr(node.args[0], context)
        right = eval_expr(node.args[1], context)
        size = bits_of(right)
        if isinstance(left, OperandNode):
            if left.kind == "REG":
                return left.value.bits == size or any(sub.bits == size for sub in left.value.subregs.values())
            if left.kind == "SREG":
                return left.value.bits == size
        if isinstance(left, RegisterInfo):
            return left.bits == size or any(sub.bits == size for sub in left.subregs.values())
        if isinstance(left, SubRegisterInfo):
            return left.bits == size
        return False
    if node.kind in {"iarch", "narch"}:
        allowed = []
        for arg in node.args:
            val = eval_expr(arg, context)
            if isinstance(val, OperandNode):
                allowed.append(val.raw.lower())
            else:
                allowed.append(str(val).lower())
        
        # Determine current architecture: default to "x86_64"
        current_arch = "x86_64"
        
        is_match = False
        for arch in allowed:
            if arch in {"x86_64", "amd64"} and current_arch == "x86_64":
                is_match = True
            elif arch == "x86" and current_arch == "x86":
                is_match = True
            elif arch == current_arch:
                is_match = True
                
        if node.kind == "iarch":
            return is_match
        else:
            return not is_match
    raise RuleExecutionError(f"unknown condition {node.kind!r}", node.line)


def eval_exists(expr: Any, context: RuleContext, line: int) -> bool:
    if isinstance(expr, RefNode):
        if expr.root in context.operands:
            operand = context.operands[expr.root]
            if operand.kind in {"REG", "SREG"}:
                return True
            if operand.kind == "SYMBOL":
                raise SymbolPendingError(f"SYMBOL exists is pending for {operand.raw!r}", operand.line)
            return False
        if expr.root in context.program.registers or context.program.find_sreg(expr.root) is not None:
            return True
        if expr.root in context.symbols:
            raise SymbolPendingError(f"SYMBOL exists is pending for {expr.root!r}", expr.line)
        raise SymbolPendingError(f"SYMBOL exists is pending for {expr.root!r}", expr.line)
    value = eval_expr(expr, context)
    if isinstance(value, OperandNode):
        if value.kind in {"REG", "SREG"}:
            return True
        if value.kind == "SYMBOL":
            raise SymbolPendingError(f"SYMBOL exists is pending for {value.raw!r}", value.line)
    return False


def alignment_padding(offset: int, align: int, pad: int) -> bytes:
    if align <= 0:
        return b""
    missing = (-offset) % align
    if missing == 0:
        return b""
    return bytes([pad]) * missing


def eval_emit(node: EmitNode, context: RuleContext) -> bytes:
    res = b""
    if node.mode == "hex":
        raw = node.args[0]
        res = bytes.fromhex(raw)
    elif node.mode == "word":
        value = eval_expr(node.args[0], context)
        if not isinstance(value, WordInfo):
            raise EmitError(f"unknown word {node.args[0].raw!r}", node.line)
        prefix = alignment_padding(context.pc, value.align, value.pad)
        res = prefix + value.data
    elif node.mode == "cbits":
        bits = "".join(bits_fragment(arg, context, node.line) for arg in node.args)
        if len(bits) % 8 != 0:
            raise EmitError("cbits output must be byte aligned", node.line)
        res = bytes(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8))
    elif node.mode == "lit":
        value = int_value(eval_expr(node.args[0], context))
        bits = eval_size(node.args[1], context)
        if not integer_fits(value, bits):
            raise EmitError(f"literal {value} does not fit in {bits} bits", node.line)
        res = integer_to_bytes(value, bits, context)
    elif node.mode == "addr":
        value = int_value(eval_expr(node.args[0], context))
        bits = eval_size(node.args[1], context)
        if value < 0 or value > (1 << bits) - 1:
            raise EmitError(f"address {value} does not fit in {bits} bits", node.line)
        res = integer_to_bytes(value, bits, context)
    elif node.mode == "jaddr":
        target_addr = int_value(eval_expr(node.args[0], context))
        bits = eval_size(node.args[1], context)
        offset = target_addr - (context.pc + (bits // 8))
        if not integer_fits(offset, bits):
            raise EmitError(f"relative offset {offset} does not fit in {bits} bits", node.line)
        res = integer_to_bytes(offset, bits, context)
    elif node.mode == "fill":
        val_expr = eval_expr(node.args[0], context)
        count_expr = eval_expr(node.args[1], context)
        count = int_value(count_expr)
        if isinstance(val_expr, str):
            try:
                b = bytes.fromhex(val_expr)
            except ValueError:
                raise EmitError(f"invalid hex value in fill: {val_expr}", node.line)
        else:
            b = bytes([int_value(val_expr)])
        res = b * count
    else:
        raise EmitError(f"unknown emmit mode {node.mode!r}", node.line)
    
    context.pc += len(res)
    return res


def eval_expr(expr: Any, context: RuleContext) -> Any:
    if isinstance(expr, CalcdistNode):
        left_val = int_value(eval_expr(expr.left, context))
        right_val = int_value(expr.right, context)
        diff = right_val - left_val
        if -128 <= diff <= 127:
            return 8
        elif -32768 <= diff <= 32767:
            return 16
        else:
            return 32
    if isinstance(expr, IntNode):
        return expr.value
    if isinstance(expr, StringNode):
        return expr.value
    if isinstance(expr, RefNode):
        if expr.root == ".":
            return context.pc
        if expr.root == "section":
            return context.symbols.get("section", ".data")
        if expr.root in context.operands:
            operand = context.operands[expr.root]
            if expr.attr is None:
                return operand
            if expr.attr == "type":
                return operand.kind
            if expr.attr == "bits":
                return operand.bits
            return operand.value.attr(expr.attr)
        if expr.root in context.program.types:
            value = context.program.types[expr.root]
            return value if expr.attr is None else value.attr(expr.attr)
        if expr.root in context.program.registers:
            value = context.program.registers[expr.root]
            return value if expr.attr is None else value.attr(expr.attr)
        if expr.root in context.program.words:
            value = context.program.words[expr.root]
            return value if expr.attr is None else value.attr(expr.attr)
        sreg = context.program.find_sreg(expr.root)
        if sreg is not None:
            return sreg if expr.attr is None else sreg.attr(expr.attr)
        if expr.root in context.symbols:
            value = context.symbols[expr.root]
            return value if expr.attr is None else value.attr(expr.attr)
        if expr.attr is None:
            return expr.root
        raise RuleExecutionError(f"unknown reference {expr.raw!r}", expr.line)
    return expr


def case_matches(value: Any, case_value: Any, context: RuleContext) -> bool:
    if isinstance(case_value, (RefNode, IntNode, StringNode)):
        case_value = eval_expr(case_value, context)
    if isinstance(value, OperandNode):
        value = value.kind
    if isinstance(case_value, OperandNode):
        case_value = case_value.kind
    if isinstance(value, int):
        if isinstance(case_value, str) and re.fullmatch(r"[+-]?[0-9]+", case_value):
            return value == int(case_value)
        return value == case_value
    return str(value) == str(case_value)


def bits_fragment(value: Any, context: RuleContext, line: int) -> str:
    if isinstance(value, StringNode):
        bits = value.value
    else:
        resolved = eval_expr(value, context)
        if isinstance(resolved, OperandNode):
            raise EmitError("operand cannot be used directly as cbits", line)
        if isinstance(resolved, int):
            bits = str(resolved)
        else:
            bits = str(resolved)
    if not re.fullmatch(r"[01]+", bits):
        raise EmitError(f"invalid bit fragment {bits!r}", line)
    return bits


def eval_size(value: Any, context: RuleContext) -> int:
    resolved = eval_expr(value, context)
    if isinstance(resolved, int):
        if resolved <= 0 or resolved % 8 != 0:
            raise EmitError(f"invalid byte size {resolved}")
        return resolved
    return bits_of(resolved)


def bits_of(value: Any) -> int:
    if isinstance(value, OperandNode):
        if value.bits is None:
            raise RuleExecutionError(f"operand {value.name!r} has no bits", value.line)
        return value.bits
    if isinstance(value, TypeInfo):
        return value.bits
    if isinstance(value, RegisterInfo):
        return value.bits
    if isinstance(value, SubRegisterInfo):
        return value.bits
    if isinstance(value, SymbolInfo):
        return value.bits
    if isinstance(value, WordInfo):
        return len(value.data) * 8
    if isinstance(value, int):
        if value <= 0:
            raise RuleExecutionError("invalid bit size")
        return value
    raise RuleExecutionError(f"cannot read bits from {value!r}")


def int_value(value: Any) -> int:
    if isinstance(value, OperandNode):
        if value.kind != "INT":
            raise RuleExecutionError(f"operand {value.name!r} is not an INT", value.line)
        return int(value.value)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    raise RuleExecutionError(f"expected integer, got {value!r}")


def integer_fits(value: int, bits: int) -> bool:
    if bits <= 0:
        return False
    if value >= 0:
        return value <= (1 << bits) - 1
    return -(1 << (bits - 1)) <= value <= (1 << (bits - 1)) - 1


def integer_to_bytes(value: int, bits: int, context: RuleContext) -> bytes:
    if bits <= 0 or bits % 8 != 0:
        raise EmitError(f"invalid byte size {bits}")
    mask = (1 << bits) - 1
    n = value & mask
    endian = str(context.program.world.get("endianess", "little"))
    if endian not in {"little", "big"}:
        raise EmitError(f"invalid endianess {endian!r}")
    return n.to_bytes(bits // 8, endian, signed=False)
