"""Bit-addressable storage used by RIF emitters and rewrites."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Literal

from rif_core.limits import resolve_limits


BitOrder = Literal["msb", "lsb"]
ByteOrder = Literal["little", "big"]
MAX_BUFFER_BITS = 1 << 31  # 256 MiB of physical output per section.


@dataclass(frozen=True)
class BitLayout:
    """Physical layout for logical bit fields."""

    bit_order: BitOrder = "msb"
    byte_order: ByteOrder = "little"

    def __post_init__(self) -> None:
        if self.bit_order not in {"msb", "lsb"}:
            raise ValueError("bit_order debe ser 'msb' o 'lsb'.")
        if self.byte_order not in {"little", "big"}:
            raise ValueError("byte_order debe ser 'little' o 'big'.")


@dataclass(frozen=True)
class BitSpan:
    """Named or anonymous half-open range in the bit buffer."""

    offset: int
    width: int
    name: str | None = None

    @property
    def end(self) -> int:
        return self.offset + self.width

    def __post_init__(self) -> None:
        if self.offset < 0:
            raise ValueError("El offset de una región no puede ser negativo.")
        if self.width <= 0:
            raise ValueError("El ancho de una región debe ser mayor que cero.")


@dataclass(frozen=True)
class BitQuery:
    """Immutable result returned by a bit-range query."""

    span: BitSpan
    value: int
    bits: tuple[int, ...]
    raw_bytes: bytes | None

    @property
    def aligned(self) -> bool:
        return self.span.offset % 8 == 0 and self.span.width % 8 == 0


@dataclass(frozen=True)
class BitCheckpoint:
    storage: bytes
    bit_length: int
    regions: tuple[tuple[str, BitSpan], ...]


class BitBuffer:
    """Compact bit-addressable buffer with stable named regions.

    ``write_bits`` is a strict in-place operation. Use ``append_bits`` when
    the cursor should extend the buffer. This distinction makes accidental
    region resizing impossible during rewrites.
    """

    def __init__(
        self,
        layout: BitLayout | None = None,
        *,
        max_bits: int = MAX_BUFFER_BITS,
    ) -> None:
        if max_bits <= 0:
            raise ValueError("max_bits debe ser mayor que cero.")
        self.layout = layout or BitLayout()
        configured_max_bits = resolve_limits().cap(MAX_BUFFER_BITS // 8) * 8
        self.max_bits = min(max_bits, configured_max_bits)
        self._storage = bytearray()
        self._bit_length = 0
        self._regions: dict[str, BitSpan] = {}

    @property
    def bit_length(self) -> int:
        return self._bit_length

    @property
    def byte_length(self) -> int:
        return (self._bit_length + 7) // 8

    @property
    def regions(self) -> dict[str, BitSpan]:
        return dict(self._regions)

    def _check_range(self, offset: int, width: int, *, allocated: bool = True) -> None:
        if offset < 0:
            raise ValueError("El offset no puede ser negativo.")
        if width < 0:
            raise ValueError("El ancho no puede ser negativo.")
        if width > self.max_bits:
            raise ValueError(f"El ancho excede el límite de {self.max_bits} bits.")
        if allocated and offset + width > self._bit_length:
            raise ValueError(
                f"El rango [{offset}, {offset + width}) está fuera del buffer "
                f"de {self._bit_length} bits."
            )

    @staticmethod
    def _check_value(value: int, width: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("El valor de bits debe ser un entero.")
        if value < 0 or value >= (1 << width):
            raise ValueError(f"El valor {value} no cabe en {width} bits.")

    def _physical_bit(self, offset: int) -> tuple[int, int]:
        byte_index, in_byte = divmod(offset, 8)
        bit_index = 7 - in_byte if self.layout.bit_order == "msb" else in_byte
        return byte_index, bit_index

    def _ensure_capacity(self, bit_end: int) -> None:
        if bit_end > self.max_bits:
            raise ValueError(
                f"El buffer excede el límite de {self.max_bits} bits."
            )
        required = (bit_end + 7) // 8
        if required > len(self._storage):
            self._storage.extend(b"\x00" * (required - len(self._storage)))

    def _write_single(self, offset: int, bit: int) -> None:
        byte_index, bit_index = self._physical_bit(offset)
        mask = 1 << bit_index
        if bit:
            self._storage[byte_index] |= mask
        else:
            self._storage[byte_index] &= ~mask

    def _read_single(self, offset: int) -> int:
        byte_index, bit_index = self._physical_bit(offset)
        return (self._storage[byte_index] >> bit_index) & 1

    def _value_bits(self, value: int, width: int) -> tuple[int, ...]:
        self._check_value(value, width)
        if self.layout.bit_order == "msb":
            return tuple((value >> shift) & 1 for shift in range(width - 1, -1, -1))
        return tuple((value >> shift) & 1 for shift in range(width))

    def _bits_value(self, bits: tuple[int, ...]) -> int:
        if self.layout.bit_order == "msb":
            value = 0
            for bit in bits:
                value = (value << 1) | bit
            return value
        return sum(bit << index for index, bit in enumerate(bits))

    def append_bits(self, value: int, width: int) -> BitSpan:
        """Append an integer field and return its anonymous span."""

        self._check_range(0, width, allocated=False)
        offset = self._bit_length
        self._ensure_capacity(offset + width)
        bits = self._value_bits(value, width)
        for index, bit in enumerate(bits):
            self._write_single(offset + index, bit)
        self._bit_length += width
        return BitSpan(offset, width)

    def append_zeros(self, width: int) -> BitSpan:
        """Append an all-zero range without iterating over individual bits."""

        self._check_range(0, width, allocated=False)
        if width <= 0:
            raise ValueError("El ancho debe ser mayor que cero.")
        offset = self._bit_length
        self._ensure_capacity(offset + width)
        self._bit_length += width
        return BitSpan(offset, width)

    def write_bit(self, offset: int, bit: int) -> None:
        self.write_bits(offset, bit, 1)

    def write_bits(self, offset: int, value: int, width: int) -> None:
        """Rewrite an already allocated field without changing its size."""

        self._check_range(offset, width)
        bits = self._value_bits(value, width)
        for index, bit in enumerate(bits):
            self._write_single(offset + index, bit)

    def read_bits(self, offset: int, width: int) -> int:
        self._check_range(offset, width)
        bits = tuple(self._read_single(offset + index) for index in range(width))
        return self._bits_value(bits)

    def read_bit_sequence(self, offset: int, width: int) -> tuple[int, ...]:
        self._check_range(offset, width)
        return tuple(self._read_single(offset + index) for index in range(width))

    def write_int(self, offset: int, value: int, width: int) -> None:
        """Rewrite a byte-oriented integer using the configured byte order."""

        if width <= 0 or width % 8:
            raise ValueError("write_int requiere un ancho positivo múltiplo de 8.")
        self._check_range(offset, width)
        self._check_value(value, width)
        data = value.to_bytes(width // 8, self.layout.byte_order, signed=False)
        for index, byte in enumerate(data):
            self.write_bits(offset + index * 8, byte, 8)

    def append_int(self, value: int, width: int) -> BitSpan:
        """Append a byte-oriented integer using the configured byte order."""

        if width <= 0 or width % 8:
            raise ValueError("append_int requiere un ancho positivo múltiplo de 8.")
        self._check_range(0, width, allocated=False)
        self._check_value(value, width)
        data = value.to_bytes(width // 8, self.layout.byte_order, signed=False)
        offset = self._bit_length
        if offset % 8 == 0:
            self._ensure_capacity(offset + width)
            self._storage[offset // 8 : offset // 8 + len(data)] = data
            self._bit_length += width
        else:
            for byte in data:
                self.append_bits(byte, 8)
        return BitSpan(offset, width)

    def append_bytes(self, data: bytes | bytearray | memoryview) -> BitSpan | None:
        """Append byte-aligned data without visiting every individual bit."""

        payload = bytes(data)
        if not payload:
            return None
        if self._bit_length % 8:
            for byte in payload:
                self.append_bits(byte, 8)
            return BitSpan(self._bit_length - len(payload) * 8, len(payload) * 8)
        offset = self._bit_length
        self._ensure_capacity(offset + len(payload) * 8)
        self._storage[offset // 8 : offset // 8 + len(payload)] = payload
        self._bit_length += len(payload) * 8
        return BitSpan(offset, len(payload) * 8)

    def read_int(self, offset: int, width: int) -> int:
        """Read a byte-oriented integer using the configured byte order."""

        if width <= 0 or width % 8:
            raise ValueError("read_int requiere un ancho positivo múltiplo de 8.")
        data = bytes(
            self.read_bits(offset + index * 8, 8) for index in range(width // 8)
        )
        return int.from_bytes(data, self.layout.byte_order, signed=False)

    def reserve(self, name: str, width: int) -> BitSpan:
        """Append a zero-filled named region."""

        if not name:
            raise ValueError("El nombre de una región no puede estar vacío.")
        if name in self._regions:
            raise ValueError(f"La región '{name}' ya existe.")
        anonymous = self.append_zeros(width)
        span = BitSpan(anonymous.offset, anonymous.width, name)
        self._regions[name] = span
        return span

    def patch(self, span_or_name: BitSpan | str, value: int) -> None:
        span = self._resolve_span(span_or_name)
        self.write_bits(span.offset, value, span.width)

    def copy_region(self, name: str) -> BitSpan:
        span = self._resolve_span(name)
        return self.append_bits(self.read_bits(span.offset, span.width), span.width)

    def drop_region(self, name: str) -> BitSpan:
        try:
            return self._regions.pop(name)
        except KeyError as exc:
            raise KeyError(f"La región '{name}' no existe.") from exc

    def _resolve_span(self, span_or_name: BitSpan | str) -> BitSpan:
        if isinstance(span_or_name, BitSpan):
            return span_or_name
        try:
            return self._regions[span_or_name]
        except KeyError as exc:
            raise KeyError(f"La región '{span_or_name}' no existe.") from exc

    def query(self, span_or_name: BitSpan | str) -> BitQuery:
        span = self._resolve_span(span_or_name)
        bits = self.read_bit_sequence(span.offset, span.width)
        raw_bytes = None
        if span.offset % 8 == 0 and span.width % 8 == 0:
            raw_bytes = bytes(
                self.read_bits(span.offset + index * 8, 8)
                for index in range(span.width // 8)
            )
        return BitQuery(
            span=span,
            value=self._bits_value(bits),
            bits=bits,
            raw_bytes=raw_bytes,
        )

    def checkpoint(self) -> BitCheckpoint:
        return BitCheckpoint(
            storage=bytes(self._storage),
            bit_length=self._bit_length,
            regions=tuple(self._regions.items()),
        )

    def rollback(self, checkpoint: BitCheckpoint) -> None:
        if not isinstance(checkpoint, BitCheckpoint):
            raise TypeError("checkpoint debe ser un BitCheckpoint.")
        self._storage = bytearray(checkpoint.storage)
        self._bit_length = checkpoint.bit_length
        self._regions = dict(checkpoint.regions)

    @contextmanager
    def transaction(self) -> Iterator["BitBuffer"]:
        checkpoint = self.checkpoint()
        try:
            yield self
        except Exception:
            self.rollback(checkpoint)
            raise

    def to_bytes(self) -> bytes:
        """Return the packed storage, masking unused trailing bits to zero."""

        if not self._storage:
            return b""
        result = bytearray(self._storage)
        unused = len(self._storage) * 8 - self._bit_length
        if unused:
            if self.layout.bit_order == "msb":
                result[-1] &= (0xFF << unused) & 0xFF
            else:
                result[-1] &= 0xFF >> unused
        return bytes(result)

    def replace_bytes(self, data: bytes | bytearray | memoryview) -> None:
        """Replace storage without changing logical length or named regions."""

        replacement = bytes(data)
        if len(replacement) != self.byte_length:
            raise ValueError(
                f"El reemplazo contiene {len(replacement)} bytes; "
                f"se esperaban {self.byte_length}."
            )
        self._storage = bytearray(replacement)
        if self._bit_length % 8 and self._storage:
            unused = len(self._storage) * 8 - self._bit_length
            if self.layout.bit_order == "msb":
                self._storage[-1] &= (0xFF << unused) & 0xFF
            else:
                self._storage[-1] &= 0xFF >> unused

    def view(self) -> memoryview:
        """Return a live byte-level view over the backing storage.

        The view is intentionally not masked or copied. Callers that need a
        stable serialized value should use :meth:`to_bytes` instead.
        """

        return memoryview(self._storage)[: self.byte_length]

    def __len__(self) -> int:
        return self._bit_length


BitWriter = BitBuffer

__all__ = [
    "BitOrder",
    "ByteOrder",
    "BitLayout",
    "MAX_BUFFER_BITS",
    "BitSpan",
    "BitQuery",
    "BitCheckpoint",
    "BitBuffer",
    "BitWriter",
]
