"""Version contract shared by RIF, its AOT frontend, packs and runtime.

The contract is deliberately small and scalar.  It describes the in-memory
FFI/AOT representation that is canonical for the current toolchain; ZIP and
SQLite are transport/cache formats and must match it before being consumed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, get_type_hints


CONTRACT_VERSION = 2
RIF_VERSION = "1.0.1"
PACK_FORMAT_VERSION = 7
COMPILED_SCHEMA_VERSION = 7
RUNTIME_ABI_VERSION = "1.1"
AOT_CACHE_FORMAT_VERSION = 2
AOT_MODE = "ffi-memory"


class ContractError(ValueError):
    """A serialized artifact does not match the active RIF contract."""


@dataclass(frozen=True)
class CompilationContract:
    """Identity of the producer/consumer ABI for a compiled target."""

    contract_version: int
    rif_version: str
    pack_format_version: int
    compiled_schema_version: int
    runtime_abi_version: str
    gram_version: str
    gir_format: str
    c_parser_abi: str
    aot_mode: str
    compiler_source_fingerprint: str

    def as_dict(self) -> dict[str, Any]:
        return {
            field.name: getattr(self, field.name)
            for field in fields(self)
        }

    @classmethod
    def from_dict(cls, data: Any) -> "CompilationContract":
        if not isinstance(data, dict):
            raise ContractError("El contrato de compilación debe ser un objeto.")
        values: dict[str, Any] = {}
        type_hints = get_type_hints(cls)
        for field in fields(cls):
            value = data.get(field.name)
            if type_hints[field.name] is int:
                valid = isinstance(value, int) and not isinstance(value, bool)
            else:
                valid = isinstance(value, str) and bool(value)
            if not valid:
                raise ContractError(
                    f"El contrato tiene un campo inválido o ausente: {field.name}."
                )
            values[field.name] = value
        return cls(**values)

    def fingerprint(self) -> str:
        encoded = json.dumps(
            self.as_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def mismatches(self, expected: "CompilationContract") -> dict[str, tuple[Any, Any]]:
        return {
            field.name: (getattr(self, field.name), getattr(expected, field.name))
            for field in fields(self)
            if getattr(self, field.name) != getattr(expected, field.name)
        }


def current_contract() -> CompilationContract:
    """Build the active contract from the installed Gram/AOT interfaces."""

    import gram
    from gram.core.parser.c_generator import C_PARSER_ABI_VERSION
    from gram.ir import GIR_VERSION_MAJOR, GIR_VERSION_MINOR

    return CompilationContract(
        contract_version=CONTRACT_VERSION,
        rif_version=RIF_VERSION,
        pack_format_version=PACK_FORMAT_VERSION,
        compiled_schema_version=COMPILED_SCHEMA_VERSION,
        runtime_abi_version=RUNTIME_ABI_VERSION,
        gram_version=str(gram.__version__),
        gir_format=f"{GIR_VERSION_MAJOR}.{GIR_VERSION_MINOR}",
        c_parser_abi=str(C_PARSER_ABI_VERSION),
        aot_mode=AOT_MODE,
        compiler_source_fingerprint=compiler_source_fingerprint(),
    )


def compiler_source_fingerprint() -> str:
    """Hash RIF's production Python sources used to consume artifacts.

    This intentionally excludes tests, examples, vendor projections and the
    generated AOT cache.  A change in the compiler, serializer, pack reader,
    frontend dispatcher or runtime therefore invalidates every derived target
    artifact even when the declarative sources are unchanged.
    """

    root = Path(__file__).resolve().parent
    paths = [
        root / "pack.py",
        root / "main.py",
        root / "rif_tools" / "cli.py",
        root / "rif_contract.py",
        root / "rif_limits.py",
        root / "rif_library.py",
        *sorted((root / "Frontend").rglob("*.py")),
        *sorted((root / "MIR").rglob("*.py")),
    ]
    digest = hashlib.sha256()
    for path in sorted({path.resolve() for path in paths}):
        if not path.is_file():
            continue
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def require_compatible(
    actual: CompilationContract,
    expected: CompilationContract | None = None,
) -> CompilationContract:
    """Reject a stale/incompatible artifact with field-level detail."""

    expected = expected or current_contract()
    mismatches = actual.mismatches(expected)
    if mismatches:
        details = ", ".join(
            f"{name}={value!r} (actual), esperado={wanted!r}"
            for name, (value, wanted) in sorted(mismatches.items())
        )
        raise ContractError(f"Contrato de compilación incompatible: {details}.")
    return actual


__all__ = [
    "AOT_CACHE_FORMAT_VERSION",
    "AOT_MODE",
    "COMPILED_SCHEMA_VERSION",
    "CONTRACT_VERSION",
    "CompilationContract",
    "ContractError",
    "PACK_FORMAT_VERSION",
    "RIF_VERSION",
    "RUNTIME_ABI_VERSION",
    "current_contract",
    "compiler_source_fingerprint",
    "require_compatible",
]
