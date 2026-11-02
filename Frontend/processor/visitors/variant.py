from __future__ import annotations

from typing import Any

from Frontend import globals
from Frontend.session import CompilationSession


def _children(node: Any) -> tuple[Any, ...]:
    if isinstance(node, (list, tuple)):
        return tuple(node)
    return tuple(getattr(node, "nodes", ()) or ())


def _token_kind(node: Any) -> str | None:
    token = getattr(node, "token", None)
    return getattr(getattr(token, "token", None), "name", None)


def _token_value(node: Any) -> Any:
    token = getattr(node, "token", None)
    return getattr(token, "value", None)


def _walk(node: Any):
    yield node
    for child in _children(node):
        yield from _walk(child)


def _identifier(node: Any) -> str:
    values = tuple(
        _token_value(child)
        for child in _walk(node)
        if _token_kind(child) == "IDENT"
    )
    if len(values) != 1 or not isinstance(values[0], str) or not values[0]:
        raise RuntimeError("La variante requiere un nombre IDENT válido.")
    return values[0]


def _string(node: Any, directive: str) -> str:
    values = tuple(
        _token_value(child)
        for child in _walk(node)
        if _token_kind(child) == "STRING"
    )
    if len(values) != 1 or not isinstance(values[0], str) or not values[0]:
        raise RuntimeError(f".{directive} requiere un string no vacío.")
    return values[0]


def visit_support(node: Any, session: CompilationSession) -> None:
    name = _identifier(node)
    if name in session.supports:
        raise RuntimeError(f"La variante '{name}' ya fue declarada con @SUPPORTS.")
    session.supports[name] = globals.SupportData(name=name, path=f"{name}.rif")


def visit_variant(node: Any, session: CompilationSession) -> None:
    children = _children(node)
    if len(children) < 6 or not isinstance(children[5], list):
        raise RuntimeError("@ASMVARIANT debe contener directivas de variante.")

    name = _identifier(children[2])
    if name not in session.supports:
        raise RuntimeError(
            f"La variante '{name}' debe declararse antes con @SUPPORTS."
        )
    if name in session.asm_variants:
        raise RuntimeError(f"La variante '{name}' ya fue configurada.")

    mode: str | None = None
    enter_rule: str | None = None
    exit_rule: str | None = None

    for item in children[5]:
        item_name = getattr(item, "name", None)
        if item_name == "VARIANT_MODE":
            values = tuple(
                _token_value(child)
                for child in _walk(item)
                if _token_kind(child) == "KEYWORD"
                and _token_value(child) in {"SWITCH", "ENCAPSULATE"}
            )
            if len(values) != 1:
                raise RuntimeError(".MODE requiere SWITCH o ENCAPSULATE.")
            if mode is not None:
                raise RuntimeError(f"La variante '{name}' repite .MODE.")
            mode = values[0]
        elif item_name == "VARIANT_ENTER":
            if enter_rule is not None:
                raise RuntimeError(f"La variante '{name}' repite .ENTER.")
            enter_rule = _string(item, "ENTER")
        elif item_name == "VARIANT_EXIT":
            if exit_rule is not None:
                raise RuntimeError(f"La variante '{name}' repite .EXIT.")
            exit_rule = _string(item, "EXIT")
        else:
            raise RuntimeError(f"Directiva de variante desconocida: {item_name}.")

    missing = [
        field
        for field, value in (
            ("MODE", mode),
            ("ENTER", enter_rule),
            ("EXIT", exit_rule),
        )
        if value is None
    ]
    if missing:
        raise RuntimeError(
            f"Faltan directivas en @ASMVARIANT {name}: " + ", ".join(missing)
        )

    session.asm_variants[name] = globals.AsmVariantData(
        name=name,
        mode=mode,
        enter_rule=enter_rule,
        exit_rule=exit_rule,
        path=session.supports[name].path,
    )


__all__ = ["visit_support", "visit_variant"]
