"""Compiler for standalone ``.store`` payload definitions."""

from __future__ import annotations

import ast
import math
import os
import re
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path

from MIR.storage import StorageError, StorageBuilder, StorageImage, parse_storage
from MIR.functions.reqsts import ReqstsError, reqsts
from plugins import PluginError, convert_audio, convert_image


SUPPORTED_ITEMS = frozenset({"IMAGE", "AUDIO", "BINARY"})
SUPPORTED_VERSIONS = frozenset({1, 2})
IMAGE_INPUTS = frozenset({"png", "jpg", "jpeg", "bmp", "gif", "tga", "webp"})
AUDIO_INPUTS = frozenset({"wav", "flac", "ogg"})
BINARY_INPUTS = frozenset({"bin", "dat", "raw"})
LABEL_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ITEM_PATTERN = re.compile(r"^@ITEM\s+([A-Za-z_][A-Za-z0-9_]*)$", re.IGNORECASE)
TYPE_PATTERN = re.compile(
    r"^(?P<type>[A-Za-z][A-Za-z0-9_]*)\s+"
    r"(?P<label>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>.+)$"
)
GET_PATTERN = re.compile(r"^get\s+([A-Za-z_][A-Za-z0-9_]*)$", re.IGNORECASE)
REQST_PATTERN = re.compile(r"^@REQST\s+([A-Za-z_][A-Za-z0-9_]*)\s+(.+)$", re.IGNORECASE)
FILE_PATTERN = re.compile(r"^@FILE\s+(.+)$", re.IGNORECASE)
CONTAINER_PATTERN = re.compile(r"^@CONTAINER\s+(.+)$", re.IGNORECASE)

TYPE_ALIASES = {
    "str": "str",
    "i8": "int8",
    "i16": "int16",
    "i32": "int32",
    "i64": "int64",
    "int8": "int8",
    "int16": "int16",
    "int32": "int32",
    "int64": "int64",
    "u8": "uint8",
    "u16": "uint16",
    "u32": "uint32",
    "u64": "uint64",
    "uint8": "uint8",
    "uint16": "uint16",
    "uint32": "uint32",
    "uint64": "uint64",
    "f32": "float32",
    "f64": "float64",
    "float32": "float32",
    "float64": "float64",
}
INTEGER_TYPES = {
    "int8": (1, True),
    "int16": (2, True),
    "int32": (4, True),
    "int64": (8, True),
    "uint8": (1, False),
    "uint16": (2, False),
    "uint32": (4, False),
    "uint64": (8, False),
}
FLOAT_TYPES = {"float32": "<f", "float64": "<d"}


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
    literal: object | None = None


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


def _register_item(
    items: list[StoreItem],
    labels: set[str],
    item: StoreItem,
) -> None:
    if not LABEL_PATTERN.fullmatch(item.label):
        raise StoreError(f"Label inválido en línea {item.line}: {item.label!r}.")
    if item.label in labels:
        raise StoreError(f"Label duplicado en .store: {item.label}.")
    labels.add(item.label)
    items.append(item)


def _parse_literal(type_name: str, value: str, line: int) -> tuple[str, object]:
    canonical = TYPE_ALIASES.get(type_name.lower())
    if canonical is None:
        raise StoreError(
            f"Tipo de variable no soportado en línea {line}: {type_name}."
        )
    try:
        literal = ast.literal_eval(value)
    except (SyntaxError, ValueError) as exc:
        raise StoreError(f"Valor literal inválido en línea {line}.") from exc
    if canonical == "str":
        if not isinstance(literal, str):
            raise StoreError(f"str requiere una cadena entre comillas, línea {line}.")
    elif canonical in INTEGER_TYPES:
        if isinstance(literal, bool) or not isinstance(literal, int):
            raise StoreError(f"{canonical} requiere un entero literal, línea {line}.")
    elif canonical in FLOAT_TYPES:
        if isinstance(literal, bool) or not isinstance(literal, (int, float)):
            raise StoreError(f"{canonical} requiere un número literal, línea {line}.")
    return canonical, literal


