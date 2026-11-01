"""Semantic resolution and validation for the RIF MIR."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from gram import lexer
from rif_limits import resolve_limits

from Frontend import globals

from .instructions import CompiledRule, CompiledRuleSet, Instruction, Operand


class MIRSemanticError(ValueError):
    """A source-level semantic error with a useful MIR location."""


@dataclass(frozen=True)
class TokenRef:
    name: str
    token: lexer.Token


@dataclass(frozen=True)
class TableRef:
    table: str
    column: str
    index: int


@dataclass(frozen=True)
class TableLookupRef:
    table: str
    selector: str
    key: Any
    column: str
    selector_index: int
    index: int


@dataclass(frozen=True)
class RuleRef:
    name: str


def _where(instruction: Instruction) -> str:
    span = instruction.span
    if span.path is None:
        return "<memoria>"
    if span.line is None:
        return span.path
    return f"{span.path}:{span.line}:{span.column or 0}"


def _error(instruction: Instruction, message: str) -> MIRSemanticError:
    return MIRSemanticError(f"{_where(instruction)}: {message}")


def _resolve_token(instruction: Instruction, operand: Operand) -> Operand:
    value = operand.value
    if isinstance(value, bool):
        raise _error(instruction, "un token numérico no puede ser booleano.")
    if isinstance(value, int):
        token = lexer.Token.from_code(value)
        if token is None:
            raise _error(instruction, f"el código de token {value} no existe.")
        return replace(operand, resolved=TokenRef(str(value), token))
    if isinstance(value, str):
        token = lexer.Token.from_string(value)
        if token is None:
            raise _error(instruction, f"el token '{value}' no existe en lexer.Token.")
        return replace(operand, resolved=TokenRef(value, token))
    raise _error(instruction, f"referencia de token inválida: {value!r}.")


def _resolve_table(
    instruction: Instruction,
    operand: Operand,
    context: globals.TargetContext,
) -> Operand:
    try:
        table_name, column_name = operand.value
    except (TypeError, ValueError) as exc:
        raise _error(instruction, "TABLE_ACCESS no tiene tabla y columna.") from exc
    table = context.tables.get(table_name)
    if table is None:
        raise _error(instruction, f"la tabla '{table_name}' no existe.")
    try:
        index = table.columns[column_name]
    except KeyError as exc:
        raise _error(
            instruction,
            f"la columna '{column_name}' no existe en la tabla '{table_name}'.",
        ) from exc
    return replace(
        operand,
        resolved=TableRef(table_name, column_name, index),
    )


def _resolve_table_lookup(
    instruction: Instruction,
    operand: Operand,
    context: globals.TargetContext,
) -> Operand:
    try:
        table_name, selector, key, column_name = operand.value
    except (TypeError, ValueError) as exc:
        raise _error(instruction, "TABLE_LOOKUP no tiene tabla, selector, clave y columna.") from exc
    table = context.tables.get(table_name)
    if table is None:
        raise _error(instruction, f"la tabla '{table_name}' no existe.")
    try:
        selector_index = table.columns[selector]
    except KeyError as exc:
        raise _error(
            instruction,
            f"la columna selectora '{selector}' no existe en la tabla '{table_name}'.",
        ) from exc
    try:
        index = table.columns[column_name]
    except KeyError as exc:
        raise _error(
            instruction,
            f"la columna '{column_name}' no existe en la tabla '{table_name}'.",
        ) from exc
    try:
        table.require_unique(selector)
        row_index = table.lookup_unique(selector, key)
    except (TypeError, ValueError) as exc:
        raise _error(instruction, str(exc)) from exc
    if row_index is None:
        raise _error(
            instruction,
            f"la clave {key!r} no existe en {table_name}.{selector}.",
        )
    return replace(
        operand,
        resolved=TableLookupRef(
            table_name,
            selector,
            key,
            column_name,
            selector_index,
            index,
        ),
    )


def _resolve_table_capture(
    instruction: Instruction,
    operand: Operand,
    context: globals.TargetContext,
) -> Operand:
    try:
        table_name, selector, column = operand.value
    except (TypeError, ValueError) as exc:
        raise _error(instruction, "DLOAD requiere tabla, columna de búsqueda y campo.") from exc
    selector_ref = _resolve_table(
        instruction, Operand("table_access", (table_name, selector)), context
    ).resolved
    value_ref = _resolve_table(
        instruction, Operand("table_access", (table_name, column)), context
    ).resolved
    try:
        context.tables[table_name].require_unique(selector)
    except ValueError as exc:
        raise _error(instruction, str(exc)) from exc
    return replace(operand, resolved=(selector_ref, value_ref))


def _resolve_operand(
    instruction: Instruction,
    operand: Operand,
    context: globals.TargetContext,
    rule_names: frozenset[str],
) -> Operand:
    if operand.kind == "token":
        return _resolve_token(instruction, operand)
    if operand.kind == "table_access":
        return _resolve_table(instruction, operand, context)
    if operand.kind == "table_lookup":
        return _resolve_table_lookup(instruction, operand, context)
    if operand.kind == "table_capture":
        return _resolve_table_capture(instruction, operand, context)
    if operand.kind == "rule":
        if operand.value not in rule_names:
            raise _error(instruction, f"la Rule '{operand.value}' no existe.")
        return replace(operand, resolved=RuleRef(operand.value))
    if operand.kind == "frame":
        rows = tuple(
            tuple(_resolve_operand(instruction, item, context, rule_names) for item in row)
            for row in operand.value
        )
        return replace(operand, value=rows, resolved=rows)
    if operand.kind == "reservation_access":
        if not isinstance(operand.value, str) or not operand.value:
            raise _error(instruction, "el nombre de reserva no es válido.")
    if operand.kind in {
        "distance",
        "vdistance",
        "reservation_address",
        "reservation_vaddress",
        "reservation_distance",
        "reservation_vdistance",
        "reservation_width",
        "reservation_vwidth",
    }:
        if not isinstance(operand.value, str) or not operand.value:
            raise _error(instruction, "el nombre de reserva o etiqueta no es válido.")
    return operand


_ARITY: dict[str, tuple[int, int | None]] = {
    "table_matcher": (2, 2),
    "consumer": (1, 1),
    "store": (1, None),
    "nibbles": (2, 2),
    "emit": (8, 8),
    "eword": (1, 1),
    "pad": (1, 1),
    "align": (1, 1),
    "kw": (1, 1),
    "jump": (1, 1),
    "save": (1, 1),
    "load": (1, 1),
    "reserve": (2, 2),
    "write_res": (2, 2),
    "drop_res": (1, 1),
    "emit_res": (1, 1),
    "jumpif": (2, 2),
    "break": (0, 0),
    "error": (1, 1),
    "frame": (1, 1),
    "fit": (1, 1),
    "fit_exact": (1, 1),
    "fit_not": (1, 1),
    "vpad": (1, 1),
    "vreserve": (2, 2),
    "dpush": (1, 1),
    "dget": (1, 1),
    "dpop": (0, 0),
    "bits": (2, 2),
    "read_bits": (2, 2),
    "patch_bits": (3, 3),
    "valign": (1, 1),
}


def _validate_instruction(
    instruction: Instruction,
    context: globals.TargetContext,
    rule_names: frozenset[str],
) -> Instruction:
    minimum, maximum = _ARITY.get(instruction.opcode, (0, None))
    count = len(instruction.operands)
    if count < minimum or (maximum is not None and count > maximum):
        expected = str(minimum) if maximum == minimum else f"{minimum}..{maximum}"
        raise _error(
            instruction,
            f"'{instruction.opcode}' requiere {expected} operandos; recibió {count}.",
        )

    operands = tuple(
        _resolve_operand(instruction, operand, context, rule_names)
        for operand in instruction.operands
    )

    if instruction.opcode == "table_matcher":
        table_ref = operands[0].resolved
        if isinstance(table_ref, TableRef):
            try:
                context.tables[table_ref.table].require_unique(table_ref.column)
            except ValueError as exc:
                raise _error(instruction, str(exc)) from exc
    elif instruction.opcode == "nibbles":
        for operand in operands:
            if operand.kind == "number" and operand.width not in {None, 4}:
                raise _error(instruction, "cada campo de nibbles debe tener exactamente 4 bits.")
    elif instruction.opcode == "emit":
        for operand in operands:
            if operand.kind == "number" and operand.value not in {0, 1}:
                raise _error(instruction, "cada campo de emit debe ser 0 o 1.")
    elif instruction.opcode == "eword":
        operand = operands[0]
        if operand.kind == "number" and context.config is not None:
            if context.config.wordsize > resolve_limits().cap(256 << 20) * 8:
                raise _error(instruction, "wordsize excede el límite de recursos configurado.")
            if operand.value >= (1 << context.config.wordsize):
                raise _error(
                    instruction,
                    f"el valor de eword no cabe en wordsize={context.config.wordsize}.",
                )
    elif instruction.opcode == "jumpif":
        if operands[1].kind not in {"bool", "call"}:
            raise _error(instruction, "JMPIF requiere BOOL o #call como condición.")
    elif instruction.opcode in {"reserve", "vreserve"}:
        size = operands[1]
        if size.kind not in {"number", "decimal"} or not isinstance(size.value, int) or size.value <= 0:
            raise _error(instruction, f"{instruction.opcode.upper()} requiere un tamaño entero mayor que cero.")
    elif instruction.opcode == "vpad":
        size = operands[0]
        if size.kind not in {"number", "decimal"} or not isinstance(size.value, int) or size.value <= 0:
            raise _error(instruction, "VPAD requiere un tamaño entero mayor que cero.")
    elif instruction.opcode in {"fit", "fit_exact", "fit_not"}:
        space = operands[0]
        if space.kind in {"number", "decimal"}:
            if not isinstance(space.value, int) or space.value <= 0 or space.value % 2:
                raise _error(instruction, "FIT requiere un ancho positivo y múltiplo de dos.")
        elif space.kind not in {
            "table_access", "table_lookup", "size", "vsize", "alignment",
            "data_pop", "data_peek", "data_depth", "reservation_width", "reservation_vwidth",
        }:
            raise _error(instruction, "FIT requiere un ancho numérico o un acceso de tabla.")
    elif instruction.opcode in {"pad", "align", "valign"}:
        size = operands[0]
        if size.kind not in {"number", "decimal"} or not isinstance(size.value, int) or size.value <= 0:
            raise _error(
                instruction,
                f"{instruction.opcode.upper()} requiere un tamaño entero mayor que cero.",
            )
    elif instruction.opcode in {"bits", "read_bits", "patch_bits"}:
        checked = operands[1]
        if checked.kind in {"number", "decimal"} and (
            not isinstance(checked.value, int) or checked.value <= 0
        ):
            raise _error(instruction, "El ancho de bits debe ser un entero positivo.")
        if instruction.opcode in {"read_bits", "patch_bits"}:
            offset = operands[0]
            if offset.kind in {"number", "decimal"} and (
                not isinstance(offset.value, int) or offset.value < 0
            ):
                raise _error(instruction, "El offset debe ser un entero no negativo.")

    return replace(instruction, operands=operands)


def resolve_rule(
    rule: CompiledRule,
    context: globals.TargetContext | None = None,
    rule_names: frozenset[str] | None = None,
) -> CompiledRule:
    selected_context = context or globals.snapshot_target_context()
    selected_rules = rule_names or frozenset(globals.RULES)
    return replace(
        rule,
        instructions=tuple(
            _validate_instruction(instruction, selected_context, selected_rules)
            for instruction in rule.instructions
        ),
    )


def resolve_program(program: CompiledRuleSet) -> CompiledRuleSet:
    """Resolve names and validate every instruction in a compiled program."""

    rule_names = frozenset(program.rules)
    return CompiledRuleSet(
        {
            name: resolve_rule(rule, program.context, rule_names)
            for name, rule in program.rules.items()
        },
        context=program.context,
    )


__all__ = [
    "MIRSemanticError",
    "TokenRef",
    "TableRef",
    "TableLookupRef",
    "RuleRef",
    "resolve_rule",
    "resolve_program",
]
