from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from Frontend import RIF_LANG_SESSION
from Frontend import globals as rif_globals
from Frontend.processor import process
from MIR import BitEmitter, MIRSemanticError, RIFMachine, RIFRuntimeError, compile_rules


CONFIG_SOURCE = """\
@block config:
    format section ".section"
    section text ""
    format section_end ":"
    entry text "_start"
    comment ";"
    format label_end ":"
    default text
    align text 8
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
"""


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


class RuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_globals()

    def tearDown(self) -> None:
        reset_globals()

    def compile(self, source: str, path: Path):
        path.write_text(source, encoding="utf-8")
        RIF_LANG_SESSION.load()
        tokens = RIF_LANG_SESSION.tokenize(source, str(path))
        ast = RIF_LANG_SESSION.parse(tokens, str(path))
        process(ast, source_path=path)
        return compile_rules(resolve=True)

    def tokenize(self, source: str, name: str = "input.rif"):
        RIF_LANG_SESSION.load()
        return RIF_LANG_SESSION.tokenize(source, name)

    def test_consumer_table_matcher_and_put_use_the_bit_buffer(self) -> None:
        source = (
            "@table registers\n"
            "| name | bits |\n"
            "__\n"
            '| "mov" | "1010" |\n'
            "@end\n"
            "@rule sample:\n"
            ". $registers.name, IDENT\n"
            ". nibbles $registers.bits 0000\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            program = self.compile(source, Path(directory) / "main.rif")
            machine = RIFMachine(program)
            result = machine.execute("sample", self.tokenize("mov"))

            self.assertEqual(result.position, 1)
            self.assertEqual(result.buffer, b"\xA0")
            self.assertEqual(machine.selected_rows["registers"], 0)

    def test_store_consumes_the_first_matching_token(self) -> None:
        source = "@rule sample:\n. [NUMBER, STRING]\n"
        with tempfile.TemporaryDirectory() as directory:
            program = self.compile(source, Path(directory) / "main.rif")
            machine = RIFMachine(program)
            result = machine.execute("sample", self.tokenize('"hello"'))

            self.assertEqual(result.position, 1)
            self.assertIsNotNone(result.stored_token)
            self.assertEqual(result.stored_token.value, "hello")

    def test_emmit_uses_the_emitter_word_size(self) -> None:
        source = "@rule sample:\n. eword 4660\n"
        with tempfile.TemporaryDirectory() as directory:
            program = self.compile(source, Path(directory) / "main.rif")
            machine = RIFMachine(program, emitter=BitEmitter(wordsize=16))
            result = machine.execute("sample", ())

            self.assertEqual(result.buffer, b"4\x12")

    def test_dynamic_reservations_rewrite_copy_and_remove_names(self) -> None:
        source = (
            '@rule sample:\n'
            '. reserve "slot" 8\n'
            '. write_res "slot" "10101010"\n'
            '. emit_res "slot"\n'
            '. drop_res "slot"\n'
        )
        with tempfile.TemporaryDirectory() as directory:
            program = self.compile(source, Path(directory) / "main.rif")
            machine = RIFMachine(program)
            result = machine.execute("sample", ())

            self.assertEqual(result.buffer, b"\xAA\xAA")
            self.assertNotIn("slot", machine.emitter.buffer.regions)

    def test_mark_defines_native_symbol_without_consuming_identifier(self) -> None:
        source = (
            "@rule mark:\n"
            ". IDENT\n"
            ". eword 1\n"
            ". mark\n"
            ". IDENT\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            program = self.compile(source, Path(directory) / "main.rif")
            machine = RIFMachine(program, emitter=BitEmitter(wordsize=8))
            result = machine.execute("mark", self.tokenize("mark label"))

        self.assertEqual(result.position, 2)
        symbol = machine.symbols["label"]
        self.assertEqual(symbol.physical_offset_bits, 8)
        self.assertEqual(symbol.virtual_offset_bits, 8)
        self.assertEqual(symbol.physical_offset, 1)
        self.assertEqual(symbol.virtual_offset, 1)

    def test_mark_rejects_duplicate_symbols_across_external_lines(self) -> None:
        source = "@rule mark:\n. IDENT\n. mark\n. IDENT\n"
        with tempfile.TemporaryDirectory() as directory:
            program = self.compile(source, Path(directory) / "main.rif")
            machine = RIFMachine(program, emitter=BitEmitter(wordsize=8))
            machine.execute_line("mark", self.tokenize("mark label"))

            with self.assertRaisesRegex(RIFRuntimeError, "ya está definido"):
                machine.execute_line("mark", self.tokenize("mark label"))

    def test_emitfr_keeps_rows_and_jmpif_can_use_boolean(self) -> None:
        source = (
            "@rule target:\n"
            ". eword 1\n"
            "@rule sample:\n"
            ". frame 0000 0\n"
            "00000000\n"
            "0000\n"
            ". frameend\n"
            ". JUMPIF target, true\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            program = self.compile(source, Path(directory) / "main.rif")
            machine = RIFMachine(program, emitter=BitEmitter(wordsize=8))
            result = machine.execute("sample", ())

            # The frame occupies 17 bits, so the following 8-bit word starts
            # unaligned and its final one-bit lands at the MSB of the last byte.
            self.assertEqual(result.buffer, b"\x00\x00\x00\x80")

    def test_padding_alignment_and_position_values_are_traced(self) -> None:
        source = CONFIG_SOURCE + (
            "@rule sample:\n"
            ". eword 00000000\n"
            ". pad 3\n"
            ". align 8\n"
            ". eword ::SIZE\n"
            ". eword ::VSIZE\n"
            ". eword ::ALIGNMENT\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            program = self.compile(source, Path(directory) / "positions.rif")
            machine = RIFMachine(program, emitter=BitEmitter(wordsize=8))
            result = machine.execute("sample", ())

            self.assertEqual(result.buffer, b"\x00\x00\x10\x18\x08")
            self.assertEqual(machine.last_rule_trace.start, 0)
            self.assertEqual(machine.last_rule_trace.bits, 40)
            self.assertEqual(machine.last_rule_trace.end, 40)
            self.assertEqual(machine.last_rule_trace.padding_bits, 8)

    def test_reservation_and_label_distances_are_values(self) -> None:
        source = (
            "@rule sample:\n"
            '. reserve "slot" 8\n'
            ". eword 00000000\n"
            '. eword resdir "slot"\n'
            '. eword resdist "slot"\n'
            '. eword dist "sample"\n'
            '. eword vdist "sample"\n'
            '. eword resvdir "slot"\n'
        )
        with tempfile.TemporaryDirectory() as directory:
            program = self.compile(source, Path(directory) / "addresses.rif")
            machine = RIFMachine(program, emitter=BitEmitter(wordsize=8))
            result = machine.execute("sample", ())

            self.assertEqual(result.buffer, b"\x00\x00\x00\x18\x20\x28\x00")
            self.assertEqual(machine.emitter.buffer.regions["slot"].offset, 0)

    def test_nested_rule_traces_keep_child_and_parent_spans(self) -> None:
        source = (
            "@rule child:\n"
            ". eword 1\n"
            ". pad 2\n"
            "@rule parent:\n"
            ". eword 2\n"
            ". JUMP child\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            program = self.compile(source, Path(directory) / "nested.rif")
            machine = RIFMachine(program, emitter=BitEmitter(wordsize=8))
            machine.execute("parent", ())

            self.assertEqual(
                [(trace.name, trace.start, trace.bits, trace.end, trace.padding_bits)
                 for trace in machine.rule_traces],
                [("child", 8, 10, 18, 2), ("parent", 0, 18, 18, 0)],
            )

    def test_padding_and_alignment_require_positive_sizes(self) -> None:
        for opcode in ("pad", "align"):
            source = f"@rule sample:\n. {opcode} 0\n"
            with self.subTest(opcode=opcode), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(MIRSemanticError):
                    self.compile(source, Path(directory) / "invalid.rif")
            reset_globals()

    def test_fits_uses_the_current_mir_token_and_truncates_low_bits(self) -> None:
        source = "@rule sample:\n. fit 8\n"
        with tempfile.TemporaryDirectory() as directory:
            program = self.compile(source, Path(directory) / "fits.rif")
            machine = RIFMachine(program, emitter=BitEmitter(wordsize=8))
            result = machine.execute("sample", self.tokenize("258"))

            self.assertEqual(result.position, 1)
            self.assertEqual(result.buffer, b"\x02")

            machine = RIFMachine(program, emitter=BitEmitter(wordsize=8))
            result = machine.execute("sample", self.tokenize("1.0"))
            self.assertEqual(result.buffer, b"\x01")

    def test_fits_can_resolve_an_indexed_table_width(self) -> None:
        source = (
            "@table registers\n"
            "| names | bits |\n"
            "__\n"
            "| rax | 16 |\n"
            "@end\n"
            "@rule sample:\n"
            ". fit $registers.names[rax].bits\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            program = self.compile(source, Path(directory) / "indexed-fits.rif")
            machine = RIFMachine(program, emitter=BitEmitter(wordsize=8))
            result = machine.execute("sample", self.tokenize("1282"))

            self.assertEqual(result.position, 1)
            self.assertEqual(result.buffer, b"\x02\x05")

    def test_iffits_is_exact_and_does_not_mutate_on_failure(self) -> None:
        source = "@rule sample:\n. fit_exact 8\n"
        with tempfile.TemporaryDirectory() as directory:
            program = self.compile(source, Path(directory) / "fit-exact.rif")
            machine = RIFMachine(program, emitter=BitEmitter(wordsize=8))
            result = machine.execute("sample", self.tokenize("255"))
            self.assertEqual(result.position, 1)
            self.assertEqual(result.buffer, b"\xff")

            machine = RIFMachine(program, emitter=BitEmitter(wordsize=8))
            with self.assertRaises(RIFRuntimeError):
                machine.execute("sample", self.tokenize("256"))
            self.assertEqual(machine.position, 0)
            self.assertEqual(machine.emitter.buffer.bit_length, 0)

    def test_ifnfits_asserts_and_consumes_without_emitting(self) -> None:
        source = "@rule sample:\n. fit_not 8\n"
        with tempfile.TemporaryDirectory() as directory:
            program = self.compile(source, Path(directory) / "fit_not.rif")
            machine = RIFMachine(program, emitter=BitEmitter(wordsize=8))
            result = machine.execute("sample", self.tokenize("256"))
            self.assertEqual(result.position, 1)
            self.assertEqual(result.buffer, b"")

            machine = RIFMachine(program, emitter=BitEmitter(wordsize=8))
            with self.assertRaises(RIFRuntimeError):
                machine.execute("sample", self.tokenize("255"))
            self.assertEqual(machine.position, 0)

    def test_virtual_padding_and_reservation_do_not_write_physical_bits(self) -> None:
        source = (
            "@rule sample:\n"
            ". eword 1\n"
            ". vpad 4\n"
            '. vreserve "virtual" 8\n'
            ". pad 2\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            program = self.compile(source, Path(directory) / "virtual.rif")
            machine = RIFMachine(program, emitter=BitEmitter(wordsize=8))
            result = machine.execute("sample", ())

            self.assertEqual(result.buffer, b"\x01\x00")
            self.assertEqual(machine.emitter.buffer.bit_length, 10)
            self.assertEqual(machine.emitter.virtual_position, 22)
            self.assertEqual(machine.emitter.virtual_query("virtual").offset, 12)
            self.assertEqual(machine.last_rule_trace.virtual_bits, 22)
            self.assertEqual(machine.last_rule_trace.virtual_padding_bits, 4)

    def test_datastack_push_pop_peek_and_depth(self) -> None:
        source = (
            "@rule sample:\n"
            ". dpush 8\n"
            ". eword ::ddepth\n"
            ". eword dpeek\n"
            ". eword dget\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            program = self.compile(source, Path(directory) / "datastack.rif")
            machine = RIFMachine(program, emitter=BitEmitter(wordsize=8))
            result = machine.execute("sample", ())
            self.assertEqual(result.buffer, b"\x01\x08\x08")
            self.assertEqual(machine.datastack, [])

    def test_datastack_table_capture_consumes_token_and_allows_repeated_data(self) -> None:
        source = (
            "@table registers\n"
            "| names | bits |\n"
            "__\n"
            "| rax | 8 |\n"
            "__\n"
            "| rbx | 8 |\n"
            "@end\n"
            "@rule sample:\n"
            ". dget ::registers.names : bits\n"
            ". fit dget\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            program = self.compile(source, Path(directory) / "capture.rif")
            self.assertEqual(program.context.tables["registers"].indexes.keys(), {"names", "bits"})
            machine = RIFMachine(program, emitter=BitEmitter(wordsize=8))
            result = machine.execute("sample", self.tokenize("rax 258"))
            self.assertEqual(result.position, 2)
            self.assertEqual(result.buffer, b"\x02")
            self.assertEqual(machine.datastack, [])
            self.assertEqual(machine.selected_rows["registers"], 0)

            missing = RIFMachine(program, emitter=BitEmitter(wordsize=8))
            with self.assertRaises(RIFRuntimeError):
                missing.execute("sample", self.tokenize("rcx 258"))
            self.assertEqual(missing.position, 0)
            self.assertEqual(missing.datastack, [])

    def test_datastack_capture_rejects_duplicate_selector_keys(self) -> None:
        source = (
            "@table registers\n"
            "| names | bits |\n"
            "__\n"
            "| rax | 8 |\n"
            "__\n"
            "| rax | 16 |\n"
            "@end\n"
            "@rule sample:\n"
            ". dget ::registers.names : bits\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(MIRSemanticError, "clave duplicada"):
                self.compile(source, Path(directory) / "duplicate-key.rif")

    def test_datastack_pop_requires_a_value(self) -> None:
        source = "@rule sample:\n. dpop\n"
        with tempfile.TemporaryDirectory() as directory:
            program = self.compile(source, Path(directory) / "empty-stack.rif")
            with self.assertRaisesRegex(RIFRuntimeError, "datastack"):
                RIFMachine(program).execute("sample", ())

    def test_datastack_survives_lines_and_fit_failure_does_not_pop(self) -> None:
        source = (
            "@rule push:\n"
            ". dpush 8\n"
            "@rule fit:\n"
            ". fit dget\n"
            "@rule exact:\n"
            ". fit_exact dget\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            program = self.compile(source, Path(directory) / "lines.rif")
            machine = RIFMachine(program, emitter=BitEmitter(wordsize=8))
            machine.execute_line("push", ())
            with self.assertRaises(RIFRuntimeError):
                machine.execute_line("exact", self.tokenize("256"))
            self.assertEqual(machine.datastack, [8])
            self.assertEqual(machine.position, 0)
            result = machine.execute_line("fit", self.tokenize("258"))
            self.assertEqual(result.buffer, b"\x02")
            self.assertEqual(machine.datastack, [])
            with self.assertRaises(RIFRuntimeError):
                machine.execute_line("fit", self.tokenize("1"))

    def test_bit_ranges_and_reservation_widths_control_output(self) -> None:
        source = (
            "@rule sample:\n"
            '. reserve "slot" 8\n'
            '. patch_bits resdir "slot" reswidth "slot" 170\n'
            ". read_bits 0 8\n"
            ". bits dget 8\n"
            ". vpad 1\n"
            ". valign 8\n"
            '. vreserve "virtual" 8\n'
            '. bits vreswidth "virtual" 8\n'
        )
        with tempfile.TemporaryDirectory() as directory:
            program = self.compile(source, Path(directory) / "ranges.rif")
            machine = RIFMachine(program, emitter=BitEmitter(wordsize=8))
            result = machine.execute("sample", ())
            self.assertEqual(result.buffer, b"\xAA\xAA\x08")
            self.assertEqual(machine.emitter.buffer.bit_length, 24)
            self.assertEqual(machine.emitter.virtual_position, 40)
            self.assertEqual(machine.last_rule_trace.virtual_padding_bits, 8)
            self.assertEqual(machine.datastack, [])

    def test_bit_range_patch_rejects_out_of_bounds(self) -> None:
        source = "@rule sample:\n. bits 255 8\n. patch_bits 7 2 3\n"
        with tempfile.TemporaryDirectory() as directory:
            program = self.compile(source, Path(directory) / "bad-range.rif")
            machine = RIFMachine(program)
            with self.assertRaises(RIFRuntimeError):
                machine.execute("sample", ())
            self.assertEqual(machine.emitter.buffer.to_bytes(), b"\xff")

        reset_globals()
        byte_source = "@rule sample:\n. bits 255 8\n. patch_bits 0 16 4660\n"
        with tempfile.TemporaryDirectory() as directory:
            program = self.compile(byte_source, Path(directory) / "bad-byte-range.rif")
            machine = RIFMachine(program)
            with self.assertRaises(RIFRuntimeError):
                machine.execute("sample", ())
            self.assertEqual(machine.emitter.buffer.to_bytes(), b"\xff")

    def test_physical_reservation_has_independent_virtual_address(self) -> None:
        source = (
            "@rule sample:\n"
            ". vpad 5\n"
            '. reserve "slot" 8\n'
            '. bits resdir "slot" 8\n'
            '. bits resvdir "slot" 8\n'
            '. bits vdist "slot" 8\n'
            '. bits resvdist "slot" 8\n'
            '. eword reswidth "slot"\n'
            '. eword vreswidth "slot"\n'
        )
        with tempfile.TemporaryDirectory() as directory:
            program = self.compile(source, Path(directory) / "virtual-address.rif")
            machine = RIFMachine(program, emitter=BitEmitter(wordsize=8))
            result = machine.execute("sample", ())
            self.assertEqual(result.buffer, bytes((0, 0, 5, 24, 32, 8, 8)))
            self.assertEqual(machine.emitter.virtual_query("slot").offset, 5)
            self.assertEqual(machine.emitter.buffer.regions["slot"].offset, 0)

    def test_byte_aligned_bit_ranges_respect_endianness(self) -> None:
        source = (
            "@rule sample:\n"
            ". bits 4660 16\n"
            ". read_bits 0 16\n"
            ". patch_bits 0 16 22136\n"
            ". bits dget 16\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            program = self.compile(source, Path(directory) / "byte-order.rif")
            machine = RIFMachine(program, emitter=BitEmitter(wordsize=8))
            result = machine.execute("sample", ())
            self.assertEqual(result.buffer, b"\x78\x56\x34\x12")


if __name__ == "__main__":
    unittest.main()
