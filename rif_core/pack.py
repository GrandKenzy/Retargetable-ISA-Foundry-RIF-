"""Formato y creación de paquetes fuente ``.pack`` de RIF.

Un paquete ``.pack`` es un ZIP reproducible que contiene todos los archivos
``.rif`` del directorio del proyecto bajo ``sources/``, un manifiesto JSON y,
cuando se crea con ``precompile=True``, una
base SQLite con las Rules, tablas y contexto del target ya resueltos. El MIR
externo y el binario final permanecen fuera del paquete.
"""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from rif_core.contract import (
    PACK_FORMAT_VERSION,
    CompilationContract,
    ContractError,
    current_contract,
    require_compatible,
)
from rif_core.limits import resolve_limits


PACK_FORMAT = "RIF_PACK"
MANIFEST_NAME = "manifest.json"
SOURCE_PREFIX = "sources/"
MAX_MANIFEST_SIZE = 1 << 20
MAX_SOURCE_FILES = 4096
MAX_SOURCE_SIZE = 16 << 20
MAX_ASSET_FILES = 4096
MAX_ASSET_SIZE = 128 << 20
MAX_COMPILED_SIZE = 128 << 20
MAX_TOTAL_UNCOMPRESSED = 512 << 20
MAX_COMPRESSION_RATIO = 10_000
_LOAD_RE = re.compile(r'^\s*@LOAD\s+"([^"]+)"(?:\s*;.*)?\s*$', re.IGNORECASE)
_LIBRARY_RE = re.compile(r'^\s*@LIBRARY\s+"([^"]+)"(?:\s*;.*)?\s*$', re.IGNORECASE)
_INSERT_FILE_RE = re.compile(r'^\s*\.file\s+"([^"]+)"(?:\s*;.*)?\s*$', re.IGNORECASE)


@dataclass(frozen=True)
class PackEntry:
    """Metadata de un archivo incluido en el paquete."""

    path: str
    size: int
    sha256: str
    loads: tuple[str, ...] = ()