def _parse_file_directive(line: str, line_number: int) -> tuple[str, str]:
    match = FILE_PATTERN.fullmatch(line)
    if not match:
        raise StoreError(f"@FILE inválido en línea {line_number}.")
    body = match.group(1).strip()
    label: str | None = None
    alias = re.search(r"\s+AS\s+([A-Za-z_][A-Za-z0-9_]*)$", body, re.IGNORECASE)
    if alias:
        label = alias.group(1)
        body = body[: alias.start()].rstrip()
    path = _quoted(body, line_number, "@FILE")
    if label is None:
        label = Path(path).stem
    if not LABEL_PATTERN.fullmatch(label):
        raise StoreError(
            f"@FILE requiere AS con un label válido cuando el nombre no es un identificador, línea {line_number}."
        )
    return path, label


def _parse_container_directive(line: str, line_number: int) -> str:
    match = CONTAINER_PATTERN.fullmatch(line)
    if not match:
        raise StoreError(f"@CONTAINER inválido en línea {line_number}.")
    body = match.group(1).strip()
    if not body.endswith(":"):
        raise StoreError(f"@CONTAINER requiere ':' al final, línea {line_number}.")
    return _quoted(body[:-1].rstrip(), line_number, "@CONTAINER")


def _is_top_level_start(line: str) -> bool:
    return bool(
        line.upper().startswith(("MAGIC ", "VERSION "))
        or ITEM_PATTERN.fullmatch(line)
        or FILE_PATTERN.fullmatch(line)
        or REQST_PATTERN.fullmatch(line)
        or CONTAINER_PATTERN.fullmatch(line)
        or TYPE_PATTERN.fullmatch(line)
    )


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
    container_source: str | None = None
    container_line = 0
    container_items = 0

    for line_number, original in enumerate(lines, 1):
        line = _strip_comment(original).strip()
        if not line:
            continue

        if container_source is not None:
            if line.lower() == "@end":
                if container_items == 0:
                    raise StoreError(
                        f"@CONTAINER en línea {container_line} requiere al menos un get."
                    )
                container_source = None
                container_line = 0
                container_items = 0
                continue
            get_match = GET_PATTERN.fullmatch(line)
            if get_match:
                label = get_match.group(1)
                _register_item(
                    items,
                    labels,
                    StoreItem(
                        "CONTAINER",
                        container_source,
                        "storage",
                        label,
                        label,
                        line_number,
                    ),
                )
                container_items += 1
                continue
            if _is_top_level_start(line):
                if container_items == 0:
                    raise StoreError(
                        f"@CONTAINER en línea {container_line} requiere al menos un get."
                    )
                container_source = None
                container_line = 0
                container_items = 0
            else:
                raise StoreError(
                    f"Se esperaba 'get etiqueta' dentro de @CONTAINER, línea {line_number}."
                )

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
            file_match = FILE_PATTERN.fullmatch(line)
            if file_match:
                file_source, label = _parse_file_directive(line, line_number)
                _register_item(
                    items,
                    labels,
                    StoreItem("FILE", file_source, "raw", "RAW", label, line_number),
                )
                continue
            reqst_match = REQST_PATTERN.fullmatch(line)
            if reqst_match:
                label = reqst_match.group(1)
                remote_source = _quoted(reqst_match.group(2), line_number, "@REQST")
                _register_item(
                    items,
                    labels,
                    StoreItem("REQST", remote_source, "url", "RAW", label, line_number),
                )
                continue
            container_match = CONTAINER_PATTERN.fullmatch(line)
            if container_match:
                container_source = _parse_container_directive(line, line_number)
                container_line = line_number
                container_items = 0
                continue
            type_match = TYPE_PATTERN.fullmatch(line)
            if type_match:
                type_name, literal = _parse_literal(
                    type_match.group("type"), type_match.group("value"), line_number
                )
                _register_item(
                    items,
                    labels,
                    StoreItem(
                        "VALUE",
                        "",
                        type_name,
                        "RAW",
                        type_match.group("label"),
                        line_number,
                        literal,
                    ),
                )
                continue
            raise StoreError(f"Instrucción desconocida en .store, línea {line_number}.")

        if line.lower() == "@end":
            if len(current_fields) != 4:
                raise StoreError(
                    f"@ITEM {current_kind} en línea {current_line} requiere cuatro campos."
                )
            source_value, source_format, data_format, label = current_fields
            _register_item(
                items,
                labels,
                StoreItem(
                    current_kind,
                    source_value,
                    source_format.lower(),
                    data_format,
                    label,
                    current_line,
                ),
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
    if container_source is not None and container_items == 0:
        raise StoreError(f"@CONTAINER en línea {container_line} requiere al menos un get.")
    if magic != "store":
        raise StoreError('MAGIC debe ser exactamente "store".')
    if version not in SUPPORTED_VERSIONS:
        raise StoreError("VERSION de .store debe ser 1 o 2.")
    if version == 1 and any(item.kind in {"VALUE", "REQST"} for item in items):
        raise StoreError("Los valores tipados y @REQST requieren VERSION 2.")
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
    if item.kind == "BINARY":
        if item.source_format not in BINARY_INPUTS:
            raise StoreError(
                f"Formato fuente binario no soportado en {item.label}: "
                f"{item.source_format}."
            )
        if item.data_format.lower() not in {"raw", "bytes"}:
            raise StoreError(
                f"El formato de datos binario de {item.label} debe ser RAW o BYTES."
            )
        if item.source_format != "raw" and path.suffix.lower().removeprefix(".") != item.source_format:
            raise StoreError(
                f"El formato declarado para {item.label} no coincide con la extensión de {path.name}."
            )
        return

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


def _encode_value(item: StoreItem) -> bytes:
    type_name = item.source_format
    value = item.literal
    if type_name == "str":
        if not isinstance(value, str):
            raise StoreError(f"{item.label}: el valor no es una cadena válida.")
        return value.encode("utf-8")
    if type_name in INTEGER_TYPES:
        if isinstance(value, bool) or not isinstance(value, int):
            raise StoreError(f"{item.label}: el valor no es un entero válido.")
        size, signed = INTEGER_TYPES[type_name]
        try:
            return value.to_bytes(size, "little", signed=signed)
        except OverflowError as exc:
            raise StoreError(
                f"{item.label}: {type_name} no puede representar {value}."
            ) from exc
    if type_name in FLOAT_TYPES:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise StoreError(f"{item.label}: el valor no es un número válido.")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise StoreError(f"{item.label}: los flotantes deben ser finitos.")
        try:
            return struct.pack(FLOAT_TYPES[type_name], numeric)
        except struct.error as exc:
            raise StoreError(
                f"{item.label}: {type_name} no puede representar {value}."
            ) from exc
    raise StoreError(f"{item.label}: tipo de variable no soportado: {type_name}.")


def compile_store(source: str | Path) -> StoreCompilation:
    definition = parse_store(source)
    builder = StorageBuilder(version=definition.version)
    root = definition.source_path.parent
    containers: dict[Path, StorageImage] = {}
    for item in definition.items:
        try:
            if item.kind == "VALUE":
                payload = _encode_value(item)
            elif item.kind == "REQST":
                payload = reqsts(item.source)
            elif item.kind == "CONTAINER":
                path = _local_source(root, item.source)
                storage = containers.get(path)
                if storage is None:
                    storage = parse_storage(path.read_bytes())
                    containers[path] = storage
                payload = storage.payload(item.data_format)
                value_type = storage.value_type(item.data_format)
            elif item.kind == "FILE":
                path = _local_source(root, item.source)
                payload = path.read_bytes()
                value_type = None
            else:
                path = _local_source(root, item.source)
                _validate_source_format(item, path)
                if item.kind == "IMAGE":
                    payload = convert_image(path, item.data_format)
                elif item.kind == "AUDIO":
                    payload = convert_audio(path, item.data_format)
                else:
                    payload = path.read_bytes()
                value_type = None
            if item.kind == "VALUE":
                value_type = item.source_format
            elif item.kind == "REQST":
                value_type = None
            builder.add(payload, label=item.label, value_type=value_type)
        except (PluginError, ReqstsError, StorageError, OSError) as exc:
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
