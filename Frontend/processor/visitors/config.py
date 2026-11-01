from __future__ import annotations

from typing import Any

from Frontend import globals
from rif_core.limits import resolve_limits


_SCALAR_FIELDS = {
    "word_size",
    "address_size",
    "byte_order",
    "comment",
    "case_sensitive",
    "symbol_prefix",
    "local_prefix",
    "undefined_symbols",
    "duplicate_symbols",
    "strict",
    "allow_empty_sections",
    "bit_order",
}
_FORMATS = {"section", "section_end", "label_end", "comment"}


def _name_value(entry: globals.BlockEntryData, field: str) -> str:
    if len(entry.values) != 1:
        raise RuntimeError(f"La entrada '{field}' requiere un nombre.")
    value = entry.values[0]
    if value.kind not in {"IDENT", "KEYWORD"} or not isinstance(value.value, str) or not value.value:
        raise RuntimeError(f"La entrada '{field}' requiere un nombre no vacío.")
    return value.value


def _string_value(
    entry: globals.BlockEntryData,
    field: str,
    *,
    allow_empty: bool = False,
) -> str:
    if len(entry.values) != 1:
        raise RuntimeError(f"La entrada '{field}' requiere un string.")
    value = entry.values[0]
    if value.kind != "STRING" or not isinstance(value.value, str):
        raise RuntimeError(f"La entrada '{field}' requiere un string.")
    if not allow_empty and not value.value:
        raise RuntimeError(f"La entrada '{field}' requiere un string no vacío.")
    return value.value


def _literal_value(entry: globals.BlockEntryData, field: str, kind: str) -> Any:
    if len(entry.values) != 1:
        raise RuntimeError(f"La entrada '{field}' requiere un valor {kind}.")
    value = entry.values[0]
    allowed = {kind}
    if kind == "NUMBER":
        allowed.add("DECIMAL")
    if value.kind not in allowed:
        raise RuntimeError(f"La entrada '{field}' requiere un valor {kind}.")
    return value.value


def _section_number(entry: globals.BlockEntryData) -> tuple[str, Any]:
    if len(entry.values) != 2:
        raise RuntimeError(f"La entrada '{entry.name}' requiere una sección y un número.")
    section = entry.values[0]
    number = entry.values[1]
    if section.kind not in {"IDENT", "KEYWORD"} or not isinstance(section.value, str) or not section.value:
        raise RuntimeError(f"{entry.name} requiere una sección no vacía.")
    if number.kind not in {"NUMBER", "DECIMAL"}:
        raise RuntimeError(f"{entry.name} requiere un número.")
    return section.value, number.value


def _section(entry: globals.BlockEntryData) -> tuple[str, str]:
    if len(entry.values) not in {1, 2}:
        raise RuntimeError("section requiere un nombre y opcionalmente sus flags.")
    name = entry.values[0]
    if name.kind not in {"IDENT", "KEYWORD"} or not isinstance(name.value, str) or not name.value:
        raise RuntimeError("section requiere un nombre no vacío.")
    flags = ""
    if len(entry.values) == 2:
        value = entry.values[1]
        if value.kind != "STRING" or not isinstance(value.value, str):
            raise RuntimeError("section requiere flags como string.")
        flags = value.value
    return name.value, flags


def _entry(entry: globals.BlockEntryData) -> tuple[str, str]:
    if len(entry.values) != 2:
        raise RuntimeError("entry requiere una sección y un label.")
    section = entry.values[0]
    label = entry.values[1]
    if section.kind not in {"IDENT", "KEYWORD"} or not isinstance(section.value, str) or not section.value:
        raise RuntimeError("entry requiere una sección no vacía.")
    if label.kind != "STRING" or not isinstance(label.value, str) or not label.value:
        raise RuntimeError("entry requiere un label no vacío.")
    return section.value, label.value