@dataclass(frozen=True)
class PackManifest:
    """Manifiesto validado de un paquete ``.pack``."""

    name: str
    version: str
    entrypoint: str
    files: tuple[PackEntry, ...]
    load_graph: dict[str, tuple[str, ...]]
    dependency_order: tuple[str, ...]
    content_sha256: str
    contract: CompilationContract
    compiled: PackEntry | None = None
    assets: tuple[PackEntry, ...] = ()
    libraries: tuple[PackEntry, ...] = ()
    origins: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": PACK_FORMAT,
            "format_version": PACK_FORMAT_VERSION,
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
            "contract": self.contract.as_dict(),
            "compiled": (
                {
                    "path": self.compiled.path,
                    "size": self.compiled.size,
                    "sha256": self.compiled.sha256,
                }
                if self.compiled is not None
                else None
            ),
            "assets": [
                {
                    "path": entry.path,
                    "size": entry.size,
                    "sha256": entry.sha256,
                }
                for entry in self.assets
            ],
            "libraries": [
                {
                    "path": entry.path,
                    "size": entry.size,
                    "sha256": entry.sha256,
                }
                for entry in self.libraries
            ],
            "origins": dict(sorted(self.origins.items())),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PackManifest":
        if data.get("format") != PACK_FORMAT:
            raise ValueError("El archivo no es un paquete RIF válido.")
        format_version = data.get("format_version")
        if format_version != PACK_FORMAT_VERSION:
            raise ValueError(
                "Versión de formato .pack no compatible: "
                f"{format_version!r}."
            )
        try:
            contract = CompilationContract.from_dict(data.get("contract"))
        except (TypeError, ValueError) as exc:
            raise ValueError("El manifiesto no contiene un contrato compatible.") from exc

        raw_files = data.get("files")
        if not isinstance(raw_files, list):
            raise ValueError("El manifiesto .pack no contiene una lista de archivos.")

        if len(raw_files) > MAX_SOURCE_FILES:
            raise ValueError("El paquete excede el límite de archivos RIF.")
        entries: list[PackEntry] = []
        for raw in raw_files:
            if not isinstance(raw, dict):
                raise ValueError("El manifiesto contiene una entrada de archivo inválida.")
            path = raw.get("path")
            size = raw.get("size")
            sha256 = raw.get("sha256")
            raw_loads = raw.get("loads", [])
            if (
                not isinstance(path, str)
                or not isinstance(size, int)
                or size < 0
                or not isinstance(sha256, str)
                or len(sha256) != 64
                or not isinstance(raw_loads, list)
                or not all(isinstance(item, str) for item in raw_loads)
            ):
                raise ValueError("El manifiesto contiene metadatos de archivo inválidos.")
            entries.append(PackEntry(path, size, sha256, tuple(raw_loads)))

        raw_graph = data.get("load_graph", {})
        raw_order = data.get("dependency_order", [])
        if not isinstance(raw_graph, dict) or not isinstance(raw_order, list):
            raise ValueError("El manifiesto contiene un índice de LOAD inválido.")
        load_graph = {
            str(path): tuple(dependencies)
            for path, dependencies in raw_graph.items()
            if isinstance(path, str)
            and isinstance(dependencies, list)
            and all(isinstance(item, str) for item in dependencies)
        }
        if len(load_graph) != len(raw_graph) or not all(
            isinstance(item, str) for item in raw_order
        ):
            raise ValueError("El manifiesto contiene un índice de LOAD inválido.")

        raw_compiled = data.get("compiled")
        compiled = None
        if raw_compiled is not None:
            if not isinstance(raw_compiled, dict):
                raise ValueError("El manifiesto contiene metadata compilada inválida.")
            compiled_path = raw_compiled.get("path")
            compiled_size = raw_compiled.get("size")
            compiled_sha256 = raw_compiled.get("sha256")
            if (
                not isinstance(compiled_path, str)
                or not isinstance(compiled_size, int)
                or compiled_size < 0
                or not isinstance(compiled_sha256, str)
                or len(compiled_sha256) != 64
            ):
                raise ValueError("El manifiesto contiene metadata compilada inválida.")
            compiled = PackEntry(compiled_path, compiled_size, compiled_sha256)

        raw_assets = data.get("assets", [])
        if not isinstance(raw_assets, list):
            raise ValueError("El manifiesto contiene metadata de assets inválida.")
        if len(raw_assets) > MAX_ASSET_FILES:
            raise ValueError("El paquete excede el límite de assets.")
        assets: list[PackEntry] = []
        for raw in raw_assets:
            if not isinstance(raw, dict):
                raise ValueError("El manifiesto contiene un asset inválido.")
            asset_path = raw.get("path")
            asset_size = raw.get("size")
            asset_sha256 = raw.get("sha256")
            if (
                not isinstance(asset_path, str)
                or not isinstance(asset_size, int)
                or asset_size < 0
                or not isinstance(asset_sha256, str)
                or len(asset_sha256) != 64
            ):
                raise ValueError("El manifiesto contiene metadata de asset inválida.")
            assets.append(PackEntry(asset_path, asset_size, asset_sha256))

        raw_libraries = data.get("libraries", [])
        if not isinstance(raw_libraries, list) or len(raw_libraries) > MAX_ASSET_FILES:
            raise ValueError("El manifiesto contiene metadata de librerías inválida.")
        libraries: list[PackEntry] = []
        for raw in raw_libraries:
            if not isinstance(raw, dict):
                raise ValueError("El manifiesto contiene una librería inválida.")
            library_path = raw.get("path")
            library_size = raw.get("size")
            library_sha256 = raw.get("sha256")
            if (
                not isinstance(library_path, str)
                or not isinstance(library_size, int)
                or library_size < 0
                or not isinstance(library_sha256, str)
                or len(library_sha256) != 64
            ):
                raise ValueError("El manifiesto contiene metadata de librería inválida.")
            libraries.append(PackEntry(library_path, library_size, library_sha256))

        raw_origins = data.get("origins", {})
        if not isinstance(raw_origins, dict) or not all(
            isinstance(key, str) and isinstance(value, str) and value
            for key, value in raw_origins.items()
        ):
            raise ValueError("El manifiesto contiene metadata de origen inválida.")

        content_sha256 = data.get("content_sha256")
        if not isinstance(content_sha256, str) or len(content_sha256) != 64:
            raise ValueError("El manifiesto no contiene una huella de contenido válida.")

        return cls(
            name=str(data.get("name", "")),
            version=str(data.get("version", "")),
            entrypoint=str(data.get("entrypoint", "")),
            files=tuple(entries),
            load_graph=load_graph,
            dependency_order=tuple(raw_order),
            content_sha256=content_sha256,
            contract=contract,
            compiled=compiled,
            assets=tuple(assets),
            libraries=tuple(libraries),
            origins=dict(raw_origins),
        )


def _canonical_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _project_files(entrypoint: Path) -> tuple[tuple[str, Path], ...]:
    """Collect all local ``.rif`` files with stable POSIX paths."""

    root = entrypoint.parent
    source_limit = resolve_limits().cap(MAX_SOURCE_SIZE)
    collected: list[tuple[str, Path]] = []
    for candidate in root.rglob("*"):
        if not candidate.is_file() or candidate.suffix.lower() != ".rif":
            continue
        resolved = candidate.resolve(strict=True)
        if resolved.stat().st_size > source_limit:
            raise ValueError(
                f"La fuente RIF '{candidate}' excede el límite de {source_limit} bytes."
            )
        try:
            relative = resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(
                f"El archivo RIF está fuera del proyecto: {candidate}"
            ) from exc
        relative_name = PurePosixPath(relative.as_posix()).as_posix()
        if any(existing == relative_name for existing, _ in collected):
            continue
        collected.append((relative_name, resolved))
        if len(collected) > MAX_SOURCE_FILES:
            raise ValueError("El proyecto excede el límite de archivos RIF.")

    expected = entrypoint.relative_to(root).as_posix()
    if expected not in {relative for relative, _ in collected}:
        raise FileNotFoundError(f"No se pudo incluir el entrypoint RIF: {entrypoint}")

    return tuple(sorted(collected, key=lambda item: item[0].casefold()))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _source_key(relative: str) -> str:
    return f"{SOURCE_PREFIX}{relative}"


