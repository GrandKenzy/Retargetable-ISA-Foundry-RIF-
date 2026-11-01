"""Portable, target-neutral libraries of reusable RIF declarations.

``.riflib`` is intentionally a source package, not a second executable
format.  It contains a deterministic ZIP with ``sources/*.rif`` and a small
manifest.  Loading a library feeds those declarations through the normal RIF
processor, so tables, defines and Rules remain extensible data owned by the
target that consumes them.
"""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from rif_limits import resolve_limits


RIFLIB_FORMAT = "RIF_LIBRARY"
RIFLIB_FORMAT_VERSION = 1
MANIFEST_NAME = "manifest.json"
SOURCE_PREFIX = "sources/"
MAX_SOURCE_FILES = 4096
MAX_SOURCE_SIZE = 16 << 20
MAX_MANIFEST_SIZE = 1 << 20
MAX_TOTAL_UNCOMPRESSED = 512 << 20
MAX_COMPRESSION_RATIO = 10_000
_LOAD_RE = re.compile(r'^\s*@LOAD\s+"([^"]+)"(?:\s*;.*)?\s*$', re.IGNORECASE)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 0
    info.external_attr = 0o100644 << 16
    return info


@dataclass(frozen=True)
class LibraryEntry:
    path: str
    size: int
    sha256: str
    loads: tuple[str, ...] = ()


@dataclass(frozen=True)
class LibraryManifest:
    name: str
    version: str
    entrypoint: str
    files: tuple[LibraryEntry, ...]
    load_graph: dict[str, tuple[str, ...]]
    dependency_order: tuple[str, ...]
    content_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": RIFLIB_FORMAT,
            "format_version": RIFLIB_FORMAT_VERSION,
            "name": self.name,
            "version": self.version,
            "entrypoint": self.entrypoint,
            "files": [
                {
                    "path": entry.path,
                    "size": entry.size,
                    "sha256": entry.sha256,
                    "loads": list(entry.loads),
                }
                for entry in self.files
            ],
            "load_graph": {
                path: list(dependencies)
                for path, dependencies in sorted(self.load_graph.items())
            },
            "dependency_order": list(self.dependency_order),
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "LibraryManifest":
        if not isinstance(data, dict) or data.get("format") != RIFLIB_FORMAT:
            raise ValueError("El archivo no es una librería RIF válida.")
        if data.get("format_version") != RIFLIB_FORMAT_VERSION:
            raise ValueError("Versión de formato .riflib no compatible.")
        raw_files = data.get("files")
        if not isinstance(raw_files, list) or len(raw_files) > MAX_SOURCE_FILES:
            raise ValueError("La librería contiene una lista de fuentes inválida.")
        files: list[LibraryEntry] = []
        for raw in raw_files:
            if not isinstance(raw, dict):
                raise ValueError("La librería contiene una entrada inválida.")
            path, size, sha256, raw_loads = (
                raw.get("path"), raw.get("size"), raw.get("sha256"), raw.get("loads", [])
            )
            if (
                not isinstance(path, str)
                or not isinstance(size, int)
                or size < 0
                or not isinstance(sha256, str)
                or len(sha256) != 64
                or not isinstance(raw_loads, list)
                or not all(isinstance(item, str) for item in raw_loads)
            ):
                raise ValueError("La librería contiene metadata de fuente inválida.")
            files.append(LibraryEntry(path, size, sha256, tuple(raw_loads)))
        raw_graph = data.get("load_graph")
        raw_order = data.get("dependency_order")
        if not isinstance(raw_graph, dict) or not isinstance(raw_order, list):
            raise ValueError("La librería contiene un índice de @LOAD inválido.")
        graph = {
            path: tuple(dependencies)
            for path, dependencies in raw_graph.items()
            if isinstance(path, str)
            and isinstance(dependencies, list)
            and all(isinstance(item, str) for item in dependencies)
        }
        if len(graph) != len(raw_graph) or not all(isinstance(item, str) for item in raw_order):
            raise ValueError("La librería contiene un índice de @LOAD inválido.")
        content = data.get("content_sha256")
        if not isinstance(content, str) or len(content) != 64:
            raise ValueError("La librería no contiene una huella válida.")
        return cls(
            name=str(data.get("name", "")),
            version=str(data.get("version", "")),
            entrypoint=str(data.get("entrypoint", "")),
            files=tuple(files),
            load_graph=graph,
            dependency_order=tuple(raw_order),
            content_sha256=content,
        )


