"""Llama una regla existente usando los bindings actuales.

Sintaxis:

    call mov

`call` no rematchea operandos. Reutiliza las capturas que ya existen en la
regla actual y ejecuta la lógica/codegen de la regla llamada.
"""

from __future__ import annotations

import re
from typing import Any

from rif import Err, Expr, Line

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_:-]*$")


def _clean(value: Any) -> str:
    if hasattr(value, "value"):
        value = value.value
    return str(value).strip()


def main():
    if Line.elements != 2:
        return Err("La instrucción call espera una regla")

    Line.Advance()  # consumir "call"
    rule_name = _clean(Line.Advance())
    Line.expects(" ", "\n")

    if not _IDENTIFIER_RE.match(rule_name):
        return Err(f'Regla inválida para call: "{rule_name}"')

    return Expr(["call", rule_name])


def _start():
    return main()
