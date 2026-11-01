"""Compiler for standalone ``.store`` media definitions."""

from __future__ import annotations

import ast
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from MIR.storage import StorageError, StorageBuilder
from plugins import PluginError, convert_audio, convert_image


SUPPORTED_ITEMS = frozenset({"IMAGE", "AUDIO"})
IMAGE_INPUTS = frozenset({"png", "jpg", "jpeg", "bmp", "gif", "tga", "webp"})
AUDIO_INPUTS = frozenset({"wav", "flac", "ogg"})
LABEL_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ITEM_PATTERN = re.compile(r"^@ITEM\s+([A-Za-z_][A-Za-z0-9_]*)$", re.IGNORECASE)


class StoreError(ValueError):
    """A store source or one of its local payloads is invalid."""


@dataclass(frozen=True)
class StoreItem:
    kind: str
    source: str
    source_format: str
    data_format: str
    label: str
    line: int


@dataclass(frozen=True)
class StoreDefinition:
    source_path: Path
    magic: str
    version: int
    items: tuple[StoreItem, ...]


@dataclass(frozen=True)
class StoreCompilation:
    source_path: Path
    storage: bytes
    items: tuple[StoreItem, ...]
    output_path: Path | None = None


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


def _quoted(value: str, line: int, field: str) -> str:
    try:
        parsed = ast.literal_eval(value)
    except (SyntaxError, ValueError) as exc:
        raise StoreError(f"{field} inválido en .store, línea {line}.") from exc
    if not isinstance(parsed, str) or not parsed:
        raise StoreError(f"{field} requiere un string no vacío, línea {line}.")
    return parsed


def _field_value(line: str, line_number: int) -> str:
    value = line[1:].strip()
    if not value:
        raise StoreError(f"Campo vacío en .store, línea {line_number}.")
    if value[0] in {"'", '"'}:
        return _quoted(value, line_number, "El campo")
    if not LABEL_PATTERN.fullmatch(value):
        raise StoreError(f"Campo inválido en .store, línea {line_number}.")
    return value


def parse_store(source: str | Path) -> StoreDefinition:
    path = Path(source).expanduser().resolve()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise StoreError(f"No se pudo leer el .store: {path}.") from exc

    magic: str | None = None
    version: int | None = None
    items: list[StoreItem] = []
    labels: set[str] = set()
    current_kind: str | None = None
    current_fields: list[str] = []
    current_line = 0

    for line_number, original in enumerate(lines, 1):
        line = _strip_comment(original).strip()
        if not line:
            continue
        if current_kind is None:
            if line.upper().startswith("MAGIC "):
                if magic is not None:
                    raise StoreError(f"MAGIC duplicado en línea {line_number}.")
                magic = _quoted(line[6:].strip(), line_number, "MAGIC")
                continue
            if line.upper().startswith("VERSION "):
                if version is not None:
                    raise StoreError(f"VERSION duplicado en línea {line_number}.")
                raw_version = line[8:].strip()
                try:
                    version = int(raw_version, 10)
                except ValueError as exc:
                    raise StoreError(f"VERSION inválida en línea {line_number}.") from exc
                continue
            match = ITEM_PATTERN.fullmatch(line)
            if match:
                current_kind = match.group(1).upper()
                if current_kind not in SUPPORTED_ITEMS:
                    raise StoreError(f"Tipo de @ITEM no soportado: {current_kind}.")
                current_fields = []
                current_line = line_number
                continue
            raise StoreError(f"Instrucción desconocida en .store, línea {line_number}.")

        if line.lower() == "@end":
            if len(current_fields) != 4:
                raise StoreError(
                    f"@ITEM {current_kind} en línea {current_line} requiere cuatro campos."
                )
            source_value, source_format, data_format, label = current_fields
            if not LABEL_PATTERN.fullmatch(label):
                raise StoreError(f"Label inválido en línea {line_number}: {label!r}.")
            if label in labels:
                raise StoreError(f"Label duplicado en .store: {label}.")
            labels.add(label)
            items.append(
                StoreItem(
                    current_kind,
                    source_value,
                    source_format.lower(),
                    data_format,
                    label,
                    current_line,
                )
            )
            current_kind = None
            current_fields = []
            continue
        if not line.startswith(":"):
            raise StoreError(f"Se esperaba ':' en .store, línea {line_number}.")
        if len(current_fields) >= 4:
            raise StoreError(f"@ITEM excede cuatro campos en línea {line_number}.")
        current_fields.append(_field_value(line, line_number))

    if current_kind is not None:
        raise StoreError(f"@ITEM {current_kind} en línea {current_line} no tiene @end.")
    if magic != "store":
        raise StoreError('MAGIC debe ser exactamente "store".')
    if version != 1:
        raise StoreError("VERSION de .store debe ser 1.")
    return StoreDefinition(path, magic, version, tuple(items))


def _local_source(root: Path, value: str) -> Path:
    requested = Path(value)
    if requested.is_absolute() or ".." in requested.parts:
        raise StoreError(f"La ruta de .store debe permanecer dentro de su carpeta: {value}.")
    candidate = (root / requested).resolve(strict=True)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise StoreError(f"La ruta de .store intenta salir de su carpeta: {value}.") from exc
    if not candidate.is_file():
        raise StoreError(f"El payload de .store no es un archivo: {value}.")
    return candidate


def _validate_source_format(item: StoreItem, path: Path) -> None:
    allowed = IMAGE_INPUTS if item.kind == "IMAGE" else AUDIO_INPUTS
    if item.source_format not in allowed:
        raise StoreError(f"Formato fuente no soportado en {item.label}: {item.source_format}.")
    suffix = path.suffix.lower().removeprefix(".")
    aliases = {"jpg": {"jpg", "jpeg"}, "jpeg": {"jpg", "jpeg"}}
    expected = aliases.get(item.source_format, {item.source_format})
    if suffix not in expected:
        raise StoreError(
            f"El formato declarado para {item.label} no coincide con la extensión de {path.name}."
        )


def compile_store(source: str | Path) -> StoreCompilation:
    definition = parse_store(source)
    builder = StorageBuilder()
    root = definition.source_path.parent
    for item in definition.items:
        path = _local_source(root, item.source)
        _validate_source_format(item, path)
        try:
            if item.kind == "IMAGE":
                payload = convert_image(path, item.data_format)
            else:
                payload = convert_audio(path, item.data_format)
            builder.add(payload, label=item.label)
        except (PluginError, StorageError) as exc:
            raise StoreError(f"{item.label}: {exc}") from exc
    return StoreCompilation(definition.source_path, builder.build(), definition.items)


def compile_store_file(source: str | Path, output: str | Path | None = None) -> Path:
    result = compile_store(source)
    if output is None:
        output_path = result.source_path.with_suffix(".storage.bin")
    else:
        output_path = Path(output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_bytes(result.storage)
        os.replace(temporary, output_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return output_path


__all__ = [
    "StoreCompilation",
    "StoreDefinition",
    "StoreError",
    "StoreItem",
    "compile_store",
    "compile_store_file",
    "parse_store",
]
