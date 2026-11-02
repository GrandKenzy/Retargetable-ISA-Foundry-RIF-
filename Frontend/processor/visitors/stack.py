from __future__ import annotations

from typing import Any

from Frontend import globals
from Frontend.session import CompilationSession


def _stack_size(node: Any) -> int:
    """Extract the NUMBER child from a STACK ASTRef."""
    sign = 1
    pending = [node]
    while pending:
        current = pending.pop(0)
        token = getattr(current, "token", None)
        token_name = getattr(getattr(token, "token", None), "name", None)
        if token_name == "MINUS":
            sign = -1
        if token_name in {"NUMBER", "DECIMAL"}:
            value = token.value
            if isinstance(value, bool) or not isinstance(value, int):
                raise RuntimeError("El tamaño de @stack debe ser un entero.")
            return sign * value
        pending.extend(getattr(current, "nodes", ()))

    raise RuntimeError("No se encontró el tamaño de @stack en el AST.")

def visit(node: Any, session: CompilationSession) -> None:
    """Procesa la declaración única de stack del programa."""
    if session.stack is not None:
        raise RuntimeError("Solo puede declararse un @stack por programa.")

    size = _stack_size(node)
    if size <= 0:
        raise RuntimeError("El tamaño de @stack debe ser mayor que cero.")

    session.stack = {}
    session.stack_size = size


__all__ = ["visit"]
