"""Build the bootable MiniOS BIOS ISO through the RIF pipeline.

RIF emits the El Torito boot image.  ``iso.py`` then assembles that output
with the PCP-I descriptor template, path tables, a root directory and a small
readme file so the result is a real ISO-9660 image consumable by QEMU.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys

import vendor.__bootstrap__  # From VNMA.

ROOT = Path(__file__).resolve().parents[3]
MINI = ROOT / "examples" / "probe" / "probe_minios"
QEMU = ROOT / "examples" / "probe" / "probe_friendlysyntax_qemu"
BUILD = MINI / "build"


def build(output: str | Path | None = None) -> Path:
    from MIR.external import compile_mir_file  # noqa: PLC0415
    from MIR.storage import load_storage_file  # noqa: PLC0415
    from iso import ISOFile, build_iso_from_pcpi, validate_bios_iso, write_iso  # noqa: PLC0415
    from pack import create_pack  # noqa: PLC0415
    from pcpi import load_pcpi_file  # noqa: PLC0415
    from pcpi_compiler import compile_pcpi_source_file  # noqa: PLC0415
    from store import compile_store_file  # noqa: PLC0415

    BUILD.mkdir(parents=True, exist_ok=True)
    qemu_assets = QEMU / "assets"
    qemu_assets.mkdir(parents=True, exist_ok=True)

    mini_pcic = BUILD / "mini_os_iso_header.pcic"
    qemu_pcic = qemu_assets / "mini_os_iso_header.pcic"
    compile_pcpi_source_file(MINI / "mini_os_iso_header.pci", mini_pcic)
    shutil.copyfile(mini_pcic, qemu_pcic)

    mini_storage = BUILD / "cursor_assets.storage.bin"
    qemu_storage = qemu_assets / "cursor_assets.storage.bin"
    compile_store_file(MINI / "cursor_assets.store", mini_storage)
    shutil.copyfile(mini_storage, qemu_storage)
    storage = load_storage_file(mini_storage)
    cursor = storage.payload("cursor_arrow_bgrx8888")
    if len(cursor) != 14 * 22 * 4:
        raise ValueError("El cursor BGRX no tiene el tamaño esperado.")

    pack_path = QEMU / "friendly-qemu.pack"
    create_pack(QEMU / "main.rif", pack_path)
    rif_output = BUILD / "mini_os_rif_output.bin"
    compilation = compile_mir_file(
        pack_path,
        QEMU / "main.mir",
        output=rif_output,
    )
    template = load_pcpi_file(mini_pcic)
    prefix_size = len(template.padding) + template.image_size + len(template.rpad)
    if len(compilation.binary) <= prefix_size:
        raise ValueError("RIF no emitió un boot image después del PCP-I.")
    boot_image = compilation.binary[prefix_size:]

    readme = (
        b"MiniOS BIOS boot image emitted by RIF.\r\n"
        b"The El Torito boot image initializes QEMU Bochs VBE mode 0x118,\r\n"
        b"draws the bundled 14x22 cursor and polls PS/2 mouse movement.\r\n"
    )
    image = build_iso_from_pcpi(
        template,
        boot_image,
        (ISOFile("README.TXT;1", readme),),
        volume_id="RIF_MINIOS",
    )
    report = validate_bios_iso(image)
    target = Path(output).expanduser().resolve() if output else BUILD / "mini_os.iso"
    write_iso(target, image, protected=(mini_pcic, rif_output, pack_path))
    print(
        f"OK MiniOS ISO: {target} ({len(image)} bytes, {report.blocks} blocks, "
        f"boot LBA {report.boot_image_lba}, {report.boot_image_sectors} sectors)"
    )
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Construye la ISO BIOS de MiniOS con RIF")
    parser.add_argument("-o", "--output", type=Path, help="ruta de la ISO final")
    args = parser.parse_args()
    sys.exit(0 if build(args.output) else 1)
