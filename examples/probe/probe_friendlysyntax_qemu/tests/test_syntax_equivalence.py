"""Compare one real program written with normal and friendly syntax."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[4]
NORMAL_TARGET = ROOT / "examples" / "AMD64_Baremetal" / "main.rif"
NORMAL_MIR = ROOT / "examples" / "probe" / "probe_amd64" / "main.mir"
FRIENDLY_TARGET = ROOT / "examples" / "amd64-friendlysyntaxs" / "main.rif"
FRIENDLY_MIR = ROOT / "examples" / "probe" / "probe_friendlysyntax" / "equivalent.mir"
EXPECTED = bytes.fromhex("48 c7 c0 2a 00 00 00 48 c7 c7 07 00 00 00 90")


def check(rif_root: Path) -> None:
    sys.path.insert(0, str(rif_root))
    from MIR.external import compile_mir_source, prepare_target  # noqa: PLC0415
    from rif_core.pack import create_pack  # noqa: PLC0415

    normal_source = NORMAL_MIR.read_text(encoding="utf-8")
    friendly_source = FRIENDLY_MIR.read_text(encoding="utf-8")

    normal_direct = compile_mir_source(
        prepare_target(NORMAL_TARGET), normal_source
    ).binary
    friendly_direct = compile_mir_source(
        prepare_target(FRIENDLY_TARGET), friendly_source
    ).binary

    with tempfile.TemporaryDirectory(prefix="rif-syntax-equivalence-") as directory:
        folder = Path(directory)
        normal_pack = create_pack(NORMAL_TARGET, folder / "normal.pack")
        friendly_pack = create_pack(FRIENDLY_TARGET, folder / "friendly.pack")
        normal_packed = compile_mir_source(
            prepare_target(normal_pack), normal_source
        ).binary
        friendly_packed = compile_mir_source(
            prepare_target(friendly_pack), friendly_source
        ).binary

    assert normal_direct == EXPECTED
    assert friendly_direct == EXPECTED
    assert normal_packed == EXPECTED
    assert friendly_packed == EXPECTED
    assert normal_direct == friendly_direct == normal_packed == friendly_packed
    print("OK normal/friendly syntax equivalence: 15 identical bytes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rif-root", type=Path, required=True)
    args = parser.parse_args()
    check(args.rif_root)
