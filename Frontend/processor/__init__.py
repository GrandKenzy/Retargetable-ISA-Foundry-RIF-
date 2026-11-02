from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from Frontend import globals
from Frontend.session import CompilationSession
from .visitors.define import visit as visit_define
from .visitors.rule import visit as visit_rule
from .visitors.stack import visit as visit_stack
from .visitors.table import (
    clear_pending_tables,
    resolve_pending_tables,
    visit as visit_table,
)
from .visitors.variant import visit_support, visit_variant
from .visitors.block import visit as visit_block
from Frontend.syntax.items.blocks import normalize_block
from .sources import is_config_load, load_source
from .libraries import load_library
from .variants import current_variant, enter_variant, exit_variant, load_variants as _load_variants
from .parsing import SourceParser


def process(
    result: Iterable[Any] | None,
    source_path: str | Path | None = None,
    *,
    load_variants: bool = True,
    scope: str = "root",
    source_provider: Any | None = None,
    project_root: str | Path | None = None,
    backend: str = "aot",
    parser: SourceParser | None = None,
    session: CompilationSession | None = None,
) -> None:
    """Recorre y despacha cada nodo producido por el parser."""
    if result is None:
        return

    nodes = []
    for node in result:
        if getattr(node, "name", None) == "BLOCK" and not hasattr(node, "block_name"):
            nodes.append(normalize_block(getattr(node, "nodes", ())))
        else:
            nodes.append(node)
    owns_session = session is None
    legacy_provider = globals.SOURCE_PROVIDER
    state = session or CompilationSession.from_globals(
        backend=backend,
        parser=parser,
        source_provider=source_provider,
        project_root=project_root,
    )
    previous_provider = legacy_provider if owns_session else state.source_provider
    if state.parser is None:
        state.parser = parser or SourceParser(backend=backend)
    source_parser = parser or state.parser
    state.backend = backend
    if state.project_root is None and project_root is not None:
        state.project_root = Path(project_root).expanduser().resolve(strict=False)
    if state.source_provider is None and source_provider is not None:
        state.source_provider = source_provider
    provider = source_provider if source_provider is not None else state.source_provider
    raw_source = str(source_path) if source_path is not None else ""
    if raw_source.startswith(("pack://", "riflib://", "packlib://")):
        source_key = raw_source
    else:
        source_key = (
            str(Path(source_path).expanduser().resolve(strict=False))
            if source_path
            else None
        )
    resolved_root = (
        Path(project_root).expanduser().resolve(strict=False)
        if project_root is not None
        else (
            Path(source_path).expanduser().resolve(strict=False).parent
            if source_path and not raw_source.startswith(("pack://", "riflib://", "packlib://"))
            else None
        )
    )
    owns_source = bool(source_key and source_key not in state.active_sources)
    if owns_source:
        state.active_sources.append(source_key)

    succeeded = False
    try:
        allowed = {
            "root": {
                "DEFINE", "SUPPORTS", "ASMVARIANT",
                "TABLE", "STACK", "RULE", "LOAD_FILE", "LIBRARY",
                "BLOCK",
            },
            "include": {"DEFINE", "TABLE", "RULE", "LOAD_FILE", "LIBRARY"},
            "variant": {"DEFINE", "RULE"},
            "config": {"BLOCK"},
        }
        try:
            allowed_names = allowed[scope]
        except KeyError as exc:
            raise ValueError(f"Alcance de procesamiento desconocido: {scope}") from exc
        forbidden = {
            getattr(node, "name", type(node).__name__)
            for node in nodes
            if getattr(node, "name", type(node).__name__) not in allowed_names
        }
        if forbidden:
            names = ", ".join(sorted(forbidden))
            raise RuntimeError(
                f"El alcance '{scope}' no permite estas declaraciones: {names}."
            )

        if scope == "config":
            invalid_blocks = {
                str(getattr(node, "block_name", "")).lower()
                for node in nodes
                if getattr(node, "name", type(node).__name__) == "BLOCK"
                and str(getattr(node, "block_name", "")).lower() not in {"config", "linker"}
            }
            if invalid_blocks:
                names = ", ".join(sorted(invalid_blocks))
                raise RuntimeError(
                    "config.rif solo puede declarar @block config o @block linker; "
                    f"se encontró: {names}."
                )

        # Los bloques genéricos, los labels y los soportes se registran antes
        # de resolver tablas u otras referencias, sin depender del orden.
        for node in nodes:
            name = getattr(node, "name", type(node).__name__)
            if name == "DEFINE":
                visit_define(node, state)
            elif name == "SUPPORTS":
                visit_support(node, state)
            elif name == "BLOCK":
                visit_block(node, source_path=source_key, session=state)

        for node in nodes:
            if getattr(node, "name", type(node).__name__) == "ASMVARIANT":
                visit_variant(node, state)

        for node in nodes:
            name = getattr(node, "name", type(node).__name__)
            if name in {"DEFINE", "SUPPORTS", "ASMVARIANT", "BLOCK"}:
                continue
            if name == "TABLE":
                visit_table(node, state)
            elif name == "STACK":
                visit_stack(node, state)
            elif name == "RULE":
                visit_rule(node, source_path=source_key, session=state)
            elif name == "LOAD_FILE":
                load_source(
                    node,
                    source_key,
                    scope=(
                        "config"
                        if scope == "root" and is_config_load(node)
                        else "include"
                    ),
                    source_provider=provider,
                    project_root=resolved_root,
                    backend=backend,
                    parser=source_parser,
                    session=state,
                )
            elif name == "LIBRARY":
                load_library(
                    node,
                    source_key,
                    source_provider=provider,
                    project_root=resolved_root,
                    backend=backend,
                    parser=source_parser,
                    session=state,
                )
            else:
                print("falta por procesar", name)

        if load_variants and source_key:
            _load_variants(
                source_key,
                source_provider=provider,
                project_root=resolved_root,
                backend=backend,
                parser=source_parser,
                session=state,
            )
        succeeded = True
    except Exception as exc:
        # Keep the original source failure attached to this session without
        # duplicating the same exception as it unwinds nested loaders.
        if not any(item is exc for item in state.diagnostics):
            state.diagnostics.append(exc)
        raise
    finally:
        if owns_source and source_key in state.active_sources:
            state.active_sources.remove(source_key)
        if owns_session:
            try:
                if succeeded:
                    resolve_pending_tables(state)
                else:
                    clear_pending_tables(state)
            except Exception:
                clear_pending_tables(state)
                raise
            finally:
                state.source_provider = previous_provider
                state.sync_to_globals()
        elif not succeeded:
            clear_pending_tables(state)


__all__ = [
    "process",
    "load_variants",
    "load_source",
    "load_library",
    "enter_variant",
    "exit_variant",
    "current_variant",
]

# API pública con el nombre previsto por el plan; el alias interno evita que
# el parámetro ``load_variants`` de process oculte la función importada.
load_variants = _load_variants
