from __future__ import annotations

import unittest

from rif_tools.oracles import (
    OracleUnavailable,
    assemble_llvm_mc,
    assemble_llvm_ias,
    assemble_nasm,
    compare_bytes,
    oracle_status,
)


class OracleTests(unittest.TestCase):
    def test_oracle_status_is_optional_and_bounded(self) -> None:
        status = oracle_status()
        self.assertIn("nasm", status)
        self.assertIn("llvm-mc", status)

    def test_nasm_nop_when_installed(self) -> None:
        if not oracle_status()["nasm"]:
            self.skipTest("NASM no está instalado")
        result = assemble_nasm("nop")
        compare_bytes(b"\x90", result, label="NASM nop")

    def test_llvm_mc_nop_when_installed(self) -> None:
        if not oracle_status()["llvm-mc"]:
            self.skipTest("LLVM MC no está instalado")
        result = assemble_llvm_mc("nop\n")
        compare_bytes(b"\x90", result, label="LLVM MC nop")

    def test_llvm_integrated_assembler_nop_when_installed(self) -> None:
        status = oracle_status()
        if not status.get("clang") or not status.get("llvm-objcopy"):
            self.skipTest("Clang/llvm-objcopy no están instalados")
        result = assemble_llvm_ias("nop\n")
        compare_bytes(b"\x90", result, label="LLVM integrated assembler nop")


if __name__ == "__main__":
    unittest.main()
