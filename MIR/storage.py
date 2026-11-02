"""Versioned indexed storage produced by standalone ``.store`` files."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from rif_core.limits import resolve_limits


MAGIC = b"RIFSTOR\0"
VERSION = 2
LEGACY_VERSION = 1
DEFAULT_ALIGNMENT = 8
MAX_STORAGE_BYTES = 512 << 20
HEADER_STRUCT = struct.Struct("<8sBBH I Q Q Q I I")
ENTRY_STRUCT = struct.Struct("<Q Q I I")
HEADER_SIZE = HEADER_STRUCT.size
ENTRY_SIZE = ENTRY_STRUCT.size

VALUE_TYPE_CODES = {
    None: 0,
    "str": 1,
    "int8": 2,
    "int16": 3,
    "int32": 4,
    "int64": 5,
    "uint8": 6,
    "uint16": 7,
    "uint32": 8,
    "uint64": 9,
    "float32": 10,
    "float64": 11,
}
VALUE_TYPE_NAMES = {code: name for name, code in VALUE_TYPE_CODES.items() if code}


class StorageError(ValueError):
    """An indexed raw storage image is invalid."""


@dataclass(frozen=True)
class StorageEntry:
    """One payload, its inline UTF-8 label, and optional value metadata."""

    relative_address: int
    raw_size: int
    padding: int
    label_size: int
    value_type: str | None = None


@dataclass(frozen=True)
class StorageImage:
    """Decoded storage image with immutable raw bytes and index entries."""

    raw: bytes
    entries: tuple[StorageEntry, ...]
    version: int = VERSION

    def _entry_at(self, index: int) -> StorageEntry:
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise StorageError(f"El índice de storage no existe: {index}.")
        try:
            return self.entries[index]
        except IndexError as exc:
            raise StorageError(f"El índice de storage no existe: {index}.") from exc

    def entry(self, index: int | str) -> StorageEntry:
        if not isinstance(index, str):
            return self._entry_at(index)
        matches = [
            entry
            for entry_index, entry in enumerate(self.entries)
            if entry.label_size and self.label(entry_index) == index
        ]
        if len(matches) != 1:
            raise StorageError(f"El label de storage no existe o no es único: {index}.")
        return matches[0]

    def label(self, index: int) -> str:
        entry = self._entry_at(index)
        if entry.label_size == 0:
            raise StorageError(f"La entrada de storage no tiene label: {index}.")
        start = entry.relative_address + entry.raw_size
        end = start + entry.label_size
        try:
            return self.raw[start:end].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise StorageError("El label del storage no es UTF-8 válido.") from exc

    def payload(self, index: int | str) -> bytes:
        entry = self.entry(index)
        start = entry.relative_address
        return self.raw[start : start + entry.raw_size]

    def value_type(self, index: int | str) -> str | None:
        """Return the declared type, or ``None`` for opaque raw payloads."""

        return self.entry(index).value_type


class StorageBuilder:
    """Build one aligned raw region and a fixed-width inline-label index."""

    def __init__(self, alignment: int = DEFAULT_ALIGNMENT, *, version: int = LEGACY_VERSION) -> None:
        if alignment <= 0 or alignment & (alignment - 1):
            raise StorageError("La alineación de storage debe ser potencia de dos.")
        if version not in {LEGACY_VERSION, VERSION}:
            raise StorageError(f"Versión de storage no soportada: {version}.")
        self.alignment = alignment
        self.version = version
        self._raw = bytearray()
        self._entries: list[StorageEntry] = []
        self._labels: set[str] = set()

    @property
    def entries(self) -> tuple[StorageEntry, ...]:
        return tuple(self._entries)

    def add(
        self,
        payload: bytes | bytearray | memoryview,
        *,
        label: str | None = None,
        value_type: str | None = None,
    ) -> StorageEntry:
        data = bytes(payload)
        if value_type not in VALUE_TYPE_CODES:
            raise StorageError(f"El tipo de valor de storage no es válido: {value_type!r}.")
        if self.version == LEGACY_VERSION and value_type is not None:
            raise StorageError(
                "Los valores tipados requieren VERSION 2 en el storage."
            )
        label_bytes = b""
        if label is not None:
            if not isinstance(label, str) or not label or label in self._labels:
                raise StorageError(f"El label de storage no es válido o está duplicado: {label!r}.")
            if "\x00" in label:
                raise StorageError("Un label de storage no puede contener NUL.")
            label_bytes = label.encode("utf-8")
            self._labels.add(label)

        padding = (-len(self._raw)) % self.alignment
        start = len(self._raw) + padding
        total = start + len(data) + len(label_bytes)
        if total > resolve_limits().cap(MAX_STORAGE_BYTES):
            raise StorageError("El storage excede el límite de recursos configurado.")
        self._raw.extend(b"\0" * padding)
        self._raw.extend(data)
        self._raw.extend(label_bytes)
        entry = StorageEntry(start, len(data), padding, len(label_bytes), value_type)
        self._entries.append(entry)
        return entry

    def build(self) -> bytes:
        raw = bytes(self._raw)
        index_offset = HEADER_SIZE + len(raw)
        index = b"".join(
            ENTRY_STRUCT.pack(
                entry.relative_address,
                entry.raw_size,
                entry.padding | (VALUE_TYPE_CODES[entry.value_type] << 16)
                if self.version == VERSION
                else entry.padding,
                entry.label_size,
            )
            for entry in self._entries
        )
        total = index_offset + len(index)
        if total > resolve_limits().cap(MAX_STORAGE_BYTES):
            raise StorageError("El storage excede el límite de recursos configurado.")
        header = HEADER_STRUCT.pack(
            MAGIC,
            self.version,
            0,
            HEADER_SIZE,
            0,
            len(raw),
            index_offset,
            len(self._entries),
            ENTRY_SIZE,
            0,
        )
        return header + raw + index


def build_storage(
    payloads: Iterable[bytes | bytearray | memoryview],
    *,
    alignment: int = DEFAULT_ALIGNMENT,
    version: int = LEGACY_VERSION,
) -> bytes:
    builder = StorageBuilder(alignment, version=version)
    for payload in payloads:
        builder.add(payload)
    return builder.build()


def parse_storage(data: bytes | bytearray | memoryview) -> StorageImage:
    blob = bytes(data)
    if len(blob) < HEADER_SIZE:
        raise StorageError("El storage no contiene una cabecera completa.")
    (
        magic,
        version,
        flags,
        header_size,
        reserved,
        raw_size,
        index_offset,
        pit_count,
        entry_size,
        reserved_tail,
    ) = HEADER_STRUCT.unpack_from(blob)
    if magic != MAGIC:
        raise StorageError("El magic del storage no es RIFSTOR.")
    if version not in {LEGACY_VERSION, VERSION}:
        raise StorageError(f"Versión de storage no soportada: {version}.")
    if flags or reserved or reserved_tail:
        raise StorageError("La cabecera del storage contiene flags o reservas no nulas.")
    if header_size != HEADER_SIZE or entry_size != ENTRY_SIZE:
        raise StorageError("El tamaño de cabecera o entrada del storage no coincide.")
    if index_offset != header_size + raw_size:
        raise StorageError("El índice del storage no apunta después del raw.")
    index_end = index_offset + pit_count * entry_size
    if index_end != len(blob):
        raise StorageError("El tamaño declarado del índice no coincide con el archivo.")
    if len(blob) > resolve_limits().cap(MAX_STORAGE_BYTES):
        raise StorageError("El storage excede el límite de recursos configurado.")

    raw = blob[header_size:index_offset]
    entries: list[StorageEntry] = []
    seen_labels: set[str] = set()
    previous_end = 0
    for index in range(pit_count):
        offset = index_offset + index * entry_size
        relative_address, raw_size_entry, encoded_padding, label_size = ENTRY_STRUCT.unpack_from(
            blob, offset
        )
        if version == VERSION:
            padding = encoded_padding & 0xFFFF
            type_code = encoded_padding >> 16
            if type_code not in VALUE_TYPE_NAMES and type_code != 0:
                raise StorageError(f"El tipo de valor de storage no es válido: {type_code}.")
            value_type = VALUE_TYPE_NAMES.get(type_code)
        else:
            padding = encoded_padding
            value_type = None
        entry = StorageEntry(
            relative_address,
            raw_size_entry,
            padding,
            label_size,
            value_type,
        )
        end = entry.relative_address + entry.raw_size + entry.label_size
        if entry.relative_address < previous_end or end > len(raw):
            raise StorageError("Una entrada de storage apunta fuera del raw o se solapa.")
        expected_padding = entry.relative_address - previous_end
        if entry.padding != expected_padding:
            raise StorageError("El padding de una entrada no coincide con su dirección relativa.")
        if entry.label_size:
            label_start = entry.relative_address + entry.raw_size
            try:
                label = raw[label_start:end].decode("utf-8")
            except UnicodeDecodeError as exc:
                raise StorageError("El label del storage no es UTF-8 válido.") from exc
            if not label or "\x00" in label:
                raise StorageError("El label del storage es inválido.")
            if label in seen_labels:
                raise StorageError(f"El storage contiene un label duplicado: {label}.")
            seen_labels.add(label)
        entries.append(entry)
        previous_end = end
    return StorageImage(raw, tuple(entries), version)


def load_storage_file(source: str | Path) -> StorageImage:
    """Load and strictly validate one compiled ``storage.bin`` file."""

    source_path = Path(source).expanduser()
    if not source_path.is_file():
        raise FileNotFoundError(f"No se encontró el storage: {source_path}")
    if source_path.stat().st_size > resolve_limits().cap(MAX_STORAGE_BYTES):
        raise StorageError("El storage excede el límite de recursos configurado.")
    return parse_storage(source_path.read_bytes())


__all__ = [
    "DEFAULT_ALIGNMENT",
    "ENTRY_SIZE",
    "HEADER_SIZE",
    "MAGIC",
    "MAX_STORAGE_BYTES",
    "StorageBuilder",
    "StorageEntry",
    "StorageError",
    "StorageImage",
    "build_storage",
    "load_storage_file",
    "parse_storage",
]
