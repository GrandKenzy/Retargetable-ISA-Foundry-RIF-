"""Deterministic BIOS ISO-9660/El Torito assembly for RIF outputs.

The RIF target owns the boot image bytes.  This module only assembles those
bytes with a validated PCP-I descriptor template and a small ISO-9660 root
directory, so the format-specific producer stays outside the RIF language.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
import struct
import tempfile
from typing import Iterable

from rif_tools.pcpi import CompiledPCPI, PCPIError


ISO_BLOCK_SIZE = 2048
SYSTEM_AREA_BLOCKS = 16
PRIMARY_DESCRIPTOR_LBA = 16
BOOT_RECORD_LBA = 17
DESCRIPTOR_TERMINATOR_LBA = 18
BOOT_CATALOG_LBA = 19
BOOT_IMAGE_LBA = 20

_PVD_OFFSET = PRIMARY_DESCRIPTOR_LBA * ISO_BLOCK_SIZE
_BOOT_RECORD_OFFSET = BOOT_RECORD_LBA * ISO_BLOCK_SIZE
_BOOT_CATALOG_OFFSET = BOOT_CATALOG_LBA * ISO_BLOCK_SIZE
_MAX_ISO_BLOCKS = 0xFFFFFFFF


class ISOError(ValueError):
    """An ISO-9660 or El Torito image is malformed."""


@dataclass(frozen=True)
class ISOFile:
    """One root-directory file in the generated ISO image."""

    name: str
    data: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ISOError("El nombre ISO debe ser un string no vacío.")
        if not isinstance(self.data, (bytes, bytearray, memoryview)):
            raise TypeError("El contenido ISO debe ser bytes.")


@dataclass(frozen=True)
class ISOReport:
    """Small structural report returned by :func:`validate_bios_iso`."""

    blocks: int
    boot_image_lba: int
    boot_image_sectors: int
    root_directory_lba: int
    root_directory_size: int


def _both_endian32(value: int) -> bytes:
    if not 0 <= value <= _MAX_ISO_BLOCKS:
        raise ISOError(f"El valor ISO de 32 bits está fuera de rango: {value}.")
    return struct.pack("<I", value) + struct.pack(">I", value)


def _block_count(size: int) -> int:
    return max(1, math.ceil(size / ISO_BLOCK_SIZE))


def _block(data: bytes) -> bytes:
    if len(data) > ISO_BLOCK_SIZE:
        raise ISOError("El bloque ISO excede 2048 bytes.")
    return data + bytes(ISO_BLOCK_SIZE - len(data))


def _iso_name(name: str) -> bytes:
    normalized = name.upper()
    if ";" not in normalized:
        normalized += ";1"
    try:
        encoded = normalized.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ISOError(f"El nombre ISO no es ASCII: {name!r}.") from exc
    if not 1 <= len(encoded) <= 31:
        raise ISOError("El identificador de archivo ISO debe medir 1..31 bytes.")
    if any(char in encoded for char in b"/\\\x00"):
        raise ISOError(f"El nombre ISO contiene un separador o NUL: {name!r}.")
    return encoded


def _record_date() -> bytes:
    # Fixed date keeps the example reproducible across machines and builds.
    return bytes((126, 11, 1, 0, 0, 0, 0))


def _pvd_date() -> bytes:
    return b"2026110100000000\x00"


def _directory_record(
    identifier: bytes,
    *,
    extent_lba: int,
    data_size: int,
    directory: bool,
) -> bytes:
    if len(identifier) > 31:
        raise ISOError("El identificador de directorio ISO excede 31 bytes.")
    if extent_lba < 0 or data_size < 0:
        raise ISOError("La extensión ISO no puede ser negativa.")
    name_padding = 1 if len(identifier) % 2 == 0 else 0
    record = bytearray(33 + len(identifier) + name_padding)
    record[0] = len(record)
    record[2:10] = _both_endian32(extent_lba)
    record[10:18] = _both_endian32(data_size)
    record[18:25] = _record_date()
    record[25] = 0x02 if directory else 0x00
    record[28:30] = struct.pack("<H", 1)
    record[30:32] = struct.pack(">H", 1)
    record[32] = len(identifier)
    record[33 : 33 + len(identifier)] = identifier
    return bytes(record)


def _path_table(*, extent_lba: int, big_endian: bool) -> bytes:
    table = bytearray(10)
    table[0] = 1
    table[2:6] = (
        struct.pack(">I", extent_lba)
        if big_endian
        else struct.pack("<I", extent_lba)
    )
    table[6:8] = struct.pack(">H", 1) if big_endian else struct.pack("<H", 1)
    # The root directory identifier is one NUL byte.
    table[8] = 0
    return _block(bytes(table))


def _validation_entry() -> bytes:
    entry = bytearray(32)
    entry[0] = 1
    manufacturer = b"RIF MiniOS El Torito"
    entry[4 : 4 + len(manufacturer)] = manufacturer
    entry[30:32] = b"\x55\xaa"
    checksum = (-sum(entry[index] | (entry[index + 1] << 8) for index in range(0, 32, 2))) & 0xFFFF
    entry[28:30] = struct.pack("<H", checksum)
    return bytes(entry)


def _default_boot_entry(*, image_lba: int, image_sectors: int) -> bytes:
    if not 1 <= image_sectors <= 0xFFFF:
        raise ISOError("El boot image El Torito debe ocupar 1..65535 sectores.")
    entry = bytearray(16)
    entry[0] = 0x88  # bootable, no-emulation image
    entry[6:8] = struct.pack("<H", image_sectors)
    entry[8:12] = struct.pack("<I", image_lba)
    return bytes(entry)


def _patch_pvd_layout(
    prefix: bytearray,
    *,
    total_blocks: int,
    little_path_lba: int,
    big_path_lba: int,
    root_record: bytes,
) -> None:
    pvd = _PVD_OFFSET
    prefix[pvd + 8 : pvd + 40] = b"RIF MINI OS".ljust(32, b" ")
    prefix[pvd + 88 : pvd + 96] = _both_endian32(1)
    prefix[pvd + 96 : pvd + 100] = b"\x01\x00\x00\x01"
    prefix[pvd + 100 : pvd + 104] = b"\x00\x08\x08\x00"
    prefix[pvd + 104 : pvd + 112] = _both_endian32(10)
    prefix[pvd + 112 : pvd + 116] = struct.pack("<I", little_path_lba)
    prefix[pvd + 116 : pvd + 120] = bytes(4)
    prefix[pvd + 120 : pvd + 124] = struct.pack(">I", big_path_lba)
    prefix[pvd + 124 : pvd + 128] = bytes(4)
    prefix[pvd + 128 : pvd + 162] = root_record
    prefix[pvd + 162 : pvd + 290] = b"RIF MiniOS".ljust(128, b" ")
    prefix[pvd + 290 : pvd + 418] = b"RIF".ljust(128, b" ")
    prefix[pvd + 418 : pvd + 546] = b"RIF build".ljust(128, b" ")
    prefix[pvd + 546 : pvd + 674] = b"RIF MiniOS".ljust(128, b" ")
    for start, size in ((674, 37), (711, 37), (748, 37)):
        prefix[pvd + start : pvd + start + size] = b" ".ljust(size, b" ")
    for start in (785, 802, 819, 836):
        prefix[pvd + start : pvd + start + 17] = _pvd_date()
    prefix[pvd + 853] = 1
    prefix[pvd + 854] = 0
    prefix[pvd + 80 : pvd + 88] = _both_endian32(total_blocks)
    prefix[_BOOT_RECORD_OFFSET + 71 : _BOOT_RECORD_OFFSET + 75] = struct.pack(
        "<I", BOOT_CATALOG_LBA
    )


def _require_template(template: CompiledPCPI) -> None:
    if not isinstance(template, CompiledPCPI):
        raise TypeError("template debe ser un CompiledPCPI.")
    if len(template.pits) != 3 or tuple(pit.size for pit in template.pits) != (8, 34, 16):
        raise ISOError(
            "La plantilla PCP-I ISO requiere exactamente los pits "
            "volume-space-size(8), root-directory-record(34) y boot-entry(16)."
        )
    rendered_size = len(template.padding) + template.image_size + len(template.rpad)
    expected = (BOOT_IMAGE_LBA * ISO_BLOCK_SIZE)
    if rendered_size != expected:
        raise ISOError(
            f"La plantilla PCP-I debe renderizar {expected} bytes antes del boot image; "
            f"renderiza {rendered_size}."
        )


def build_iso_from_pcpi(
    template: CompiledPCPI,
    boot_image: bytes | bytearray | memoryview,
    files: Iterable[ISOFile] = (),
    *,
    volume_id: str = "RIF_MINIOS",
) -> bytes:
    """Assemble a bootable ISO from a PCP-I descriptor and RIF boot bytes."""

    _require_template(template)
    boot_source = bytes(boot_image)
    if not boot_source or len(boot_source) % 512:
        raise ISOError("El boot image debe ser no vacío y múltiplo de 512 bytes.")
    boot_blocks = _block_count(len(boot_source))
    boot_payload = boot_source.ljust(boot_blocks * ISO_BLOCK_SIZE, b"\0")
    boot_sectors = len(boot_payload) // 512

    normalized_files: list[tuple[bytes, bytes]] = []
    names: set[bytes] = set()
    for item in files:
        if not isinstance(item, ISOFile):
            raise TypeError("files solo acepta objetos ISOFile.")
        name = _iso_name(item.name)
        if name in names:
            raise ISOError(f"Archivo ISO duplicado: {name.decode('ascii')}.")
        names.add(name)
        normalized_files.append((name, bytes(item.data)))

    little_path_lba = BOOT_IMAGE_LBA + boot_blocks
    big_path_lba = little_path_lba + 1
    root_lba = big_path_lba + 1
    provisional_records = [
        _directory_record(b"\x00", extent_lba=root_lba, data_size=ISO_BLOCK_SIZE, directory=True),
        _directory_record(b"\x01", extent_lba=root_lba, data_size=ISO_BLOCK_SIZE, directory=True),
    ]
    provisional_records.extend(
        _directory_record(name, extent_lba=0, data_size=len(data), directory=False)
        for name, data in normalized_files
    )
    root_size = _block_count(sum(len(record) for record in provisional_records)) * ISO_BLOCK_SIZE
    file_lba = root_lba + root_size // ISO_BLOCK_SIZE
    file_locations: list[tuple[bytes, bytes, int]] = []
    for name, data in normalized_files:
        file_locations.append((name, data, file_lba))
        file_lba += _block_count(len(data))

    records = [
        _directory_record(b"\x00", extent_lba=root_lba, data_size=root_size, directory=True),
        _directory_record(b"\x01", extent_lba=root_lba, data_size=root_size, directory=True),
    ]
    for name, data, extent_lba in file_locations:
        records.append(
            _directory_record(
                name,
                extent_lba=extent_lba,
                data_size=len(data),
                directory=False,
            )
        )
    records_size = sum(len(record) for record in records)
    calculated_root_size = _block_count(records_size) * ISO_BLOCK_SIZE
    if calculated_root_size != root_size:
        raise ISOError("El cálculo del tamaño del directorio raíz no es estable.")
    root_directory = b"".join(records).ljust(root_size, b"\0")

    total_blocks = file_lba
    root_record = _directory_record(
        b"\x00",
        extent_lba=root_lba,
        data_size=root_size,
        directory=True,
    )
    default_entry = _default_boot_entry(
        image_lba=BOOT_IMAGE_LBA,
        image_sectors=boot_sectors,
    )
    try:
        rendered = template.render(
            {
                0: _both_endian32(total_blocks),
                1: root_record,
                2: default_entry,
            }
        )
    except PCPIError as exc:
        raise ISOError(f"No se pudo rellenar la plantilla PCP-I ISO: {exc}") from exc
    prefix = bytearray(rendered)
    _patch_pvd_layout(
        prefix,
        total_blocks=total_blocks,
        little_path_lba=little_path_lba,
        big_path_lba=big_path_lba,
        root_record=root_record,
    )
    if volume_id:
        try:
            volume_bytes = volume_id.encode("ascii")[:32].ljust(32, b" ")
        except UnicodeEncodeError as exc:
            raise ISOError("volume_id debe ser ASCII.") from exc
        prefix[_PVD_OFFSET + 40 : _PVD_OFFSET + 72] = volume_bytes
    prefix[_BOOT_CATALOG_OFFSET : _BOOT_CATALOG_OFFSET + 32] = _validation_entry()
    prefix[_BOOT_CATALOG_OFFSET + 32 : _BOOT_CATALOG_OFFSET + 48] = default_entry

    output = bytearray(prefix)
    output.extend(boot_payload)
    output.extend(_path_table(extent_lba=root_lba, big_endian=False))
    output.extend(_path_table(extent_lba=root_lba, big_endian=True))
    output.extend(root_directory)
    for _name, data, _extent_lba in file_locations:
        output.extend(data.ljust(_block_count(len(data)) * ISO_BLOCK_SIZE, b"\0"))
    result = bytes(output)
    report = validate_bios_iso(result)
    if report.blocks != total_blocks:
        raise ISOError("La ISO ensamblada no coincide con su volumen declarado.")
    return result


def validate_bios_iso(image: bytes | bytearray | memoryview) -> ISOReport:
    """Validate the structural BIOS/ISO contract without executing the image."""

    data = bytes(image)
    if len(data) == 0 or len(data) % ISO_BLOCK_SIZE:
        raise ISOError("La ISO debe ser no vacía y múltiplo de 2048 bytes.")
    blocks = len(data) // ISO_BLOCK_SIZE
    pvd = data[_PVD_OFFSET : _PVD_OFFSET + ISO_BLOCK_SIZE]
    if pvd[0:7] != b"\x01CD001\x01":
        raise ISOError("Falta un Primary Volume Descriptor ISO-9660 válido.")
    if struct.unpack_from("<I", pvd, 80)[0] != blocks or struct.unpack_from(">I", pvd, 84)[0] != blocks:
        raise ISOError("Volume Space Size no coincide con la longitud de la ISO.")
    boot_record = data[_BOOT_RECORD_OFFSET : _BOOT_RECORD_OFFSET + ISO_BLOCK_SIZE]
    if (
        boot_record[0:7] != b"\x00CD001\x01"
        or boot_record[7:30] != b"EL TORITO SPECIFICATION"
        or boot_record[30:39] != bytes(9)
        or struct.unpack_from("<I", boot_record, 71)[0] != BOOT_CATALOG_LBA
    ):
        raise ISOError("Falta el Boot Record El Torito o su catálogo.")
    terminator = data[DESCRIPTOR_TERMINATOR_LBA * ISO_BLOCK_SIZE : (DESCRIPTOR_TERMINATOR_LBA + 1) * ISO_BLOCK_SIZE]
    if terminator[0:7] != b"\xffCD001\x01":
        raise ISOError("Falta el terminador de descriptores ISO-9660.")
    catalog = data[_BOOT_CATALOG_OFFSET : _BOOT_CATALOG_OFFSET + ISO_BLOCK_SIZE]
    if catalog[30:32] != b"\x55\xaa":
        raise ISOError("La entrada de validación El Torito no tiene 55 AA.")
    if sum(catalog[index] | (catalog[index + 1] << 8) for index in range(0, 32, 2)) & 0xFFFF:
        raise ISOError("La suma de validación El Torito no es cero.")
    default = catalog[32:48]
    if default[0] != 0x88:
        raise ISOError("La entrada El Torito no está marcada como arrancable.")
    sectors = struct.unpack_from("<H", default, 6)[0]
    boot_lba = struct.unpack_from("<I", default, 8)[0]
    if not sectors or boot_lba * ISO_BLOCK_SIZE + sectors * 512 > len(data):
        raise ISOError("El boot image El Torito queda fuera de la ISO.")
    root = pvd[128:162]
    if root[0] != len(root) or root[25] != 0x02 or root[32] != 1 or root[33] != 0:
        raise ISOError("El registro raíz ISO-9660 no es válido.")
    root_lba = struct.unpack_from("<I", root, 2)[0]
    root_size = struct.unpack_from("<I", root, 10)[0]
    if root_lba * ISO_BLOCK_SIZE + root_size > len(data):
        raise ISOError("El directorio raíz queda fuera de la ISO.")
    return ISOReport(blocks, boot_lba, sectors, root_lba, root_size)


def write_iso(path: str | Path, image: bytes, *, protected: Iterable[str | Path] = ()) -> Path:
    """Write an ISO atomically, refusing to overwrite declared inputs."""

    target = Path(path).expanduser().resolve()
    protected_paths = {Path(item).expanduser().resolve() for item in protected}
    if target in protected_paths:
        raise ISOError(f"La salida ISO no puede sobrescribir una entrada: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_bytes(bytes(image))
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


__all__ = [
    "BOOT_CATALOG_LBA",
    "BOOT_IMAGE_LBA",
    "ISO_BLOCK_SIZE",
    "ISOError",
    "ISOFile",
    "ISOReport",
    "build_iso_from_pcpi",
    "validate_bios_iso",
    "write_iso",
]