def _resolve_load(
    requested: str,
    relative_source: str,
    root: Path,
) -> str:
    requested_path = Path(requested).expanduser()
    if requested_path.is_absolute() or requested_path.suffix.lower() != ".rif":
        raise ValueError(
            f"@LOAD inválido en {relative_source}: se esperaba una ruta .rif local, "
            f"se recibió {requested!r}."
        )

    candidate = (root / Path(relative_source).parent / requested_path).resolve(strict=False)
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"@LOAD en {relative_source} intenta salir del proyecto: {requested!r}."
        ) from exc
    if not candidate.is_file():
        raise FileNotFoundError(
            f"@LOAD en {relative_source} referencia un archivo inexistente: {requested!r}."
        )
    return _source_key(PurePosixPath(relative.as_posix()).as_posix())


def _scan_loads(relative: str, path: Path, root: Path) -> tuple[str, ...]:
    dependencies: list[str] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = _LOAD_RE.match(line)
        if match is None:
            continue
        try:
            dependency = _resolve_load(match.group(1), relative, root)
        except (FileNotFoundError, ValueError) as exc:
            raise type(exc)(f"{exc} (línea {line_number})") from exc
        if dependency not in dependencies:
            dependencies.append(dependency)
    return tuple(dependencies)


def _dependency_index(
    entrypoint: Path,
    files: tuple[tuple[str, Path], ...],
) -> tuple[dict[str, tuple[str, ...]], tuple[str, ...]]:
    """Build and validate a dependency-first index for every local source."""

    root = entrypoint.parent
    graph = {
        _source_key(relative): _scan_loads(relative, path, root)
        for relative, path in files
    }
    entry_key = _source_key(entrypoint.relative_to(root).as_posix())
    order: list[str] = []
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(source: str) -> None:
        if source in visited:
            return
        if source in visiting:
            cycle = " -> ".join((*visiting, source))
            raise ValueError(f"Ciclo de @LOAD detectado al empaquetar: {cycle}")
        visiting.append(source)
        for dependency in graph[source]:
            if dependency not in graph:
                raise ValueError(
                    f"El índice de @LOAD referencia una fuente no incluida: {dependency}"
                )
            visit(dependency)
        visiting.pop()
        visited.add(source)
        order.append(source)

    visit(entry_key)
    for source in sorted(graph):
        visit(source)
    return graph, tuple(order)


def _collect_assets(
    files: tuple[tuple[str, Path], ...],
    root: Path,
) -> dict[str, bytes]:
    """Collect binary files named by ``.file`` insert directives."""

    assets: dict[str, bytes] = {}
    asset_limit = resolve_limits().cap(MAX_ASSET_SIZE)
    total_limit = resolve_limits().cap(MAX_TOTAL_UNCOMPRESSED)
    total = 0
    for relative, path in files:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = _INSERT_FILE_RE.match(line)
            if match is None:
                continue
            requested = Path(match.group(1)).expanduser()
            if requested.is_absolute() or ".." in requested.parts:
                raise ValueError(
                    f".file inválido en {relative}:{line_number}: {match.group(1)!r}"
                )
            candidate = (path.parent / requested).resolve(strict=False)
            try:
                asset_relative = candidate.relative_to(root.resolve())
            except ValueError as exc:
                raise ValueError(
                    f".file intenta salir del proyecto en {relative}:{line_number}."
                ) from exc
            if not candidate.is_file():
                raise FileNotFoundError(
                    f"No se encontró el asset de .file en {relative}:{line_number}: {candidate}"
                )
            key = PurePosixPath(asset_relative.as_posix()).as_posix()
            if candidate.stat().st_size > asset_limit:
                raise ValueError(
                    f"El asset '{candidate}' excede el límite de {asset_limit} bytes."
                )
            data = candidate.read_bytes()
            previous = assets.get(key)
            if previous is not None and previous != data:
                raise ValueError(f"El asset '{key}' fue definido con bytes distintos.")
            assets[key] = data
            total += len(data) if previous is None else 0
            if len(assets) > MAX_ASSET_FILES or total > total_limit:
                raise ValueError("Los assets exceden el límite del paquete.")
    return assets


