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
    from rif_core.pack import create_pack  # noqa: PLC0415
    from rif_tools.pcpi import load_pcpi_file  # noqa: PLC0415
    from MIR.storage import load_storage_file  # noqa: PLC0415

    assert (BASE / "friendly.riflib").is_file()
    assert not (BASE / "registers.rif").exists()
    assert not (BASE / "rules.rif").exists()

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
            0: bytes.fromhex("1900000000000019"),
            1: bytes.fromhex(
                "2200170000000000001700080000000000087e0b0100000000020000010000010100"
            ),
            2: bytes.fromhex("88000000000004001400000000000000"),
        }
    )
    cursor = load_storage_file(BASE / "assets" / "cursor_assets.storage.bin").payload(
        "cursor_arrow_bgrx8888"
    )
    expected_boot_code = bytes.fromhex(
        "fa31c08ed88ed0bc007cfbb8024fbb1801cd1083f84f0f85c201c70600063901"
        "c7060206e50066c7060406e4f60800ba6400eca8017404e460ebf766e8cb0000"
        "00b0a8ee66e8c2000000b0d4ee66e8b9000000b0f4e660eca80174fbe4603cfa"
        "75f5b30166e8b6000000ba640066e8a0000000a80874f3a2080666e893000000"
        "a2090666e88a000000a20a06f6060806c075d730db66e885000000a009069801"
        "060006833e0006007d06c70600060000813e000672027e06c70600067202a00a"
        "0698f7d801060206833e0206007d06c70602060000813e0206ca017e06c70602"
        "06ca01660fb70602066669c0000a0000660fb71e000666c1e3026601d866a304"
        "06b30166e817000000e95effeca80275fb66c3eca80174fba82074f7e46066c3"
        "881e0b06b800a08ec066a1040666a30c06c70610060000c7061206007e66a10c"
        "0689c666c1e810a3140666e86b00000089f78b361206b90e0089f883c0387335"
        "89f8f7d8c1e802a3160689c166e856000000a11606c1e00201c6ff06140666e8"
        "3700000031ffb90e002b0e160666e835000000eb0666e82d00000066a10c0666"
        "05000a000066a30c068306120638ff061006833e100616728466c3b8054f31db"
        "8b161406cd1066c3803e0b0600740566f3a566c36631c066f3ab66c3faf4ebfc"
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
