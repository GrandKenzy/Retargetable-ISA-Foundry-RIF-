"""Optional, target-neutral maps for a completed MIR image."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


OUTPUT_MAP_FORMAT = "RIF_OUTPUT_MAP"
OUTPUT_MAP_VERSION = 1


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _path(value: Path | None) -> str | None:
    return str(value) if value is not None else None


@dataclass(frozen=True)
class OutputMap:
    """Serializable description of one successful MIR compilation."""

    target: dict[str, Any]
    mir: dict[str, Any]
    binary: dict[str, Any]
    sections: tuple[dict[str, Any], ...]
    symbols: tuple[dict[str, Any], ...]
    rules: tuple[dict[str, Any], ...]
    relocations: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": OUTPUT_MAP_FORMAT,
            "format_version": OUTPUT_MAP_VERSION,
            "target": dict(self.target),
            "mir": dict(self.mir),
            "binary": dict(self.binary),
            "sections": [dict(item) for item in self.sections],
            "symbols": [dict(item) for item in self.symbols],
            "rules": [dict(item) for item in self.rules],
            "relocations": [dict(item) for item in self.relocations],
        }

    def json_bytes(self) -> bytes:
        return (
            json.dumps(
                self.as_dict(),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )


def build_output_map(compilation: Any) -> OutputMap:
    """Build a bounded, deterministic map from a finalized MIR result."""

    image = compilation.image
    image.layout()
    sections = tuple(
        {
            "name": section.name,
            "flags": section.flags,
            "alignment": section.alignment,
            "file_offset": section.file_offset,
            "file_size": section.file_size,
            "file_end": section.file_end,
            "virtual_base": section.virtual_base,
            "virtual_size": section.virtual_size,
            "virtual_end": section.virtual_end,
            "initialized_size": section.initialized_size,
            "uninitialized_size": section.uninitialized_size,
        }
        for _, section in sorted(image.sections.items())
    )

    symbols = []
    absolute_symbols = compilation.symbols
    for name, symbol in sorted(compilation.context.symbols.items()):
        section_name = symbol.section or compilation.section
        symbols.append(
            {
                "name": name,
                "section": section_name,
                "physical_offset": symbol.physical_offset,
                "virtual_offset": symbol.virtual_offset,
                "address": absolute_symbols[name],
                "physical_offset_bits": symbol.physical_offset_bits,
                "virtual_offset_bits": symbol.virtual_offset_bits,
            }
        )

    rules = tuple(
        {
            "index": index,
            "name": trace.name,
            "section": trace.section or compilation.section,
            "physical_offset": trace.start,
            "physical_end": trace.end,
            "bits": trace.bits,
            "padding_bits": trace.padding_bits,
            "virtual_offset": trace.virtual_start,
            "virtual_bits": trace.virtual_bits,
            "virtual_end": trace.virtual_end,
            "virtual_padding_bits": trace.virtual_padding_bits,
        }
        for index, trace in enumerate(compilation.context.rule_traces)
    )

    relocations = []
    for index, fixup in enumerate(compilation.context.fixups):
        section_name = fixup.section or compilation.section
        section = image.sections[section_name]
        target_address = absolute_symbols[fixup.symbol]
        next_address = section.virtual_base + fixup.next_virtual_bits // 8
        value = target_address - next_address if fixup.kind.startswith("pc") else target_address
        relocations.append(
            {
                "index": index,
                "kind": fixup.kind,
                "symbol": fixup.symbol,
                "section": section_name,
                "reservation": fixup.reservation,
                "offset_bits": fixup.offset_bits,
                "width_bits": fixup.width_bits,
                "next_virtual_bits": fixup.next_virtual_bits,
                "target_address": target_address,
                "resolved_value": value,
                "resolved": True,
            }
        )

    binary = bytes(compilation.binary)
    return OutputMap(
        target={
            "path": _path(compilation.target_path),
            "contract_fingerprint": compilation.program.contract.fingerprint(),
        },
        mir={
            "path": _path(compilation.mir_path),
            "section": compilation.section,
            "executed_rules": [
                {
                    "index": index,
                    "rule": result.rule,
                    "consumed_tokens": result.position,
                }
                for index, result in enumerate(compilation.executions)
            ],
        },
        binary={
            "size": len(binary),
            "sha256": _sha256(binary),
            "section_size": len(compilation.section_binary),
        },
        sections=sections,
        symbols=tuple(symbols),
        rules=rules,
        relocations=tuple(relocations),
    )


__all__ = [
    "OUTPUT_MAP_FORMAT",
    "OUTPUT_MAP_VERSION",
    "OutputMap",
    "build_output_map",
]
