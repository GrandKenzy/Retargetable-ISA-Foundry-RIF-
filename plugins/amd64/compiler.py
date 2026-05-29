"""AMD64 precompile hook.

The core compiler exposes the parsed Program through Operators.program before
compilation. This hook keeps architecture/platform defaults out of the core.
"""

from __future__ import annotations

from rif import HeaderBlock, Operators


WINDOWS_HEADERS = (
    ("IMAGE_DOS_HEADER", 64, "", "00000000"),
    ("DOS_STUB", 64, "", "00000000"),
    ("PE_SIGNATURE", 4, "50 45 00 00", ""),
    ("IMAGE_FILE_HEADER", 20, "", "00000000"),
    ("IMAGE_OPTIONAL_HEAD64", 240, "", "00000000"),
    ("SECTION_HEADERS", "*", "", "00000000"),
    ("HEADERS_PADDING", "*", "", "00000000"),
)


def _is_windows(value) -> bool:
    if isinstance(value, int):
        return value == 1
    return str(value).strip().lower() in {"1", "windows", "win", "pe"}


def _start():
    program = Operators.program
    if program is None:
        return 0

    if "endianness" not in program.world.values and "endianess" in program.world.values:
        program.world.values["endianness"] = program.world.values["endianess"]

    if not _is_windows(program.world.values.get("os", 0)):
        program.world.values.setdefault("os", 0)
        return 0

    program.world.values["os"] = 1
    program.world.values.setdefault("endianness", "little")

    if program.headers.blocks:
        return 0

    for name, size, hex_value, fill in WINDOWS_HEADERS:
        program.headers.add(HeaderBlock(name=name, size=size, hex=hex_value, fill=fill))

    return 0


def resolve_link_value(program, op, args, context):
    if op != "link:voffset" or not args or args[0] != "amd64:entry":
        return None

    linker = context.get("linker")
    if linker is None:
        return None

    block = linker._block_for(".text", context) or linker._block_for("text", context)
    if block is None:
        return 0
    return block.virtual_offset
