"""Target-extensible relocation specifications."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from Frontend import globals
from .operations import OperationError, execute_operation


@dataclass(frozen=True)
class RelocationSpec:
    """A target-neutral relocation calculation declared by name."""

    name: str
    width_bits: int
    mode: str

    @property
    def relative(self) -> bool:
        return self.mode == "pc"

    def encode(self, value: int) -> int:
        try:
            return execute_operation(
                "encode_relocation", value, self.width_bits, "pc" if self.relative else "abs"
            )
        except OperationError as exc:
            raise ValueError(f"{self.name}: {exc}") from exc


_BUILTINS: Mapping[str, RelocationSpec] = {
    **{
        f"pc{width}": RelocationSpec(f"pc{width}", width, "pc")
        for width in (8, 16, 32, 64)
    },
    **{
        f"abs{width}": RelocationSpec(f"abs{width}", width, "abs")
        for width in (8, 16, 32, 64)
    },
}


def _block_value(entry: globals.BlockEntryData, index: int) -> object:
    try:
        return entry.values[index].value
    except IndexError as exc:
        raise ValueError(
            f"La relocación '{entry.name}' requiere ancho y modo."
        ) from exc


def relocation_specs(context: globals.TargetContext) -> dict[str, RelocationSpec]:
    """Return built-ins plus declarations from ``@block relocations``.

    Each generic block line is ``name width mode``. ``mode`` is ``pc`` for a
    signed displacement from the next virtual instruction byte, or ``abs``
    for an unsigned absolute virtual address. The declaration is deliberately
    independent of any ISA.
    """

    specs = dict(_BUILTINS)
    for block in context.blocks.get("relocations", ()):
        for entry in block.entries:
            if len(entry.values) != 2:
                raise ValueError(
                    f"La relocación '{entry.name}' requiere ancho y modo."
                )
            width = _block_value(entry, 0)
            mode = str(_block_value(entry, 1)).casefold()
            if isinstance(width, bool) or not isinstance(width, int):
                raise ValueError(
                    f"El ancho de la relocación '{entry.name}' debe ser entero."
                )
            if width <= 0 or width % 8:
                raise ValueError(
                    f"El ancho de la relocación '{entry.name}' debe ser positivo y múltiplo de ocho."
                )
            if mode in {"relative", "pcrel", "pc"}:
                mode = "pc"
            elif mode in {"absolute", "abs"}:
                mode = "abs"
            else:
                raise ValueError(
                    f"El modo de la relocación '{entry.name}' debe ser pc o abs."
                )
            name = entry.name
            if not name or name in specs:
                raise ValueError(f"La relocación '{name}' está duplicada.")
            specs[name] = RelocationSpec(name, width, mode)
    return specs


def relocation_spec(context: globals.TargetContext, name: str) -> RelocationSpec:
    try:
        return relocation_specs(context)[name]
    except KeyError as exc:
        raise ValueError(f"Clase de relocación desconocida: {name!r}.") from exc


__all__ = ["RelocationSpec", "relocation_spec", "relocation_specs"]
