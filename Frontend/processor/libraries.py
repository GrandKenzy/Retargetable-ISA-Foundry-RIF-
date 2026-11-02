"""Load portable ``.riflib`` declaration packages through the normal processor."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from Frontend import globals
from Frontend.session import CompilationSession
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
    session: CompilationSession | None = None,
) -> None:
    """Load one library once, with cycle protection and bounded source input."""

    owns_session = session is None
    state = session or CompilationSession.from_globals(
        backend=backend,
        parser=parser,
        source_provider=source_provider,
        project_root=project_root,
    )
    provider = source_provider if source_provider is not None else state.source_provider
    requested = _requested_path(node)
    reader: LibraryReader
    if provider is not None and hasattr(provider, "resolve_library"):
        library_key = provider.resolve_library(source_path, requested)
        reader = provider.open_library(library_key)
    else:
        path = resolve_library(requested, source_path, project_root)
        reader = LibraryReader(path)
        library_key = str(path)

    entry_key = reader.virtual_path()
    if library_key in state.active_sources or entry_key in state.active_sources:
        cycle = " -> ".join((*state.active_sources, entry_key))
        reader.close()
        raise RuntimeError(f"Ciclo de @LIBRARY detectado: {cycle}")
    if library_key in state.loaded_sources or entry_key in state.loaded_sources:
        reader.close()
        return

    from . import process

    source_parser = parser or state.parser or SourceParser(backend=backend)
    state.active_sources.append(entry_key)
    try:
        source = reader.source_text()
        state.source_texts[entry_key] = source
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
            session=state,
        )
        state.loaded_sources[entry_key] = "library"
        if library_key != entry_key:
            state.loaded_sources[library_key] = "library"
    finally:
        if state.active_sources and state.active_sources[-1] == entry_key:
            state.active_sources.pop()
        elif entry_key in state.active_sources:
            state.active_sources.remove(entry_key)
        reader.close()
        if owns_session:
            state.sync_to_globals()


__all__ = ["load_library"]