def visit(block: globals.BlockData) -> None:
    """Validate and materialize the canonical generic ``config`` block."""

    if globals.CONFIG is not None:
        raise RuntimeError("Solo puede declararse un bloque @block config por programa.")

    values: dict[str, Any] = {}
    formats: dict[str, str] = {}
    sections: list[str] = []
    section_flags: dict[str, str] = {}
    section_align: dict[str, int] = {}
    section_vaddr: dict[str, int] = {}
    entry_section: str | None = None
    entry_label: str | None = None
    default_section: str | None = None

    for entry in block.entries:
        name = entry.name
        if name == "format":
            if len(entry.values) != 2:
                raise RuntimeError("format requiere un destino y un string.")
            target = entry.values[0]
            if target.kind not in {"IDENT", "KEYWORD"} or target.value not in _FORMATS:
                raise RuntimeError("format admite section, section_end, label_end o comment.")
            if target.value in formats:
                raise RuntimeError(f"format '{target.value}' solo puede aparecer una vez.")
            value = entry.values[1]
            if value.kind != "STRING" or not isinstance(value.value, str) or not value.value:
                raise RuntimeError(f"format {target.value} requiere un string no vacío.")
            formats[target.value] = value.value
        elif name == "section":
            section, flags = _section(entry)
            if section in sections:
                raise RuntimeError(f"La sección '{section}' ya fue declarada.")
            sections.append(section)
            section_flags[section] = flags
        elif name == "entry":
            if entry_section is not None:
                raise RuntimeError("La entrada 'entry' solo puede aparecer una vez.")
            entry_section, entry_label = _entry(entry)
        elif name == "default":
            if default_section is not None:
                raise RuntimeError("La entrada 'default' solo puede aparecer una vez.")
            default_section = _name_value(entry, name)
        elif name in {"align", "vaddr"}:
            section, number = _section_number(entry)
            target = section_align if name == "align" else section_vaddr
            if section in target:
                raise RuntimeError(f"{name} ya fue declarada para '{section}'.")
            if isinstance(number, bool) or not isinstance(number, int):
                raise RuntimeError(f"{name} debe ser un entero.")
            if name == "align":
                if number <= 0:
                    raise RuntimeError("align debe ser un entero mayor que cero.")
            elif number < 0:
                raise RuntimeError("vaddr debe ser un entero no negativo.")
            target[section] = number
        elif name in _SCALAR_FIELDS:
            if name in values:
                raise RuntimeError(f"La entrada '{name}' solo puede aparecer una vez.")
            values[name] = entry
        else:
            raise RuntimeError(f"Entrada de @block config desconocida: {name}.")

    if not sections:
        raise RuntimeError("@block config debe declarar al menos una sección.")

    entry_section = entry_section or sections[0]
    entry_label = entry_label or "_start"
    default_section = default_section or entry_section
    if entry_section not in sections:
        raise RuntimeError(f"entry referencia la sección desconocida '{entry_section}'.")
    if default_section not in sections:
        raise RuntimeError(f"default referencia la sección desconocida '{default_section}'.")
    for section in (*section_align.keys(), *section_vaddr.keys()):
        if section not in sections:
            raise RuntimeError(f"La sección '{section}' no fue declarada con section.")

    def number(name: str, default: int) -> int:
        entry = values.get(name)
        value = default if entry is None else _literal_value(entry, name, "NUMBER")
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise RuntimeError(f"'{name}' debe ser un entero mayor que cero.")
        if value > resolve_limits().cap(256 << 20) * 8:
            raise RuntimeError(f"'{name}' excede el límite de recursos configurado.")
        return value

    def boolean(name: str, default: bool) -> bool:
        entry = values.get(name)
        if entry is None:
            return default
        value = _literal_value(entry, name, "BOOL")
        if not isinstance(value, bool):
            raise RuntimeError(f"'{name}' debe ser booleano.")
        return value

    def string(name: str, default: str, *, allow_name: bool = False) -> str:
        entry = values.get(name)
        if entry is None:
            return default
        if allow_name and len(entry.values) == 1:
            value = entry.values[0]
            if value.kind in {"IDENT", "KEYWORD"} and isinstance(value.value, str):
                return value.value
        return _string_value(entry, name)

    word_size = number("word_size", 32)
    address_size = number("address_size", word_size)
    byte_order = string("byte_order", "little", allow_name=True).lower()
    bit_order = string("bit_order", "msb", allow_name=True).lower()
    if byte_order not in {"little", "big"}:
        raise RuntimeError("byte_order debe ser 'little' o 'big'.")
    if bit_order not in {"msb", "lsb"}:
        raise RuntimeError("bit_order debe ser 'msb' o 'lsb'.")

    undefined_symbols = string("undefined_symbols", "error")
    duplicate_symbols = string("duplicate_symbols", "error")
    if undefined_symbols not in {"error", "warn", "ignore"}:
        raise RuntimeError("undefined_symbols debe ser 'error', 'warn' o 'ignore'.")
    if duplicate_symbols not in {"error", "warn", "ignore"}:
        raise RuntimeError("duplicate_symbols debe ser 'error', 'warn' o 'ignore'.")

    globals.CONFIG = globals.ConfigData(
        sectiondef=formats.get("section", ".section"),
        sections=tuple(sections),
        sectionend=formats.get("section_end", ":"),
        entrysection=entry_section,
        entrylabel=entry_label,
        comment=formats.get("comment", ";"),
        labelend=formats.get("label_end", ":"),
        # ``datasection`` is no longer part of the source contract.  The
        # internal snapshot keeps the default section for old serialized data.
        datasection=default_section,
        defaultsection=default_section,
        sectionflags=section_flags,
        sectionalign=section_align,
        wordsize=word_size,
        addresssize=address_size,
        endianness=byte_order,
        casesensitive=boolean("case_sensitive", True),
        symbolprefix=string("symbol_prefix", "_"),
        localprefix=string("local_prefix", "."),
        undefinedsymbols=undefined_symbols,
        duplicatesymbols=duplicate_symbols,
        strict=boolean("strict", True),
        allowemptysections=boolean("allow_empty_sections", False),
        bitorder=bit_order,
        sectionvaddr=section_vaddr,
    )


__all__ = ["visit"]
