"""Benchmark reproducible: proyecto RIF en carpeta contra proyecto .pack."""

from __future__ import annotations

import statistics
import tempfile
import time
from pathlib import Path

from Frontend import globals
from MIR import compile_source
from pack import create_pack, read_pack


def reset_globals() -> None:
    globals.STACK = None
    globals.STACK_SIZE = None
    globals.DEFINES.clear()
    globals.TABLES.clear()
    globals.RULES.clear()
    globals.CONFIG = None
    globals.LINKER = None
    globals.SUPPORTS.clear()
    globals.ASM_VARIANTS.clear()
    globals.LOADED_SOURCES.clear()
    globals.ACTIVE_SOURCES.clear()
    globals.VARIANT_STACK.clear()
    globals.SOURCE_PROVIDER = None


def make_project(root: Path, count: int = 32) -> Path:
    project = root / "project"
    nodes = project / "rules"
    nodes.mkdir(parents=True)
    for index in range(count - 1, -1, -1):
        body = f"@rule rule_{index}:\n. NUMBER\n"
        if index + 1 < count:
            body = f'@LOAD "rule_{index + 1:03d}.rif"\n' + body
        (nodes / f"rule_{index:03d}.rif").write_text(body, encoding="utf-8")
    main = project / "main.rif"
    main.write_text('@LOAD "rules/rule_000.rif"\n', encoding="utf-8")
    return main


def measure(label: str, function, rounds: int = 3) -> tuple[str, list[float]]:
    reset_globals()
    function()
    samples: list[float] = []
    for _ in range(rounds):
        reset_globals()
        start = time.perf_counter()
        function()
        samples.append((time.perf_counter() - start) * 1000)
    return label, samples


def main() -> int:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        main_rif = make_project(root)
        package = create_pack(main_rif, root / "target.pack", precompile=True)
        manifest = read_pack(package)

        def compile_folder() -> None:
            compile_source(main_rif)

        def compile_package() -> None:
            compile_source(package)

        _, folder = measure("folder", compile_folder)
        _, packed = measure("pack", compile_package)

        package_start = time.perf_counter()
        create_pack(main_rif, root / "second.pack", precompile=True)
        package_ms = (time.perf_counter() - package_start) * 1000

        print("RIF pack benchmark")
        print(f"sources={len(manifest.files)}")
        print(f"pack_bytes={package.stat().st_size}")
        print(f"folder_compile_ms median={statistics.median(folder):.3f} samples={[round(v, 3) for v in folder]}")
        print(f"pack_compile_ms median={statistics.median(packed):.3f} samples={[round(v, 3) for v in packed]}")
        print(f"pack_create_ms={package_ms:.3f}")
        print(f"pack_vs_folder={statistics.median(packed) / statistics.median(folder):.3f}x")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
