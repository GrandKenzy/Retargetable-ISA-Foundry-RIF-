"""Carga y controla las variantes ISA declaradas por un programa RIF.

Las variantes se procesan en el mismo contexto global que el archivo raíz. El
archivo de una variante solamente añade ``@define`` y ``@rule``; no crea un
segundo ``Session`` ni un segundo espacio semántico.
"""

from __future__ import annotations

from pathlib import Path

from Frontend import globals
from rif_limits import resolve_limits
from .parsing import SourceParser


MAX_SOURCE_BYTES = 16 << 20


def canonical_path(path: str | Path) -> str:
    """Devuelve una ruta estable para detectar archivos repetidos y ciclos."""

    return str(Path(path).expanduser().resolve(strict=False))


def _root_directory(root_path: Path) -> Path:
    """Obtiene el directorio base desde el que se resuelven variantes."""

    if root_path.exists() and root_path.is_dir():
        return root_path
    return root_path.parent


def resolve_variant(
    name: str,
    root_path: str | Path,
    project_root: str | Path | None = None,
) -> Path:
    """Resuelve ``<name>.rif`` respetando ``search_path`` del linker."""

    root = Path(root_path).expanduser()
    linker = globals.LINKER
    search_path: tuple[str, ...] | bool = ("",)
    if linker is not None:
        search_path = linker.search_path

    if search_path is False:
        raise RuntimeError(
            f"El linker deshabilita la carga automática; no se puede cargar la variante '{name}'."
        )

    boundary = Path(project_root).expanduser().resolve(strict=False) if project_root else _root_directory(root).resolve(strict=False)
    base_directory = _root_directory(root)
    candidates: list[Path] = []
    for relative in search_path:
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise RuntimeError("search_path solo acepta carpetas relativas dentro del proyecto.")
        directory = base_directory / relative if relative else base_directory
        candidate = Path(canonical_path(directory / f"{name}.rif"))
        try:
            candidate.relative_to(boundary)
        except ValueError as exc:
            raise RuntimeError("La variante intenta salir de la raíz del proyecto.") from exc
        candidates.append(candidate)
        if candidate.is_file():
            return candidate
    return candidates[-1]


def _load_variant(
    variant: globals.AsmVariantData,
    root_path: Path | str,
    source_provider=None,
    project_root: str | Path | None = None,
    backend: str = "aot",
    parser: SourceParser | None = None,
) -> None:
    """Carga recursivamente el archivo asociado a una variante."""

    if source_provider is not None:
        search_path = globals.LINKER.search_path if globals.LINKER is not None else ("",)
        path_key = source_provider.resolve_variant(variant.name, search_path)
        path = None
    else:
        path = resolve_variant(variant.name, root_path, project_root)
        path_key = canonical_path(path)

    if path_key in globals.ACTIVE_SOURCES:
        cycle = " -> ".join((*globals.ACTIVE_SOURCES, path_key))
        raise RuntimeError(f"Ciclo de variantes detectado: {cycle}")
    if path_key in globals.LOADED_SOURCES:
        return
    if path is not None and not path.is_file():
        raise FileNotFoundError(
            f"No se encontró el archivo de la variante '{variant.name}': {path}"
        )

    # Importaciones locales para evitar un ciclo: processor importa este
    # módulo y el cargador, a su vez, necesita el entrypoint del processor.
    from . import process

    source_parser = parser or SourceParser(backend=backend)
    globals.ACTIVE_SOURCES.append(path_key)
    try:
        if path is not None and path.stat().st_size > resolve_limits().cap(MAX_SOURCE_BYTES):
            raise ValueError(f"La variante excede el límite de tamaño: {path}")
        if backend == "aot":
            if path is None:
                raise ValueError("El backend AOT no puede recibir una variante virtual.")
            ast = source_parser.parse_file(path)
        else:
            source = (
                source_provider.source_text(path_key)
                if source_provider is not None
                else path.read_text(encoding="utf-8")
            )
            ast = source_parser.parse_text(source, path_key)
        process(
            ast,
            source_path=path_key,
            load_variants=False,
            scope="variant",
            source_provider=source_provider,
            project_root=project_root,
            backend=backend,
            parser=source_parser,
        )
        globals.LOADED_SOURCES[path_key] = variant.name
    finally:
        if globals.ACTIVE_SOURCES and globals.ACTIVE_SOURCES[-1] == path_key:
            globals.ACTIVE_SOURCES.pop()
        elif path_key in globals.ACTIVE_SOURCES:
            globals.ACTIVE_SOURCES.remove(path_key)


def validate_variant_rules() -> None:
    """Verifica que las Rules de entrada y salida estén disponibles."""

    for variant in globals.ASM_VARIANTS.values():
        missing = [
            rule
            for rule in (variant.enter_rule, variant.exit_rule)
            if rule not in globals.RULES
        ]
        if missing:
            raise RuntimeError(
                f"La variante '{variant.name}' referencia Rules inexistentes: "
                + ", ".join(missing)
            )


def load_variants(
    root_path: str | Path,
    source_provider=None,
    project_root: str | Path | None = None,
    backend: str = "aot",
    parser: SourceParser | None = None,
) -> None:
    """Carga todos los archivos de variantes y valida sus reglas."""

    root = Path(root_path).expanduser()
    root_key = canonical_path(root)
    if root_key not in globals.LOADED_SOURCES:
        globals.LOADED_SOURCES[root_key] = "root"

    for variant in tuple(globals.ASM_VARIANTS.values()):
        _load_variant(
            variant,
            root,
            source_provider=source_provider,
            project_root=project_root,
            backend=backend,
            parser=parser,
        )
    validate_variant_rules()


def enter_variant(
    name: str,
    source_path: str | Path,
    token_position: int,
    return_rule: str | None = None,
) -> globals.VariantFrame:
    """Abre un frame de variante conservando el contexto global."""

    try:
        variant = globals.ASM_VARIANTS[name]
    except KeyError as exc:
        raise KeyError(f"Variante ISA desconocida: {name}") from exc
    frame = globals.VariantFrame(
        variant=variant,
        source_path=canonical_path(source_path),
        return_rule=return_rule,
        token_position=token_position,
    )
    globals.VARIANT_STACK.append(frame)
    return frame


def exit_variant(expected: str | None = None) -> globals.VariantFrame:
    """Cierra el frame actual y comprueba opcionalmente su nombre."""

    if not globals.VARIANT_STACK:
        raise RuntimeError("No hay una variante activa para cerrar.")
    frame = globals.VARIANT_STACK.pop()
    if expected is not None and frame.variant.name != expected:
        raise RuntimeError(
            f"Se intentó cerrar '{expected}', pero la variante activa es "
            f"'{frame.variant.name}'."
        )
    return frame


def current_variant() -> globals.VariantFrame | None:
    """Devuelve el frame activo sin modificar el stack."""

    return globals.VARIANT_STACK[-1] if globals.VARIANT_STACK else None


__all__ = [
    "canonical_path",
    "resolve_variant",
    "load_variants",
    "validate_variant_rules",
    "enter_variant",
    "exit_variant",
    "current_variant",
]