def _read_member(archive: zipfile.ZipFile, name: str, maximum: int) -> bytes:
    try:
        info = archive.getinfo(name)
    except KeyError as exc:
        raise ValueError(f"Falta el archivo declarado por la librería: {name}") from exc
    if info.flag_bits & 0x1:
        raise ValueError(f"El miembro ZIP cifrado no está permitido: {name}")
    if info.file_size > maximum:
        raise ValueError(f"El miembro '{name}' excede el límite de tamaño.")
    if info.file_size and (
        info.compress_size == 0 or info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
    ):
        raise ValueError(f"El miembro '{name}' excede el ratio de compresión permitido.")
    return archive.read(info)


def _content_fingerprint(entrypoint: str, files: tuple[LibraryEntry, ...]) -> str:
    payload = {
        "entrypoint": entrypoint,
        "files": [
            {"path": entry.path, "size": entry.size, "sha256": entry.sha256, "loads": list(entry.loads)}
            for entry in files
        ],
    }
    return _sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


def _collect_files(entrypoint: Path) -> tuple[tuple[str, Path], ...]:
    root = entrypoint.parent
    limit = resolve_limits().cap(MAX_SOURCE_SIZE)
    collected: list[tuple[str, Path]] = []
    for candidate in root.rglob("*"):
        if not candidate.is_file() or candidate.suffix.lower() != ".rif":
            continue
        resolved = candidate.resolve(strict=True)
        if resolved.stat().st_size > limit:
            raise ValueError(f"La fuente RIF excede el límite: {resolved}")
        relative = PurePosixPath(resolved.relative_to(root).as_posix()).as_posix()
        collected.append((relative, resolved))
        if len(collected) > MAX_SOURCE_FILES:
            raise ValueError("La librería excede el límite de fuentes.")
    expected = entrypoint.resolve(strict=True).relative_to(root).as_posix()
    if expected not in {relative for relative, _ in collected}:
        raise FileNotFoundError(f"No se pudo incluir el entrypoint: {entrypoint}")
    return tuple(sorted(collected, key=lambda item: item[0].casefold()))


def _resolve_load(requested: str, relative: str, root: Path) -> str:
    path = Path(requested)
    if path.is_absolute() or path.suffix.lower() != ".rif":
        raise ValueError(f"@LOAD inválido en {relative}: {requested!r}")
    candidate = (root / Path(relative).parent / path).resolve(strict=False)
    try:
        rel = candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"@LOAD intenta salir de la librería: {requested!r}") from exc
    if not candidate.is_file():
        raise FileNotFoundError(f"@LOAD no encontrado en {relative}: {requested!r}")
    return f"{SOURCE_PREFIX}{PurePosixPath(rel.as_posix()).as_posix()}"


def _index(entrypoint: Path, files: tuple[tuple[str, Path], ...]):
    root = entrypoint.parent
    graph: dict[str, tuple[str, ...]] = {}
    for relative, path in files:
        dependencies: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            match = _LOAD_RE.match(line)
            if match:
                dependency = _resolve_load(match.group(1), relative, root)
                if dependency not in dependencies:
                    dependencies.append(dependency)
        graph[f"{SOURCE_PREFIX}{relative}"] = tuple(dependencies)
    entry = f"{SOURCE_PREFIX}{entrypoint.relative_to(root).as_posix()}"
    order: list[str] = []
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(source: str) -> None:
        if source in visited:
            return
        if source in visiting:
            raise ValueError("Ciclo de @LOAD en la librería: " + " -> ".join((*visiting, source)))
        visiting.append(source)
        for dependency in graph[source]:
            if dependency not in graph:
                raise ValueError(f"@LOAD referencia una fuente no incluida: {dependency}")
            visit(dependency)
        visiting.pop()
        visited.add(source)
        order.append(source)

    visit(entry)
    return graph, tuple(order)


