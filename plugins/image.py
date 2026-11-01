"""Deterministic local image-to-RGBA conversion."""

from __future__ import annotations

from pathlib import Path

from .paths import PluginError, local_file, output_limit


SUPPORTED_IMAGE_FORMATS = frozenset({"RGB888", "RGBA8888"})


def convert_image(source: str | Path, pixel_format: str = "RGBA8888") -> bytes:
    """Decode one local image to canonical, row-major RGB/RGBA bytes."""

    path = local_file(source, "convert_image")
    normalized_format = str(pixel_format).upper()
    modes = {"RGB888": "RGB", "RGBA8888": "RGBA"}
    if normalized_format not in modes:
        raise PluginError(
            "convert_image solo admite los tipos de dato RGB888 y RGBA8888."
        )
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:
        raise PluginError(
            "convert_image requiere Pillow; instala el plugin con `vnma install pillow`."
        ) from exc

    try:
        with Image.open(path) as image:
            width, height = image.size
            if width <= 0 or height <= 0:
                raise PluginError("convert_image recibió una imagen sin dimensiones.")
            channels = 3 if normalized_format == "RGB888" else 4
            expected = width * height * channels
            if expected > output_limit():
                raise PluginError("convert_image excede el límite de salida permitido.")
            mode = modes[normalized_format]
            data = image.convert(mode).tobytes("raw", mode)
    except PluginError:
        raise
    except (OSError, UnidentifiedImageError) as exc:
        raise PluginError(f"convert_image no pudo decodificar {path.name}.") from exc

    if len(data) != expected:
        raise PluginError("convert_image produjo una cantidad de bytes inesperada.")
    return data


__all__ = ["SUPPORTED_IMAGE_FORMATS", "convert_image"]
