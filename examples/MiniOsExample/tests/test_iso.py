"""Validate the generated MiniOS ISO-9660/El Torito artifact."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


BASE = Path(__file__).resolve().parents[1]


def check(rif_root: Path) -> None:
    sys.path.insert(0, str(rif_root))
    from iso import validate_bios_iso  # noqa: PLC0415

    image_path = BASE / "build" / "mini_os.iso"
    report = validate_bios_iso(image_path.read_bytes())
    assert report.blocks == 25
    assert report.boot_image_lba == 20
    assert report.boot_image_sectors == 4
    assert report.root_directory_lba == 23
    assert report.root_directory_size == 2048
    print(
        f"OK MiniOS ISO: {len(image_path.read_bytes())} bytes, "
        f"boot LBA {report.boot_image_lba}, root LBA {report.root_directory_lba}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rif-root", type=Path, required=True)
    args = parser.parse_args()
    check(args.rif_root)
