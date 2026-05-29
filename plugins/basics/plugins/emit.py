"""Construye IR de emisión de bits exactos para el codegen.

Sintaxis soportada:

    emit 0000 0100
    emit bits 0000 0100
    emit cbits 000 0 op2.code

`emit`/`emit bits` emite exactamente un byte cuando todo es estático. Si
encuentra 8 bits estáticos los compacta a un chunk `byte` para que el codegen
pueda escribirlo directamente.

`emit cbits` conserva los chunks como bits/placeholders crudos. Sirve para
plantillas que se completan más tarde con campos de operandos, por ejemplo
`op2.code`.
"""

from __future__ import annotations

import re
from typing import Any

from rif import (
    EmitChunk,
    EmitInstruction,
    Err,
    Expr,
    Line,
    Operator,
    Operators,
    RuleIndicator,
    TYPES_MAP,
)

_BITS_RE = re.compile(r"^[01]+$")
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_:-]*$")
_PLACEHOLDER_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_:-]*)\.([A-Za-z_][A-Za-z0-9_]*)$")
_MODES = {"bits", "cbits"}
_MAX_BITS_PER_EMIT = 8


def _clean(value: Any) -> str:
    if hasattr(value, "value"):
        value = value.value
    return str(value).strip()


def _section_for_type(type_ref: Any) -> str | None:
    """Convierte una referencia de tipo en sección verificable, si aplica."""
    name = _clean(type_ref)

    # Tipos especiales que no necesariamente tienen tabla durante parse.
    if name == "SYMBOL":
        return None

    # SREG se deriva de la tabla .regs.
    if name == ".regs.subs":
        return ".regs"

    if name.startswith("."):
        return name

    mapped = TYPES_MAP.get(name)
    if mapped is None:
        return None

    mapped_name = _clean(mapped)
    if mapped_name == ".regs.subs":
        return ".regs"
    if mapped_name.startswith("."):
        return mapped_name
    return None


def _validate_placeholder(target: str, field: str) -> Err | None:
    binding = Operator.Binding(target, RuleIndicator.current)
    if binding is None:
        return Err(f'Placeholder desconocido "{target}.{field}". "{target}" no fue capturado por need')

    program = Operators.program
    if program is None:
        return None

    checked_sections: set[str] = set()
    missing: list[str] = []

    for type_ref in binding.valid_types:
        section_name = _section_for_type(type_ref)
        if not section_name or section_name in checked_sections:
            continue
        checked_sections.add(section_name)

        table = program.tables.get(section_name)
        if table is None:
            # La sección puede ser un tipo derivado o builtin que resolverá el codegen.
            continue
        if field not in table.fields:
            missing.append(section_name)

    if missing:
        sections = ", ".join(sorted(missing))
        return Err(f'El placeholder "{target}.{field}" requiere el campo "{field}" en: {sections}')

    return None


def _parse_chunk(token: str) -> EmitChunk | Err:
    if _BITS_RE.match(token):
        if len(token) > _MAX_BITS_PER_EMIT:
            return Err("Un fragmento literal de emit no puede superar 8 bits")
        return EmitChunk(kind="bits", value=token, width=len(token))

    program = Operators.program
    if program is not None and token in getattr(program, "vars", {}):
        bit_var = program.vars[token]
        return EmitChunk(kind="bits", value=bit_var.bits, width=bit_var.width)

    match = _PLACEHOLDER_RE.match(token)
    if match:
        target, field = match.groups()
        error = _validate_placeholder(target, field)
        if error is not None:
            return error
        return EmitChunk(
            kind="placeholder",
            value=token,
            target=target,
            field=field,
            width=None,
        )

    if _IDENT_RE.match(token):
        return EmitChunk(kind="bits_ref", value=token, width=None)

    return Err(f'Fragmento inválido para emit: "{token}"')


def _compact_static_byte(chunks: list[EmitChunk]) -> list[EmitChunk]:
    if any(chunk.kind != "bits" for chunk in chunks):
        return chunks

    bits = "".join(chunk.value for chunk in chunks)
    if len(bits) != 8:
        return chunks

    return [EmitChunk(kind="byte", value=bits, width=8, byte=int(bits, 2))]


def main():
    if Line.elements <= 1:
        return Err("Se esperaba al menos un fragmento de bits")

    Line.Advance()  # consumir "emit"

    mode = "bits"
    first = Line.Peek()
    if first in _MODES:
        mode = _clean(Line.Advance())

    raw_chunks = [_clean(item) for item in Line.toks if _clean(item) != ","]
    Line.toks.clear()
    Line.expects(" ", "\n")

    if not raw_chunks:
        return Err("Se esperaba al menos un fragmento de bits")

    chunks: list[EmitChunk] = []
    static_width = 0
    has_placeholder = False

    for token in raw_chunks:
        if not token:
            return Err("emit no permite fragmentos vacíos")

        chunk = _parse_chunk(token)
        if isinstance(chunk, Err):
            return chunk

        chunks.append(chunk)
        if chunk.kind == "bits":
            static_width += chunk.width or 0
        else:
            has_placeholder = True

    if static_width > _MAX_BITS_PER_EMIT:
        return Err("Cada emit solamente permite hasta 8 bits estáticos")

    requires_byte = mode != "cbits"

    if requires_byte and not has_placeholder and static_width != 8:
        return Err("emit bits requiere exactamente 8 bits cuando no hay placeholders")

    if requires_byte:
        chunks = _compact_static_byte(chunks)

    instruction = EmitInstruction(
        mode=mode,
        chunks=tuple(chunks),
        rule_name=RuleIndicator.current,
        line=getattr(Line, "line", None),
        requires_byte=requires_byte,
    )

    return Expr(["emit_bits_exact", instruction])


def _start():
    return main()
