from __future__ import annotations

import sys
import re
from pathlib import Path

from .compiler import compile_file
from .errors import CompileError


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        print("usage: python pack_compiler.py input.pack [output.txt]", file=sys.stderr)
        return 2
    input_path = argv[1]

    path = Path(input_path)
    filename = path.name
    is_unpacked = re.match(r"^unpacked[._-]([^.]+)\.pack$", filename, re.IGNORECASE)

    if is_unpacked:
        try:
            from .packer import pack_architecture
            packed_path = pack_architecture(input_path)
            input_path = str(packed_path)
        except Exception as exc:
            print(f"error during packing: {exc}", file=sys.stderr)
            return 1

    output_path = argv[2] if len(argv) == 3 else str(Path(input_path).with_suffix(".txt"))
    try:
        compile_file(input_path, output_path)
        return 0
    except CompileError as exc:
        path = Path(output_path)
        if path.exists():
            path.unlink()
        print(f"error: {exc}", file=sys.stderr)
        return 1


def run() -> None:
    raise SystemExit(main(sys.argv))
