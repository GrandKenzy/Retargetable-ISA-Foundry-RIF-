"""Compiler for the standalone declarative PCP-I ``.pci`` source format."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import os
from pathlib import Path
import re
import tempfile

from pcpi import (
    BITORDER_LSB,
    BITORDER_MSB,
    CompiledPCPI,
    ENDIAN_BIG,
    ENDIAN_LITTLE,
    PCPI_MAGIC,
    PCPI_HEADER_SIZE,
    PCPI_PIT_ALIGNMENT,
    PCPI_VERSION,
    PCPIPit,
    PCPIError,
    parse_pcpi,
)
from rif_limits import resolve_limits


MAX_PCPI_BYTES = 128 << 20
_HEX = re.compile(r"^(?:0x)?[0-9A-Fa-f]{2}$")
_PIT = re.compile(r"^\[(\d+)\]$")


@dataclass(frozen=True)
class PCPIHeaderSource:
    signature: bytes
    endianness: int
    bitorder: int
    padding_size: int


@dataclass(frozen=True)
class PCPISourceCompilation:
    """Compiled PCP-I plus its source path."""

    source: Path
    image: CompiledPCPI


def _strip_comment(line: str) -> str:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote is not None:
            escaped = True
            continue
        if char in {"'", '"'}:
            quote = None if quote == char else char if quote is None else quote
            continue
        if char == ";" and quote is None:
            return line[:index]
    return line


def _string(value: str, line: int, field: str) -> str:
    try:
        parsed = ast.literal_eval(value)
    except (SyntaxError, ValueError) as exc:
        raise PCPIError(f"{field} inválido en línea {line}.") from exc
    if not isinstance(parsed, str) or not parsed:
        raise PCPIError(f"{field} requiere un string no vacío en línea {line}.")
    return parsed


def _integer(value: str, line: int, field: str) -> int:
    try:
        result = int(value, 0)
    except ValueError as exc:
        raise PCPIError(f"{field} inválido en línea {line}.") from exc
    if result < 0:
        raise PCPIError(f"{field} no puede ser negativo en línea {line}.")
    return result


def _parse_header(lines: list[tuple[int, str]]) -> tuple[PCPIHeaderSource, int]:
    values: dict[str, object] = {}
    index = 0
    required = {"MAGIC", "VERSION", "ENDIANNESS", "BITORDER", "SIGNATURE"}
    while index < len(lines):
        line_number, line = lines[index]
        if line == "@RAW":
            break
        parts = line.split(None, 1)
        if len(parts) != 2:
            raise PCPIError(f"Cabecera PCP-I inválida en línea {line_number}.")
        key, value = parts
        if key not in {"MAGIC", "VERSION", "ENDIANNESS", "BITORDER", "SIGNATURE", "PADDING"}:
            raise PCPIError(f"Campo PCP-I desconocido en línea {line_number}: {key}.")
        if key in values:
            raise PCPIError(f"Campo PCP-I duplicado en línea {line_number}: {key}.")
        if key == "MAGIC":
            values[key] = _string(value, line_number, "MAGIC")
        elif key == "SIGNATURE":
            values[key] = _string(value, line_number, "SIGNATURE")
        else:
            values[key] = _integer(value, line_number, key)
        index += 1

    missing = required - values.keys()
    if missing or index >= len(lines) or lines[index][1] != "@RAW":
        missing_text = ", ".join(sorted(missing)) or "@RAW"
        raise PCPIError(f"Falta PCP-I en la cabecera: {missing_text}.")
    if values["MAGIC"] != PCPI_MAGIC.decode("ascii"):
        raise PCPIError('MAGIC debe ser exactamente "pcpi".')
    if values["VERSION"] != PCPI_VERSION:
        raise PCPIError(f"VERSION PCP-I debe ser {PCPI_VERSION}.")
    endianness = values["ENDIANNESS"]
    bitorder = values["BITORDER"]
    if endianness not in {ENDIAN_LITTLE, ENDIAN_BIG}:
        raise PCPIError("ENDIANNESS debe ser 1 (little) o 2 (big).")
    if bitorder not in {BITORDER_LSB, BITORDER_MSB}:
        raise PCPIError("BITORDER debe ser 0 (LSB) o 1 (MSB).")
    signature = str(values["SIGNATURE"]).encode("utf-8")
    if not 0 < len(signature) <= 100:
        raise PCPIError("SIGNATURE debe tener entre 1 y 100 bytes UTF-8.")
    padding_size = int(values.get("PADDING", 0))
    return PCPIHeaderSource(signature, int(endianness), int(bitorder), padding_size), index


def _parse_raw(
    lines: list[tuple[int, str]], start: int
) -> tuple[bytes, tuple[PCPIPit, ...], int]:
    raw = bytearray()
    pits: list[PCPIPit] = []
    ended = False
    end_index = -1
    for index in range(start + 1, len(lines)):
        line_number, line = lines[index]
        if line == "@END":
            ended = True
            end_index = index
            break
        for token in line.split():
            pit_match = _PIT.fullmatch(token)
            if pit_match:
                size = _integer(pit_match.group(1), line_number, "Pit")
                if size == 0:
                    raise PCPIError(f"Un pit no puede tener tamaño cero en línea {line_number}.")
                padding = (-len(raw)) % PCPI_PIT_ALIGNMENT
                address = len(raw) + padding
                maximum = resolve_limits().cap(MAX_PCPI_BYTES)
                if address + size > maximum:
                    raise PCPIError("La imagen PCP-I excede el límite de recursos configurado.")
                raw.extend(b"\0" * padding)
                raw.extend(b"\0" * size)
                pits.append(PCPIPit(address, size, padding))
                continue
            if not _HEX.fullmatch(token):
                raise PCPIError(f"Byte o pit inválido en línea {line_number}: {token}.")
            raw.append(int(token.removeprefix("0x"), 16))
            if len(raw) > resolve_limits().cap(MAX_PCPI_BYTES):
                raise PCPIError("La imagen PCP-I excede el límite de recursos configurado.")
    if not ended:
        raise PCPIError("@RAW no contiene un @END.")
    return bytes(raw), tuple(pits), end_index


def parse_pcpi_source(source: str | Path) -> tuple[PCPIHeaderSource, bytes, tuple[PCPIPit, ...]]:
    source_path = Path(source).expanduser().resolve()
    try:
        raw_lines = source_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise FileNotFoundError(f"No se encontró la fuente PCP-I: {source_path}") from exc
    lines = [
        (line_number, _strip_comment(line).strip())
        for line_number, line in enumerate(raw_lines, 1)
        if _strip_comment(line).strip()
    ]
    header, raw_start = _parse_header(lines)
    image, pits, end_index = _parse_raw(lines, raw_start)
    trailing = [line_number for line_number, _line in lines[end_index + 1 :]]
    if trailing:
        raise PCPIError(f"Contenido después de @END en línea {trailing[0]}.")
    return header, image, pits


def compile_pcpi_source(source: str | Path) -> PCPISourceCompilation:
    source_path = Path(source).expanduser().resolve()
    header, image_data, pits = parse_pcpi_source(source_path)
    if header.padding_size > resolve_limits().cap(MAX_PCPI_BYTES):
        raise PCPIError("PADDING excede el límite de recursos configurado.")
    rpad_size = (
        -(PCPI_HEADER_SIZE + header.padding_size + len(image_data))
    ) % PCPI_PIT_ALIGNMENT
    compiled = CompiledPCPI(
        version=PCPI_VERSION,
        signature=header.signature,
        image_size=len(image_data),
        padding=b"\0" * header.padding_size,
        rpad=b"\0" * rpad_size,
        bitorder=header.bitorder,
        endianness=header.endianness,
        image=image_data,
        pits=pits,
    )
    validated = parse_pcpi(compiled.to_bytes())
    return PCPISourceCompilation(source_path, validated)


def _write_atomic(path: Path, data: bytes, *, protected: Path) -> Path:
    target = path.expanduser().resolve()
    if target == protected.resolve():
        raise PCPIError("La salida PCP-I no puede sobrescribir la fuente.")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_bytes(data)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def compile_pcpi_source_file(
    source: str | Path,
    output: str | Path | None = None,
) -> Path:
    """Compile textual ``.pci`` source to a binary ``.pcic`` artifact."""

    result = compile_pcpi_source(source)
    output_path = (
        Path(output).expanduser()
        if output is not None
        else result.source.with_suffix(".pcic")
    )
    return _write_atomic(output_path, result.image.to_bytes(), protected=result.source)


__all__ = [
    "PCPIHeaderSource",
    "PCPISourceCompilation",
    "compile_pcpi_source",
    "compile_pcpi_source_file",
    "parse_pcpi_source",
]
