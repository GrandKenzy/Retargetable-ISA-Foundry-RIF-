from __future__ import annotations

from typing import Any

from Frontend import globals
from Frontend.syntax.items.instructions import normalize_instruction


def _children(node: Any) -> tuple[Any, ...]:
    if isinstance(node, (list, tuple)):
        return tuple(node)
    return tuple(getattr(node, "nodes", ()) or ())


def _rule_name(node: Any) -> str:
    # RULE: AT, keyword, IDENT, COLON, NEWLINE, instructions.
    children = _children(node)
    if len(children) < 3:
        raise RuntimeError("La declaración @rule está incompleta.")

    identifier = children[2]
    token = getattr(identifier, "token", None)
    name = getattr(token, "value", None)
    if not isinstance(name, str) or not name:
        raise RuntimeError("El nombre de @rule no es válido.")
    return name


def _instructions(node: Any) -> tuple[Any, ...]:
    children = _children(node)
    if len(children) < 6 or not isinstance(children[5], list):
        raise RuntimeError("@rule debe contener una lista de instrucciones.")
    return tuple(normalize_instruction(instruction) for instruction in children[5])

def visit(node: Any, source_path: str | None = None) -> None:
    """Registra una regla y deja su ejecución para una fase posterior."""
    name = _rule_name(node)
    if name in globals.RULES:
        previous = globals.RULES[name].source_path or "<memoria>"
        current = source_path or "<memoria>"
        raise RuntimeError(
            f"La regla '{name}' ya fue declarada ({previous} y {current})."
        )

    globals.RULES[name] = globals.RuleData(
        name=name,
        node=node,
        instructions=_instructions(node),
        source_path=source_path,
    )


__all__ = ["visit"]
