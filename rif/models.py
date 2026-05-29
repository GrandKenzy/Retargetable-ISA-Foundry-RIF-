from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any

"""Modelos de datos y estructuras AST del compilador RIF.

Define las clases fundamentales para la representación de tokens, programas,
secciones, instrucciones, configuraciones de empaquetado, bindings de operadores
y estructuras utilizadas en las fases del compilador.
"""

TYPES_MAP: dict[str, Any] = {}
GLOBAL_STATE_LOCK = RLock()


class TypeInfo(dict):
    """Diccionario con acceso por atributo para tipos resueltos.

    Los plugins históricos usan tanto `op.type["NAME"]` como
    `op.type.PRIVTYPE`, así que esta clase soporta ambos estilos sin
    perder compatibilidad con el código que ya esperaba un dict.
    """

    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc

    def copy(self) -> "TypeInfo":
        return TypeInfo(super().copy())


class RuleIndicator:
    current: str | None = None


@dataclass
class OperatorBinding:
    name: str
    rule_name: str | None
    valid_types: list[Any] = field(default_factory=list)
    literal: str | None = None

    @property
    def is_literal(self) -> bool:
        return self.literal is not None


class Operators:
    program: Any = None
    saved_operators: dict[str, list[str]] = {}
    bindings: dict[str, dict[str, OperatorBinding]] = {}

    @classmethod
    def set_program(cls, program: Any) -> None:
        cls.program = program

    @classmethod
    def Reset(cls) -> None:
        cls.saved_operators.clear()
        cls.bindings.clear()

    @staticmethod
    def _name(value: Any) -> str:
        if hasattr(value, "value"):
            value = value.value
        return str(value).strip()

    @classmethod
    def Save(
        cls,
        op_name: str,
        rule_name: str | None,
        valid_types: list[Any] | None = None,
        literal: str | None = None,
    ) -> OperatorBinding:
        op_name = cls._name(op_name)
        binding = OperatorBinding(op_name, rule_name, list(valid_types or []), literal)

        if rule_name:
            saved = cls.saved_operators.setdefault(rule_name, [])
            if op_name not in saved:
                saved.append(op_name)
            cls.bindings.setdefault(rule_name, {})[op_name] = binding

        return binding

    @classmethod
    def Binding(cls, op_name: str, rule_name: str | None = None) -> OperatorBinding | None:
        op_name = cls._name(op_name)
        if rule_name and op_name in cls.bindings.get(rule_name, {}):
            return cls.bindings[rule_name][op_name]

        found: OperatorBinding | None = None
        for bindings in cls.bindings.values():
            current = bindings.get(op_name)
            if current is None:
                continue
            if found is not None:
                return None
            found = current
        return found

    @classmethod
    def is_operator(cls, op_name: str, rule_name: str | None = None) -> bool:
        op_name = cls._name(op_name)
        if not op_name:
            return False

        scope = rule_name or RuleIndicator.current
        if cls.Binding(op_name, scope) is not None:
            return True

        program = cls.program
        if program is None:
            return False

        if REG.exists(op_name):
            return True

        obj = program.objects.get(op_name)
        return obj is not None and getattr(obj, "section", None) == ".data"

    @classmethod
    def Load(cls, op_name: str, rule_name: str | None = None) -> Any:
        op_name = cls._name(op_name)

        reg = None
        if cls.program:
            reg = next((r for r in cls.program.regs.registers if r.name == op_name), None)
            if not reg:
                reg = next((r for r in cls.program.regs.registers if r.alias == op_name), None)
            if not reg:
                obj = cls.program.objects.get(op_name)
                if obj:
                    class GenericOp:
                        def __init__(self, name, row):
                            self.name = name
                            priv = "symbol" if getattr(row, "section", None) == ".data" else "object"
                            self.type = TypeInfo(row.values)
                            self.type.setdefault("NAME", row.name)
                            self.type.setdefault("PRIVTYPE", priv)
                            self.resolved = True
                    return GenericOp(op_name, obj)

        if reg:
            class ResolvedOp:
                def __init__(self, r):
                    self.name = r.name
                    priv = "register" if r.is_parent else "subregister"
                    self.type = TypeInfo(r.values)
                    self.type["NAME"] = r.name
                    self.type["bits"] = r.bits
                    self.type["PRIVTYPE"] = priv
                    self.resolved = True
            return ResolvedOp(reg)

        binding = cls.Binding(op_name, rule_name)
        if binding is not None:
            class RuleOp:
                def __init__(self, b):
                    self.name = b.name
                    self.binding = b
                    self.type = TypeInfo({
                        "NAME": b.name,
                        "PRIVTYPE": "operator",
                        "bits": None,
                        "types": b.valid_types,
                    })
                    self.resolved = False
            return RuleOp(binding)

        class DummyOp:
            def __init__(self, name):
                self.name = name
                self.type = TypeInfo({"NAME": name, "PRIVTYPE": "unknown", "bits": None})
                self.resolved = False
        return DummyOp(op_name)

