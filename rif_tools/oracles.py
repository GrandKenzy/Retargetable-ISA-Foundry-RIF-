"""Optional external encoders used as verification oracles.

The tools are deliberately discovered at runtime.  RIF can compile without
NASM, LLVM MC, or Clang installed; callers get an explicit unavailable result
or ``OracleUnavailable`` instead of a hidden dependency or an unbounded
process.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


ORACLE_TIMEOUT_SECONDS = 10
MAX_ORACLE_OUTPUT = 1 << 20
_ENCODING_RE = re.compile(r"encoding:\s*\[([^]]*)\]", re.IGNORECASE)
_BYTE_RE = re.compile(r"0x([0-9a-fA-F]{1,2})|\b([0-9a-fA-F]{2})\b")


class OracleError(RuntimeError):
    """An external oracle failed or returned data that cannot be trusted."""


class OracleUnavailable(OracleError):
    """The optional external assembler is not installed."""


class OracleMismatch(OracleError):
    """The oracle bytes differ from the RIF-produced bytes."""


@dataclass(frozen=True)
class OracleResult:
    tool: str
    command: tuple[str, ...]
    data: bytes
    stdout: str = ""
    stderr: str = ""


def tool_path(name: str) -> str | None:
    """Return an executable path without invoking it."""

    return shutil.which(name)


def oracle_status() -> dict[str, str | None]:
    return {
        name: tool_path(name)
        for name in ("nasm", "llvm-mc", "clang", "llvm-objcopy")
    }


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=ORACLE_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise OracleError(f"El oráculo excedió {ORACLE_TIMEOUT_SECONDS} segundos.") from exc
    if len(completed.stdout.encode(errors="replace")) > MAX_ORACLE_OUTPUT or len(completed.stderr.encode(errors="replace")) > MAX_ORACLE_OUTPUT:
        raise OracleError("La salida del oráculo excede el límite permitido.")
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip() or "sin diagnóstico"
        raise OracleError(f"El oráculo terminó con código {completed.returncode}: {detail}")
    return completed


def assemble_nasm(source: str, *, bits: int = 64) -> OracleResult:
    """Assemble NASM source as flat binary for one architecture width."""

    executable = tool_path("nasm")
    if executable is None:
        raise OracleUnavailable("NASM no está instalado.")
    if bits not in {16, 32, 64}:
        raise ValueError("NASM solo admite bits 16, 32 o 64 en este helper.")
    with tempfile.TemporaryDirectory(prefix="rif-oracle-") as temporary:
        root = Path(temporary)
        source_path = root / "input.asm"
        output_path = root / "output.bin"
        source_path.write_text(f"bits {bits}\n{source}", encoding="utf-8", newline="\n")
        command = [executable, "-f", "bin", str(source_path), "-o", str(output_path)]
        completed = _run(command, cwd=root)
        data = output_path.read_bytes()
        return OracleResult("nasm", tuple(command), data, completed.stdout, completed.stderr)


def _parse_llvm_encoding(stdout: str) -> bytes:
    encoded: list[int] = []
    for match in _ENCODING_RE.finditer(stdout):
        text = match.group(1)
        for token in text.split(","):
            token = token.strip()
            byte_match = _BYTE_RE.fullmatch(token)
            if byte_match is None:
                raise OracleError(f"LLVM MC devolvió un byte inválido: {token!r}")
            value = byte_match.group(1) or byte_match.group(2)
            assert value is not None
            encoded.append(int(value, 16))
    if not encoded:
        raise OracleError("LLVM MC no devolvió una línea # encoding.")
    return bytes(encoded)


def assemble_llvm_mc(
    source: str,
    *,
    triple: str = "x86_64-unknown-none",
    syntax: str = "att",
) -> OracleResult:
    """Encode LLVM MC source using its ``# encoding`` output."""

    executable = tool_path("llvm-mc")
    if executable is None:
        raise OracleUnavailable("LLVM MC no está instalado.")
    if syntax not in {"att", "intel"}:
        raise ValueError("syntax debe ser 'att' o 'intel'.")
    command = [executable, f"-triple={triple}", "-show-encoding", f"-x86-asm-syntax={syntax}"]
    completed = _run(command, input_text=source)
    return OracleResult("llvm-mc", tuple(command), _parse_llvm_encoding(completed.stdout), completed.stdout, completed.stderr)


def assemble_llvm_ias(
    source: str,
    *,
    triple: str = "x86_64-unknown-none-elf",
    syntax: str = "intel",
) -> OracleResult:
    """Assemble through LLVM's integrated assembler and extract ``.text``.

    This is a bounded fallback for environments that ship Clang and
    ``llvm-objcopy`` but not the standalone ``llvm-mc`` executable.  It uses
    the same LLVM instruction encoder; the object container is only a
    transport and is never exposed as a RIF output.
    """

    compiler = tool_path("clang")
    objcopy = tool_path("llvm-objcopy")
    if compiler is None or objcopy is None:
        raise OracleUnavailable(
            "El oráculo LLVM integrado requiere clang y llvm-objcopy."
        )
    if syntax not in {"att", "intel"}:
        raise ValueError("syntax debe ser 'att' o 'intel'.")
    with tempfile.TemporaryDirectory(prefix="rif-llvm-ias-") as temporary:
        root = Path(temporary)
        source_path = root / "input.s"
        object_path = root / "output.o"
        section_path = root / "text.bin"
        prefix = ".intel_syntax noprefix\n" if syntax == "intel" else ""
        source_path.write_text(prefix + ".text\n" + source, encoding="utf-8", newline="\n")
        assemble_command = [
            compiler,
            "-target",
            triple,
            "-c",
            "-x",
            "assembler",
            "-integrated-as",
            str(source_path),
            "-o",
            str(object_path),
        ]
        assembled = _run(assemble_command, cwd=root)
        extract_command = [
            objcopy,
            "--dump-section",
            f".text={section_path}",
            str(object_path),
        ]
        extracted = _run(extract_command, cwd=root)
        return OracleResult(
            "llvm-integrated-as",
            tuple(assemble_command + ["--", *extract_command]),
            section_path.read_bytes(),
            assembled.stdout + extracted.stdout,
            assembled.stderr + extracted.stderr,
        )


def compare_bytes(expected: bytes, actual: OracleResult, *, label: str = "oráculo") -> None:
    """Raise a bounded diagnostic when an oracle and RIF disagree."""

    if expected != actual.data:
        limit = min(len(expected), len(actual.data))
        first = next((index for index in range(limit) if expected[index] != actual.data[index]), limit)
        raise OracleMismatch(
            f"{label}: bytes distintos (esperado={expected.hex()}, "
            f"obtenido={actual.data.hex()}, primer_offset={first})."
        )


__all__ = [
    "MAX_ORACLE_OUTPUT",
    "ORACLE_TIMEOUT_SECONDS",
    "OracleError",
    "OracleMismatch",
    "OracleResult",
    "OracleUnavailable",
    "assemble_llvm_mc",
    "assemble_llvm_ias",
    "assemble_nasm",
    "compare_bytes",
    "oracle_status",
    "tool_path",
]
