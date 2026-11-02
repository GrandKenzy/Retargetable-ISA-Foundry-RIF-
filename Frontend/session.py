"""Explicit mutable state for one RIF frontend compilation."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from Frontend import globals


@dataclass
class CompilationSession:
    """Own the mutable state of exactly one source compilation.

    The legacy module globals are used only when ``from_globals`` creates a
    compatibility session for old callers. Normal compilation creates a fresh
    session and passes it through every loader and visitor.
    """

    stack: dict[int, Any] | None = None
    stack_size: int | None = None
    defines: set[str] = field(default_factory=set)
    tables: dict[str, globals.TableData] = field(default_factory=dict)
    pending_tables: dict[str, Any] = field(default_factory=dict)
    rules: dict[str, globals.RuleData] = field(default_factory=dict)
    config: globals.ConfigData | None = None
    linker: globals.LinkerData | None = None
    supports: dict[str, globals.SupportData] = field(default_factory=dict)
    asm_variants: dict[str, globals.AsmVariantData] = field(default_factory=dict)
    loaded_sources: dict[str, str] = field(default_factory=dict)
    active_sources: list[str] = field(default_factory=list)
    variant_stack: list[globals.VariantFrame] = field(default_factory=list)
    source_provider: Any | None = None
    source_texts: dict[str, str] = field(default_factory=dict)
    blocks: dict[str, list[globals.BlockData]] = field(default_factory=dict)
    diagnostics: list[Any] = field(default_factory=list)
    backend: str = "aot"
    parser: Any | None = None
    project_root: Path | None = None

    @classmethod
    def from_globals(
        cls,
        *,
        backend: str = "aot",
        parser: Any | None = None,
        source_provider: Any | None = None,
        project_root: str | Path | None = None,
    ) -> "CompilationSession":
        """Create a compatibility view over the legacy frontend globals."""

        return cls(
            # Compatibility input only: the fresh session owns all mutable
            # containers from this point onward.
            stack=dict(globals.STACK) if globals.STACK is not None else None,
            stack_size=globals.STACK_SIZE,
            defines=set(globals.DEFINES),
            tables=dict(globals.TABLES),
            pending_tables={},
            rules=dict(globals.RULES),
            config=globals.CONFIG,
            linker=globals.LINKER,
            supports=dict(globals.SUPPORTS),
            asm_variants=dict(globals.ASM_VARIANTS),
            loaded_sources=dict(globals.LOADED_SOURCES),
            active_sources=[],
            variant_stack=list(globals.VARIANT_STACK),
            source_provider=(
                source_provider if source_provider is not None else globals.SOURCE_PROVIDER
            ),
            blocks={name: list(items) for name, items in globals.BLOCKS.items()},
            backend=backend,
            parser=parser,
            project_root=(
                Path(project_root).expanduser().resolve(strict=False)
                if project_root is not None
                else None
            ),
        )

    def sync_to_globals(self) -> None:
        """Expose a compatibility session through the old module globals."""

        globals.STACK = self.stack
        globals.STACK_SIZE = self.stack_size
        globals.CONFIG = self.config
        globals.LINKER = self.linker
        globals.SOURCE_PROVIDER = self.source_provider
        globals.DEFINES = self.defines
        globals.TABLES = self.tables
        # Pending declarations never come from or return to the legacy state.
        # Keep the old container empty for callers that still clear/inspect it.
        globals.PENDING_TABLES.clear()
        globals.RULES = self.rules
        globals.SUPPORTS = self.supports
        globals.ASM_VARIANTS = self.asm_variants
        globals.LOADED_SOURCES = dict(self.loaded_sources)
        globals.ACTIVE_SOURCES = list(self.active_sources)
        globals.VARIANT_STACK = list(self.variant_stack)
        globals.BLOCKS = {name: list(items) for name, items in self.blocks.items()}

    def freeze(self) -> globals.TargetContext:
        """Return an immutable target snapshot detached from this session."""

        config = self.config
        if config is not None:
            config = replace(
                config,
                sectionflags=dict(config.sectionflags),
                sectionalign=dict(config.sectionalign),
                sectionvaddr=dict(config.sectionvaddr),
            )
        tables = {
            name: globals.TableData(
                name=table.name,
                headers=tuple(table.headers),
                matrix=tuple(tuple(row) for row in table.matrix),
                columns=dict(table.columns),
            )
            for name, table in self.tables.items()
        }
        return globals.TargetContext(
            config=config,
            linker=self.linker,
            defines=frozenset(self.defines),
            stack_size=self.stack_size,
            tables=tables,
            supports=dict(self.supports),
            asm_variants=dict(self.asm_variants),
            loaded_sources=dict(self.loaded_sources),
            blocks={name: tuple(items) for name, items in self.blocks.items()},
        )

    def finalize(self) -> globals.TargetContext:
        """Resolve frontend declarations and freeze the target context.

        MIR resolution remains a separate phase. This method owns the last
        mutable frontend work, currently table joins/lookups and variant rule
        validation, before any compiled instruction can observe the context.
        """

        from Frontend.processor.variants import validate_variant_rules
        from Frontend.processor.visitors.table import resolve_pending_tables

        resolve_pending_tables(self)
        validate_variant_rules(self)
        return self.freeze()


__all__ = ["CompilationSession"]