Operator = Operators
class IDENT:
    def __init__(self, value: str):
        self.value = value

    def __repr__(self) -> str:
        return f"IDENT({self.value!r})"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, IDENT):
            return self.value == other.value
        return self.value == other


class Err(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)

    @property
    def msg(self) -> str:
        return self.message

    def __repr__(self) -> str:
        return f"Err({self.message!r})"


class Expr:
    def __init__(self, elements: list[Any] | None = None, kind: Any = None):
        self.elements = elements or []
        self.kind = kind

    def __repr__(self) -> str:
        return f"Expr({self.elements!r}, {self.kind!r})"


class Line:
    toks: list[str] = []
    elements: int = 0
    line: int | None = None

    @classmethod
    def set_tokens(cls, tokens: list[str]) -> None:
        cls.toks = list(tokens)
        cls.elements = len(tokens)

    @classmethod
    def clear(cls) -> None:
        cls.toks.clear()
        cls.elements = 0
        cls.line = None

    @classmethod
    def Advance(cls) -> str | None:
        if cls.toks:
            return cls.toks.pop(0)
        return None

    @classmethod
    def Peek(cls) -> str | None:
        if cls.toks:
            return cls.toks[0]
        return None

    @classmethod
    def expect(cls, value: str) -> str | None:
        if cls.toks:
            current = cls.toks.pop(0)
            if cls.toks and cls.toks[0] == value:
                cls.toks.pop(0)
            return current
        return None

    @classmethod
    def expects(cls, expected_val: str, final: str = '\n') -> None:
        remaining = [t for t in cls.toks if t.strip()]
        if remaining:
            from .errors import PackError
            raise PackError(f"Unexpected trailing tokens: {remaining}")
        cls.toks.clear()

    @classmethod
    def Unpack(cls, separator: str) -> list[str]:
        if not cls.toks:
            return []

        out: list[str] = []
        current: list[str] = []
        saw_separator = False

        def push_current() -> None:
            out.append(" ".join(current).strip())
            current.clear()

        for token in cls.toks:
            if token == separator:
                saw_separator = True
                push_current()
                continue



            if separator and separator in token and token != separator:
                parts = token.split(separator)
                for index, part in enumerate(parts):
                    if part:
                        current.append(part)
                    if index != len(parts) - 1:
                        saw_separator = True
                        push_current()
                continue

            current.append(token)

        if saw_separator:
            push_current()
        elif current:
            out.append(" ".join(current).strip())

        cls.toks.clear()
        return out


@dataclass(frozen=True)
class Placeholder:
    """Expresión diferida para valores que todavía no existen o no están resueltos.

    No representa un error. Le dice al resolver/codegen que debe dejar un
    hueco semántico, por ejemplo un símbolo externo, un campo pendiente o un
    valor que otra fase completará.
    """

    target: str
    kind: str = "unknown"
    field: str | None = None
    reason: str | None = None
    rule_name: str | None = None
    line: int | None = None
    width: int | None = None

    @property
    def name(self) -> str:
        if self.field:
            return f"{self.target}.{self.field}"
        return self.target


@dataclass(frozen=True)
class Relocation:
    kind: str
    target: str
    offset_bits: int
    width: int
    section: str | None = None
    relative_to: str | None = None
    addend: int = 0
    signed: bool = False
    byteorder: str = "little"
    rule_name: str | None = None
    source: str | None = None
    line: int | None = None


@dataclass
class OperandValue:
    """Operando real o placeholder ligado a una captura de regla."""

    name: str
    type: TypeInfo
    resolved: bool = True
    placeholder: Placeholder | None = None

    def get(self, field_name: str, default: Any = None) -> Any:
        return self.type.get(field_name, default)


@dataclass
class CompileResult:
    """Resultado de compilar una instrucción concreta."""

    rule_name: str
    source: str
    data: bytes | None
    bits: str
    placeholders: list[Placeholder] = field(default_factory=list)
    expressions: list[Any] = field(default_factory=list)
    resolved_placeholders: list["ResolvedPlaceholder"] = field(default_factory=list)
    relocations: list[Relocation] = field(default_factory=list)

    @property
    def hex(self) -> str | None:
        if self.data is None:
            return None
        return self.data.hex()


