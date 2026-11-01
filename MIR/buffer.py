"""External byte-buffer phase for bounded native acquisitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from Frontend import globals
from rif_limits import resolve_limits

from .functions import ReqstsError, reqsts
from .preprocessor import RIFMetaDirective


MAX_BUFFER_BYTES = 16 << 20


class BufferError(RuntimeError):
    """A buffer declaration or operation is invalid."""


@dataclass(frozen=True)
class BufferResult:
    """Immutable result of one external buffer program."""

    capacity_bytes: int
    data: bytes
    extractions: tuple[bytes, ...] = ()


def _entry_value(entry: globals.BlockEntryData, index: int) -> Any:
    try:
        return entry.values[index].value
    except IndexError as exc:
        raise BufferError(
            f"buffer {entry.name} requiere {index + 1} valor(es)."
        ) from exc


def _require_values(entry: globals.BlockEntryData, count: int) -> None:
    if len(entry.values) != count:
        raise BufferError(
            f"buffer {entry.name} requiere exactamente {count} valor(es)."
        )


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BufferError(f"buffer {label} requiere un entero.")
    return value


def execute_buffer(blocks: Iterable[globals.BlockData]) -> BufferResult | None:
    """Execute the single root ``@block buffer`` declaration, if present."""

    declared = tuple(blocks)
    if not declared:
        return None
    if len(declared) != 1:
        raise BufferError("Solo se puede declarar un @block buffer por target.")

    entries = declared[0].entries
    if not entries or entries[0].name.lower() != "capacity":
        raise BufferError("@block buffer debe comenzar con capacity.")
    _require_values(entries[0], 1)
    capacity_kib = _integer(_entry_value(entries[0], 0), "capacity")
    if capacity_kib <= 0:
        raise BufferError("buffer capacity debe ser positiva.")
    capacity_bytes = capacity_kib * 1024
    if capacity_bytes > resolve_limits().cap(MAX_BUFFER_BYTES):
        raise BufferError("buffer capacity excede el límite configurado.")

    data = bytearray()
    extractions: list[bytes] = []
    for entry in entries[1:]:
        name = entry.name.lower()
        if name == "capacity":
            raise BufferError("buffer capacity solo puede declararse una vez.")
        if name == "clean":
            _require_values(entry, 0)
            data.clear()
            continue
        if name == "call":
            _require_values(entry, 2)
            function_name = str(_entry_value(entry, 0)).lower()
            source = _entry_value(entry, 1)
            if function_name != "reqsts" or not isinstance(source, str):
                raise BufferError("buffer call solo acepta reqsts y una ruta string.")
            try:
                payload = reqsts(source)
            except ReqstsError as exc:
                raise BufferError(str(exc)) from exc
            if len(data) + len(payload) > capacity_bytes:
                raise BufferError("buffer call excede la capacidad reservada.")
            data.extend(payload)
            continue
        if name == "extract":
            _require_values(entry, 2)
            start = _integer(_entry_value(entry, 0), "extract")
            end = _integer(_entry_value(entry, 1), "extract")
            if start < 0 or end < start or end > len(data):
                raise BufferError("buffer extract está fuera del rango disponible.")
            extractions.append(bytes(data[start:end]))
            continue
        raise BufferError(f"Operación de buffer desconocida: {entry.name}.")

    return BufferResult(capacity_bytes, bytes(data), tuple(extractions))


def execute_preprocessor_buffer(
    directives: Iterable[RIFMetaDirective],
) -> BufferResult | None:
    """Execute the assembler-side buffer and GitHub acquisition directives.

    Buffer state belongs to one external MIR compilation. It is deliberately
    not part of the RIF target context, so a target can be reused safely by
    several MIR inputs.
    """

    events = tuple(
        directive
        for directive in directives
        if directive.name in {"RIF_BUFFER", "RIF_REQSTS"}
    )
    if not events:
        return None

    capacity_bytes: int | None = None
    data = bytearray()
    extractions: list[bytes] = []
    for directive in events:
        if directive.name == "RIF_REQSTS":
            if capacity_bytes is None:
                raise BufferError("::RIF_REQSTS requiere un ::RIF_BUFFER SET previo.")
            if not directive.path:
                raise BufferError("::RIF_REQSTS requiere una ruta GitHub.")
            try:
                payload = reqsts(directive.path)
            except ReqstsError as exc:
                raise BufferError(str(exc)) from exc
            if len(data) + len(payload) > capacity_bytes:
                raise BufferError("::RIF_REQSTS excede la capacidad reservada.")
            data.extend(payload)
            continue

        operation = directive.operation
        if operation == "SET":
            if capacity_bytes is not None:
                raise BufferError("::RIF_BUFFER SET solo puede declararse una vez.")
            capacity_kib = directive.index
            if capacity_kib is None or capacity_kib <= 0:
                raise BufferError("::RIF_BUFFER SET requiere una capacidad positiva.")
            capacity_bytes = capacity_kib * 1024
            if capacity_bytes > resolve_limits().cap(MAX_BUFFER_BYTES):
                raise BufferError("::RIF_BUFFER SET excede el límite configurado.")
            continue
        if capacity_bytes is None:
            raise BufferError("::RIF_BUFFER requiere SET antes de sus operaciones.")
        if operation == "CLEAN":
            data.clear()
            continue
        if operation == "EXTRACT":
            start = directive.index
            try:
                end = int(directive.section) if directive.section is not None else None
            except ValueError as exc:
                raise BufferError("::RIF_BUFFER EXTRACT requiere bytes enteros.") from exc
            if start is None or end is None or start < 0 or end < start or end > len(data):
                raise BufferError("::RIF_BUFFER EXTRACT está fuera del rango disponible.")
            extractions.append(bytes(data[start:end]))
            continue
        raise BufferError(f"Operación de buffer desconocida: {operation}.")

    assert capacity_bytes is not None
    return BufferResult(capacity_bytes, bytes(data), tuple(extractions))


__all__ = [
    "BufferError",
    "BufferResult",
    "MAX_BUFFER_BYTES",
    "execute_buffer",
    "execute_preprocessor_buffer",
]
