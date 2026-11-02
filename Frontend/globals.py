from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


TableKey = tuple[type[Any], Any]


@dataclass(frozen=True)
class TableData:
    """Tabla compilada, inmutable y preindexada por todas sus columnas."""

    name: str
    headers: tuple[str, ...]
    matrix: tuple[tuple[Any, ...], ...]
    columns: Mapping[str, int]
    indexes: Mapping[str, Mapping[TableKey, tuple[int, ...]]] = field(init=False)
    unique_columns: frozenset[str] = field(init=False)

    def __post_init__(self) -> None:
        rows = tuple(tuple(row) for row in self.matrix)
        headers = tuple(self.headers)
        columns = MappingProxyType(dict(self.columns))
        if any(len(row) != len(headers) for row in rows):
            raise ValueError(f"La tabla '{self.name}' contiene filas con ancho inconsistente.")
        if set(columns) != set(headers):
            raise ValueError(f"La tabla '{self.name}' tiene un mapa de columnas inconsistente.")
        if any(index < 0 or index >= len(headers) for index in columns.values()):
            raise ValueError(f"La tabla '{self.name}' contiene un índice de columna inválido.")
        indexes: dict[str, Mapping[TableKey, tuple[int, ...]]] = {}
        unique_columns: set[str] = set()
        for column, column_index in columns.items():
            values: dict[TableKey, list[int]] = {}
            for row_number, row in enumerate(rows):
                value = row[column_index]
                key = self._key(value)
                values.setdefault(key, []).append(row_number)
            indexes[column] = MappingProxyType(
                {key: tuple(row_numbers) for key, row_numbers in values.items()}
            )
            if all(len(row_numbers) == 1 for row_numbers in values.values()):
                unique_columns.add(column)
        object.__setattr__(self, "headers", headers)
        object.__setattr__(self, "matrix", rows)
        object.__setattr__(self, "columns", columns)
        object.__setattr__(self, "indexes", MappingProxyType(indexes))
        object.__setattr__(self, "unique_columns", frozenset(unique_columns))

    @staticmethod
    def _key(value: Any) -> TableKey:
        try:
            hash(value)
        except TypeError as exc:
            raise ValueError(f"El valor de tabla {value!r} no es indexable.") from exc
        return type(value), value

    def index_for(self, column: str) -> Mapping[TableKey, tuple[int, ...]]:
        """Return the immutable precomputed index for one column."""
        if column not in self.columns:
            raise KeyError(f"La columna '{column}' no existe en la tabla '{self.name}'.")
        return self.indexes[column]

    def require_unique(self, column: str) -> None:
        """Require every key in a column to select exactly one row."""
        if column in self.unique_columns:
            return
        for key, rows in self.index_for(column).items():
            if len(rows) > 1:
                raise ValueError(
                    f"La columna '{column}' de la tabla '{self.name}' contiene "
                    f"la clave duplicada {key[1]!r}."
                )

    def lookup_unique(self, column: str, value: Any) -> int | None:
        """Return one row for a typed key, or ``None`` when it is absent."""
        rows = self.index_for(column).get(self._key(value))
        if rows is None:
            return None
        if len(rows) != 1:
            raise ValueError(
                f"La columna '{column}' de la tabla '{self.name}' contiene "
                f"la clave duplicada {value!r}."
            )
        return rows[0]

    def select(
        self,
        column: str,
        value: Any,
    ) -> tuple[int, tuple[Any, ...]] | None:
        """Select one row through any declared column.

        Targets may use tables for arbitrary metadata, not only registers.
        Keeping row selection here gives matching, captures, and lookups one
        typed and duplicate-aware implementation.
        """

        row_index = self.lookup_unique(column, value)
        if row_index is None:
            return None
        return row_index, self.matrix[row_index]


@dataclass
class RuleData:
    """Regla registrada, conservando sus instrucciones sin ejecutarlas."""

    name: str
    node: Any
    instructions: tuple[Any, ...]
    source_path: str | None = None


@dataclass(frozen=True)
class ConfigData:
    """Configuración del formato ensamblador objetivo."""

    sectiondef: str
    sections: tuple[str, ...]
    sectionend: str
    entrysection: str
    entrylabel: str
    comment: str
    labelend: str
    datasection: str
    defaultsection: str
    sectionflags: Mapping[str, str]
    sectionalign: Mapping[str, int]
    wordsize: int
    addresssize: int
    endianness: str
    casesensitive: bool
    symbolprefix: str
    localprefix: str
    undefinedsymbols: str
    duplicatesymbols: str
    strict: bool
    allowemptysections: bool
    bitorder: str = "msb"
    sectionvaddr: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "sectionflags", MappingProxyType(dict(self.sectionflags)))
        object.__setattr__(self, "sectionalign", MappingProxyType(dict(self.sectionalign)))
        object.__setattr__(self, "sectionvaddr", MappingProxyType(dict(self.sectionvaddr)))


@dataclass(frozen=True)
class BlockValueData:
    """One value captured by a generic block line."""

    kind: str
    value: Any
    raw: str | None = None


@dataclass(frozen=True)
class BlockEntryData:
    """A generic block line: one name and zero to two values."""

    name: str
    values: tuple[BlockValueData, ...] = ()


@dataclass(frozen=True)
class BlockData:
    """A generic block preserved in the compiled target context."""

    name: str
    entries: tuple[BlockEntryData, ...]
    source_path: str | None = None


@dataclass(frozen=True)
class LinkerData:
    """Configuración de descubrimiento de archivos del linker."""

    extension: str
    search_path: tuple[str, ...] | bool


@dataclass(frozen=True)
class SupportData:
    """Variante declarada y su archivo RIF esperado."""

    name: str
    path: str


