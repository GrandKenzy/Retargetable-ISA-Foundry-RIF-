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
    from pcpi import load_pcpi_file  # noqa: PLC0415
    from MIR.storage import load_storage_file  # noqa: PLC0415

    source = (BASE / "demo.mir").read_text(encoding="utf-8")
    direct_target = prepare_target(BASE / "main.rif")
    framebuffer = direct_target.program.context.blocks["framebuffer"][0]
    framebuffer_values = {
        entry.name: tuple(value.value for value in entry.values)
        for entry in framebuffer.entries
    }
    assert framebuffer_values["provider"] == ("qemu-std-vga",)
    assert framebuffer_values["protocol"] == ("bochs-vbe",)
    assert framebuffer_values["width"] == (640,)
    assert framebuffer_values["height"] == (480,)
    assert framebuffer_values["bits_per_pixel"] == (32,)
    assert framebuffer_values["cursor_source_format"] == ("RGBA8888",)
    assert framebuffer_values["pixel_format"] == ("BGRX8888",)
    assert framebuffer_values["cursor_format"] == ("BGRX8888",)
    assert framebuffer_values["cursor_asset"] == ("cursor_arrow_bgrx8888",)
    registers = direct_target.program.context.tables["framebuffer_registers"].matrix
    assert registers[0] == ("ID", 0, 16)
    assert registers[4] == ("ENABLE", 4, 16)
    assert registers[-1] == ("Y_OFFSET", 9, 16)
    subregs = direct_target.program.context.tables["subregs"].matrix
    assert subregs[0] == ("SR0", "R0", 32)
    assert subregs[-1] == ("SR15", "R15", 32)
    direct = compile_mir_source(direct_target, source)
    assert direct.binary == EXPECTED, (direct.binary.hex(" "), EXPECTED.hex(" "))

    integrated_source = (BASE / "main.mir").read_text(encoding="utf-8")
    integrated = compile_mir_source(
        direct_target,
        integrated_source,
        name=str(BASE / "main.mir"),
    )
    template = load_pcpi_file(BASE / "assets" / "mini_os_iso_header.pcic")
    expected_payload = template.render(
        {
            0: bytes.fromhex("1500000000000015"),
            1: bytes(32),
            2: bytes(16),
            3: bytes.fromhex("88000000000004001400000000000000"),
        }
    )
    cursor = load_storage_file(BASE / "assets" / "cursor_assets.storage.bin").payload(
        "cursor_arrow_bgrx8888"
    )
    expected_boot_code = bytes.fromhex(
        "fa31c08ed88ed0bc007cfbb8024fbb1801cd10"
        "83f84f7544b8054f31dbba0800cd10b800a08ec0"
        "be007ebfe4f6b90e0066f3a5b8054f31dbba0900"
        "cd10b800a08ec0be387ebfe400bd1500b90e0066"
        "f3a581c7c8094d75f3faf4ebfcfaf4ebfc"
    )
    boot = integrated.binary[len(expected_payload) :]
    assert integrated.binary[: len(expected_payload)] == expected_payload
    assert len(boot) == 2048
    assert boot[: len(expected_boot_code)] == expected_boot_code
    assert boot[len(expected_boot_code) : 510] == bytes(510 - len(expected_boot_code))
    assert boot[510:512] == b"\x55\xaa"
    assert boot[512 : 512 + len(cursor)] == cursor
    assert boot[512 + len(cursor) :] == bytes(304)
    assert integrated.symbols["_start"] == len(expected_payload)

    with tempfile.TemporaryDirectory(prefix="rif-friendly-pack-") as directory:
        package = create_pack(BASE / "main.rif", Path(directory) / "friendly.pack")
        packed_target = prepare_target(package)
        packed_framebuffer = packed_target.program.context.blocks["framebuffer"][0]
        assert packed_framebuffer.name == framebuffer.name
        assert packed_framebuffer.entries == framebuffer.entries
        packed = compile_mir_source(packed_target, source)
        packed_integrated = compile_mir_source(
            packed_target,
            integrated_source,
            name=str(BASE / "main.mir"),
        )

    assert packed.binary == EXPECTED
    assert packed.binary == direct.binary
    assert packed_integrated.binary == integrated.binary

    # Friendly syntax must reject, rather than truncate, signed imm32 and
    # disp32 fields.  These are intentionally invalid MIR inputs.
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
    print(f"OK AMD64 friendly syntax: {len(EXPECTED)} bytes; source == pack")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rif-root", type=Path, required=True)
    args = parser.parse_args()
    check(args.rif_root)