def create_library(
    source: str | Path,
    output: str | Path | None = None,
    *,
    name: str | None = None,
    version: str = "1.0.0",
) -> Path:
    """Create a reproducible ``.riflib`` from a source project."""

    entrypoint = Path(source).expanduser().resolve(strict=True)
    if entrypoint.suffix.lower() != ".rif":
        raise ValueError("El entrypoint de una librería debe ser .rif.")
    files = _collect_files(entrypoint)
    graph, order = _index(entrypoint, files)
    entries = tuple(
        LibraryEntry(
            path=f"{SOURCE_PREFIX}{relative}",
            size=len(path.read_bytes()),
            sha256=_sha256(path.read_bytes()),
            loads=graph[f"{SOURCE_PREFIX}{relative}"],
        )
        for relative, path in files
    )
    manifest = LibraryManifest(
        name=name or entrypoint.stem,
        version=version,
        entrypoint=f"{SOURCE_PREFIX}{entrypoint.relative_to(entrypoint.parent).as_posix()}",
        files=entries,
        load_graph=graph,
        dependency_order=order,
        content_sha256=_content_fingerprint(
            f"{SOURCE_PREFIX}{entrypoint.relative_to(entrypoint.parent).as_posix()}", entries
        ),
    )
    target = Path(output).expanduser().resolve() if output else entrypoint.with_suffix(".riflib")
    if target in {entrypoint, *(path for _, path in files)}:
        raise ValueError(f"La salida no puede sobrescribir una fuente: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.stem}.", suffix=".tmp", dir=target.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            archive.writestr(_zip_info(MANIFEST_NAME), json.dumps(manifest.as_dict(), sort_keys=True, separators=(",", ":")).encode() + b"\n")
            for relative, path in files:
                archive.writestr(_zip_info(f"{SOURCE_PREFIX}{relative}"), path.read_bytes())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


class LibraryReader:
    """Bounded reader/provider for one ``.riflib`` archive."""

    def __init__(self, path: str | Path, *, verify: bool = True, data: bytes | None = None) -> None:
        self.path = Path(path).expanduser().resolve(strict=False)
        self._temporary: Path | None = None
        if data is not None:
            fd, temporary_name = tempfile.mkstemp(prefix="riflib-", suffix=".riflib")
            os.close(fd)
            self._temporary = Path(temporary_name)
            self._temporary.write_bytes(data)
            archive_path = self._temporary
        else:
            archive_path = self.path
        self._archive = zipfile.ZipFile(archive_path, "r")
        try:
            infos = self._archive.infolist()
            if len(infos) > MAX_SOURCE_FILES + 1 or sum(info.file_size for info in infos) > resolve_limits().cap(MAX_TOTAL_UNCOMPRESSED):
                raise ValueError("La librería excede los límites de recursos.")
            raw = _read_member(self._archive, MANIFEST_NAME, resolve_limits().cap(MAX_MANIFEST_SIZE))
            self.manifest = LibraryManifest.from_dict(json.loads(raw.decode("utf-8")))
            self._known_sources = {entry.path for entry in self.manifest.files}
            if self.manifest.entrypoint not in self._known_sources or set(self.manifest.load_graph) != self._known_sources:
                raise ValueError("El manifiesto de la librería no cubre sus fuentes.")
            if len(self._known_sources) != len(self.manifest.files):
                raise ValueError("La librería contiene fuentes duplicadas.")
            for entry in self.manifest.files:
                normalized = PurePosixPath(entry.path)
                if (
                    not entry.path.startswith(SOURCE_PREFIX)
                    or normalized.is_absolute()
                    or ".." in normalized.parts
                    or entry.path == SOURCE_PREFIX
                    or tuple(self.manifest.load_graph[entry.path]) != entry.loads
                ):
                    raise ValueError(f"Ruta o índice de fuente inválido: {entry.path}")
            if (
                len(self.manifest.dependency_order) != len(self._known_sources)
                or set(self.manifest.dependency_order) != self._known_sources
            ):
                raise ValueError("El orden de dependencias de la librería es inválido.")
            positions = {
                source: index for index, source in enumerate(self.manifest.dependency_order)
            }
            for source, dependencies in self.manifest.load_graph.items():
                if any(
                    dependency not in self._known_sources
                    or positions[dependency] >= positions[source]
                    for dependency in dependencies
                ):
                    raise ValueError("El orden de @LOAD de la librería es inválido.")
            if _content_fingerprint(self.manifest.entrypoint, self.manifest.files) != self.manifest.content_sha256:
                raise ValueError("La huella de contenido de la librería es inválida.")
            declared = {MANIFEST_NAME, *self._known_sources}
            if set(self._archive.namelist()) != declared:
                raise ValueError("El contenido ZIP no coincide con el manifiesto de la librería.")
            if verify:
                for entry in self.manifest.files:
                    data_value = _read_member(self._archive, entry.path, resolve_limits().cap(MAX_SOURCE_SIZE))
                    if len(data_value) != entry.size or _sha256(data_value) != entry.sha256:
                        raise ValueError(f"Hash o tamaño inválido para {entry.path}")
        except Exception:
            self._archive.close()
            if self._temporary is not None:
                self._temporary.unlink(missing_ok=True)
            raise

    @classmethod
    def from_bytes(cls, data: bytes, *, name: str = "<memory>.riflib") -> "LibraryReader":
        return cls(name, data=data)

    def close(self) -> None:
        self._archive.close()
        if self._temporary is not None:
            self._temporary.unlink(missing_ok=True)

    def __enter__(self) -> "LibraryReader":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _source_key(self, source: str | Path | None) -> str:
        value = self.manifest.entrypoint if source is None else str(source).replace("\\", "/")
        if "::" in value:
            value = value.rsplit("::", 1)[1]
        value = PurePosixPath(value).as_posix()
        if not value.startswith(SOURCE_PREFIX):
            value = f"{SOURCE_PREFIX}{value.lstrip('/')}"
        if value not in self._known_sources or PurePosixPath(value).is_absolute() or ".." in PurePosixPath(value).parts:
            raise FileNotFoundError(f"Fuente no incluida en la librería: {source}")
        return value

    def virtual_path(self, source: str | Path | None = None) -> str:
        return f"riflib://{self.path.as_posix()}::{self._source_key(source)}"

    def resolve_load(self, source: str | Path | None, requested: str) -> str:
        source_key = self._source_key(source)
        requested_path = PurePosixPath(requested.replace("\\", "/"))
        if Path(requested).is_absolute() or requested_path.is_absolute() or ".." in requested_path.parts:
            raise ValueError(f"@LOAD intenta salir de la librería: {requested!r}")
        key = posixpath.normpath(str(PurePosixPath(PurePosixPath(source_key).parent) / requested_path))
        if key not in self._known_sources or key not in self.manifest.load_graph.get(source_key, ()):
            raise ValueError(f"@LOAD no coincide con el índice de la librería: {requested!r}")
        return self.virtual_path(key)

    def source_text(self, source: str | Path | None = None) -> str:
        return _read_member(self._archive, self._source_key(source), resolve_limits().cap(MAX_SOURCE_SIZE)).decode("utf-8")

    def source_bytes(self, source: str | Path | None = None) -> bytes:
        return _read_member(self._archive, self._source_key(source), resolve_limits().cap(MAX_SOURCE_SIZE))


def resolve_library(requested: str, source_path: str | Path | None, project_root: str | Path | None = None) -> Path:
    path = Path(requested).expanduser()
    if path.is_absolute() or path.suffix.lower() != ".riflib":
        raise ValueError("@LIBRARY solo acepta rutas relativas .riflib.")
    base = Path(source_path).expanduser().parent if source_path else Path.cwd()
    candidate = (base / path).resolve(strict=False)
    root = Path(project_root).expanduser().resolve(strict=False) if project_root else base.resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("@LIBRARY intenta salir de la raíz del proyecto.") from exc
    return candidate


__all__ = [
    "LibraryEntry",
    "LibraryManifest",
    "LibraryReader",
    "RIFLIB_FORMAT",
    "RIFLIB_FORMAT_VERSION",
    "create_library",
    "resolve_library",
]
