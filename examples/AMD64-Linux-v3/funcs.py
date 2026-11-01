"""Linking experiment for RIF on Linux AMD64.

The RIF source defines the instruction encodings and reserves every relocation
slot. This optional, explicit Python escape computes final signed PC-relative
and virtual-address fixups because RIF 1.0.1 cannot yet express a dynamic
.patch offset or generic arithmetic over two arbitrary MIR labels. The
``link_image`` hook is reached through an explicit MIR Rule, never through
``::RIF_PATCH``.

State is stored on *this compilation's* machine, never in module globals.
"""
from __future__ import annotations

from collections.abc import Mapping


def _state(context):
    return context.storage.setdefault("__amd64_linker__", {"symbols": {}, "fixups": []})


def _symbol_token(context) -> str:
    token = context.current_token
    value = getattr(token, "value", None)
    if not isinstance(value, str) or not value.isidentifier():
        raise ValueError(f"Se esperaba un identificador de símbolo, recibido {value!r}.")
    return value


def _virtual_address(context) -> int:
    if context.virtual_position % 8:
        raise ValueError("La posición virtual no está alineada a bytes.")
    return context.virtual_base + context.virtual_position // 8


def _reserve_location(context, name: str) -> tuple[int, int, int]:
    span = context.buffer.regions.get(name)
    if span is None:
        raise ValueError(f"No existe la reserva de fixup {name!r}.")
    if span.offset % 8 or span.width % 8:
        raise ValueError("Reserva de relocación desalineada.")
    # Position after the entire instruction (current cursor) is PC for rel8/rel32.
    return context.file_offset + span.offset // 8, span.width // 8, _virtual_address(context)


def _define_symbol(context) -> bool:
    name = _symbol_token(context)
    state = _state(context)
    if name in state["symbols"]:
        raise ValueError(f"Símbolo duplicado: {name}")
    state["symbols"][name] = _virtual_address(context)
    return True


def _record_relocation(context, *, kind: str, width: int) -> bool:
    target = _symbol_token(context)
    offset, reserved_width, pc_after_instruction = _reserve_location(context, f"fix{width * 8}")
    if reserved_width != width:
        raise ValueError(f"Reserva inconsistente: {reserved_width} bytes para {kind}.")
    state = _state(context)
    state["fixups"].append((kind, offset, width, pc_after_instruction, target))
    return True


def _relocate_image(context) -> bool:
    state = _state(context)
    if context.image is None:
        raise ValueError("La compilación no tiene AssemblyImage.")
    # main_rw uses a fixed 0x401000 RW mapping; prevent silent segment overlap.
    if context.program.context.config and context.config.sectionvaddr.get("data") == 0x401000:
        if context.image.sections["text"].buffer.byte_length > 4096:
            raise ValueError(".text supera 4096 bytes y solapa el segmento RW 0x401000")
    image = bytearray(context.image_binary)
    # Preflight ALL fixes first, no partial output on failure.
    planned = []
    for kind, offset, width, next_ip, symbol in state["fixups"]:
        if symbol not in state["symbols"]:
            raise ValueError(f"Símbolo no definido: {symbol}")
        address = state["symbols"][symbol]
        value = address - next_ip if kind.startswith("pc") else address
        bits = width * 8
        if kind.startswith("pc"):
            if not -(1 << (bits - 1)) <= value < (1 << (bits - 1)):
                raise ValueError(f"{kind}: desplazamiento {value} fuera del rango int{bits} para {symbol}")
            payload = value.to_bytes(width, "little", signed=True)
        else:
            if not 0 <= value < (1 << bits):
                raise ValueError(f"{kind}: dirección virtual inválida: {value}")
            payload = value.to_bytes(width, "little", signed=False)
        if not (0 <= offset and offset + width <= len(image)):
            raise ValueError(f"Relocación fuera del binario: {offset}:{width}")
        planned.append((offset, width, payload))
    spans = sorted((offset, offset + width) for offset, width, _ in planned)
    for previous, current in zip(spans, spans[1:]):
        if current[0] < previous[1]:
            raise ValueError("Relocaciones solapadas")
    for offset, width, payload in planned:
        image[offset : offset + width] = payload
    context.image.set_final_bytes(bytes(image))
    return True


def _select_section(context, section: str) -> bool:
    """Demonstration bridge: external MIR currently binds just one section."""
    if context.image is None or section not in context.image.sections:
        raise ValueError(f"Sección desconocida: {section}")
    context.image.select(section)
    context.machine.emitter = context.image.emitter(section)
    context.machine.section_name = section
    context.section = context.image.section(section)
    return True


def handler(name: str, context):
    if name == "select_text":
        return _select_section(context, "text")
    if name == "select_data":
        return _select_section(context, "data")
    if name == "define_symbol":
        return _define_symbol(context)
    if name == "record_pc32":
        return _record_relocation(context, kind="pc32", width=4)
    if name == "record_pc8":
        return _record_relocation(context, kind="pc8", width=1)
    if name == "record_abs64":
        return _record_relocation(context, kind="abs64", width=8)
    if name == "link_image":
        return _relocate_image(context)
    raise ValueError(f"Función de link desconocida: {name}")
