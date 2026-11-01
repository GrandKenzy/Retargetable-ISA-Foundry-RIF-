from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from Frontend.aot import AOTError
from MIR import MIRInputError, compile_definition, compile_mir_source
from MIR.artifacts import ArtifactError, evaluate_expression
from MIR.functions import CalcError, calc


TARGET = '''\
@block config:
    format section ".section"
    section text ""
    format section_end ":"
    entry text "_start"
    comment ";"
    format label_end ":"
    default text
    word_size 8
    address_size 64
    byte_order "little"
    case_sensitive true
    symbol_prefix "_"
    local_prefix "."
    undefined_symbols "error"
    duplicate_symbols "error"
    strict true
    allow_empty_sections false
@end

@block linker:
    extension ".asm"
    search_path ""
@end

@rule mov:
. IDENT
. eword 1
'''


class ArtifactSyntaxTests(unittest.TestCase):
    def test_legacy_rif_artifact_blocks_are_not_grammar(self) -> None:
        source = TARGET + '@insert:\n.bytes "aa"\n@end\n'
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "main.rif"
            target.write_text(source, encoding="utf-8")
            with self.assertRaises(AOTError):
                compile_definition(target, backend="aot")

    def test_insert_and_patch_are_assembler_side_directives(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "main.rif"
            target.write_text(TARGET, encoding="utf-8")
            program = compile_definition(target)
            result = compile_mir_source(
                program,
                '::RIF_INSERT BYTES "aa" SECTION text\n'
                '::RIF_PATCH 0, 1, 187\n'
                "mov\n",
                name=str(Path(directory) / "program.asm"),
            )

            self.assertEqual(result.binary, b"\xbb\x01")
            self.assertEqual(result.executions[0].position, 1)
            self.assertFalse(hasattr(result.program, "inserts"))
            self.assertFalse(hasattr(result.program, "before"))

    def test_native_queries_cover_physical_and_virtual_layout(self) -> None:
        source = (
            TARGET.replace('byte_order "little"', 'byte_order "little"\n    vaddr text 4096')
            .replace(
                '@rule mov:\n. IDENT\n. eword 1\n',
                '@rule mov:\n. IDENT\n. eword 5\n',
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "main.rif"
            target.write_text(source, encoding="utf-8")
            program = compile_definition(target)
            result = compile_mir_source(
                program,
                '::RIF_INSERT BYTES "aabbccdd" SECTION text\n'
                '::RIF_PATCH 0, 1, #:qssize(0, "text")\n'
                '::RIF_PATCH 1, 1, #:qlsize(0, "mov")\n'
                '::RIF_PATCH 2, 2, #:qvsize(0, "mov")\n'
                '::RIF_PATCH 4, 1, #:calc(#:qvssize(0, "text") - 4096)\n'
                '::RIF_PATCH 0, 1, #:query(4, 1)\n'
                "mov\n",
            )

            self.assertEqual(result.binary, b"\x05\x04\x04\x10\x05")
            self.assertEqual(result.image.section_offset("text"), 0)
            self.assertEqual(result.image.section_virtual_base("text"), 4096)
            self.assertEqual(result.image.sections["text"].virtual_size, 5)
            self.assertEqual(result.image.file_bytes(), result.binary)
            self.assertEqual(result.section_binary, result.binary)

    def test_insert_rejects_unsupported_operation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "main.rif"
            target.write_text(TARGET, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "BYTES, BINARY o FILE"):
                compile_mir_source(
                    target,
                    '::RIF_INSERT CALL "make_payload"\n',
                )

    def test_patch_rejects_external_call_expression(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "main.rif"
            target.write_text(TARGET, encoding="utf-8")
            with self.assertRaisesRegex(MIRInputError, "no permite #call"):
                compile_mir_source(
                    target,
                    "::RIF_PATCH 0, 1, #call[not_allowed]\nmov\n",
                )

    def test_runtime_rejects_compiled_external_call_expression(self) -> None:
        with self.assertRaisesRegex(ArtifactError, "no está permitido"):
            evaluate_expression(
                {"kind": "call", "name": "not_allowed"},
                image=None,
                machine=None,
                working=b"",
            )


class CalcFunctionTests(unittest.TestCase):
    def test_calc_addition_and_subtraction_preserve_widest_width(self) -> None:
        self.assertEqual(calc("+", 4096, 2, 128, 4), (4224, 4))
        self.assertEqual(calc("-", 10, 8, 3, 16), (7, 16))

    def test_calc_rejects_unknown_operator_and_invalid_width(self) -> None:
        with self.assertRaises(CalcError):
            calc("*", 1, 1, 2, 1)
        with self.assertRaises(CalcError):
            calc("+", 1, 0, 2, 1)

    def test_calc_rejects_signed_int64_overflow(self) -> None:
        with self.assertRaises(CalcError):
            calc("+", (1 << 63) - 1, 1, 1, 1)

    def test_nested_calc_expression_and_negative_patch_are_checked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "main.rif"
            target.write_text(TARGET, encoding="utf-8")
            result = compile_mir_source(
                target,
                "::RIF_PATCH 0, 1, #:calc(1 + (2 - 3))\nmov\n",
            )
            self.assertEqual(result.binary, b"\x00")

            with self.assertRaisesRegex(ArtifactError, "no cabe"):
                compile_mir_source(
                    target,
                    "::RIF_PATCH 0, 1, #:calc(0 - 1)\nmov\n",
                )


if __name__ == "__main__":
    unittest.main()
