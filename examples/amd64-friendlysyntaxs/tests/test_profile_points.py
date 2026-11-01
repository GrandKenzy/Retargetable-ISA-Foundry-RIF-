"""Focused coverage for AMD64 bare-metal profile points 1 through 5.

The expected bytes are written independently of the target's RIF tables.  The
test only checks raw bytes; it never executes them on the host.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


BASE = Path(__file__).resolve().parents[1]


def check(rif_root: Path) -> None:
    sys.path.insert(0, str(rif_root))
    from MIR.external import compile_mir_source, prepare_target  # noqa: PLC0415

    target = prepare_target(BASE / "amd64.pack")
    cases: list[tuple[str, bytes, str]] = [
        # 8-bit registers, including REX-only low bytes and legacy high bytes.
        ("mov8rr al, r8b", bytes.fromhex("41 8a c0"), "width8-reg"),
        ("add8rr r9b, spl", bytes.fromhex("44 02 cc"), "width8-reg"),
        ("and8rr r8b, bl", bytes.fromhex("44 22 c3"), "width8-reg"),
        ("test8hrr ah, ch", bytes.fromhex("84 e5"), "width8-high-reg"),
        ("mov8hrr ah, bh", bytes.fromhex("8a e7"), "width8-high-reg"),
        ("mov8hri bh, 127", bytes.fromhex("b7 7f"), "width8-imm"),
        ("mov8ri r15b, 255", bytes.fromhex("41 b7 ff"), "width8-imm"),
        ("add8ri spl, 255", bytes.fromhex("40 80 c4 ff"), "width8-imm8"),
        # 16-bit register and immediate forms, including 0x66 and REX.B/R.
        ("mov16rr ax, r15w", bytes.fromhex("66 41 8b c7"), "width16-reg"),
        ("add16rr r8w, bx", bytes.fromhex("66 44 03 c3"), "width16-reg"),
        ("and16rr r8w, bx", bytes.fromhex("66 44 23 c3"), "width16-reg"),
        ("imul16rr r15w, ax", bytes.fromhex("66 44 0f af f8"), "width16-reg"),
        ("test16rr bp, di", bytes.fromhex("66 40 85 ef"), "width16-reg"),
        ("mov16ri r8w, 4660", bytes.fromhex("66 41 b8 34 12"), "width16-imm"),
        ("add16ri8 ax, -128", bytes.fromhex("66 40 83 c0 80"), "width16-imm8"),
        ("cmp16ri bx, 65535", bytes.fromhex("66 40 81 fb ff ff"), "width16-imm16"),
        # 32-bit register, imm8 and imm32 forms.
        ("and32rr r8d, r15d", bytes.fromhex("45 23 c7"), "width32-reg"),
        ("imul32rr r15d, eax", bytes.fromhex("44 0f af f8"), "width32-reg"),
        ("mov32imm r8d, 305419896", bytes.fromhex("41 b8 78 56 34 12"), "width32-imm32"),
        ("add32ri8 r15d, -1", bytes.fromhex("41 83 c7 ff"), "width32-imm8"),
        ("cmp32ri eax, 4294967295", bytes.fromhex("40 81 f8 ff ff ff ff"), "width32-imm32"),
        # 64-bit signed imm8/imm32 and full-width imm64.
        ("addri8 r15, -1", bytes.fromhex("49 83 c7 ff"), "width64-imm8"),
        ("cmpri rax, -2147483648", bytes.fromhex("48 81 f8 00 00 00 80"), "width64-imm32"),
        (
            "movabs r10, 1234605616436508552",
            bytes.fromhex("49 ba 88 77 66 55 44 33 22 11"),
            "width64-imm64",
        ),
        # Base addressing: no displacement, signed disp8, and disp32.
        ("load64_0 rax, rbx", bytes.fromhex("48 8b 04 23"), "memory-no-disp"),
        ("store64_0 r12, rsp", bytes.fromhex("4c 89 24 24"), "memory-no-disp"),
        ("load64_0 rax, r12", bytes.fromhex("49 8b 04 24"), "memory-no-disp"),
        ("lea64_0bp r8, rbp", bytes.fromhex("4c 8d 44 25 00"), "memory-zero-disp"),
        ("load64_0bp rax, r13", bytes.fromhex("49 8b 44 25 00"), "memory-zero-disp"),
        ("load64_8 r8, r13, -8", bytes.fromhex("4d 8b 44 25 f8"), "memory-disp8"),
        ("store64_8 r15, r12, 127", bytes.fromhex("4d 89 7c 24 7f"), "memory-disp8"),
        ("load64 rax, rbp, 256", bytes.fromhex("48 8b 84 25 00 01 00 00"), "memory-disp32"),
        # Indexed SIB forms use all scale classes and the special rbp/r13 case.
        ("loadx64_0 rax, rbx, rcx, 2", bytes.fromhex("48 8b 04 4b"), "indexed-no-disp"),
        ("storex64_0bp r9, rbp, r12, 8", bytes.fromhex("4e 89 4c e5 00"), "indexed-zero-disp"),
        ("leax64_8 r15, r13, r14, 4, -128", bytes.fromhex("4f 8d 7c b5 80"), "indexed-disp8"),
        (
            "loadx64 r8, r12, r9, 8, 256",
            bytes.fromhex("4f 8b 84 cc 00 01 00 00"),
            "indexed-disp32",
        ),
        # Direct short and long branches.
        ("jmp8 -128", bytes.fromhex("eb 80"), "branch-short"),
        ("jcc8 e, -128", bytes.fromhex("74 80"), "branch-short"),
        ("jmp32 -2147483648", bytes.fromhex("e9 00 00 00 80"), "branch-long"),
        ("jcc32 g, -2147483648", bytes.fromhex("0f 8f 00 00 00 80"), "branch-long"),
        # Indirect register and memory branches.
        ("jmpreg64 r8", bytes.fromhex("41 ff e0"), "branch-indirect-reg"),
        ("callreg64 r15", bytes.fromhex("41 ff d7"), "branch-indirect-reg"),
        ("jmpmem64_0 rax", bytes.fromhex("40 ff 24 20"), "branch-indirect-mem"),
        ("callmem64_0bp rbp", bytes.fromhex("40 ff 54 25 00"), "branch-indirect-mem"),
        ("jmpmem64_8 r12, -128", bytes.fromhex("41 ff 64 24 80"), "branch-indirect-mem"),
        ("callmem64 rbp, 256", bytes.fromhex("40 ff 94 25 00 01 00 00"), "branch-indirect-mem"),
    ]

    lines = ["_start"] + [line for line, _, _ in cases]
    expected = b"".join(data for _, data, _ in cases)
    try:
        result = compile_mir_source(target, "\n".join(lines) + "\n")
    except Exception as exception:
        # Keep the failing MIR line visible when a new Rule consumes the wrong
        # token; the aggregate assertion alone is otherwise hard to diagnose.
        for line, _, _ in cases:
            try:
                compile_mir_source(target, "_start\n" + line + "\n")
            except Exception as line_exception:
                raise AssertionError(f"failing profile case: {line}") from line_exception
        raise exception
    if result.binary != expected:
        first = next(
            (index for index, (actual, wanted) in enumerate(zip(result.binary, expected)) if actual != wanted),
            min(len(result.binary), len(expected)),
        )
        raise AssertionError(
            "AMD64 profile mismatch at byte "
            f"{first}: actual={result.binary[first:first + 8].hex(' ')} "
            f"expected={expected[first:first + 8].hex(' ')}"
        )

    counts: dict[str, int] = {}
    for _, _, family in cases:
        counts[family] = counts.get(family, 0) + 1

    # Exercise every condition code with both opcode families.  This catches
    # accidental reuse of the near opcode for short branches.
    conditions = "o no b ae e ne be a s ns p np l ge le g".split()
    branch_lines = ["_start"]
    branch_expected = bytearray()
    for index, condition in enumerate(conditions):
        branch_lines.extend((f"jcc8 {condition}, 0", f"jcc32 {condition}, 0"))
        branch_expected.extend((0x70 + index, 0, 0x0f, 0x80 + index, 0, 0, 0, 0))
    branches = compile_mir_source(target, "\n".join(branch_lines) + "\n")
    assert branches.binary == bytes(branch_expected)

    # Ensure the 32-bit displacement branch is actually signed, not merely
    # an unsigned 32-bit field that happens to accept positive test values.
    assert compile_mir_source(target, "_start\njmp32 -1\n").binary == bytes.fromhex("e9 ff ff ff ff")

    print(f"OK AMD64 profile points 1-5: {len(cases)} focused encodings")
    for family, count in counts.items():
        print(f"  {family}: {count}")
    print("  branch-conditions: 16 short + 16 long")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rif-root", type=Path, required=True)
    args = parser.parse_args()
    check(args.rif_root)
