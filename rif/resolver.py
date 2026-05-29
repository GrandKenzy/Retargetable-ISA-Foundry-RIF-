from __future__ import annotations

"""Módulo de resolución de placeholders del compilador RIF.

Se encarga de evaluar y resolver los marcadores de posición (placeholders)
generados durante la compilación, tales como etiquetas, símbolos diferidos
y referencias relativas de memoria.
"""

from typing import Any

from .errors import PackError
from .models import Placeholder, PlaceholderResolution, Program, ResolvedPlaceholder


class PlaceholderResolver:
    """Resuelve marcadores de posición genéricos en base a etiquetas y símbolos conocidos.

    Esta fase es independiente de la arquitectura. Resuelve nombres que se conocen
    a partir de tablas de símbolos y etiquetas (`symbol`, `label`, `reldis`), y
    evita materializar bytes cuando el marcador no reservó un ancho definido.
    """

    def __init__(self, program: Program, labels: dict[str, int] | None = None):
        self.program = program
        self.labels = labels or {}

    def resolve_all(self, placeholders: list[Placeholder] | tuple[Placeholder, ...]) -> PlaceholderResolution:
        """Resuelve todos los marcadores de posición suministrados."""
        resolved: list[ResolvedPlaceholder] = []
        unresolved: list[Placeholder] = []
        seen_unresolved: set[tuple[Any, ...]] = set()
        seen_resolved: set[tuple[Any, ...]] = set()

        for placeholder in placeholders:
            item = self.resolve_one(placeholder)
            if item is None:
                key = self._placeholder_key(placeholder)
                if key not in seen_unresolved:
                    unresolved.append(placeholder)
                    seen_unresolved.add(key)
                continue

            key = self._placeholder_key(item.placeholder)
            if key not in seen_resolved:
                resolved.append(item)
                seen_resolved.add(key)

        return PlaceholderResolution(tuple(resolved), tuple(unresolved))

    def resolve_one(self, placeholder: Placeholder) -> ResolvedPlaceholder | None:
        """Intenta resolver un único marcador de posición."""
        if placeholder.kind == "label":
            if placeholder.target in self.labels:
                value = self.labels[placeholder.target]
                return ResolvedPlaceholder(placeholder, value, _int_to_bits(value, placeholder.width), "label")
            return None

        if placeholder.kind == "symbol":
            row = self.program.objects.get(placeholder.target)
            if row is not None and row.section == ".data":
                value = row.values.get("addrs", row.name)
                return ResolvedPlaceholder(placeholder, value, _optional_bits(value, placeholder.width), "symbol")
            return None

        if placeholder.kind in {"stack", "heap", "memory"}:
            value = self._address_value(placeholder.target)
            if value is None:
                return None
            return ResolvedPlaceholder(placeholder, value, _optional_bits(value, placeholder.width), placeholder.kind)

        if placeholder.kind == "address":
            value = self._address_value(placeholder.target)
            if value is None or placeholder.width is None:
                return None
            return ResolvedPlaceholder(placeholder, value, _int_to_bits(value, placeholder.width), "address")

        if placeholder.kind == "reldis":
            value = self._address_value(placeholder.target)
            if value is None:
                return None
            return ResolvedPlaceholder(placeholder, value, _optional_bits(value, placeholder.width), "reldis")

        if placeholder.field:
            row = self.program.objects.get(placeholder.target)
            if row is None:
                return None
            value = row.values.get(placeholder.field)
            if value in (None, ""):
                return None
            return ResolvedPlaceholder(
                placeholder,
                value,
                _optional_bits(value, placeholder.width),
                f"field:{placeholder.field}",
            )

        return None

    def _address_value(self, target: str) -> int | None:
        if target in self.labels:
            return self.labels[target]

        row = self.program.objects.get(target)
        if row is None:
            return None

        value = row.values.get("addrs")
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise PackError(f'direccion invalida para "{target}": {value!r}') from exc

    def _placeholder_key(self, placeholder: Placeholder) -> tuple[Any, ...]:
        return (
            placeholder.target,
            placeholder.kind,
            placeholder.field,
            placeholder.rule_name,
            placeholder.line,
            placeholder.width,
        )


def resolve_placeholders(
    program: Program,
    placeholders: list[Placeholder] | tuple[Placeholder, ...],
    labels: dict[str, int] | None = None,
) -> PlaceholderResolution:
    """Función de utilidad global para resolver una lista de marcadores de posición."""
    return PlaceholderResolver(program, labels).resolve_all(placeholders)


def _optional_bits(value: Any, width: int | None) -> str | None:
    if width is None:
        return None
    return _int_to_bits(value, width)


def _int_to_bits(value: Any, width: int | None) -> str | None:
    if width is None:
        return None
    try:
        numeric = int(value)
    except (TypeError, ValueError) as exc:
        raise PackError(f"placeholder no numerico no puede emitirse con ancho {width}: {value!r}") from exc
    if numeric < 0:
        raise PackError("placeholder negativo no puede emitirse como bits")
    if numeric >= (1 << width):
        raise PackError(f"placeholder {numeric} no cabe en {width} bits")
    return format(numeric, f"0{width}b")