@dataclass(frozen=True)
class ResolvedPlaceholder:
    """Placeholder que una fase posterior pudo resolver sin plugins extra."""

    placeholder: Placeholder
    value: Any
    bits: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class PlaceholderResolution:
    """Resultado de intentar cerrar huecos diferidos."""

    resolved: tuple[ResolvedPlaceholder, ...] = ()
    unresolved: tuple[Placeholder, ...] = ()


@dataclass(frozen=True)
class EmitChunk:
    """Fragmento de una emisión que el codegen resolverá después."""

    kind: str
    value: str
    width: int | None = None
    byte: int | None = None
    target: str | None = None
    field: str | None = None

    @property
    def is_static(self) -> bool:
        return self.kind in {"bits", "byte"}

    @property
    def is_placeholder(self) -> bool:
        return self.kind == "placeholder"


@dataclass(frozen=True)
class EmitInstruction:
    """Instrucción IR: el parser le dice al codegen qué bits exactos emitir."""

    mode: str
    chunks: tuple[EmitChunk, ...]
    rule_name: str | None = None
    line: int | None = None
    requires_byte: bool = True

    @property
    def has_placeholders(self) -> bool:
        return any(chunk.is_placeholder for chunk in self.chunks)

    @property
    def static_bits(self) -> str | None:
        if self.has_placeholders:
            return None
        bits: list[str] = []
        for chunk in self.chunks:
            if chunk.kind == "byte":
                bits.append(chunk.value)
            elif chunk.kind == "bits":
                bits.append(chunk.value)
            else:
                return None
        return "".join(bits)

    @property
    def static_bytes(self) -> bytes | None:
        static = self.static_bits
        if static is None or len(static) % 8 != 0:
            return None
        return bytes(int(static[i:i + 8], 2) for i in range(0, len(static), 8))


@dataclass
class FlowInstruction:
    """Nodo IR de control de flujo para codegen.

    El parser no evalúa condiciones. Solo conserva argumentos y estructura:
    ON/OFF como ramas, switch/case como selección por casos, y las
    instrucciones internas ya resueltas por plugins como hijos.
    """

    kind: str
    args: tuple[str, ...] = field(default_factory=tuple)
    rule_name: str | None = None
    line: int | None = None
    body: list[Any] = field(default_factory=list)
    branches: list["FlowInstruction"] = field(default_factory=list)

    @property
    def condition(self) -> tuple[str, ...]:
        return self.args


@dataclass
class CodegenInfo:
    """IR acumulada por plugins para una futura fase de codegen."""

    expressions_by_rule: dict[str, list[Expr]] = field(default_factory=dict)
    expressions: list[Expr] = field(default_factory=list)
    emissions_by_rule: dict[str, list[EmitInstruction]] = field(default_factory=dict)
    emissions: list[EmitInstruction] = field(default_factory=list)
    flows_by_rule: dict[str, list[FlowInstruction]] = field(default_factory=dict)
    flows: list[FlowInstruction] = field(default_factory=list)

    def add_expr(self, expr: Expr, rule_name: str | None = None) -> None:
        self.expressions.append(expr)
        if rule_name:
            self.expressions_by_rule.setdefault(rule_name, []).append(expr)

        emission = self._extract_emission(expr)
        if emission is not None:
            self.emissions.append(emission)
            if emission.rule_name:
                self.emissions_by_rule.setdefault(emission.rule_name, []).append(emission)

        flow = self._extract_flow(expr)
        if flow is not None:
            self.add_flow(flow, flow.rule_name or rule_name)

    def add_flow(self, flow: FlowInstruction, rule_name: str | None = None) -> None:
        self.flows.append(flow)
        scope = flow.rule_name or rule_name
        if scope:
            self.flows_by_rule.setdefault(scope, []).append(flow)

    @staticmethod
    def _extract_emission(expr: Expr) -> EmitInstruction | None:
        if not expr.elements:
            return None
        if isinstance(expr.elements[0], EmitInstruction):
            return expr.elements[0]
        if len(expr.elements) >= 2 and expr.elements[0] in {"emit", "emit_bits_exact"}:
            candidate = expr.elements[1]
            if isinstance(candidate, EmitInstruction):
                return candidate
        return None

    @staticmethod
    def _extract_flow(expr: Expr) -> FlowInstruction | None:
        if not expr.elements:
            return None
        if isinstance(expr.elements[0], FlowInstruction):
            return expr.elements[0]
        if len(expr.elements) >= 2 and expr.elements[0] in {"flow", "control_flow"}:
            candidate = expr.elements[1]
            if isinstance(candidate, FlowInstruction):
                return candidate
        return None


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    line: int
    col: int
    raw: str = ""