def _collect_libraries(
    files: tuple[tuple[str, Path], ...],
    root: Path,
) -> dict[str, bytes]:
    """Collect portable ``@LIBRARY`` packages referenced by project sources."""

    libraries: dict[str, bytes] = {}
    library_limit = resolve_limits().cap(MAX_ASSET_SIZE)
    total_limit = resolve_limits().cap(MAX_TOTAL_UNCOMPRESSED)
    total = 0
    for relative, path in files:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = _LIBRARY_RE.match(line)
            if match is None:
                continue
            requested = Path(match.group(1)).expanduser()
            if requested.is_absolute() or requested.suffix.lower() != ".riflib" or ".." in requested.parts:
                raise ValueError(
                    f"@LIBRARY inválido en {relative}:{line_number}: {match.group(1)!r}"
                )
            candidate = (path.parent / requested).resolve(strict=False)
            try:
                library_relative = candidate.relative_to(root.resolve())
            except ValueError as exc:
                raise ValueError(
                    f"@LIBRARY intenta salir del proyecto en {relative}:{line_number}."
                ) from exc
            if not candidate.is_file():
                raise FileNotFoundError(
                    f"No se encontró la librería en {relative}:{line_number}: {candidate}"
                )
            key = PurePosixPath(library_relative.as_posix()).as_posix()
            if candidate.stat().st_size > library_limit:
                raise ValueError(f"La librería '{candidate}' excede el límite del paquete.")
            data = candidate.read_bytes()
            previous = libraries.get(key)
            if previous is not None and previous != data:
                raise ValueError(f"La librería '{key}' fue definida con bytes distintos.")
            libraries[key] = data
            total += len(data) if previous is None else 0
            if len(libraries) > MAX_ASSET_FILES or total > total_limit:
                raise ValueError("Las librerías exceden el límite del paquete.")
    return libraries


