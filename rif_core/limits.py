"""Process-wide resource limits shared by the RIF CLI and library layers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from threading import RLock


MIB = 1 << 20
ENV_KEY = "RIF_PLIMIT_MIB"
COMPILATION_LOCK = RLock()


@dataclass(frozen=True)
class ResourceLimits:
    """Optional per-operation byte budget selected for one RIF invocation."""

    bytes: int | None = None

    def cap(self, default: int) -> int:
        if self.bytes is None:
            return default
        return min(default, self.bytes)


def _env_value(path: Path = Path(".env")) -> str | None:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            if key.strip() == ENV_KEY:
                return value.strip().strip("\"'")
    except OSError:
        return None
    return None


def parse_mib(value: object) -> int:
    try:
        mib = int(str(value), 10)
    except (TypeError, ValueError) as exc:
        raise ValueError("--plimit debe ser un entero positivo en MiB.") from exc
    if mib <= 0:
        raise ValueError("--plimit debe ser un entero positivo en MiB.")
    return mib


def resolve_limits(cli_value: int | None = None, env_path: str | Path = ".env") -> ResourceLimits:
    raw = (
        str(cli_value)
        if cli_value is not None
        else os.environ.get(ENV_KEY) or _env_value(Path(env_path))
    )
    return ResourceLimits(None if not raw else parse_mib(raw) * MIB)


def write_mib(value: int, env_path: str | Path = ".env") -> None:
    mib = parse_mib(value)
    path = Path(env_path)
    lines: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise OSError(f"No se pudo leer {path}: {exc}") from exc

    replaced = False
    output: list[str] = []
    for line in lines:
        if line.strip().startswith(f"{ENV_KEY}="):
            if not replaced:
                output.append(f"{ENV_KEY}={mib}")
                replaced = True
            continue
        output.append(line)
    if not replaced:
        output.append(f"{ENV_KEY}={mib}")
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


__all__ = [
    "COMPILATION_LOCK",
    "ENV_KEY",
    "MIB",
    "ResourceLimits",
    "parse_mib",
    "resolve_limits",
    "write_mib",
]
