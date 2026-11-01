"""Shared validation for local-only plugin inputs."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from rif_core.limits import resolve_limits


MAX_PLUGIN_BYTES = 64 << 20


class PluginError(ValueError):
    """A plugin input or conversion result is invalid."""


def local_file(source: str | Path, operation: str) -> Path:
    """Resolve one existing local file and reject URL-like inputs."""

    if isinstance(source, bytes) or not isinstance(source, (str, Path)):
        raise PluginError(f"{operation} requiere una ruta local string o Path.")
    text = str(source)
    if not text.strip() or "\x00" in text:
        raise PluginError(f"{operation} recibió una ruta local inválida.")
    parsed = urlsplit(text)
    windows_drive = len(text) >= 2 and text[0].isalpha() and text[1] == ":"
    if parsed.netloc or "://" in text or (parsed.scheme and not windows_drive):
        raise PluginError(f"{operation} solo acepta rutas locales, no URLs.")

    path = Path(source).expanduser()
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise PluginError(f"{operation} requiere un archivo local: {source!s}.")
        if resolved.stat().st_size > resolve_limits().cap(MAX_PLUGIN_BYTES):
            raise PluginError(f"{operation} excede el límite de entrada permitido.")
    except PluginError:
        raise
    except OSError as exc:
        raise PluginError(f"{operation} no pudo abrir la ruta local: {source!s}.") from exc
    return resolved


def output_limit() -> int:
    return resolve_limits().cap(MAX_PLUGIN_BYTES)


__all__ = ["MAX_PLUGIN_BYTES", "PluginError", "local_file", "output_limit"]
