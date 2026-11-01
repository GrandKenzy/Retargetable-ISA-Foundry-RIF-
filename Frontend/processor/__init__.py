from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from Frontend import globals
from .visitors.define import visit as visit_define
from .visitors.rule import visit as visit_rule
from .visitors.stack import visit as visit_stack
from .visitors.table import visit as visit_table
from .visitors.variant import visit_support, visit_variant
from .visitors.block import visit as visit_block
from Frontend.syntax.items.blocks import normalize_block
from .sources import is_config_load, load_source
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
    provider = source_provider if source_provider is not None else globals.SOURCE_PROVIDER
    source_parser = parser or SourceParser(backend=backend)
    raw_source = str(source_path) if source_path is not None else ""
    if raw_source.startswith("pack://"):
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
            if source_path and not raw_source.startswith("pack://")
            else None
        )
    )
    previous_provider = globals.SOURCE_PROVIDER
    owns_provider = source_provider is not None and previous_provider is not source_provider
    if owns_provider:
        globals.SOURCE_PROVIDER = source_provider
    owns_source = bool(source_key and source_key not in globals.ACTIVE_SOURCES)
    if owns_source:
        globals.ACTIVE_SOURCES.append(source_key)

    try:
        allowed = {
            "root": {
                "DEFINE", "SUPPORTS", "ASMVARIANT",
                "TABLE", "STACK", "RULE", "LOAD_FILE",
                "BLOCK",
            },
            "include": {"DEFINE", "TABLE", "RULE", "LOAD_FILE"},
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
                visit_define(node)
            elif name == "SUPPORTS":
                visit_support(node)
            elif name == "BLOCK":
                visit_block(node, source_path=source_key)

        for node in nodes:
            if getattr(node, "name", type(node).__name__) == "ASMVARIANT":
                visit_variant(node)

        for node in nodes:
            name = getattr(node, "name", type(node).__name__)
            if name in {"DEFINE", "SUPPORTS", "ASMVARIANT", "BLOCK"}:
                continue
            if name == "TABLE":
                visit_table(node)
            elif name == "STACK":
                visit_stack(node)
            elif name == "RULE":
                visit_rule(node, source_path=source_key)
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
            )
    finally:
        if owns_source and source_key in globals.ACTIVE_SOURCES:
            globals.ACTIVE_SOURCES.remove(source_key)
        if owns_provider:
            globals.SOURCE_PROVIDER = previous_provider


__all__ = [
    "process",
    "load_variants",
    "load_source",
    "enter_variant",
    "exit_variant",
    "current_variant",
]

# API pública con el nombre previsto por el plan; el alias interno evita que
# el parámetro ``load_variants`` de process oculte la función importada.
load_variants = _load_variants