@dataclass
class LexerConfig:
    comment: str = ";"
    separator: str = "|"
    block: str = ":"
    encoding: str = "utf-8"

    def validate(self) -> None:
        for name, value in (
            ("comment", self.comment),
            ("separator", self.separator),
            ("block", self.block),
        ):
            if len(value) != 1:
                raise ValueError(f"{name} must be one character")
        if len({self.comment, self.separator, self.block}) != 3:
            raise ValueError("comment, separator and block characters must be different")


@dataclass
class Statement:
    name: str
    args: list[Token]
    line: int
    indent: int
    raw: str
    children: list[Statement] = field(default_factory=list)
    block: bool = False

    def arg_values(self) -> list[str]:
        return [token.value for token in self.args]


@dataclass
class PluginContext:
    program: Any
    phase: str
    config: Any = None
    rule_name: str | None = None
    statement: Statement | None = None
    compiler: Any = None
    linker: Any = None
    line: int | None = None


@dataclass
class TableRow:
    name: str
    values: dict[str, Any]
    line: int
    section: str | None = None

    def attr(self, key: str) -> Any:
        return self.values[key]


@dataclass
class Table:
    section: str
    fields: list[str]
    owner: str | None = None
    rows: dict[str, TableRow] = field(default_factory=dict)

    def add_row(self, row: TableRow) -> None:
        self.rows[row.name] = row


@dataclass
class Section:
    name: str
    line: int
    prefix: str | None = None
    statements: list[Statement] = field(default_factory=list)
    body_lines: list[tuple[int, str]] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)

    @property
    def canonical(self) -> str:
        return self.name if self.name.startswith(".") else f".{self.name}"


@dataclass
class WorldObject:
    values: dict[str, Any] = field(default_factory=dict)

    def attr(self, key: str) -> Any:
        return self.values[key]


@dataclass
class Register:
    name: str
    family: str
    bits: int
    is_parent: bool
    parent_name: str | None
    alias: str | None
    values: dict[str, Any]


@dataclass
class RegsInfo:
    hiddesubs: bool = False
    order_column: str | None = None
    registers: list[Register] = field(default_factory=list)
    families: dict[str, list[Register]] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)


@dataclass
class HeaderBlock:
    name: str
    size: Any = None
    hex: str = ""
    fill: str = ""
    line: int | None = None
    table: Table | None = None
    statements: list[Statement] = field(default_factory=list)


@dataclass
class HeadersInfo:
    order: list[str] = field(default_factory=list)
    blocks: dict[str, HeaderBlock] = field(default_factory=dict)

    def add(self, block: HeaderBlock) -> None:
        if block.name not in self.blocks:
            self.order.append(block.name)
        self.blocks[block.name] = block


@dataclass
class TypeDefinition:
    name: str
    size: Any = None
    values: dict[str, Any] = field(default_factory=dict)
    line: int | None = None

    @property
    def bits(self) -> int | None:
        try:
            return int(self.size)
        except (TypeError, ValueError):
            return None


@dataclass
class TypesInfo:
    order: list[str] = field(default_factory=list)
    definitions: dict[str, TypeDefinition] = field(default_factory=dict)

    def add(self, definition: TypeDefinition) -> None:
        if definition.name not in self.definitions:
            self.order.append(definition.name)
        self.definitions[definition.name] = definition

    def get(self, name: str) -> TypeDefinition | None:
        return self.definitions.get(name)


@dataclass
class DataDefinitionInfo:
    pattern: list[tuple[str, Any | None]] = field(default_factory=list)
    options: dict[str, list[Any]] = field(default_factory=dict)

    def add_option(self, name: str, values: list[Any]) -> None:
        self.options[name] = values


@dataclass
class MemoryRegion:
    kind: str
    name: str
    type_token: str
    type_name: str
    section: str
    bytes: int
    bits: int
    count: int
    element_bits: int | None = None
    align: int = 1
    fill: Any = 0
    line: int | None = None
    values: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryInfo:
    order: list[str] = field(default_factory=list)
    regions: dict[str, MemoryRegion] = field(default_factory=dict)
    by_kind: dict[str, list[str]] = field(default_factory=dict)
    by_section: dict[str, list[str]] = field(default_factory=dict)

    def add(self, region: MemoryRegion) -> None:
        if region.name not in self.regions:
            self.order.append(region.name)
        self.regions[region.name] = region

        kind_items = self.by_kind.setdefault(region.kind, [])
        if region.name not in kind_items:
            kind_items.append(region.name)

        section_items = self.by_section.setdefault(region.section, [])
        if region.name not in section_items:
            section_items.append(region.name)

    def get(self, name: str) -> MemoryRegion | None:
        return self.regions.get(name)



