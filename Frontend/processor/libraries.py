"""Load portable ``.riflib`` declaration packages through the normal processor."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from Frontend import globals
from rif_core.library import LibraryReader, resolve_library
from .parsing import SourceParser


def _children(node: Any) -> tuple[Any, ...]:
    if isinstance(node, (list, tuple)):
        return tuple(node)
    return tuple(getattr(node, "nodes", ()) or ())


def _walk(node: Any):
    yield node
    for child in _children(node):
        yield from _walk(child)


def _requested_path(node: Any) -> str:
    values = tuple(
        getattr(getattr(current, "token", None), "value", None)
        for current in _walk(node)
        if getattr(getattr(getattr(current, "token", None), "token", None), "name", None) == "STRING"
    )
    if len(values) != 1 or not isinstance(values[0], str) or not values[0]:
        raise RuntimeError("@LIBRARY requiere un único path string no vacío.")
    if Path(values[0]).suffix.lower() != ".riflib":
        raise RuntimeError(f"@LIBRARY solo acepta archivos .riflib: {values[0]}")
    return values[0]


def load_library(
    node: Any,
    source_path: str | Path | None,
    *,
    source_provider: Any | None = None,
    project_root: str | Path | None = None,
    backend: str = "aot",
    parser: SourceParser | None = None,
) -> None:
    """Load one library once, with cycle protection and bounded source input."""

    requested = _requested_path(node)
    reader: LibraryReader
    if source_provider is not None and hasattr(source_provider, "resolve_library"):
        library_key = source_provider.resolve_library(source_path, requested)
        reader = source_provider.open_library(library_key)
    else:
        path = resolve_library(requested, source_path, project_root)
        reader = LibraryReader(path)
        library_key = str(path)

    entry_key = reader.virtual_path()
    if library_key in globals.ACTIVE_SOURCES or entry_key in globals.ACTIVE_SOURCES:
        cycle = " -> ".join((*globals.ACTIVE_SOURCES, entry_key))
        reader.close()
        raise RuntimeError(f"Ciclo de @LIBRARY detectado: {cycle}")
    if library_key in globals.LOADED_SOURCES or entry_key in globals.LOADED_SOURCES:
        reader.close()
        return

    from . import process

    source_parser = parser or SourceParser(backend=backend)
    globals.ACTIVE_SOURCES.append(entry_key)
    try:
        source = reader.source_text()
        ast = source_parser.parse_text(source, entry_key)
        process(
            ast,
            source_path=entry_key,
            load_variants=False,
            scope="include",
            source_provider=reader,
            project_root=None,
            backend=backend,
            parser=source_parser,
        )
        globals.LOADED_SOURCES[entry_key] = "library"
        if library_key != entry_key:
            globals.LOADED_SOURCES[library_key] = "library"
    finally:
        if globals.ACTIVE_SOURCES and globals.ACTIVE_SOURCES[-1] == entry_key:
            globals.ACTIVE_SOURCES.pop()
        elif entry_key in globals.ACTIVE_SOURCES:
            globals.ACTIVE_SOURCES.remove(entry_key)
        reader.close()


__all__ = ["load_library"]
