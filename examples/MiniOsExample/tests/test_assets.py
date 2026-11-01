"""Validate the MiniOS PCP-I and RIF storage artifacts."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess


BASE = Path(__file__).resolve().parents[1]


def check() -> None:
    from pcpi import load_pcpi_file  # noqa: PLC0415
    from MIR.storage import load_storage_file  # noqa: PLC0415

    pcic = load_pcpi_file(BASE / "build" / "mini_os_iso_header.pcic")
    assert pcic.signature == b"MiniOS AMD64 ISO descriptor template"
    assert pcic.image_size == 4 * 2048
    assert len(pcic.padding) == 16 * 2048
    assert tuple(pit.size for pit in pcic.pits) == (8, 34, 16)
    assert max(pit.size for pit in pcic.pits) == 34

    storage = load_storage_file(BASE / "build" / "cursor_assets.storage.bin")
    assert storage.payload("cursor_arrow_rgba8888")
    assert len(storage.payload("cursor_arrow_rgba8888")) == 14 * 22 * 4
    assert storage.payload("cursor_arrow_bgrx8888")
    assert len(storage.payload("cursor_arrow_bgrx8888")) == 14 * 22 * 4

    qemu = shutil.which("qemu-system-x86_64")
    if qemu:
        version = subprocess.run(
            [qemu, "--version"], capture_output=True, text=True, check=False
        )
        assert version.returncode == 0
        print(version.stdout.splitlines()[0])
    else:
        print("SKIP QEMU: qemu-system-x86_64 no está en PATH")
    print("OK MiniOS PCP-I descriptor template and cursor storage")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rif-root", type=Path, required=False)
    parser.parse_args()
    check()
