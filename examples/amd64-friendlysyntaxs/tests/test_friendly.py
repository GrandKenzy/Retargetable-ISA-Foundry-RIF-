"""Verify the friendly AMD64 syntax from source and from a compiled pack."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile


BASE = Path(__file__).resolve().parents[1]

EXPECTED = bytes.fromhex(
    "48 c7 c0 2a 00 00 00 "
    "48 c7 c7 07 00 00 00 "
    "4c 8b c0 "
    "4c 03 c7 "
    "49 81 c0 05 00 00 00 "
    "4c 89 84 24 00 01 00 00 "
    "4c 8b 8c 24 00 01 00 00 "
    "90 c3"
)


def check(rif_root: Path) -> None:
    sys.path.insert(0, str(rif_root))
    from MIR.external import compile_mir_source, prepare_target  # noqa: PLC0415
    from pack import create_pack  # noqa: PLC0415

    source = (BASE / "demo.mir").read_text(encoding="utf-8")
    direct_target = prepare_target(BASE / "main.rif")
    subregs = direct_target.program.context.tables["subregs"].matrix
    assert subregs[0] == ("SR0", "R0", 32)
    assert subregs[-1] == ("SR15", "R15", 32)
    direct = compile_mir_source(direct_target, source)
    assert direct.binary == EXPECTED, (direct.binary.hex(" "), EXPECTED.hex(" "))

    with tempfile.TemporaryDirectory(prefix="rif-friendly-pack-") as directory:
        package = create_pack(BASE / "main.rif", Path(directory) / "friendly.pack")
        packed = compile_mir_source(prepare_target(package), source)

    assert packed.binary == EXPECTED
    assert packed.binary == direct.binary
    print(f"OK AMD64 friendly syntax: {len(EXPECTED)} bytes; source == pack")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rif-root", type=Path, required=True)
    args = parser.parse_args()
    check(args.rif_root)
