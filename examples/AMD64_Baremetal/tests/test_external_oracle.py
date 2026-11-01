"""Cross-check representative RIF encodings with LLVM's external assembler.

This is intentionally a differential smoke suite, not a second AMD64
assembler.  The exhaustive raw-byte coverage remains in ``test_encoding.py``;
this suite checks that independent LLVM encoding agrees across every family
declared by the current bare-metal profile.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


BASE = Path(__file__).resolve().parents[1]


CASES = (
    # Widths, register extensions and immediate forms.
    ("mov8hri bh, 127", "mov bh, 127"),
    ("mov8ri r15b, 255", "mov r15b, 255"),
    ("imul16rr r15w, ax", "imul r15w, ax"),
    ("mov16ri r8w, 4660", "mov r8w, 4660"),
    ("imul32rr r15d, eax", "imul r15d, eax"),
    ("mov32imm r8d, 305419896", "mov r8d, 305419896"),
    ("add32ri8 r15d, -1", "add r15d, -1"),
    ("imulrr r10, r11", "imul r10, r11"),
    ("addri8 r15, -1", "add r15, -1"),
    ("cmpri r10, -2147483648", "cmp r10, -2147483648"),
    ("movabs r10, 1234605616436508552", "mov r10, 1234605616436508552"),
    # Memory forms with bases that force the same SIB/displacement choice in
    # both encoders.
    ("load64_0 rax, rsp", "mov rax, qword ptr [rsp]"),
    ("store64_0 r12, rsp", "mov qword ptr [rsp], r12"),
    ("load64_0 rax, r12", "mov rax, qword ptr [r12]"),
    ("load64_8 r8, r12, -8", "mov r8, qword ptr [r12 - 8]"),
    ("store64_8 r15, r12, 127", "mov qword ptr [r12 + 127], r15"),
    ("load64 rax, rsp, 256", "mov rax, qword ptr [rsp + 256]"),
    ("loadx64_0 rax, rbx, rcx, 2", "mov rax, qword ptr [rbx + rcx*2]"),
    ("storex64_0bp r9, rbp, r12, 8", "mov qword ptr [rbp + r12*8], r9"),
    ("leax64_8 r15, r13, r14, 4, -128", "lea r15, [r13 + r14*4 - 128]"),
    (
        "loadx64 r8, r12, r9, 8, 256",
        "mov r8, qword ptr [r12 + r9*8 + 256]",
    ),
    # Integer operations and bit manipulation.
    ("not64 rax", "not rax"),
    ("neg64 r15", "neg r15"),
    ("not32 r8d", "not r8d"),
    ("neg32 r8d", "neg r8d"),
    ("mul64 rdx", "mul rdx"),
    ("idiv64 r15", "idiv r15"),
    ("div32 r8d", "div r8d"),
    ("shl64r rax, cl", "shl rax, cl"),
    ("shr64r r15, cl", "shr r15, cl"),
    ("sar32r r8d, cl", "sar r8d, cl"),
    ("shl32i r15d, 2", "shl r15d, 2"),
    ("sar32i r8d, 31", "sar r8d, 31"),
    ("bt64rr rax, rcx", "bt rax, rcx"),
    ("bts64rr r8, r15", "bts r8, r15"),
    ("btr64ri r10, 5", "btr r10, 5"),
    ("btc64ri r10, 5", "btc r10, 5"),
    ("bsf64 r15, rax", "bsf r15, rax"),
    ("bsr64 r8, r9", "bsr r8, r9"),
    ("popcnt64 r10, r11", "popcnt r10, r11"),
    ("popcnt32 r8d, r9d", "popcnt r8d, r9d"),
    ("bswap64 r12", "bswap r12"),
    ("bswap32 r9d", "bswap r9d"),
    # Address-size, locking, repetition and segment prefixes.
    ("load64_67 rax, esp, 256", "mov rax, qword ptr [esp + 256]"),
    ("store64_67 r8, r12d, 256", "mov qword ptr [r12d + 256], r8"),
    ("lock_add64 r10, rsp, 256", "lock add qword ptr [rsp + 256], r10"),
    ("lock_inc64 rsp, 256", "lock inc qword ptr [rsp + 256]"),
    ("rep_movsb", "rep movsb"),
    ("rep_movsq", "rep movsq"),
    ("rep_stosb", "rep stosb"),
    ("rep_stosq", "rep stosq"),
    ("fs_load64 rax, rsp, 256", "mov rax, qword ptr fs:[rsp + 256]"),
    ("gs_store64 r8, r12, 256", "mov qword ptr gs:[r12 + 256], r8"),
    # Indirect control transfer forms.
    ("jmpreg64 r8", "jmp r8"),
    ("callreg64 r15", "call r15"),
    ("jmpmem64_0 r12", "jmp qword ptr [r12]"),
    ("callmem64_0 r12", "call qword ptr [r12]"),
    ("callmem64_8 r12, -128", "call qword ptr [r12 - 128]"),
    ("jmpmem64_8 r12, -128", "jmp qword ptr [r12 - 128]"),
    ("callmem64 r12, 256", "call qword ptr [r12 + 256]"),
)


def check(rif_root: Path) -> None:
    sys.path.insert(0, str(rif_root))
    from MIR.external import compile_mir_source, prepare_target  # noqa: PLC0415
    from rif_tools.oracles import (  # noqa: PLC0415
        OracleUnavailable,
        assemble_llvm_ias,
        compare_bytes,
        oracle_status,
    )

    status = oracle_status()
    if not status.get("llvm-mc") and not status.get("nasm") and not status.get("clang"):
        print("SKIP external oracle: NASM, LLVM MC and Clang are unavailable")
        return
    if not status.get("clang") or not status.get("llvm-objcopy"):
        print("SKIP LLVM integrated oracle: clang/llvm-objcopy unavailable")
        return

    target = prepare_target(BASE / "amd64.pack")
    checked = 0
    for rif_line, assembly in CASES:
        rif_result = compile_mir_source(target, "_start\n" + rif_line + "\n")
        try:
            oracle = assemble_llvm_ias(assembly + "\n")
        except OracleUnavailable as exception:
            print(f"SKIP external oracle: {exception}")
            return
        compare_bytes(rif_result.binary, oracle, label=f"LLVM IA {rif_line}")
        checked += 1
    print(f"OK LLVM integrated assembler cross-check: {checked} encodings")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rif-root", type=Path, required=True)
    args = parser.parse_args()
    check(args.rif_root)
