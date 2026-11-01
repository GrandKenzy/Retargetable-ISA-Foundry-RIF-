"""Small executable runtime for the resolved RIF MIR."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from gram import lexer
from rif_limits import resolve_limits

from .emitter import BitEmitter, BitField
from .instructions import CompiledRuleSet, Instruction, Operand
from .semantic import RuleRef, TableLookupRef, TableRef, TokenRef


MAX_RULE_CALL_DEPTH = 256
MAX_DYNAMIC_WIDTH_BYTES = 256 << 20


class RIFRuntimeError(RuntimeError):
    """An execution failure associated with a MIR instruction."""


class _BreakFlow(Exception):
    pass


@dataclass(frozen=True)
class ExecutionResult:
    rule: str
    position: int
    last_token: lexer.TokenType | None
    stored_token: lexer.TokenType | None
    buffer: bytes


@dataclass(frozen=True)
class RuleTrace:
    """Physical and virtual spans produced by one Rule invocation."""

    name: str
    start: int
    bits: int
    end: int
    padding_bits: int
    virtual_start: int
    virtual_bits: int
    virtual_end: int
    virtual_padding_bits: int

    @property
    def emitted_bits(self) -> int:
        return self.bits


@dataclass(frozen=True)
class SymbolAddress:
    """A user-defined symbol captured at one physical/virtual cursor pair."""

    name: str
    section: str | None
    physical_offset_bits: int
    virtual_offset_bits: int

    @property
    def physical_offset(self) -> int:
        """Return the physical byte offset when the cursor is byte-aligned."""

        return self.physical_offset_bits // 8

    @property
    def virtual_offset(self) -> int:
        """Return the virtual byte offset when the cursor is byte-aligned."""

        return self.virtual_offset_bits // 8


@dataclass(frozen=True)
class Fixup:
    """A deferred patch against one named symbol and reserved bit range."""

    kind: str
    symbol: str
    reservation: str
    section: str | None
    offset_bits: int
    width_bits: int
    next_virtual_bits: int


@dataclass
class _RuleTraceState:
    name: str
    start: int
    virtual_start: int
    padding_bits: int = 0
    virtual_padding_bits: int = 0


class RIFMachine:
    """Execute the resolved subset of RIF instructions over input tokens."""

    def __init__(
        self,
        program: CompiledRuleSet,
        *,
        emitter: BitEmitter | None = None,
        section_name: str | None = None,
    ) -> None:
        self.program = program
        self.context = program.context
        self.emitter = emitter or BitEmitter(
            wordsize=self.context.config.wordsize if self.context.config else 32
        )
        self.section_name = section_name
        self.tokens: tuple[lexer.TokenType, ...] = ()
        self.position = 0
        self.last_token: lexer.TokenType | None = None
        self.stored_token: lexer.TokenType | None = None
        self.storage: dict[str, lexer.TokenType] = {}
        self.stack: dict[int, Any] | None = (
            {} if self.context.stack_size is not None else None
        )
        self.datastack: list[Any] = []
        self.selected_rows: dict[str, int] = {}
        self.rule_traces: list[RuleTrace] = []
        self.last_rule_trace: RuleTrace | None = None
        self.rule_addresses: dict[str, int] = {}
        self.virtual_rule_addresses: dict[str, int] = {}
        self.symbols: dict[str, SymbolAddress] = {}
        self.fixups: list[Fixup] = []
        self.variant_stack: list[str] = []
        self._trace_stack: list[_RuleTraceState] = []
        self._rule_depth = 0

    @property
    def config(self) -> Any:
        """Expose target configuration for external MIR result inspection."""

        return self.context.config

    @property
    def virtual_position(self) -> int:
        """Expose the active emitter's virtual position."""

        return self.emitter.virtual_position

    def execute(
        self,
        rule_name: str,
        tokens: Iterable[lexer.TokenType],
    ) -> ExecutionResult:
        if rule_name not in self.program.rules:
            raise RIFRuntimeError(f"La Rule '{rule_name}' no existe en el MIR.")
        self.storage.clear()
        self.datastack.clear()
        self.selected_rows.clear()
        self.rule_traces.clear()
        self.last_rule_trace = None
        self.rule_addresses.clear()
        self.virtual_rule_addresses.clear()
        self.symbols.clear()
        self.fixups.clear()
        self.variant_stack.clear()
        self._trace_stack.clear()
        self._rule_depth = 0
        return self.execute_line(rule_name, tokens)

    def execute_line(
        self,
        rule_name: str,
        tokens: Iterable[lexer.TokenType],
    ) -> ExecutionResult:
        """Execute one external MIR instruction while keeping machine state.

        ``execute`` starts a fresh standalone run. External MIR programs use
        this method for each logical line so reservations, saved tokens and
        selected table rows can survive between instructions.
        """
        if rule_name not in self.program.rules:
            raise RIFRuntimeError(f"La Rule '{rule_name}' no existe en el MIR.")
        self.tokens = tuple(tokens)
        self.position = 0
        self.last_token = None
        self.stored_token = None
        self._execute_rule(rule_name)
        return ExecutionResult(
            rule=rule_name,
            position=self.position,
            last_token=self.last_token,
            stored_token=self.stored_token,
            buffer=self.emitter.buffer.to_bytes(),
        )

    def _current(self) -> lexer.TokenType:
        if self.position >= len(self.tokens):
            raise RIFRuntimeError("Se alcanzó EOF mientras se ejecutaba una Rule.")
        token = self.tokens[self.position]
        if token.token == lexer.Token.EOF:
            raise RIFRuntimeError("Se alcanzó EOF mientras se ejecutaba una Rule.")
        return token

    @staticmethod
    def _matches_token(token: lexer.TokenType, reference: TokenRef) -> bool:
        return token.token == reference.token

    def _consume_token(self, reference: TokenRef) -> lexer.TokenType:
        token = self._current()
        if not self._matches_token(token, reference):
            raise RIFRuntimeError(
                f"Se esperaba Token.{reference.token.name}, pero se encontró "
                f"Token.{token.token.name} ({token.value!r})."
            )
        self.position += 1
        self.last_token = token
        return token

    def _table_value(self, reference: TableRef) -> Any:
        if reference.table not in self.selected_rows:
            raise RIFRuntimeError(
                f"La tabla '{reference.table}' no tiene una fila seleccionada."
            )
        table = self.context.tables[reference.table]
        row = table.matrix[self.selected_rows[reference.table]]
        return row[reference.index]

    def _table_lookup_value(self, reference: TableLookupRef) -> Any:
        table = self.context.tables[reference.table]
        try:
            row_index = table.lookup_unique(reference.selector, reference.key)
        except ValueError as exc:
            raise RIFRuntimeError(str(exc)) from exc
        if row_index is None:
            raise RIFRuntimeError(
                f"La clave {reference.key!r} no existe en "
                f"{reference.table}.{reference.selector}."
            )
        return table.matrix[row_index][reference.index]

    def _value(self, operand: Operand, source: Instruction | None = None) -> Any:
        if operand.kind == "data_pop":
            if not self.datastack:
                raise RIFRuntimeError("DLOAD requiere un valor en el datastack.")
            return self.datastack.pop()
        if operand.kind == "data_peek":
            if not self.datastack:
                raise RIFRuntimeError("DPEEK requiere un valor en el datastack.")
            return self.datastack[-1]
        if operand.kind == "data_depth":
            return len(self.datastack)
        if operand.kind == "size":
            return self.emitter.buffer.bit_length
        if operand.kind == "vsize":
            return self.emitter.virtual_position
        if operand.kind == "alignment":
            return self._current_alignment()
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
            return self._address_value(operand.kind, str(operand.value))
        if operand.kind == "table_access":
            if not isinstance(operand.resolved, TableRef):
                raise RIFRuntimeError("TABLE_ACCESS no fue resuelto semánticamente.")
            return self._table_value(operand.resolved)
        if operand.kind == "table_lookup":
            if not isinstance(operand.resolved, TableLookupRef):
                raise RIFRuntimeError("TABLE_LOOKUP no fue resuelto semánticamente.")
            return self._table_lookup_value(operand.resolved)
        if operand.kind == "reservation_access":
            return self.emitter.query(str(operand.value)).value
        if operand.kind == "call":
            raise RIFRuntimeError(
                f"No existe una función nativa registrada para #call[{operand.value}]."
            )
        return operand.value

    def _current_alignment(self) -> int:
        config = self.context.config
        if config is None:
            return 0
        section = self.section_name or config.defaultsection
        return config.sectionalign.get(section, 0)

    def _address_value(self, kind: str, name: str) -> int:
        regions = self.emitter.buffer.regions
        virtual = kind in {
            "vdistance",
            "reservation_vaddress",
            "reservation_vdistance",
            "reservation_vwidth",
        }
        if kind in {
            "reservation_address",
            "reservation_vaddress",
            "reservation_distance",
            "reservation_vdistance",
            "reservation_width",
            "reservation_vwidth",
        }:
            if virtual:
                try:
                    address = self.emitter.virtual_query(name).offset
                except KeyError as exc:
                    raise RIFRuntimeError(f"No existe una reserva virtual llamada '{name}'.") from exc
            else:
                if name not in regions:
                    raise RIFRuntimeError(f"No existe una reserva llamada '{name}'.")
                address = regions[name].offset
        else:
            if virtual and name in self.emitter.virtual_regions:
                address = self.emitter.virtual_query(name).offset
            elif virtual and name in self.virtual_rule_addresses:
                address = self.virtual_rule_addresses[name]
            elif not virtual and name in regions:
                address = regions[name].offset
            elif not virtual and name in self.rule_addresses:
                address = self.rule_addresses[name]
            elif name in self.symbols:
                symbol = self.symbols[name]
                address = (
                    symbol.virtual_offset_bits if virtual
                    else symbol.physical_offset_bits
                )
            else:
                raise RIFRuntimeError(f"No existe una reserva o etiqueta llamada '{name}'.")
        if kind in {"reservation_width", "reservation_vwidth"}:
            return self.emitter.virtual_query(name).width if virtual else regions[name].width
        if kind in {
            "distance",
            "vdistance",
            "reservation_distance",
            "reservation_vdistance",
        }:
            current = self.emitter.virtual_position if virtual else self.emitter.buffer.bit_length
            return current - address
        return address

    def _record_padding(self, width: int) -> None:
        if self._trace_stack:
            self._trace_stack[-1].padding_bits += width

    def _record_virtual_padding(self, width: int) -> None:
        if self._trace_stack:
            self._trace_stack[-1].virtual_padding_bits += width

    def _bit_integer(
        self, operand: Operand, source: Instruction, name: str, *, positive: bool
    ) -> int:
        value = self._value(operand, source)
        if isinstance(value, bool) or not isinstance(value, int) or value < (1 if positive else 0):
            minimum = "positivo" if positive else "no negativo"
            raise RIFRuntimeError(f"{name.capitalize()} debe ser un entero {minimum}.")
        return value

    def _fit_width(self, operand: Operand, source: Instruction) -> int:
        value = (
            self._value(Operand("data_peek", None), source)
            if operand.kind == "data_pop"
            else self._value(operand, source)
        )
        if isinstance(value, bool) or not isinstance(value, int):
            raise RIFRuntimeError("FIT requiere un ancho entero.")
        if value <= 0 or value % 2:
            raise RIFRuntimeError("FIT requiere un ancho positivo y múltiplo de dos.")
        if value > resolve_limits().cap(MAX_DYNAMIC_WIDTH_BYTES) * 8:
            raise RIFRuntimeError("FIT excede el límite de recursos configurado.")
        return value

    @staticmethod
    def _immediate_fits(token: lexer.TokenType, width: int) -> bool:
        if width <= 0 or width > resolve_limits().cap(MAX_DYNAMIC_WIDTH_BYTES) * 8:
            raise RIFRuntimeError("El ancho inmediato excede el límite de recursos configurado.")
        if token.token not in {lexer.Token.NUMBER, lexer.Token.DECIMAL, lexer.Token.STRING}:
            raise RIFRuntimeError(
                "FIT requiere que el token actual sea NUMBER, DECIMAL o STRING."
            )
        value = token.value
        if token.token == lexer.Token.STRING:
            if not isinstance(value, str) or not value or any(bit not in "01" for bit in value):
                raise RIFRuntimeError("FIT solo puede emitir strings binarios.")
            return len(value) <= width
        if token.token == lexer.Token.DECIMAL and isinstance(value, float) and value.is_integer():
            value = int(value)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise RIFRuntimeError("FIT requiere un inmediato entero no negativo.")
        return value < (1 << width)

    @staticmethod
    def _immediate_bits(token: lexer.TokenType, width: int, *, truncate: bool) -> int:
        if width <= 0 or width > resolve_limits().cap(MAX_DYNAMIC_WIDTH_BYTES) * 8:
            raise RIFRuntimeError("El ancho inmediato excede el límite de recursos configurado.")
        if not RIFMachine._immediate_fits(token, width) and not truncate:
            value = token.value
            if token.token == lexer.Token.STRING:
                raise RIFRuntimeError(
                    f"El string binario tiene {len(value)} bits y no cabe en {width}."
                )
            raise RIFRuntimeError(f"El inmediato {value} no cabe en {width} bits.")
        value = token.value
        if token.token == lexer.Token.DECIMAL and isinstance(value, float) and value.is_integer():
            value = int(value)
        if token.token == lexer.Token.STRING:
            value = value[-width:] if truncate else value
            return int(value, 2)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise RIFRuntimeError("FIT requiere un inmediato entero no negativo.")
        return value & ((1 << width) - 1)

    def _emit_fit(self, operand: Operand, instruction: Instruction, *, exact: bool) -> None:
        width = self._fit_width(operand, instruction)
        token = self._current()
        value = self._immediate_bits(token, width, truncate=not exact)
        self.emitter.bits(value, width)
        if operand.kind == "data_pop":
            self.datastack.pop()
        self.position += 1
        self.last_token = token

    def _bit_field(
        self,
        operand: Operand,
        source: Instruction | None = None,
    ) -> BitField | int | str:
        value = self._value(operand, source)
        if operand.kind == "number" and operand.width:
            return BitField(int(value), operand.width)
        if operand.kind == "bool":
            return BitField(1 if value else 0, 1)
        if operand.kind == "reservation_access":
            query = self.emitter.query(str(operand.value))
            return BitField(query.value, query.span.width)
        if operand.kind == "string" and isinstance(value, str) and set(value) <= {"0", "1"}:
            return value
        if operand.kind == "table_access" and isinstance(value, str):
            return value
        if isinstance(value, int):
            return value
        return str(value)

    def _frame_field(
        self,
        operand: Operand,
        source: Instruction | None = None,
    ) -> BitField | str:
        value = self._bit_field(operand, source)
        if isinstance(value, BitField):
            return value
        if isinstance(value, str):
            return value
        if isinstance(value, int):
            return BitField(value, self.emitter.wordsize)
        raise RIFRuntimeError(f"El valor {value!r} no puede emitirse en un frame.")

    def _condition(self, operand: Operand, source: Instruction | None = None) -> bool:
        if operand.kind == "bool":
            return bool(operand.value)
        if operand.kind == "call":
            raise RIFRuntimeError(
                f"No existe una función nativa registrada para #call[{operand.value}]."
            )
        raise RIFRuntimeError("La condición no es booleana ni una llamada nativa.")

    def _mark_symbol(self) -> None:
        token = self._current()
        name = token.value
        if not isinstance(name, str) or not name.isidentifier():
            raise RIFRuntimeError(
                f"MARK requiere un identificador de símbolo; recibió {name!r}."
            )
        if self.emitter.virtual_position % 8:
            raise RIFRuntimeError("MARK requiere una posición virtual alineada a bytes.")
        if name in self.symbols:
            raise RIFRuntimeError(f"El símbolo '{name}' ya está definido.")
        self.symbols[name] = SymbolAddress(
            name=name,
            section=self.section_name or (
                self.context.config.defaultsection if self.context.config else None
            ),
            physical_offset_bits=self.emitter.buffer.bit_length,
            virtual_offset_bits=self.emitter.virtual_position,
        )

    def _record_fixup(self, kind: str, reservation: str) -> None:
        token = self._current()
        symbol = token.value
        if not isinstance(symbol, str) or not symbol.isidentifier():
            raise RIFRuntimeError(
                f"FIXUP requiere un identificador de símbolo; recibió {symbol!r}."
            )
        widths = {"pc8": 8, "pc32": 32, "abs64": 64}
        try:
            width_bits = widths[kind]
        except KeyError as exc:
            raise RIFRuntimeError(f"Clase de FIXUP desconocida: {kind!r}.") from exc
        try:
            span = self.emitter.buffer.query(reservation).span
        except KeyError as exc:
            raise RIFRuntimeError(
                f"No existe la reserva de FIXUP '{reservation}'."
            ) from exc
        if span.offset % 8 or span.width % 8:
            raise RIFRuntimeError("La reserva de FIXUP debe estar alineada a bytes.")
        if span.width != width_bits:
            raise RIFRuntimeError(
                f"FIXUP {kind} requiere una reserva de {width_bits} bits; "
                f"'{reservation}' tiene {span.width}."
            )
        if self.emitter.virtual_position % 8:
            raise RIFRuntimeError("FIXUP requiere una posición virtual alineada a bytes.")
        section = self.section_name or (
            self.context.config.defaultsection if self.context.config else None
        )
        start = span.offset
        end = span.offset + span.width
        for previous in self.fixups:
            if previous.section != section:
                continue
            previous_end = previous.offset_bits + previous.width_bits
            if start < previous_end and previous.offset_bits < end:
                raise RIFRuntimeError("Las relocaciones FIXUP se solapan.")
        self.fixups.append(
            Fixup(
                kind=kind,
                symbol=symbol,
                reservation=reservation,
                section=section,
                offset_bits=span.offset,
                width_bits=span.width,
                next_virtual_bits=self.emitter.virtual_position,
            )
        )

    def finalize_fixups(self, *, virtual_bases: Mapping[str, int] | None = None) -> None:
        """Resolve all deferred symbol fixups atomically after MIR execution."""

        if not self.fixups:
            return
        bases = dict(virtual_bases or {})
        widths = {"pc8": 8, "pc32": 32, "abs64": 64}
        planned: list[tuple[Fixup, int]] = []
        for fixup in self.fixups:
            symbol = self.symbols.get(fixup.symbol)
            if symbol is None:
                raise RIFRuntimeError(f"Símbolo no definido: {fixup.symbol}.")
            if symbol.virtual_offset_bits % 8:
                raise RIFRuntimeError(
                    f"El símbolo '{fixup.symbol}' no está alineado a bytes."
                )
            target_base = bases.get(symbol.section, 0)
            next_base = bases.get(fixup.section, 0)
            target = target_base + symbol.virtual_offset
            next_ip = next_base + fixup.next_virtual_bits // 8
            if fixup.kind in {"pc8", "pc32"}:
                value = target - next_ip
                limit = 1 << (widths[fixup.kind] - 1)
                if not -limit <= value < limit:
                    raise RIFRuntimeError(
                        f"{fixup.kind}: desplazamiento {value} fuera del rango signed "
                        f"de {widths[fixup.kind]} bits para {fixup.symbol}."
                    )
                encoded = value & ((1 << widths[fixup.kind]) - 1)
            else:
                value = target
                if not 0 <= value < (1 << widths[fixup.kind]):
                    raise RIFRuntimeError(
                        f"{fixup.kind}: dirección virtual inválida: {value}."
                    )
                encoded = value
            planned.append((fixup, encoded))

        with self.emitter.buffer.transaction():
            for fixup, value in planned:
                try:
                    self.emitter.patch_bits(fixup.offset_bits, fixup.width_bits, value)
                except (TypeError, ValueError) as exc:
                    raise RIFRuntimeError(
                        f"No se pudo aplicar FIXUP {fixup.kind} en {fixup.offset_bits // 8}: {exc}"
                    ) from exc

    def _execute_rule(self, rule_name: str) -> None:
        if self._rule_depth >= MAX_RULE_CALL_DEPTH:
            raise RIFRuntimeError(
                f"La profundidad de llamadas excede {MAX_RULE_CALL_DEPTH} Rules."
            )
        rule = self.program.rules[rule_name]
        frame = _RuleTraceState(
            rule_name,
            self.emitter.buffer.bit_length,
            self.emitter.virtual_position,
        )
        self.rule_addresses.setdefault(rule_name, frame.start)
        self.virtual_rule_addresses.setdefault(rule_name, frame.virtual_start)
        self._trace_stack.append(frame)
        self._rule_depth += 1
        try:
            for instruction in rule.instructions:
                self._execute_instruction(instruction)
        except _BreakFlow:
            return
        finally:
            end = self.emitter.buffer.bit_length
            trace = RuleTrace(
                name=frame.name,
                start=frame.start,
                bits=end - frame.start,
                end=end,
                padding_bits=frame.padding_bits,
                virtual_start=frame.virtual_start,
                virtual_bits=self.emitter.virtual_position - frame.virtual_start,
                virtual_end=self.emitter.virtual_position,
                virtual_padding_bits=frame.virtual_padding_bits,
            )
            self.rule_traces.append(trace)
            self.last_rule_trace = trace
            self._trace_stack.pop()
            self._rule_depth -= 1

    def _execute_instruction(self, instruction: Instruction) -> None:
        opcode = instruction.opcode
        operands = instruction.operands

        if opcode == "consumer":
            self._consume_token(operands[0].resolved)
            return

        if opcode == "mark":
            self._mark_symbol()
            return

        if opcode == "fixup":
            self._record_fixup(str(operands[0].value), str(operands[1].value))
            return

        if opcode == "table_matcher":
            table_ref = operands[0].resolved
            token_ref = operands[1].resolved
            if not isinstance(table_ref, TableRef) or not isinstance(token_ref, TokenRef):
                raise RIFRuntimeError("TABLE_MATCHER no fue resuelto semánticamente.")
            token = self._current()
            if not self._matches_token(token, token_ref):
                raise RIFRuntimeError(
                    f"TABLE_MATCHER esperaba Token.{token_ref.token.name}."
                )
            table = self.context.tables[table_ref.table]
            try:
                index = table.lookup_unique(table_ref.column, token.value)
            except (TypeError, ValueError) as exc:
                raise RIFRuntimeError(str(exc)) from exc
            if index is not None:
                self.selected_rows[table_ref.table] = index
                self.position += 1
                self.last_token = token
                return
            raise RIFRuntimeError(
                f"El valor {token.value!r} no existe en "
                f"{table_ref.table}.{table_ref.column}."
            )

        if opcode == "dget":
            references = operands[0].resolved
            if not isinstance(references, tuple) or len(references) != 2 or not all(isinstance(ref, TableRef) for ref in references):
                raise RIFRuntimeError("DLOAD no fue resuelto semánticamente.")
            selector, field = references
            token = self._current()
            table = self.context.tables[selector.table]
            try:
                row_index = table.lookup_unique(selector.column, token.value)
            except (TypeError, ValueError) as exc:
                raise RIFRuntimeError("El token actual no es indexable en la tabla.") from exc
            if row_index is None:
                raise RIFRuntimeError(
                    f"El valor {token.value!r} no existe en {selector.table}.{selector.column}."
                )
            self.datastack.append(table.matrix[row_index][field.index])
            self.selected_rows[selector.table] = row_index
            self.position += 1
            self.last_token = token
            return

        if opcode == "dpush":
            self.datastack.append(self._value(operands[0], instruction))
            return

        if opcode == "dpop":
            self._value(Operand("data_pop", None), instruction)
            return

        if opcode == "store":
            token = self._current()
            refs = tuple(
                operand.resolved
                for operand in operands
                if isinstance(operand.resolved, TokenRef)
            )
            if not any(self._matches_token(token, reference) for reference in refs):
                raise RIFRuntimeError("STORE no encontró un token candidato.")
            self.position += 1
            self.last_token = token
            self.stored_token = token
            return

        if opcode == "nibbles":
            self.emitter.nibbles(
                self._bit_field(operands[0], instruction),
                self._bit_field(operands[1], instruction),
            )
            return

        if opcode == "emit":
            self.emitter.emit(
                *(self._bit_field(operand, instruction) for operand in operands)
            )
            return

        if opcode == "eword":
            value = self._value(operands[0], instruction)
            if isinstance(value, bool) or not isinstance(value, (int, str, BitField)):
                raise RIFRuntimeError("EWORD requiere un valor numérico o un campo binario.")
            self.emitter.eword(value)
            return

        if opcode == "fit":
            self._emit_fit(operands[0], instruction, exact=False)
            return

        if opcode == "fit_exact":
            self._emit_fit(operands[0], instruction, exact=True)
            return

        if opcode == "fit_not":
            width = self._fit_width(operands[0], instruction)
            token = self._current()
            if not self._immediate_fits(token, width):
                if operands[0].kind == "data_pop":
                    self.datastack.pop()
                self.position += 1
                self.last_token = token
                return
            raise RIFRuntimeError(f"El inmediato cabe en {width} bits; FIT_NOT falló.")

        if opcode == "pad":
            width = int(operands[0].value)
            self.emitter.pad(width)
            self._record_padding(width)
            return

        if opcode == "align":
            alignment = int(operands[0].value)
            remainder = self.emitter.buffer.bit_length % alignment
            width = 0 if remainder == 0 else alignment - remainder
            if width:
                self.emitter.pad(width)
                self._record_padding(width)
            return

        if opcode == "vpad":
            width = int(operands[0].value)
            self.emitter.vpad(width)
            self._record_virtual_padding(width)
            return

        if opcode == "valign":
            alignment = int(operands[0].value)
            width = (-self.emitter.virtual_position) % alignment
            if width:
                self.emitter.vpad(width)
                self._record_virtual_padding(width)
            return

        if opcode in {"bits", "read_bits", "patch_bits"}:
            try:
                if opcode == "bits":
                    value = self._value(operands[0], instruction)
                    width = self._bit_integer(operands[1], instruction, "ancho", positive=True)
                    self.emitter.bits(value, width)
                else:
                    offset = self._bit_integer(operands[0], instruction, "offset", positive=False)
                    width = self._bit_integer(operands[1], instruction, "ancho", positive=True)
                    if opcode == "read_bits":
                        self.datastack.append(self.emitter.read_bits(offset, width))
                    else:
                        self.emitter.patch_bits(offset, width, self._value(operands[2], instruction))
            except (ValueError, TypeError) as exc:
                raise RIFRuntimeError(str(exc)) from exc
            return

        if opcode == "frame":
            rows = operands[0].value
            self.emitter.frame(
                tuple(
                    tuple(self._frame_field(operand, instruction) for operand in row)
                    for row in rows
                )
            )
            return

        if opcode == "kw":
            token = self._current()
            expected = operands[0].value
            if token.token != lexer.Token.KEYWORD or token.value != expected:
                raise RIFRuntimeError(f"KW esperaba {expected!r}.")
            self.position += 1
            self.last_token = token
            return

        if opcode == "jump":
            reference = operands[0].resolved
            if not isinstance(reference, RuleRef):
                raise RIFRuntimeError("JUMP no fue resuelto semánticamente.")
            self._execute_rule(reference.name)
            return

        if opcode == "jumpif":
            reference = operands[0].resolved
            if not isinstance(reference, RuleRef):
                raise RIFRuntimeError("JUMPIF no fue resuelto semánticamente.")
            if self._condition(operands[1], instruction):
                self._execute_rule(reference.name)
            return

        if opcode == "break":
            raise _BreakFlow()

        if opcode == "error":
            raise RIFRuntimeError(str(operands[0].value))

        if opcode == "reserve":
            self.emitter.reserve(str(operands[0].value), int(operands[1].value))
            return

        if opcode == "vreserve":
            self.emitter.vreserve(str(operands[0].value), int(operands[1].value))
            return

        if opcode == "write_res":
            self.emitter.write_res(
                str(operands[0].value),
                self._value(operands[1], instruction),
            )
            return

        if opcode == "emit_res":
            self.emitter.emit_res(str(operands[0].value))
            return

        if opcode == "drop_res":
            self.emitter.drop_res(str(operands[0].value))
            return

        if opcode == "save":
            self.storage[str(operands[0].value)] = self._current()
            return

        if opcode == "load":
            name = str(operands[0].value)
            if name not in self.storage:
                raise RIFRuntimeError(f"No existe token guardado bajo '{name}'.")
            saved = self.storage[name]
            current = self._current()
            if current.token != saved.token or current.value != saved.value:
                raise RIFRuntimeError(f"LOAD no coincide con el token guardado '{name}'.")
            self.position += 1
            self.last_token = current
            return

        raise NotImplementedError(f"El runtime todavía no implementa '{opcode}'.")


__all__ = [
    "MAX_RULE_CALL_DEPTH",
    "RIFRuntimeError",
    "ExecutionResult",
    "RuleTrace",
    "RIFMachine",
    "SymbolAddress",
    "Fixup",
]
