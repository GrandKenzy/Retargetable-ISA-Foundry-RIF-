"""Verify the QEMU-independent Friendly AMD64 syntax."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile


BASE = Path(__file__).resolve().parents[1]
PROBE = BASE.parents[0] / "probe" / "probe_friendlysyntax"

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

    source = (PROBE / "demo.mir").read_text(encoding="utf-8")
    direct_target = prepare_target(BASE / "main.rif")
    assert "framebuffer" not in direct_target.program.context.blocks
    assert "framebuffer_registers" not in direct_target.program.context.tables
    subregs = direct_target.program.context.tables["subregs"].matrix
    assert subregs[0] == ("SR0", "R0", 32)
    assert subregs[-1] == ("SR15", "R15", 32)
    direct = compile_mir_source(direct_target, source)
    assert direct.binary == EXPECTED, (direct.binary.hex(" "), EXPECTED.hex(" "))

    with tempfile.TemporaryDirectory(prefix="rif-friendly-pack-") as directory:
        package = create_pack(BASE / "main.rif", Path(directory) / "friendly.pack")
        packed_target = prepare_target(package)
        assert "framebuffer" not in packed_target.program.context.blocks
        assert "framebuffer_registers" not in packed_target.program.context.tables
        packed = compile_mir_source(packed_target, source)

    assert packed.binary == EXPECTED
    assert packed.binary == direct.binary

    # Friendly syntax must reject, rather than truncate, signed imm32 and
    # disp32 fields. These are intentionally invalid MIR inputs.
    invalid = (
        "set R0 = 2147483648\n",
        "increase R0, 2147483648\n",
        "load R0, R4, 2147483648\n",
        "store R0, R4, -2147483649\n",
    )
    for program in invalid:
        try:
            compile_mir_source(direct_target, program)
        except Exception:
            pass
        else:
            raise AssertionError(f"friendly input should be rejected: {program!r}")

    entry = compile_mir_source(direct_target, "_start\nnoop\n")
    assert entry.symbols["_start"] == 0
    print(f"OK AMD64 friendly syntax without QEMU dependencies: {len(EXPECTED)} bytes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rif-root", type=Path, required=True)
    args = parser.parse_args()
    check(args.rif_root)