@dataclass(frozen=True)
class AsmVariantData:
    """Reglas de entrada/salida y modo de delegación de una variante."""

    name: str
    mode: str
    enter_rule: str
    exit_rule: str
    path: str


@dataclass(frozen=True)
class VariantFrame:
    """Contexto sintáctico activo; el estado semántico permanece global."""

    variant: AsmVariantData
    source_path: str
    return_rule: str | None
    token_position: int


@dataclass(frozen=True)
class TargetContext:
    """Self-contained target state captured after processing a RIF project.

    The frontend still uses module globals while it visits a source tree, but
    compiled programs must never consult those mutable globals.  Keeping the
    snapshot on the compiled Rule set makes prepared targets independent and
    safe to reuse in the same Python process.
    """

    config: ConfigData | None = None
    linker: LinkerData | None = None
    defines: frozenset[str] = frozenset()
    stack_size: int | None = None
    tables: Mapping[str, TableData] = field(default_factory=dict)
    supports: Mapping[str, SupportData] = field(default_factory=dict)
    asm_variants: Mapping[str, AsmVariantData] = field(default_factory=dict)
    loaded_sources: Mapping[str, str] = field(default_factory=dict)
    blocks: Mapping[str, tuple[BlockData, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "tables", MappingProxyType(dict(self.tables)))
        object.__setattr__(self, "supports", MappingProxyType(dict(self.supports)))
        object.__setattr__(self, "asm_variants", MappingProxyType(dict(self.asm_variants)))
        object.__setattr__(self, "loaded_sources", MappingProxyType(dict(self.loaded_sources)))
        object.__setattr__(
            self,
            "blocks",
            MappingProxyType({name: tuple(items) for name, items in self.blocks.items()}),
        )


def snapshot_target_context() -> TargetContext:
    """Return a detached copy of the target currently built by visitors."""

    from Frontend.session import CompilationSession

    return CompilationSession.from_globals().freeze()


def activate_target_context(context: TargetContext) -> None:
    """Expose a snapshot through legacy frontend globals.

    This is kept only for processor/introspection compatibility. Runtime code
    reads ``CompiledRuleSet.context`` directly and is therefore unaffected by
    later calls to this helper.
    """

    global STACK, STACK_SIZE, CONFIG, LINKER, PROCESS_DEPTH, SOURCE_PROVIDER
    STACK_SIZE = context.stack_size
    STACK = {} if STACK_SIZE is not None else None
    CONFIG = context.config
    LINKER = context.linker
    DEFINES.clear()
    DEFINES.update(context.defines)
    TABLES.clear()
    TABLES.update(context.tables)
    PENDING_TABLES.clear()
    PROCESS_DEPTH = 0
    SOURCE_PROVIDER = None
    SUPPORTS.clear()
    SUPPORTS.update(context.supports)
    ASM_VARIANTS.clear()
    ASM_VARIANTS.update(context.asm_variants)
    LOADED_SOURCES.clear()
    LOADED_SOURCES.update(context.loaded_sources)
    BLOCKS.clear()
    BLOCKS.update({name: list(items) for name, items in context.blocks.items()})
    ACTIVE_SOURCES.clear()
    VARIANT_STACK.clear()


# Se crea al procesar la primera declaración @stack.
STACK: dict[int, Any] | None = None
STACK_SIZE: int | None = None

# Nombres declarados con @define. Son etiquetas del lenguaje, no slots del
# stack ni valores runtime.
DEFINES: set[str] = set()

# Las tablas se conservan como valores inmutables y sus índices se construyen
# al materializarse; el diccionario global solo cambia durante el frontend.
TABLES: dict[str, TableData] = {}

# Compatibilidad legacy únicamente. Las declaraciones pendientes viven en
# CompilationSession y nunca se consultan durante una compilación moderna.
PENDING_TABLES: dict[str, Any] = {}

# Compatibilidad legacy únicamente; el anidamiento de loaders usa la sesión.
PROCESS_DEPTH = 0

# Reglas localizadas por nombre. Su AST se conserva para la fase de ejecución.
RULES: dict[str, RuleData] = {}

# Configuración única del ensamblador objetivo.
CONFIG: ConfigData | None = None

# Configuración única del linker.
LINKER: LinkerData | None = None

# El contexto publicado para introspección legacy conserva estas vistas; el
# frontend moderno las mantiene dentro de CompilationSession.
SUPPORTS: dict[str, SupportData] = {}
ASM_VARIANTS: dict[str, AsmVariantData] = {}
LOADED_SOURCES: dict[str, str] = {}
ACTIVE_SOURCES: list[str] = []
VARIANT_STACK: list[VariantFrame] = []

# Proveedor opcional de fuentes empaquetadas. Permite que @LOAD y las
# variantes lean desde un .pack sin volver al filesystem.
SOURCE_PROVIDER: Any | None = None

# Generic @block data. Known blocks are materialized by their direct visitors;
# unknown blocks remain available to higher-level consumers.
BLOCKS: dict[str, list[BlockData]] = {}

__all__ = [
    "STACK",
    "STACK_SIZE",
    "DEFINES",
    "TableData",
    "TableKey",
    "TABLES",
    "PENDING_TABLES",
    "PROCESS_DEPTH",
    "RuleData",
    "RULES",
    "ConfigData",
    "BlockValueData",
    "BlockEntryData",
    "BlockData",
    "CONFIG",
    "LinkerData",
    "LINKER",
    "SupportData",
    "SUPPORTS",
    "AsmVariantData",
    "ASM_VARIANTS",
    "VariantFrame",
    "TargetContext",
    "snapshot_target_context",
    "activate_target_context",
    "LOADED_SOURCES",
    "ACTIVE_SOURCES",
    "VARIANT_STACK",
    "SOURCE_PROVIDER",
    "BLOCKS",
]
