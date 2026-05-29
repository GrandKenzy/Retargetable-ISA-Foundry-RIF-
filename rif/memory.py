from __future__ import annotations

"""Módulo de configuración y layout de memoria del compilador RIF.

Se encarga de estructurar regiones de memoria (stacks, heaps, buffers)
y calcular sus tamaños, alineaciones, rellenos y offsets a partir de los
tipos de datos y dimensiones definidas.
"""

from typing import Any

from .errors import PackError
from .models import MemoryRegion, Program


def memory_region_from_values(
    kind: str,
    name: str,
    values: dict[str, Any],
    line: int | None,
    program: Program,
) -> MemoryRegion:
    """Construye y normaliza un objeto MemoryRegion a partir de un conjunto de atributos."""
    kind = kind.strip().lower()
    type_token = str(_field(values, "TYPE", "type", default="b8")).strip()
    type_name, dimensions = _split_type_token(type_token)
    element_bits = _type_bits(type_name, program)

    count = _intish(_field(values, "COUNT", "count", "ELEMENTS", "elements", "LENGTH", "length", default=None), 0)
    if dimensions:
        count = 1
        for item in dimensions:
            count *= item
    if count <= 0:
        count = 1

    explicit_bits = _intish(_field(values, "BITS", "bits", default=None), 0)
    explicit_bytes = _intish(_field(values, "SIZE", "size", "BYTES", "bytes", default=None), 0)
    if explicit_bits > 0:
        bits = explicit_bits
        total_bytes = _ceil_div(bits, 8)
    elif explicit_bytes > 0:
        total_bytes = explicit_bytes
        bits = total_bytes * 8
    elif element_bits is not None:
        bits = element_bits * count
        total_bytes = _ceil_div(bits, 8)
    else:
        raise PackError(f'{kind} "{name}" necesita SIZE/BITS o un TYPE con SIZE fijo')

    section = str(_field(values, "SECTION", "section", "SEGMENT", "segment", default="") or "").strip()
    if not section:
        section = _default_memory_section(program)
    if not section.startswith("."):
        section = f".{section}"

    align = max(1, _intish(_field(values, "ALIGN", "align", default=1), 1))
    fill = _field(values, "FILL", "fill", default=0)

    normalized = dict(values)
    normalized.update({
        "NAME": name,
        "KIND": kind,
        "PRIVTYPE": kind,
        "TYPE": type_name,
        "TYPE_RAW": type_token,
        "SECTION": section,
        "COUNT": count,
        "count": count,
        "ELEMENT_BITS": element_bits,
        "bits": bits,
        "bytes": total_bytes,
        "SIZE": total_bytes,
        "ALIGN": align,
        "FILL": fill,
        "vsize": total_bytes,
        "psize": 0,
    })

    return MemoryRegion(
        kind=kind,
        name=name,
        type_token=type_token,
        type_name=type_name,
        section=section,
        bytes=total_bytes,
        bits=bits,
        count=count,
        element_bits=element_bits,
        align=align,
        fill=fill,
        line=line,
        values=normalized,
    )


def memory_kind_for_section(section_name: str) -> str | None:
    """Devuelve la clasificación de la región de memoria ('stack' o 'heap') asociada a la sección."""
    lowered = section_name.strip().lower()
    if lowered in {".stacks", ".stack"}:
        return "stack"
    if lowered in {".heaps", ".heap"}:
        return "heap"
    return None


def _split_type_token(token: str) -> tuple[str, list[int]]:
    token = token.strip()
    if "[" not in token or not token.endswith("]"):
        return token, []
    name, rest = token.split("[", 1)
    body = rest[:-1].strip()
    if not body:
        return name.strip(), []
    dims: list[int] = []
    for item in body.split(","):
        value = item.strip()
        if not value:
            raise PackError(f'TYPE invalido "{token}"')
        dims.append(int(value.replace("_", ""), 0))
    return name.strip(), dims


def _type_bits(name: str, program: Program) -> int | None:
    definition = program.type_defs.get(name)
    if definition is None:
        return None
    return definition.bits


def _default_memory_section(program: Program) -> str:
    table = program.tables.get(".sections")
    for candidate in (".bss", ".data"):
        if table is not None and candidate in table.rows:
            return candidate

    if table is not None and table.rows:
        return next(iter(table.rows))
    return ".data"


def _field(values: dict[str, Any], *names: str, default: Any = None) -> Any:
    lowered = {key.lower(): key for key in values}
    for name in names:
        key = lowered.get(name.lower())
        if key is not None:
            value = values.get(key)
            if value not in (None, ""):
                return value
    return default


def _intish(value: Any, default: int = 0) -> int:
    if value in (None, "", "*"):
        return default
    if isinstance(value, int):
        return value
    text = str(value).strip().replace("_", "")
    return int(text, 0)


def _ceil_div(value: int, divisor: int) -> int:
    return (value + divisor - 1) // divisor
