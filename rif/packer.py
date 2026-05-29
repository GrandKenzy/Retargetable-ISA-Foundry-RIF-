from __future__ import annotations

"""Módulo empaquetador del compilador RIF.

Proporciona envoltorios y utilidades compatibles con versiones anteriores del
sistema de enlazado genérico (Linker) para empaquetar y construir archivos RIF.
"""

from pathlib import Path

from .linker import Linker, build_file, link_file
from .models import BinaryLinkResult, PackedResult


class Packer:
    """Envolvedor compatible con versiones anteriores del enlazador genérico (Linker)."""

    def __init__(self, source_path: str | Path):
        self.source_path = Path(source_path)

    def pack(self, output_path: str | Path | None = None) -> PackedResult:
        """Enlaza el archivo de origen empaquetando todas sus dependencias y secciones."""
        return Linker(self.source_path).link(output_path, write=True)

    def build(self, output_path: str | Path | None = None, source: str = "") -> BinaryLinkResult:
        """Compila un código fuente de ensamblador RIF generando su representación binaria y resolviendo dependencias."""
        return Linker(self.source_path).build_binary(source, output_path, write=output_path is not None)


def pack_file(source_path: str | Path, output_path: str | Path | None = None) -> PackedResult:
    """Función de utilidad para empaquetar un archivo RIF de forma rápida."""
    return link_file(source_path, output_path, write=True)


def build_pack(source_path: str | Path, output_path: str | Path | None = None, source: str = "") -> BinaryLinkResult:
    """Función de utilidad para compilar un código ensamblador en un binario ejecutable."""
    return build_file(source_path, output_path, source, write=output_path is not None)
