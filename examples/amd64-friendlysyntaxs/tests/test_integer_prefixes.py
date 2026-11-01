"""Focused checks for the AMD64 profile's integer and prefix extensions."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


BASE = Path(__file__).resolve().parents[1]


def check(rif_root: Path) -> None:
    sys.path.insert(0, str(rif_root))
    from MIR.external import compile_mir_source, prepare_target  # noqa: PLC0415

    target = prepare_target(BASE / "amd64.pack")
    assert "isa_scope" in target.program.context.blocks
    scope = target.program.context.blocks["isa_scope"]
    if isinstance(scope, tuple):
        scope = scope[-1]
    scope_values = {
        entry.name: entry.values[0].value
        for entry in scope.entries
        if entry.values
    }
    assert scope_values["mmx"] == "excluded"
    assert scope_values["sse"] == "excluded"
    assert scope_values["avx"] == "excluded"
    assert scope_values["avx512"] == "excluded"
    assert scope_values["x87"] == "excluded"
    assert scope_values["system"] == "excluded"

    cases: list[tuple[str, bytes, str]] = [
        ("not64 rax", bytes.fromhex("48 f7 d0"), "unary64"),
        ("neg64 r15", bytes.fromhex("49 f7 df"), "unary64"),
        ("inc64 r8", bytes.fromhex("49 ff c0"), "unary64"),
        ("dec64 rbp", bytes.fromhex("48 ff cd"), "unary64"),
        ("mul64 rdx", bytes.fromhex("48 f7 e2"), "muldiv64"),
        ("imul64 r10", bytes.fromhex("49 f7 ea"), "muldiv64"),
        ("div64 rax", bytes.fromhex("48 f7 f0"), "muldiv64"),
        ("idiv64 r15", bytes.fromhex("49 f7 ff"), "muldiv64"),
        ("neg32 r8d", bytes.fromhex("41 f7 d8"), "unary32"),
        ("mul32 eax", bytes.fromhex("40 f7 e0"), "muldiv32"),
        ("idiv32 r15d", bytes.fromhex("41 f7 ff"), "muldiv32"),
        ("inc32 ecx", bytes.fromhex("40 ff c1"), "unary32"),
        ("shl64r rax, cl", bytes.fromhex("48 d3 e0"), "shift-variable"),
        ("sar64r r15, cl", bytes.fromhex("49 d3 ff"), "shift-variable"),
        ("shr32r r8d, cl", bytes.fromhex("41 d3 e8"), "shift-variable"),
        ("shl32i r15d, 1", bytes.fromhex("41 c1 e7 01"), "shift-immediate"),
        ("sar32i eax, 31", bytes.fromhex("40 c1 f8 1f"), "shift-immediate"),
        ("bt64rr rax, rcx", bytes.fromhex("48 0f a3 c8"), "bits"),
        ("bts64rr r8, r15", bytes.fromhex("4d 0f ab f8"), "bits"),
        ("btr64ri r10, 5", bytes.fromhex("49 0f ba f2 05"), "bits-immediate"),
        ("bsf64 r15, rax", bytes.fromhex("4c 0f bc f8"), "bits"),
        ("bsr64 r8, r9", bytes.fromhex("4d 0f bd c1"), "bits"),
        ("popcnt64 r10, r11", bytes.fromhex("f3 4d 0f b8 d3"), "bits"),
        ("bt32rr r8d, r15d", bytes.fromhex("45 0f a3 f8"), "bits"),
        ("bswap64 r12", bytes.fromhex("49 0f cc"), "bits"),
        ("bswap32 r9d", bytes.fromhex("41 0f c9"), "bits"),
        ("load64_67 rax, ebx, 256", bytes.fromhex("67 48 8b 84 23 00 01 00 00"), "address-size"),
        ("store64_67 r8, r12d, -4", bytes.fromhex("67 4d 89 84 24 fc ff ff ff"), "address-size"),
        ("lock_add64 r10, rbp, 16", bytes.fromhex("f0 4c 01 94 25 10 00 00 00"), "lock"),
        ("lock_inc64 rsp, 0", bytes.fromhex("f0 48 ff 84 24 00 00 00 00"), "lock"),
        ("rep_movsb", bytes.fromhex("f3 a4"), "rep"),
        ("rep_movsq", bytes.fromhex("f3 48 a5"), "rep"),
        ("rep_stosb", bytes.fromhex("f3 aa"), "rep"),
        ("rep_stosq", bytes.fromhex("f3 48 ab"), "rep"),
        ("fs_load64 rax, rbp, 8", bytes.fromhex("64 48 8b 84 25 08 00 00 00"), "segment"),
        ("gs_store64 r8, r12, 16", bytes.fromhex("65 4d 89 84 24 10 00 00 00"), "segment"),
    ]

    source = "\n".join(["_start", *(line for line, _, _ in cases)]) + "\n"
    result = compile_mir_source(target, source)
    expected = b"".join(data for _, data, _ in cases)
    assert result.binary == expected, (
        "integer/prefix profile mismatch",
        result.binary.hex(" "),
        expected.hex(" "),
    )

    counts: dict[str, int] = {}
    for _, _, family in cases:
        counts[family] = counts.get(family, 0) + 1
    print(f"OK AMD64 integer/prefix profile: {len(cases)} encodings")
    for family, count in counts.items():
        print(f"  {family}: {count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rif-root", type=Path, required=True)
    args = parser.parse_args()
    check(args.rif_root)
