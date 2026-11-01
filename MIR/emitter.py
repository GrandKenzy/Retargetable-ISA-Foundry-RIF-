"""Small semantic adapter for RIF bit-emitting instructions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from rif_limits import resolve_limits

from .bitbuffer import (
    MAX_BUFFER_BITS,
    BitBuffer,
    BitCheckpoint,
    BitLayout,
    BitQuery,
    BitSpan,
)


@dataclass(frozen=True)
class BitField:
    value: int
    width: int


@dataclass(frozen=True)
class VirtualRegion:
    """Named range in the virtual address space."""

    offset: int
    width: int
    name: str | None = None

    @property
    def end(self) -> int:
        return self.offset + self.width


@dataclass(frozen=True)
class BitEmitterCheckpoint:
    """Physical and virtual state required for an atomic Rule execution."""

    buffer: BitCheckpoint
    virtual_position: int
    virtual_regions: tuple[tuple[str, VirtualRegion], ...]


def field(value: int | str | BitField, width: int | None = None) -> BitField:
    """Normalize a literal while preserving binary strings such as ``0000``."""

    if isinstance(value, BitField):
        _validate_width(value.width)
        if width is not None and value.width != width:
            raise ValueError("El ancho del campo no coincide con el esperado.")
        return value
    if isinstance(value, str):
        if not value or any(bit not in "01" for bit in value):
            raise ValueError("Un campo binario debe contener solamente 0 y 1.")
        inferred = len(value)
        _validate_width(inferred)
        if width is not None and inferred != width:
            raise ValueError(
                f"El campo binario tiene {inferred} bits; se esperaban {width}."
            )
        return BitField(int(value, 2), inferred)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("El campo debe ser un entero, string binario o BitField.")
    if width is None:
        raise ValueError("Un entero requiere un ancho explícito.")
    _validate_width(width)
    if value < 0 or value >= (1 << width):
        raise ValueError(f"El valor {value} no cabe en {width} bits.")
    return BitField(value, width)


def _validate_width(width: int) -> None:
    if isinstance(width, bool) or not isinstance(width, int) or width <= 0:
        raise ValueError("El ancho debe ser un entero positivo.")
    maximum = resolve_limits().cap(MAX_BUFFER_BITS // 8) * 8
    if width > maximum:
        raise ValueError(f"El ancho excede el límite de {maximum} bits.")


class BitEmitter:
    """Implements the bit-oriented RIF operations over a BitBuffer."""

    def __init__(
        self,
        buffer: BitBuffer | None = None,
        *,
        wordsize: int = 32,
        layout: BitLayout | None = None,
    ) -> None:
        if wordsize <= 0:
            raise ValueError("wordsize debe ser mayor que cero.")
        self.buffer = buffer if buffer is not None else BitBuffer(layout)
        self.wordsize = wordsize
        self._virtual_position = 0
        self._virtual_regions: dict[str, VirtualRegion] = {}

    @classmethod
    def from_config(cls, config: object) -> "BitEmitter":
        """Build an emitter from the fields already materialized by RIF config."""

        return cls(
            wordsize=int(getattr(config, "wordsize")),
            layout=BitLayout(
                bit_order=str(getattr(config, "bitorder", "msb")),
                byte_order=str(getattr(config, "endianness")),
            ),
        )

    def nibbles(self, first: int | str | BitField, second: int | str | BitField) -> tuple[BitSpan, BitSpan]:
        left = field(first, 4)
        right = field(second, 4)
        spans = (
            self.buffer.append_bits(left.value, left.width),
            self.buffer.append_bits(right.value, right.width),
        )
        self._advance_virtual(left.width + right.width)
        return spans

    def emit(self, *values: int | str | BitField) -> tuple[BitSpan, ...]:
        if len(values) != 8:
            raise ValueError("emit requiere exactamente ocho campos de un bit.")
        normalized = tuple(field(value, 1) for value in values)
        spans = tuple(
            self.buffer.append_bits(item.value, 1) for item in normalized
        )
        self._advance_virtual(len(spans))
        return spans

    def eword(self, value: int | str | BitField) -> BitSpan:
        item = field(value, self.wordsize)
        return self.bits(value, item.width)

    def bits(self, value: int | str | BitField, width: int) -> BitSpan:
        """Append one value using an explicit bit width."""

        item = field(value, width)
        if item.width % 8 == 0:
            span = self.buffer.append_int(item.value, item.width)
        else:
            span = self.buffer.append_bits(item.value, item.width)
        self._advance_virtual(item.width)
        return span

    def emit_bytes(self, data: bytes | bytearray | memoryview) -> BitSpan | None:
        """Append aligned bytes using the buffer's bulk path."""

        payload = bytes(data)
        span = self.buffer.append_bytes(payload)
        if span is not None:
            self._advance_virtual(span.width)
        return span

    def read_bits(self, offset: int, width: int) -> int:
        """Read an existing physical field using the configured byte order."""
        if width <= 0:
            raise ValueError("read_bits requiere un ancho positivo.")
        if width % 8 == 0:
            return self.buffer.read_int(offset, width)
        return self.buffer.read_bits(offset, width)

    def patch_bits(self, offset: int, width: int, value: int | str | BitField) -> None:
        """Rewrite an existing physical field without advancing either cursor."""
        if width <= 0:
            raise ValueError("patch_bits requiere un ancho positivo.")
        item = field(value, width)
        if width % 8 == 0:
            self.buffer.write_int(offset, item.value, width)
        else:
            self.buffer.write_bits(offset, item.value, width)

    def pad(self, width: int) -> BitSpan:
        """Append explicit zero bits and return their span."""

        if isinstance(width, bool) or not isinstance(width, int) or width <= 0:
            raise ValueError("pad requiere un ancho entero mayor que cero.")
        span = self.buffer.append_zeros(width)
        self._advance_virtual(width)
        return span

    @property
    def virtual_position(self) -> int:
        return self._virtual_position

    @property
    def virtual_regions(self) -> dict[str, VirtualRegion]:
        return dict(self._virtual_regions)

    def checkpoint(self) -> BitEmitterCheckpoint:
        return BitEmitterCheckpoint(
            buffer=self.buffer.checkpoint(),
            virtual_position=self._virtual_position,
            virtual_regions=tuple(self._virtual_regions.items()),
        )

    def rollback(self, checkpoint: BitEmitterCheckpoint) -> None:
        if not isinstance(checkpoint, BitEmitterCheckpoint):
            raise TypeError("checkpoint debe ser un BitEmitterCheckpoint.")
        self.buffer.rollback(checkpoint.buffer)
        self._virtual_position = checkpoint.virtual_position
        self._virtual_regions = dict(checkpoint.virtual_regions)

    def _advance_virtual(self, width: int) -> None:
        if width < 0:
            raise ValueError("El avance virtual no puede ser negativo.")
        self._virtual_position += width

    def vpad(self, width: int) -> None:
        """Advance only the virtual cursor."""

        if isinstance(width, bool) or not isinstance(width, int) or width <= 0:
            raise ValueError("vpad requiere un ancho entero mayor que cero.")
        self._advance_virtual(width)

    def vreserve(self, name: str, width: int) -> VirtualRegion:
        """Reserve a named virtual range without writing physical bits."""

        if not name:
            raise ValueError("El nombre de una región no puede estar vacío.")
        if isinstance(width, bool) or not isinstance(width, int) or width <= 0:
            raise ValueError("vreserve requiere un ancho entero mayor que cero.")
        if name in self._virtual_regions or name in self.buffer.regions:
            raise ValueError(f"La región '{name}' ya existe.")
        region = VirtualRegion(self._virtual_position, width, name)
        self._virtual_regions[name] = region
        self._advance_virtual(width)
        return region

    def reserve(self, name: str, width: int) -> BitSpan:
        if name in self._virtual_regions:
            raise ValueError(f"La región '{name}' ya existe.")
        virtual_offset = self._virtual_position
        span = self.buffer.reserve(name, width)
        self._virtual_regions[name] = VirtualRegion(virtual_offset, span.width, name)
        self._advance_virtual(width)
        return span

    def write_res(self, name: str, value: int | str | BitField) -> None:
        if name not in self.buffer.regions and name in self._virtual_regions:
            raise ValueError(f"La reserva '{name}' solo existe en el espacio virtual.")
        span = self.buffer.query(name).span
        item = field(value, span.width)
        self.buffer.patch(span, item.value)

    def emit_res(self, name: str) -> BitSpan:
        if name not in self.buffer.regions and name in self._virtual_regions:
            raise ValueError(f"La reserva '{name}' solo existe en el espacio virtual.")
        span = self.buffer.copy_region(name)
        self._advance_virtual(span.width)
        return span

    def drop_res(self, name: str) -> BitSpan | VirtualRegion:
        if name in self.buffer.regions:
            span = self.buffer.drop_region(name)
            self._virtual_regions.pop(name, None)
            return span
        try:
            return self._virtual_regions.pop(name)
        except KeyError as exc:
            raise KeyError(f"La región '{name}' no existe.") from exc

    def virtual_query(self, name: str) -> VirtualRegion:
        try:
            return self._virtual_regions[name]
        except KeyError as exc:
            raise KeyError(f"La región virtual '{name}' no existe.") from exc

    def query(self, span_or_name: BitSpan | str) -> BitQuery:
        return self.buffer.query(span_or_name)

    def frame(self, rows: Iterable[Sequence[int | str | BitField]]) -> tuple[BitSpan, ...]:
        """Emit a multiline frame atomically after validating every field."""

        normalized: list[tuple[BitField, ...]] = []
        for row in rows:
            current = tuple(field(value) for value in row)
            if not current:
                raise ValueError("frame no admite filas vacías.")
            normalized.append(current)
        if not normalized:
            raise ValueError("frame requiere al menos una fila.")

        spans: list[BitSpan] = []
        with self.buffer.transaction():
            for row in normalized:
                for item in row:
                    spans.append(self.buffer.append_bits(item.value, item.width))
        self._advance_virtual(sum(item.width for row in normalized for item in row))
        return tuple(spans)


__all__ = [
    "BitField",
    "VirtualRegion",
    "BitEmitterCheckpoint",
    "field",
    "BitEmitter",
]