@dataclass(frozen=True)
class BitVariable:
    """Variable de bits declarada en `.vars` con ancho fijo de 4 u 8 bits."""

    name: str
    bits: str
    line: int

    @property
    def width(self) -> int:
        return len(self.bits)

    @property
    def byte(self) -> int | None:
        if len(self.bits) != 8:
            return None
        return int(self.bits, 2)


@dataclass
class Program:
    source_path: Path | None
    lexer_config: LexerConfig
    sections: dict[str, Section]
    top_level: list[Statement] = field(default_factory=list)
    world: WorldObject = field(default_factory=WorldObject)
    objects: dict[str, TableRow] = field(default_factory=dict)
    tables: dict[str, Table] = field(default_factory=dict)
    regs: RegsInfo = field(default_factory=RegsInfo)
    vars: dict[str, BitVariable] = field(default_factory=dict)
    headers: HeadersInfo = field(default_factory=HeadersInfo)
    type_defs: TypesInfo = field(default_factory=TypesInfo)
    data_definition: DataDefinitionInfo = field(default_factory=DataDefinitionInfo)
    memory: MemoryInfo = field(default_factory=MemoryInfo)
    codegen: CodegenInfo = field(default_factory=CodegenInfo)
    type_map: dict[str, Any] = field(default_factory=dict)
    operator_saved: dict[str, list[str]] = field(default_factory=dict)
    operator_bindings: dict[str, dict[str, OperatorBinding]] = field(default_factory=dict)

    @property
    def comment_char(self) -> str:
        return self.lexer_config.comment

    def section(self, name: str) -> Section | None:
        key = name if name.startswith(".") else f".{name}"
        return self.sections.get(key)

    def has_section(self, name: str) -> bool:
        return self.section(name) is not None

    def object(self, name: str) -> TableRow | None:
        return self.objects.get(name)


class REG:
    """Vista global de registros para plugins básicos.

    Usa el `Program` activo de Operators para no duplicar estado.
    """

    @classmethod
    def exists(cls, name: str) -> bool:
        name = str(name).strip()
        program = Operators.program
        if program is None or not name:
            return False

        return any(reg.name == name or reg.alias == name for reg in program.regs.registers)


class DATA:
    """Vista global de símbolos de .data para plugins básicos."""

    @classmethod
    def exists(cls, name: str) -> bool:
        name = str(name).strip()
        program = Operators.program
        if program is None or not name:
            return False

        table = program.tables.get(".data")
        return table is not None and name in table.rows


@dataclass
class PackerConfig:
    enabled: bool = False
    fsystem: int = 0
    ext: str = ".pack"
    sectpre: str | None = None
    subpre: str | None = None
    defined_sections: set[str] = field(default_factory=set)
    prefix_to_section: dict[str, str] = field(default_factory=dict)
    required_prefixes: set[str] = field(default_factory=set)
    plugext: str = ".py"
    plugins: list[str] = field(default_factory=list)
    precompilers: list[str] = field(default_factory=list)
    types: dict[str, str] = field(default_factory=dict)

    @property
    def recursive(self) -> bool:
        return self.fsystem == 1

    @staticmethod
    def normalize_section(value: str) -> str:
        value = value.strip()
        return value if value.startswith(".") else f".{value}"

    def known_section(self, section: str) -> bool:
        return self.normalize_section(section) in self.defined_sections


@dataclass
class LinkBlock:
    name: str
    kind: str
    data: bytes = b""
    physical_offset: int = 0
    virtual_offset: int = 0
    physical_size: int = 0
    virtual_size: int = 0
    align: int = 1
    row: TableRow | None = None
    placeholders: list[Placeholder] = field(default_factory=list)


@dataclass
class BinaryLinkResult:
    program: Program
    blocks: list[LinkBlock]
    data: bytes
    placeholders: list[Placeholder] = field(default_factory=list)
    relocations: list[Relocation] = field(default_factory=list)

    @property
    def hex(self) -> str:
        return self.data.hex()


@dataclass
class PackedResult:
    source_path: Path
    output_path: Path
    fragments: list[Path]
    program: Program
    config: PackerConfig
    linked_source: str = ""
    initial_program: Program | None = None
