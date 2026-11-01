from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from Frontend import globals as rif_globals
from MIR import (
    MIRInputError,
    DiagnosticBag,
    PCPIPitAddress,
    RIFRuntimeError,
    compile_definition,
    compile_mir_file,
    compile_mir_source,
    compile_mir_tokens,
    prepare_target,
    tokenize_mir,
)
from MIR.storage import StorageBuilder
from pack import PackReader, create_pack, read_pack
from pcpi_compiler import compile_pcpi_source_file
from rif import main as rif_main


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
    address_size 8
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


def reset_globals() -> None:
    rif_globals.STACK = None
    rif_globals.STACK_SIZE = None
    rif_globals.DEFINES.clear()
    rif_globals.TABLES.clear()
    rif_globals.RULES.clear()
    rif_globals.CONFIG = None
    rif_globals.LINKER = None
    rif_globals.SUPPORTS.clear()
    rif_globals.ASM_VARIANTS.clear()
    rif_globals.LOADED_SOURCES.clear()
    rif_globals.ACTIVE_SOURCES.clear()
    rif_globals.VARIANT_STACK.clear()
    rif_globals.SOURCE_PROVIDER = None


class ExternalMIRTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_globals()

    def tearDown(self) -> None:
        reset_globals()

    def test_direct_source_and_pre_tokenized_input_produce_same_binary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "main.rif"
            target.write_text(TARGET, encoding="utf-8")

            program = compile_definition(target)
            direct = compile_mir_source(program, "mov\nmov\n")
            tokens = tokenize_mir("mov\nmov\n", "direct.asm")
            token_direct = compile_mir_tokens(program, tokens)

            self.assertEqual(direct.binary, b"\x01\x01")
            self.assertEqual(token_direct.binary, direct.binary)
            self.assertEqual(len(direct.executions), 2)

    def test_native_mark_exposes_absolute_virtual_symbol_address(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "main.rif"
            target.write_text(
                TARGET.replace("    default text\n", "    default text\n    vaddr text 4096\n")
                + "\n@rule mark:\n. IDENT\n. eword 1\n. mark\n. IDENT\n",
                encoding="utf-8",
            )
            program = compile_definition(target)
            result = compile_mir_source(program, "mark label\n")

        self.assertEqual(result.symbols, {"label": 4097})
        self.assertEqual(result.context.symbols["label"].section, "text")

    def test_native_pc32_fixup_resolves_forward_and_backward_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "main.rif"
            target.write_text(
                TARGET.replace("    default text\n", "    default text\n    vaddr text 4096\n")
                + "\n"
                "@rule mark:\n"
                ". IDENT\n"
                ". mark\n"
                ". IDENT\n"
                "@rule jmp:\n"
                ". IDENT\n"
                ". bits 233 8\n"
                '. reserve "fix32" 32\n'
                '. fixup pc32 "fix32"\n'
                '. drop_res "fix32"\n'
                ". IDENT\n",
                encoding="utf-8",
            )
            program = compile_definition(target)
            forward = compile_mir_source(program, "jmp target\nmark target\n")
            backward = compile_mir_source(program, "mark target\njmp target\n")

        self.assertEqual(forward.binary, b"\xE9\x00\x00\x00\x00")
        self.assertEqual(backward.binary, b"\xE9\xFB\xFF\xFF\xFF")
        self.assertEqual(forward.context.fixups[0].kind, "pc32")

    def test_target_declared_relocations_extend_fixup_calculations(self) -> None:
        target_source = (
            TARGET.replace(
                "    default text\n",
                "    default text\n    vaddr text 4096\n",
            )
            + "\n"
            "@block relocations:\n"
            "    rel24 16 pc\n"
            "    abs24 24 abs\n"
            "@end\n\n"
            "@rule mark:\n"
            ". IDENT\n"
            ". mark\n"
            ". IDENT\n"
            "@rule rel:\n"
            ". IDENT\n"
            ". bits 233 8\n"
            '. reserve "fix16" 16\n'
            '. fixup rel24 "fix16"\n'
            '. drop_res "fix16"\n'
            ". IDENT\n"
            "@rule absolute:\n"
            ". IDENT\n"
            '. reserve "fix24" 24\n'
            '. fixup abs24 "fix24"\n'
            '. drop_res "fix24"\n'
            ". IDENT\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "main.rif"
            target.write_text(target_source, encoding="utf-8")
            program = compile_definition(target)
            relative = compile_mir_source(program, "rel target\nmark target\n")
            absolute = compile_mir_source(program, "absolute target\nmark target\n")

        self.assertEqual(relative.binary, b"\xE9\x00\x00")
        self.assertEqual(absolute.binary, b"\x03\x10\x00")

    def test_diagnostics_carry_rule_location_and_phase(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "main.rif"
            target.write_text(
                TARGET
                + "\n@rule bad:\n"
                ". IDENT\n"
                ". patch_bits 0 16 1\n",
                encoding="utf-8",
            )
            program = compile_definition(target)
            diagnostics = DiagnosticBag()
            with self.assertRaises(RIFRuntimeError):
                compile_mir_source(program, "bad\n", diagnostics=diagnostics)

        self.assertEqual(len(diagnostics.items), 1)
        diagnostic = diagnostics.items[0]
        self.assertEqual(diagnostic.phase, "rules")
        self.assertEqual(diagnostic.rule, "bad")
        self.assertEqual(diagnostic.section, "text")

    def test_native_pc32_fixup_rejects_unresolved_symbol_before_patching(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "main.rif"
            target.write_text(
                TARGET
                + "\n@rule jmp:\n"
                ". IDENT\n"
                ". bits 233 8\n"
                '. reserve "fix32" 32\n'
                '. fixup pc32 "fix32"\n'
                '. drop_res "fix32"\n'
                ". IDENT\n",
                encoding="utf-8",
            )
            program = compile_definition(target)
            with self.assertRaisesRegex(RIFRuntimeError, "Símbolo no definido"):
                compile_mir_source(program, "jmp missing\n")

    def test_native_section_switch_keeps_symbols_and_emitters_per_section(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "main.rif"
            target.write_text(
                TARGET.replace('    section text ""\n', '    section text ""\n    section data "rw"\n')
                .replace(
                    "    default text\n",
                    "    default text\n    vaddr text 4096\n    vaddr data 8192\n",
                )
                + "\n"
                "@rule mark:\n"
                ". IDENT\n"
                ". mark\n"
                ". IDENT\n",
                encoding="utf-8",
            )
            program = compile_definition(target)
            result = compile_mir_source(
                program,
                "::RIF_SECTION data\n"
                "mark data_label\n"
                "::RIF_SECTION text\n"
                "mark text_label\n",
            )

        self.assertEqual(result.context.section_name, "text")
        self.assertEqual(result.context.symbols["data_label"].section, "data")
        self.assertEqual(result.symbols, {"data_label": 8192, "text_label": 4096})

    def test_layout_exposes_initialized_and_virtual_only_section_space(self) -> None:
        target_source = '''\
@block config:
    section text "rx"
    section bss "rw"
    entry text "_start"
    default text
    vaddr text 4096
    vaddr bss 8192
    word_size 8
    address_size 64
    byte_order "little"
    case_sensitive true
    undefined_symbols "error"
    duplicate_symbols "error"
    strict true
    allow_empty_sections true
@end

@block linker:
    extension ".asm"
    search_path ""
@end

@rule emit:
. IDENT
. eword 1

@rule reserve:
. IDENT
. vreserve "scratch" 16
'''
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "layout.rif"
            target.write_text(target_source, encoding="utf-8")
            program = compile_definition(target)
            result = compile_mir_source(
                program,
                "emit\n::RIF_SECTION bss\nreserve\n",
            )

        text = result.image.sections["text"]
        bss = result.image.sections["bss"]
        self.assertEqual(result.binary, b"\x01")
        self.assertEqual(text.initialized_size, 1)
        self.assertEqual(text.uninitialized_size, 0)
        self.assertEqual(bss.initialized_size, 0)
        self.assertEqual(bss.uninitialized_size, 2)
        self.assertEqual(bss.virtual_base, 8192)
        self.assertEqual(result.image.file_bytes(), b"\x01")

    def test_layout_rejects_overlapping_explicit_virtual_sections(self) -> None:
        target_source = TARGET.replace(
            "    default text\n",
            "    section data \"rw\"\n"
            "    default text\n"
            "    vaddr text 4096\n"
            "    vaddr data 4096\n",
        ) + (
            "\n@rule data:\n"
            ". IDENT\n"
            ". eword 1\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "overlap.rif"
            target.write_text(target_source, encoding="utf-8")
            program = compile_definition(target)
            with self.assertRaisesRegex(ValueError, "se solapan"):
                compile_mir_source(
                    program,
                    "mov\n::RIF_SECTION data\ndata\n",
                )

    def test_metaprogramming_directives_are_recognized_without_emission(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = Path(directory) / "main.rif"
            source = Path(directory) / "program.asm"
            storage = Path(directory) / "imagenes.bin"
            pci_source = Path(directory) / "header.pci"
            pcic = Path(directory) / "header.pcic"
            target.write_text(TARGET, encoding="utf-8")
            source.write_text(
                "::RIF_PCPI SET \"header.pcic\"\n"
                "::RIF_PCPI PIT 0\n"
                "::RIF_PCPI PIT 0 SECTION text\n"
                "::RIF_STORE \"imagenes.bin\" payload 1 0\n",
                encoding="utf-8",
            )
            pci_source.write_text(
                'MAGIC "pcpi"\n'
                "VERSION 1\n"
                "ENDIANNESS 1\n"
                "BITORDER 1\n"
                'SIGNATURE "test"\n'
                "@RAW\n"
                "AA\n"
                "[2]\n"
                "@END\n",
                encoding="utf-8",
            )
            compile_pcpi_source_file(pci_source, pcic)
            builder = StorageBuilder()
            builder.add(b"RAWIMAGE", label="payload")
            storage.write_bytes(builder.build())

            program = compile_definition(target)
            loaded = compile_mir_file(program, source)
            package = root / "target.pack"
            create_pack(target, package, precompile=True)
            loaded_from_pack = compile_mir_file(package, source)

            pcpi_bytes = pcic.read_bytes()
            self.assertEqual(loaded.binary, pcpi_bytes + b"RAWIMAGE")
            self.assertEqual(loaded.executions, ())
            self.assertEqual(
                loaded.pcpi_pit_addresses,
                (
                    PCPIPitAddress(0, 152, "text"),
                    PCPIPitAddress(0, 152, "text"),
                ),
            )
            self.assertEqual(loaded_from_pack.binary, loaded.binary)

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

    def test_store_directive_rejects_invalid_layout_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "main.rif"
            target.write_text(TARGET, encoding="utf-8")
            program = compile_definition(target)

            with self.assertRaisesRegex(ValueError, "ENDIANNESS"):
                compile_mir_source(
                    program,
                    '::RIF_STORE "imagenes.bin" payload 3 0\n',
                )

            with self.assertRaisesRegex(ValueError, "BITORDER"):
                compile_mir_source(
                    program,
                    '::RIF_STORE "imagenes.bin" payload 1 2\n',
                )

    def test_file_entry_validates_linker_extension_and_writes_pure_binary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "main.rif"
            source = root / "program.asm"
            output = root / "program.bin"
            target.write_text(TARGET, encoding="utf-8")
            source.write_text("mov\n", encoding="utf-8")

            result = compile_mir_file(target, source, output=output)

            self.assertEqual(result.binary, b"\x01")
            self.assertEqual(output.read_bytes(), b"\x01")

            wrong = root / "program.txt"
            wrong.write_text("mov\n", encoding="utf-8")
            with self.assertRaises(MIRInputError):
                compile_mir_file(target, wrong)

    def test_file_entry_accepts_a_precompiled_pack(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "main.rif"
            package = root / "target.pack"
            source = root / "program.asm"
            target.write_text(TARGET, encoding="utf-8")
            source.write_text("mov\n", encoding="utf-8")
            create_pack(target, package, precompile=True)

            result = compile_mir_file(package, source)

            self.assertEqual(result.binary, b"\x01")

    def test_assembler_insert_file_resolves_relative_to_mir(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "main.rif"
            source = root / "program.asm"
            target.write_text(TARGET, encoding="utf-8")
            (root / "payload.bin").write_bytes(b"\x10\x20")
            source.write_text(
                '::RIF_INSERT FILE "payload.bin"\nmov\n',
                encoding="utf-8",
            )
            result = compile_mir_file(target, source)

            self.assertEqual(result.binary, b"\x10\x20\x01")

    def test_precompiled_pack_preserves_indexed_fits_and_virtual_space(self) -> None:
        target_source = TARGET.replace(
            '@rule mov:\n. IDENT\n. eword 1\n',
            '@table registers\n'
            '| names | bits |\n'
            '__\n'
            '| rax | 16 |\n'
            '@end\n\n'
            '@rule mov:\n'
            '. IDENT\n'
            '. fit $registers.names[rax].bits\n'
            '. vpad 8\n',
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "main.rif"
            package = root / "target.pack"
            source = root / "program.asm"
            target.write_text(target_source, encoding="utf-8")
            source.write_text("mov 1282\n", encoding="utf-8")
            create_pack(target, package, precompile=True)

            result = compile_mir_file(package, source)

            self.assertEqual(result.binary, b"\x02\x05")
            self.assertEqual(result.context.virtual_position, 24)

    def test_datastack_capture_survives_mir_lines_and_precompiled_pack(self) -> None:
        target_source = TARGET.replace(
            '@rule mov:\n. IDENT\n. eword 1\n',
            '@table registers\n'
            '| names | bits |\n'
            '__\n'
            '| rax | 8 |\n'
            '__\n'
            '| rbx | 8 |\n'
            '@end\n\n'
            '@rule capture:\n'
            '. IDENT\n'
            '. dget ::registers.names : bits\n'
            '@rule emit:\n'
            '. IDENT\n'
            '. fit dget\n',
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "main.rif"
            package = root / "target.pack"
            source = root / "program.asm"
            target.write_text(target_source, encoding="utf-8")
            source.write_text("capture rax\nemit 258\n", encoding="utf-8")

            direct = compile_mir_source(compile_definition(target), source.read_text(encoding="utf-8"))
            self.assertEqual(direct.binary, b"\x02")
            self.assertEqual(direct.context.datastack, [])
            self.assertEqual(direct.program.context.tables["registers"].indexes.keys(), {"names", "bits"})

            create_pack(target, package, precompile=True)
            packed = compile_mir_file(package, source)
            self.assertEqual(packed.binary, direct.binary)
            self.assertEqual(packed.context.datastack, [])

    @unittest.skip("legacy: callbacks Python serán migrados a funciones nativas")
    def test_funcs_py_is_loaded_from_a_precompiled_pack(self) -> None:
        target_source = TARGET.replace(
            '@rule mov:\n. IDENT\n. eword 1\n',
            '@rule mov:\n. IDENT\n. eword #call[value]\n',
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "main.rif"
            package = root / "target.pack"
            source = root / "program.asm"
            target.write_text(target_source, encoding="utf-8")
            (root / "funcs.py").write_text(
                'def handler(name, context):\n'
                '    return "00000001"\n',
                encoding="utf-8",
            )
            source.write_text("mov\n", encoding="utf-8")
            create_pack(target, package, precompile=True)

            manifest = read_pack(package)
            self.assertIsNotNone(manifest.functions)
            with PackReader(package) as reader:
                self.assertEqual(reader.function_source(), (root / "funcs.py").read_bytes().decode("utf-8"))

            result = compile_mir_file(package, source)

            self.assertEqual(result.binary, b"\x01")

    @unittest.skip("legacy: callbacks Python serán migrados a funciones nativas")
    def test_pack_rejects_tampered_funcs_py(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "main.rif"
            package = root / "target.pack"
            tampered = root / "tampered.pack"
            target.write_text(TARGET, encoding="utf-8")
            (root / "funcs.py").write_text(
                'def handler(name, context):\n'
                '    return "00000001"\n',
                encoding="utf-8",
            )
            create_pack(target, package, precompile=True)

            with zipfile.ZipFile(package, "r") as source_archive, zipfile.ZipFile(
                tampered, "w", compression=zipfile.ZIP_DEFLATED
            ) as target_archive:
                for info in source_archive.infolist():
                    data = source_archive.read(info.filename)
                    if info.filename == "funcs.py":
                        data += b"\n# tampered\n"
                    target_archive.writestr(info, data)

            with self.assertRaisesRegex(ValueError, "Hash inválido para funcs.py"):
                read_pack(tampered)

    @unittest.skip("legacy: callbacks Python serán migrados a funciones nativas")
    def test_funcs_handler_receives_live_context_and_drives_calls(self) -> None:
        target_source = TARGET.replace(
            '@rule mov:\n. IDENT\n. eword 1\n',
            '@rule mov:\n. IDENT\n. eword #call[value]\n'
            '@rule callrule:\n. IDENT\n. CALL #call[emit]\n'
            '@rule branch:\n. IDENT\n. JUMPIF target, #call[condition]\n'
            '@rule target:\n. eword 1\n',
        )
        target_source = target_source.replace(
            '@rule mov:',
            '@table registers\n| name |\n__\n| "mov" |\n@end\n\n@rule mov:',
        )
        function_source = '''\
calls = []

def handler(name, context):
    calls.append((name, context))
    assert context.config.wordsize == 8
    assert context.coder is context.machine.emitter
    from Frontend import globals as rif_globals
    assert context.tables is not rif_globals.TABLES
    assert context.tables["registers"].matrix[0][0] == "mov"
    if name == "value":
        return "00000010"
    if name == "emit":
        context.coder.eword("00000011")
        return "0"
    if name == "condition":
        return True
    raise RuntimeError(name)
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "main.rif"
            target.write_text(target_source, encoding="utf-8")
            (root / "funcs.py").write_text(function_source, encoding="utf-8")

            prepared = prepare_target(target)
            result = compile_mir_source(prepared, "mov\ncallrule\nbranch\n")

            self.assertEqual(result.binary, b"\x02\x03\x01")
            calls = prepared.function_module.module.calls
            self.assertEqual([name for name, _context in calls], ["value", "emit", "condition"])
            self.assertIs(calls[0][1], result.context)

    @unittest.skip("legacy: callbacks Python serán migrados a funciones nativas")
    def test_funcs_handler_rejects_invalid_return_and_numeric_conditions(self) -> None:
        target_source = TARGET.replace(
            '@rule mov:\n. IDENT\n. eword 1\n',
            '@rule mov:\n. IDENT\n. eword #call[invalid]\n'
            '@rule branch:\n. IDENT\n. JUMPIF target, #call[zero]\n'
            '@rule target:\n. eword 1\n',
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "main.rif"
            target.write_text(target_source, encoding="utf-8")
            (root / "funcs.py").write_text(
                'def handler(name, context):\n'
                '    return 1 if name == "invalid" else "000"\n',
                encoding="utf-8",
            )
            prepared = prepare_target(target)

            with self.assertRaisesRegex(RuntimeError, "solo se permiten"):
                compile_mir_source(prepared, "mov\n")
            with self.assertRaisesRegex(RuntimeError, "debe devolver True o False"):
                compile_mir_source(prepared, "branch\n")

    @unittest.skip("legacy: callbacks Python serán migrados a funciones nativas")
    def test_funcs_module_requires_handler(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "main.rif"
            target.write_text(TARGET, encoding="utf-8")
            (root / "funcs.py").write_text("VALUE = True\n", encoding="utf-8")

            prepared = prepare_target(target)
            self.assertFalse(prepared.function_module.loaded)
            self.assertTrue((root / "funcs.py").is_file())

    def test_cli_uses_the_same_binary_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "main.rif"
            source = root / "program.asm"
            output = root / "program.bin"
            target.write_text(TARGET, encoding="utf-8")
            source.write_text("mov\nmov\n", encoding="utf-8")

            status = rif_main([str(target), str(source), "-o", str(output)])

            self.assertEqual(status, 0)
            self.assertEqual(output.read_bytes(), b"\x01\x01")


if __name__ == "__main__":
    unittest.main()
