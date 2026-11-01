"""PCP-I v1 binary container and strict pit filler."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct

from rif_core.limits import resolve_limits


MAX_PCPI_BYTES = 128 << 20
PCPI_VERSION = 1
PCPI_MAGIC = b"pcpi"
PCPI_SIGNATURE_SIZE = 100
PCPI_HEADER_SIZE = 144
PCPI_PIT_ALIGNMENT = 8

BITORDER_LSB = 0
BITORDER_MSB = 1
ENDIAN_LITTLE = 1
ENDIAN_BIG = 2

_HEADER = struct.Struct("<4sBBBB100sIIQIIIII")
_PIT = struct.Struct("<QQI")


class PCPIError(ValueError):
    """A PCP-I container or source is malformed."""


@dataclass(frozen=True)
class PCPIPit:
    """A fixed-size byte range and the alignment padding before it."""

    address: int
    size: int
    padding: int = 0
    name: str | None = None

    @property
    def end(self) -> int:
        return self.address + self.size


@dataclass(frozen=True)
class CompiledPCPI:
    """Validated PCP-I data ready for filling or serialization."""

    version: int
    signature: bytes
    image_size: int
    padding: bytes
    rpad: bytes
    bitorder: int
    endianness: int
    image: bytes
    pits: tuple[PCPIPit, ...]
    magic: bytes = PCPI_MAGIC

    def fill(self, index: int, value: bytes | bytearray | memoryview) -> bytes:
        """Return the raw image with one pit replaced exactly."""

        try:
            pit = self.pits[index]
        except IndexError as exc:
            raise PCPIError(f"No existe el pit {index}.") from exc
        replacement = bytes(value)
        if len(replacement) != pit.size:
            raise PCPIError(
                f"El pit {index} requiere {pit.size} bytes; "
                f"se recibieron {len(replacement)}."
            )
        output = bytearray(self.image)
        output[pit.address : pit.end] = replacement
        return bytes(output)

    def render(self, values: dict[int, bytes] | None = None) -> bytes:
        """Return explicit padding, filled raw image, and generated RPAD."""

        output = bytearray(self.image)
        for index, value in (values or {}).items():
            try:
                pit = self.pits[index]
            except IndexError as exc:
                raise PCPIError(f"No existe el pit {index}.") from exc
            replacement = bytes(value)
            if len(replacement) != pit.size:
                raise PCPIError(
                    f"El pit {index} requiere {pit.size} bytes; "
                    f"se recibieron {len(replacement)}."
                )
            output[pit.address : pit.end] = replacement
        return self.padding + bytes(output) + self.rpad

    def to_bytes(self) -> bytes:
        """Serialize the validated image in the fixed v1 layout."""

        signature = bytes(self.signature)
        if not signature or len(signature) > PCPI_SIGNATURE_SIZE:
            raise PCPIError("La firma PCP-I debe tener entre 1 y 100 bytes.")
        signature_field = signature.ljust(PCPI_SIGNATURE_SIZE, b"\0")
        header = _HEADER.pack(
            self.magic,
            self.version,
            self.endianness,
            self.bitorder,
            0,
            signature_field,
            len(self.padding),
            len(self.rpad),
            self.image_size,
            len(self.pits),
            PCPI_HEADER_SIZE,
            0,
            0,
            0,
        )
        table = b"".join(
            _PIT.pack(pit.address, pit.size, pit.padding) for pit in self.pits
        )
        return header + self.padding + self.image + self.rpad + table


def _maximum_bytes() -> int:
    return resolve_limits().cap(MAX_PCPI_BYTES)


def _ensure_size(value: int, label: str, maximum: int) -> None:
    if value < 0 or value > maximum:
        raise PCPIError(f"{label} excede el límite de recursos configurado.")


def _validate_signature(signature: bytes) -> bytes:
    if not signature or len(signature) > PCPI_SIGNATURE_SIZE:
        raise PCPIError("La firma PCP-I debe tener entre 1 y 100 bytes.")
    if b"\0" in signature:
        raise PCPIError("La firma PCP-I no puede contener NUL.")
    try:
        signature.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PCPIError("La firma PCP-I debe ser UTF-8 válida.") from exc
    return signature


def _validate_pits(pits: tuple[PCPIPit, ...], image_size: int) -> None:
    ordered = sorted(pits, key=lambda pit: pit.address)
    previous: PCPIPit | None = None
    for index, pit in enumerate(pits):
        if pit.size == 0:
            raise PCPIError(f"El pit {index} no puede tener tamaño cero.")
        if pit.end > image_size:
            raise PCPIError(
                f"El pit {index} termina fuera de la imagen ({pit.end} > {image_size})."
            )
        if pit.address % PCPI_PIT_ALIGNMENT:
            raise PCPIError(f"El pit {index} no está alineado a 8 bytes.")
        if pit.padding > pit.address:
            raise PCPIError(f"El padding del pit {index} excede su dirección.")
    for pit in ordered:
        if previous is not None and previous.end > pit.address:
            raise PCPIError("Los pits no pueden solaparse.")
        previous = pit


def parse_pcpi(data: bytes | bytearray | memoryview) -> CompiledPCPI:
    """Parse and strictly validate a binary PCP-I container."""

    raw = bytes(data)
    maximum = _maximum_bytes()
    _ensure_size(len(raw), "La PCP-I", maximum)
    if len(raw) < PCPI_HEADER_SIZE:
        raise PCPIError("La PCP-I no contiene un header completo.")

    (
        magic,
        version,
        endianness,
        bitorder,
        flags,
        signature_field,
        padding_size,
        rpad_size,
        image_size,
        pit_count,
        header_size,
        reserved_a,
        reserved_b,
        reserved_c,
    ) = _HEADER.unpack_from(raw)
    signature = signature_field.rstrip(b"\0")
    if magic != PCPI_MAGIC:
        raise PCPIError("El MAGIC de PCP-I no es 'pcpi'.")
    if version != PCPI_VERSION:
        raise PCPIError(f"Versión PCP-I no soportada: {version}.")
    if endianness not in {ENDIAN_LITTLE, ENDIAN_BIG}:
        raise PCPIError(f"ENDIANNESS PCP-I no válido: {endianness}.")
    if bitorder not in {BITORDER_LSB, BITORDER_MSB}:
        raise PCPIError(f"BITORDER PCP-I no válido: {bitorder}.")
    if flags or reserved_a or reserved_b or reserved_c:
        raise PCPIError("El header PCP-I contiene campos reservados no nulos.")
    if header_size != PCPI_HEADER_SIZE:
        raise PCPIError("El tamaño fijo del header PCP-I no coincide.")
    _validate_signature(signature)
    _ensure_size(image_size, "La imagen", maximum)
    _ensure_size(padding_size, "El padding", maximum)
    _ensure_size(rpad_size, "El RPAD", maximum)

    image_start = PCPI_HEADER_SIZE + padding_size
    image_end = image_start + image_size
    rpad_end = image_end + rpad_size
    table_size = pit_count * _PIT.size
    expected_size = rpad_end + table_size
    if expected_size != len(raw):
        raise PCPIError(
            "El tamaño de la PCP-I no coincide con el header y pit_count "
            f"(esperado {expected_size}, recibido {len(raw)})."
        )

    padding = raw[PCPI_HEADER_SIZE:image_start]
    image = raw[image_start:image_end]
    rpad = raw[image_end:rpad_end]
    if any(padding) or any(rpad):
        raise PCPIError("El padding y RPAD PCP-I deben contener solamente ceros.")
    pits = tuple(
        PCPIPit(address, size, pit_padding)
        for address, size, pit_padding in struct.iter_unpack("<QQI", raw[rpad_end:])
    )
    _validate_pits(pits, image_size)
    return CompiledPCPI(
        version=version,
        signature=signature,
        image_size=image_size,
        padding=padding,
        rpad=rpad,
        bitorder=bitorder,
        endianness=endianness,
        image=image,
        pits=pits,
        magic=magic,
    )


def load_pcpi_file(source: str | Path) -> CompiledPCPI:
    """Load and validate one compiled binary ``.pcic`` file."""

    source_path = Path(source)
    if not source_path.is_file():
        raise FileNotFoundError(f"No se encontró la PCP-I: {source_path}")
    maximum = _maximum_bytes()
    if source_path.stat().st_size > maximum:
        raise PCPIError("La PCP-I excede el límite de recursos configurado.")
    return parse_pcpi(source_path.read_bytes())


__all__ = [
    "BITORDER_LSB",
    "BITORDER_MSB",
    "CompiledPCPI",
    "ENDIAN_BIG",
    "ENDIAN_LITTLE",
    "MAX_PCPI_BYTES",
    "PCPI_HEADER_SIZE",
    "PCPI_MAGIC",
    "PCPI_PIT_ALIGNMENT",
    "PCPI_SIGNATURE_SIZE",
    "PCPIError",
    "PCPIPit",
    "PCPI_VERSION",
    "load_pcpi_file",
    "parse_pcpi",
]
