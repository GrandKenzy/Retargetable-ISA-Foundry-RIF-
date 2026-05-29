"""Emite una dirección de memoria como placeholder.

Se conserva el nombre `emitadress` porque así fue definido en la DSL.
"""

from __future__ import annotations

from typing import Any

from rif import Err, Expr, Line, Placeholder, RuleIndicator


def _clean(value: Any) -> str:
    if hasattr(value, "value"):
        value = value.value
    return str(value).strip()


def main():
    if Line.elements != 2:
        return Err("emitadress espera un operando")

    Line.Advance()  # consumir "emitadress"
    target = _clean(Line.Advance())
    Line.expects(" ", "\n")

    if not target:
        return Err("emitadress espera un operando")

    return Expr([
        "emit_address",
        Placeholder(
            target=target,
            kind="address",
            reason="dirección de memoria diferida",
            rule_name=RuleIndicator.current,
            line=getattr(Line, "line", None),
        ),
    ])


def _start():
    return main()
