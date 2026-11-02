from __future__ import annotations

from typing import Any

from Frontend import globals
from Frontend.session import CompilationSession


def _define_name(node: Any) -> str:
    """Extrae el IDENT de una declaración DEFINE del AST."""
    pending = [node]
    while pending:
        current = pending.pop(0)
        token = getattr(current, "token", None)
        token_kind = getattr(getattr(token, "token", None), "name", None)
        if token_kind == "IDENT":
            value = getattr(token, "value", None)
            if isinstance(value, str) and value:
                return value
        pending.extend(getattr(current, "nodes", ()) or ())

    raise RuntimeError("No se encontró el nombre de @define en el AST.")


def visit(node: Any, session: CompilationSession) -> None:
    """Registra una etiqueta de palabra declarada con @define."""
    name = _define_name(node)
    if name in session.defines:
        raise RuntimeError(f"El nombre '{name}' ya fue declarado con @define.")

    session.defines.add(name)


__all__ = ["visit"]
