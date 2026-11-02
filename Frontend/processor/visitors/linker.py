from __future__ import annotations

from Frontend import globals
from Frontend.session import CompilationSession


def _value(entry: globals.BlockEntryData) -> str | bool:
    if len(entry.values) != 1:
        raise RuntimeError(f"La entrada '{entry.name}' requiere un único valor.")
    value = entry.values[0]
    if value.kind == "STRING" and isinstance(value.value, str):
        return value.value
    if value.kind == "BOOL" and isinstance(value.value, bool):
        return value.value
    raise RuntimeError(f"La entrada '{entry.name}' requiere un string o booleano.")


def visit(block: globals.BlockData, session: CompilationSession) -> None:
    """Validate and materialize the canonical generic ``linker`` block."""

    if session.linker is not None:
        raise RuntimeError("Solo puede declararse un bloque @block linker por programa.")

    extension: str | None = None
    search_paths: list[str] = []
    search_disabled = False
    for entry in block.entries:
        if entry.name not in {"extension", "search_path"}:
            raise RuntimeError(f"Entrada de @block linker desconocida: {entry.name}.")
        value = _value(entry)
        if entry.name == "extension":
            if extension is not None:
                raise RuntimeError("La entrada 'extension' solo puede aparecer una vez.")
            if not isinstance(value, str) or not value:
                raise RuntimeError("extension debe ser un string no vacío.")
            extension = value
            continue
        if value is True:
            raise RuntimeError("search_path acepta carpetas, \"\" o false; true no es válido.")
        if value is False:
            if search_disabled:
                raise RuntimeError("La entrada 'search_path' solo puede aparecer una vez como false.")
            if search_paths:
                raise RuntimeError("search_path false no puede combinarse con carpetas.")
            search_disabled = True
            continue
        if search_disabled:
            raise RuntimeError("search_path no puede combinarse con false.")
        search_paths.append(value)

    missing = []
    if extension is None:
        missing.append("extension")
    if not search_paths and not search_disabled:
        missing.append("search_path")
    if missing:
        raise RuntimeError(
            "Faltan entradas obligatorias en @block linker: " + ", ".join(missing)
        )
    assert extension is not None

    session.linker = globals.LinkerData(
        extension=extension,
        search_path=False if search_disabled else tuple(search_paths),
    )


__all__ = ["visit"]