def _content_fingerprint(
    entrypoint: str,
    files: tuple[PackEntry, ...],
    assets: tuple[PackEntry, ...],
    libraries: tuple[PackEntry, ...] = (),
) -> str:
    """Bind a compiled cache to every source and opaque input it represents."""

    payload = {
        "entrypoint": entrypoint,
        "files": [
            {
                "path": entry.path,
                "size": entry.size,
                "sha256": entry.sha256,
                "loads": list(entry.loads),
            }
            for entry in files
        ],
        "assets": [
            {"path": entry.path, "size": entry.size, "sha256": entry.sha256}
            for entry in assets
        ],
        "libraries": [
            {"path": entry.path, "size": entry.size, "sha256": entry.sha256}
            for entry in libraries
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256(encoded)


def _manifest_for(
    entrypoint: Path,
    files: tuple[tuple[str, Path], ...],
    compiled_data: bytes | None = None,
    asset_data: dict[str, bytes] | None = None,
    library_data: dict[str, bytes] | None = None,
    origins: dict[str, str] | None = None,
    contract: CompilationContract | None = None,
) -> PackManifest:
    contract = contract or current_contract()
    load_graph, dependency_order = _dependency_index(entrypoint, files)
    entries: list[PackEntry] = []
    for relative, path in files:
        data = path.read_bytes()
        key = _source_key(relative)
        entries.append(
            PackEntry(
                path=key,
                size=len(data),
                sha256=_sha256(data),
                loads=load_graph[key],
            )
        )
    entrypoint_key = f"{SOURCE_PREFIX}{entrypoint.relative_to(entrypoint.parent).as_posix()}"
    asset_entries = tuple(
        PackEntry(
            path=f"assets/{relative}",
            size=len(data),
            sha256=_sha256(data),
        )
        for relative, data in sorted((asset_data or {}).items())
    )
    library_entries = tuple(
        PackEntry(
            path=f"libraries/{relative}",
            size=len(data),
            sha256=_sha256(data),
        )
        for relative, data in sorted((library_data or {}).items())
    )
    file_entries = tuple(entries)
    return PackManifest(
        name=entrypoint.stem,
        version="1.0.0",
        entrypoint=entrypoint_key,
        files=file_entries,
        load_graph=load_graph,
        dependency_order=dependency_order,
        content_sha256=_content_fingerprint(
            entrypoint_key, file_entries, asset_entries, library_entries
        ),
        contract=contract,
        compiled=(
            PackEntry(
                path="compiled/program.sqlite3",
                size=len(compiled_data),
                sha256=_sha256(compiled_data),
            )
            if compiled_data is not None
            else None
        ),
        assets=asset_entries,
        libraries=library_entries,
        origins=dict(origins or {}),
    )


def _build_compiled_database(
    entrypoint: Path,
    source_fingerprint: str,
    contract: CompilationContract,
) -> bytes:
    """Compile a source project in an isolated global context."""

    try:
        # Direct ``main.py --pack`` must bootstrap the VNMA vendor projection before
        # importing MIR/Gram. Under ``vnma run`` this is already initialized.
        import vendor  # noqa: F401
        from Frontend import globals as rif_globals
        from MIR import compile_source
        from MIR.compiled import build_database
        from MIR import compiler as compiler_module
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "No se pudo precompilar el paquete: instala Gram con 'vnma install'."
        ) from exc

    mutable_names = (
        "DEFINES",
        "TABLES",
        "RULES",
        "SUPPORTS",
        "ASM_VARIANTS",
        "LOADED_SOURCES",
        "ACTIVE_SOURCES",
        "VARIANT_STACK",
    )
    previous = {
        "STACK": rif_globals.STACK,
        "STACK_SIZE": rif_globals.STACK_SIZE,
        "CONFIG": rif_globals.CONFIG,
        "LINKER": rif_globals.LINKER,
        "SOURCE_PROVIDER": rif_globals.SOURCE_PROVIDER,
        **{name: getattr(rif_globals, name) for name in mutable_names},
        "SOURCE_TEXTS": dict(compiler_module.SOURCE_TEXTS),
    }
    try:
        rif_globals.STACK = None
        rif_globals.STACK_SIZE = None
        rif_globals.CONFIG = None
        rif_globals.LINKER = None
        rif_globals.SOURCE_PROVIDER = None
        rif_globals.DEFINES = set()
        rif_globals.TABLES = {}
        rif_globals.RULES = {}
        rif_globals.SUPPORTS = {}
        rif_globals.ASM_VARIANTS = {}
        rif_globals.LOADED_SOURCES = {}
        rif_globals.ACTIVE_SOURCES = []
        rif_globals.VARIANT_STACK = []
        compiler_module.SOURCE_TEXTS.clear()
        program = compile_source(entrypoint)
        return build_database(
            program,
            source_root=entrypoint.parent,
            source_fingerprint=source_fingerprint,
            contract=contract,
        )
    finally:
        for name, value in previous.items():
            if name == "SOURCE_TEXTS":
                compiler_module.SOURCE_TEXTS.clear()
                compiler_module.SOURCE_TEXTS.update(value)
            else:
                setattr(rif_globals, name, value)


def _zip_info(name: str) -> zipfile.ZipInfo:
    """Create deterministic ZIP metadata independent of filesystem time."""

    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 0
    info.external_attr = 0o100644 << 16
    return info


def create_pack(
    source: str | Path,
    output: str | Path | None = None,
    *,
    precompile: bool = False,
) -> Path:
    """Create a reproducible ``.pack`` from the project containing ``source``.

    ``precompile=True`` adds the SQLite/CompiledRuleSet cache used by the
    normal ``main.py --pack`` command. The default remains source-only for
    low-level callers that only need the archive and dependency graph.
    """

    entrypoint = _canonical_path(source)
    if not entrypoint.is_file():
        raise FileNotFoundError(f"Archivo RIF no encontrado: {entrypoint}")
    if entrypoint.suffix.lower() != ".rif":
        raise ValueError(f"El entrypoint del paquete debe ser .rif: {entrypoint}")

    limits = resolve_limits()
    source_limit = limits.cap(MAX_SOURCE_SIZE)
    total_limit = limits.cap(MAX_TOTAL_UNCOMPRESSED)
    files = _project_files(entrypoint)
    asset_data = _collect_assets(files, entrypoint.parent)
    library_data = _collect_libraries(files, entrypoint.parent)
    source_total = sum(path.stat().st_size for _, path in files)
    total_size = (
        source_total
        + sum(len(data) for data in asset_data.values())
        + sum(len(data) for data in library_data.values())
    )
    if total_size > total_limit:
        raise ValueError("El contenido del paquete excede el límite configurado.")
    contract = current_contract()
    origins = {
        f"{SOURCE_PREFIX}{relative}": str(path)
        for relative, path in files
    }
    origins.update(
        {
            f"assets/{relative}": str((entrypoint.parent / relative).resolve())
            for relative in asset_data
        }
    )
    input_manifest = _manifest_for(
        entrypoint,
        files,
        None,
        asset_data,
        library_data,
        origins,
        contract,
    )
    compiled_data = (
        _build_compiled_database(
            entrypoint,
            input_manifest.content_sha256,
            contract,
        )
        if precompile
        else None
    )
    manifest = _manifest_for(
        entrypoint,
        files,
        compiled_data,
        asset_data,
        library_data,
        origins,
        contract,
    )
    target = _canonical_path(output) if output is not None else entrypoint.with_suffix(".pack")
    protected = {entrypoint, *(path for _, path in files)}
    protected.update((entrypoint.parent / key).resolve(strict=False) for key in asset_data)
    protected.update((entrypoint.parent / key).resolve(strict=False) for key in library_data)
    if target in protected:
        raise ValueError(f"La salida .pack no puede sobrescribir una entrada: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{target.stem}.",
        suffix=".pack.tmp",
        dir=target.parent,
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(
            temporary,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            manifest_bytes = (
                json.dumps(
                    manifest.as_dict(),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                + b"\n"
            )
            archive.writestr(_zip_info(MANIFEST_NAME), manifest_bytes)
            if compiled_data is not None:
                archive.writestr(_zip_info("compiled/program.sqlite3"), compiled_data)
            for relative, path in files:
                archive.writestr(
                    _zip_info(f"{SOURCE_PREFIX}{relative}"),
                    path.read_bytes(),
                )
            for relative, data in sorted(asset_data.items()):
                archive.writestr(_zip_info(f"assets/{relative}"), data)
            for relative, data in sorted(library_data.items()):
                archive.writestr(_zip_info(f"libraries/{relative}"), data)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()

    return target


def _read_member(
    archive: zipfile.ZipFile,
    name: str,
    *,
    maximum: int,
) -> bytes:
    try:
        info = archive.getinfo(name)
    except KeyError as exc:
        raise ValueError(f"Falta el archivo declarado por el manifiesto: {name}") from exc
    if info.flag_bits & 0x1:
        raise ValueError(f"El miembro ZIP cifrado no está permitido: {name}")
    if info.file_size > maximum:
        raise ValueError(f"El miembro '{name}' excede el límite de tamaño.")
    if info.file_size and (
        info.compress_size == 0
        or info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
    ):
        raise ValueError(f"El miembro '{name}' excede el ratio de compresión permitido.")
    return archive.read(info)


def _compiled_source_fingerprint(data: bytes) -> str:
    connection = sqlite3.connect(":memory:")
    try:
        connection.deserialize(data)
        row = connection.execute(
            "SELECT value FROM meta WHERE key = 'source_fingerprint'"
        ).fetchone()
    except sqlite3.DatabaseError as exc:
        raise ValueError("La base SQLite compilada no es válida.") from exc
    finally:
        connection.close()
    if row is None or not isinstance(row[0], str):
        raise ValueError("La base compilada no declara su huella de fuentes.")
    return row[0]


def _compiled_contract_fingerprint(data: bytes) -> str:
    """Read the contract identity without loading the compiled program."""

    connection = sqlite3.connect(":memory:")
    try:
        connection.deserialize(data)
        row = connection.execute(
            "SELECT value FROM meta WHERE key = 'contract_fingerprint'"
        ).fetchone()
    except sqlite3.DatabaseError as exc:
        raise ValueError("La base SQLite compilada no es válida.") from exc
    finally:
        connection.close()
    if row is None or not isinstance(row[0], str):
        raise ValueError("La base compilada no declara su contrato.")
    return row[0]


def read_pack(path: str | Path, *, verify: bool = True) -> PackManifest:
    """Read and validate a bounded, self-consistent RIF package."""

    package = _canonical_path(path)
    if not package.is_file():
        raise FileNotFoundError(f"Paquete RIF no encontrado: {package}")

    with zipfile.ZipFile(package, mode="r") as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ValueError("El paquete contiene nombres ZIP duplicados.")
        limits = resolve_limits()
        if sum(info.file_size for info in infos) > limits.cap(MAX_TOTAL_UNCOMPRESSED):
            raise ValueError("El paquete excede el tamaño total permitido.")
        try:
            manifest_bytes = _read_member(
                archive, MANIFEST_NAME, maximum=limits.cap(MAX_MANIFEST_SIZE)
            )
            manifest_data = json.loads(manifest_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("manifest.json no es JSON válido.") from exc

        if not isinstance(manifest_data, dict):
            raise ValueError("manifest.json debe contener un objeto JSON.")
        manifest = PackManifest.from_dict(manifest_data)
        try:
            require_compatible(manifest.contract)
        except ContractError as exc:
            raise ValueError(f"Contrato .pack incompatible: {exc}") from exc
        source_names = {entry.path for entry in manifest.files}
        asset_names = {entry.path for entry in manifest.assets}
        library_names = {entry.path for entry in manifest.libraries}
        if (
            len(source_names) != len(manifest.files)
            or len(asset_names) != len(manifest.assets)
            or len(library_names) != len(manifest.libraries)
        ):
            raise ValueError("El manifiesto contiene rutas duplicadas.")
        if manifest.entrypoint not in source_names:
            raise ValueError("El entrypoint no está incluido en el paquete.")

        declared = {MANIFEST_NAME, *source_names, *asset_names, *library_names}
        if manifest.compiled is not None:
            declared.add(manifest.compiled.path)
        if any(path not in declared for path in manifest.origins):
            raise ValueError("El manifiesto contiene orígenes no declarados.")
        if set(names) != declared:
            extras = sorted(set(names) - declared)
            missing = sorted(declared - set(names))
            detail = extras or missing
            raise ValueError(
                "El contenido ZIP no coincide exactamente con el manifiesto: "
                + ", ".join(detail)
            )

        for entry in manifest.files:
            normalized = PurePosixPath(entry.path)
            if (
                not entry.path.startswith(SOURCE_PREFIX)
                or normalized.is_absolute()
                or ".." in normalized.parts
                or entry.size > resolve_limits().cap(MAX_SOURCE_SIZE)
            ):
                raise ValueError(f"Ruta o tamaño de fuente inválido: {entry.path}")
            data = _read_member(archive, entry.path, maximum=limits.cap(MAX_SOURCE_SIZE))
            if len(data) != entry.size or (verify and _sha256(data) != entry.sha256):
                raise ValueError(f"Hash o tamaño inválido para {entry.path}")

        if set(manifest.load_graph) != source_names:
            raise ValueError("El índice de @LOAD no coincide con los archivos del paquete.")
        entries_by_name = {entry.path: entry for entry in manifest.files}
        for source, dependencies in manifest.load_graph.items():
            if tuple(dependencies) != entries_by_name[source].loads:
                raise ValueError(f"Índice de @LOAD inconsistente para {source}.")
            if any(dependency not in source_names for dependency in dependencies):
                raise ValueError(f"@LOAD apunta fuera del paquete desde {source}.")
        if len(manifest.dependency_order) != len(source_names) or set(manifest.dependency_order) != source_names:
            raise ValueError("El orden de dependencias no cubre el paquete completo.")
        positions = {source: index for index, source in enumerate(manifest.dependency_order)}
        for source, dependencies in manifest.load_graph.items():
            if any(positions[dependency] >= positions[source] for dependency in dependencies):
                raise ValueError("El orden de dependencias del paquete es inválido.")

        for asset in manifest.assets:
            normalized = PurePosixPath(asset.path)
            if (
                not asset.path.startswith("assets/")
                or normalized.is_absolute()
                or ".." in normalized.parts
                or asset.size > resolve_limits().cap(MAX_ASSET_SIZE)
            ):
                raise ValueError(f"Ruta o tamaño de asset inválido: {asset.path}")
            data = _read_member(archive, asset.path, maximum=limits.cap(MAX_ASSET_SIZE))
            if len(data) != asset.size or (verify and _sha256(data) != asset.sha256):
                raise ValueError(f"Hash o tamaño inválido para {asset.path}")

        for library in manifest.libraries:
            normalized = PurePosixPath(library.path)
            if (
                not library.path.startswith("libraries/")
                or normalized.is_absolute()
                or ".." in normalized.parts
                or library.size > resolve_limits().cap(MAX_ASSET_SIZE)
            ):
                raise ValueError(f"Ruta o tamaño de librería inválido: {library.path}")
            data = _read_member(archive, library.path, maximum=limits.cap(MAX_ASSET_SIZE))
            if len(data) != library.size or (verify and _sha256(data) != library.sha256):
                raise ValueError(f"Hash o tamaño inválido para {library.path}")

        expected_fingerprint = _content_fingerprint(
            manifest.entrypoint,
            manifest.files,
            manifest.assets,
            manifest.libraries,
        )
        if expected_fingerprint != manifest.content_sha256:
            raise ValueError("La huella de contenido del paquete es inválida.")

        if manifest.compiled is not None:
            compiled = manifest.compiled
            if compiled.path != "compiled/program.sqlite3" or compiled.size > limits.cap(MAX_COMPILED_SIZE):
                raise ValueError("Ruta o tamaño de base compilada inválida.")
            data = _read_member(archive, compiled.path, maximum=limits.cap(MAX_COMPILED_SIZE))
            if len(data) != compiled.size or (verify and _sha256(data) != compiled.sha256):
                raise ValueError("Hash o tamaño inválido para la base SQLite compilada.")
            if _compiled_source_fingerprint(data) != manifest.content_sha256:
                raise ValueError(
                    "La base SQLite compilada no corresponde al contenido del paquete."
                )
            if _compiled_contract_fingerprint(data) != manifest.contract.fingerprint():
                raise ValueError(
                    "La base SQLite compilada no corresponde al contrato del paquete."
                )

    return manifest


class PackReader:
    """Lector directo de fuentes empaquetadas sin recorrer el filesystem."""

    def __init__(self, path: str | Path, *, verify: bool = True) -> None:
        self.path = _canonical_path(path)
        self.manifest = read_pack(self.path, verify=verify)
        self._archive = zipfile.ZipFile(self.path, mode="r")
        self._known_sources = {entry.path for entry in self.manifest.files}
        self._known_assets = {entry.path for entry in self.manifest.assets}
        self._known_libraries = {entry.path for entry in self.manifest.libraries}

    def close(self) -> None:
        self._archive.close()

    def __enter__(self) -> "PackReader":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def _source_key(self, source: str | Path | None) -> str:
        if source is None:
            return self.manifest.entrypoint
        value = str(source).replace("\\", "/")
        if value.startswith("pack://") and "::" in value:
            value = value.rsplit("::", 1)[1]
        value = PurePosixPath(value).as_posix()
        if not value.startswith(SOURCE_PREFIX):
            value = f"{SOURCE_PREFIX}{value.lstrip('/')}"
        normalized = PurePosixPath(value)
        if normalized.is_absolute() or ".." in normalized.parts:
            raise ValueError(f"Ruta de fuente inválida: {source}")
        key = normalized.as_posix()
        if key not in self._known_sources:
            raise FileNotFoundError(f"Fuente no incluida en el paquete: {source}")
        return key

    def virtual_path(self, source: str | Path | None = None) -> str:
        """Return a stable source identifier usable in diagnostics and ASTs."""

        return f"pack://{self.path.as_posix()}::{self._source_key(source)}"

    def resolve_load(self, source: str | Path | None, requested: str) -> str:
        """Resolve an @LOAD through the precomputed package graph."""

        source_key = self._source_key(source)
        requested_path = PurePosixPath(requested.replace("\\", "/"))
        if Path(requested).is_absolute() or requested_path.is_absolute() or ".." in requested_path.parts:
            raise ValueError(f"@LOAD intenta salir del paquete: {requested!r}")
        candidate = posixpath.normpath(
            str(PurePosixPath(PurePosixPath(source_key).parent) / requested_path)
        )
        if not candidate.startswith(SOURCE_PREFIX) or candidate == SOURCE_PREFIX.rstrip("/"):
            raise ValueError(f"@LOAD intenta salir del paquete: {requested!r}")
        key = candidate
        if key not in self._known_sources:
            raise FileNotFoundError(f"Fuente no incluida en el paquete: {requested}")
        if key not in self.manifest.load_graph.get(source_key, ()):
            raise ValueError(
                f"@LOAD no coincide con el índice precalculado: {source_key} -> {key}"
            )
        return self.virtual_path(key)

    def resolve_variant(
        self,
        name: str,
        search_paths: tuple[str, ...] | bool = ("",),
    ) -> str:
        if search_paths is False:
            raise ValueError("search_path false deshabilita la carga de variantes.")
        for relative in search_paths:
            searching_path = PurePosixPath(relative.replace("\\", "/"))
            if Path(relative).is_absolute() or searching_path.is_absolute() or ".." in searching_path.parts:
                raise ValueError("search_path solo acepta carpetas relativas dentro del paquete.")
            directory = PurePosixPath(SOURCE_PREFIX)
            if relative:
                directory /= searching_path
            key = (directory / f"{name}.rif").as_posix()
            if key in self._known_sources:
                return self.virtual_path(key)
        raise FileNotFoundError(f"Variante no incluida en el paquete: {name}")

    def source_bytes(self, source: str | Path | None = None) -> bytes:
        """Read one source directly from the package archive."""

        return _read_member(
            self._archive,
            self._source_key(source),
            maximum=resolve_limits().cap(MAX_SOURCE_SIZE),
        )

    def source_text(self, source: str | Path | None = None) -> str:
        return self.source_bytes(source).decode("utf-8")

    def resolve_library(self, source: str | Path | None, requested: str) -> str:
        """Resolve a packaged ``@LIBRARY`` relative to its declaring source."""

        source_key = self._source_key(source)
        requested_path = PurePosixPath(requested.replace("\\", "/"))
        if (
            Path(requested).is_absolute()
            or requested_path.is_absolute()
            or requested_path.suffix.lower() != ".riflib"
            or ".." in requested_path.parts
        ):
            raise ValueError(f"@LIBRARY intenta salir del paquete: {requested!r}")
        source_relative = PurePosixPath(source_key.removeprefix(SOURCE_PREFIX))
        candidate = posixpath.normpath(
            str(source_relative.parent / requested_path)
        )
        key = f"libraries/{candidate}"
        if key not in self._known_libraries:
            raise FileNotFoundError(f"Librería no incluida en el paquete: {requested}")
        return f"packlib://{self.path.as_posix()}::{key}"

    def open_library(self, library: str | Path) -> Any:
        """Open one packaged library without exposing its ZIP to callers."""

        from rif_core.library import LibraryReader

        value = str(library)
        key = value.rsplit("::", 1)[1] if "::" in value else value
        if key not in self._known_libraries:
            raise FileNotFoundError(f"Librería no incluida en el paquete: {library}")
        entry = next(item for item in self.manifest.libraries if item.path == key)
        data = _read_member(self._archive, key, maximum=resolve_limits().cap(MAX_ASSET_SIZE))
        if len(data) != entry.size or _sha256(data) != entry.sha256:
            raise ValueError(f"Hash o tamaño inválido para {key}")
        return LibraryReader.from_bytes(data, name=value)

    def dependencies(self, source: str | Path | None = None) -> tuple[str, ...]:
        return self.manifest.load_graph[self._source_key(source)]

    def ordered_sources(self) -> tuple[str, ...]:
        """Return the precomputed dependency-first source order."""

        return self.manifest.dependency_order

    def compiled_database(self) -> bytes | None:
        if self.manifest.compiled is None:
            return None
        return _read_member(
            self._archive,
            self.manifest.compiled.path,
            maximum=resolve_limits().cap(MAX_COMPILED_SIZE),
        )

    def assets(self) -> dict[str, bytes]:
        """Return opaque insert assets keyed by project-relative path."""

        return {
            path.removeprefix("assets/"): _read_member(
                self._archive, path, maximum=resolve_limits().cap(MAX_ASSET_SIZE)
            )
            for path in sorted(self._known_assets)
        }

    @property
    def origins(self) -> dict[str, str]:
        """Absolute creator paths kept for diagnostics only."""

        return dict(self.manifest.origins)

    @property
    def has_compiled_database(self) -> bool:
        return self.manifest.compiled is not None


__all__ = [
    "MANIFEST_NAME",
    "PACK_FORMAT",
    "PACK_FORMAT_VERSION",
    "PackEntry",
    "PackManifest",
    "PackReader",
    "create_pack",
    "read_pack",
]
