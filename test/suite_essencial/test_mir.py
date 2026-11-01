from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from Frontend import RIF_LANG_SESSION
from Frontend import globals as rif_globals
from Frontend.processor import process
from gram import lexer
from MIR import CompiledRuleSet, MIRSemanticError, TableRef, TokenRef, compile_rules


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


class MIRCompilerTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_globals()

    def tearDown(self) -> None:
        reset_globals()

    def parse_and_process(self, source: str, path: Path):
        path.write_text(source, encoding="utf-8")
        RIF_LANG_SESSION.load()
        tokens = RIF_LANG_SESSION.tokenize(source, str(path))
        ast = RIF_LANG_SESSION.parse(tokens, str(path))
        process(ast, source_path=path)

    def test_rule_compiles_to_flat_instructions_and_preserves_raw_width(self) -> None:
        source = (
            "@table registers\n"
            "| opcode |\n"
            "__\n"
            "| 7 |\n"
            "@end\n"
            "@rule sample:\n"
            ". $registers.opcode, IDENT\n"
            ". COMMA\n"
            ". [NUMBER, STRING]\n"
            ". nibbles 0000 0000\n"
            ". eword 42\n"
            ". JUMPIF other, true\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.rif"
            self.parse_and_process(source, path)

            program = compile_rules()
            rule = program.rules["sample"]

            self.assertEqual(
                [instruction.opcode for instruction in rule.instructions],
                ["table_matcher", "consumer", "store", "nibbles", "eword", "jumpif"],
            )
            self.assertEqual(rule.instructions[0].operands[0].kind, "table_access")
            self.assertEqual(rule.instructions[0].operands[0].value, ("registers", "opcode"))
            self.assertEqual(rule.instructions[3].operands[0].raw, "0000")
            self.assertEqual(rule.instructions[3].operands[0].width, 4)
            self.assertEqual(rule.instructions[5].operands[0].value, "other")

    def test_emitfr_is_represented_as_one_instruction(self) -> None:
        source = (
            "@rule frames:\n"
            ". frame 0000 0\n"
            "00000000\n"
            ". frameend\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frames.rif"
            self.parse_and_process(source, path)

            rule = compile_rules().rules["frames"]
            self.assertEqual(len(rule.instructions), 1)
            self.assertEqual(rule.instructions[0].opcode, "frame")
            self.assertEqual(rule.instructions[0].operands[0].kind, "frame")
            self.assertEqual(len(rule.instructions[0].operands[0].value), 2)
            self.assertEqual(len(rule.instructions[0].operands[0].value[0]), 2)
            self.assertEqual(len(rule.instructions[0].operands[0].value[1]), 1)

    def test_resolve_converts_tokens_tables_and_rules(self) -> None:
        source = (
            "@table registers\n"
            "| opcode |\n"
            "__\n"
            "| 7 |\n"
            "@end\n"
            "@rule other:\n"
            ". IDENT\n"
            "@rule sample:\n"
            ". $registers.opcode, IDENT\n"
            ". JUMP other\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "resolve.rif"
            self.parse_and_process(source, path)

            program = compile_rules(resolve=True)
            matcher = program.rules["sample"].instructions[0]
            jump = program.rules["sample"].instructions[1]

            self.assertIsInstance(matcher.operands[0].resolved, TableRef)
            self.assertEqual(matcher.operands[0].resolved.index, 0)
            self.assertIsInstance(matcher.operands[1].resolved, TokenRef)
            self.assertIs(matcher.operands[1].resolved.token, lexer.Token.IDENT)
            self.assertEqual(jump.operands[0].resolved.name, "other")

    def test_resolve_reports_missing_symbols_and_invalid_token_codes(self) -> None:
        source = (
            "@rule sample:\n"
            ". 999\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.rif"
            self.parse_and_process(source, path)
            with self.assertRaises(MIRSemanticError):
                compile_rules(resolve=True)

        reset_globals()
        source = (
            "@table registers\n"
            "| opcode |\n"
            "__\n"
            "| 7 |\n"
            "@end\n"
            "@rule sample:\n"
            ". $registers.missing, IDENT\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing-column.rif"
            self.parse_and_process(source, path)
            with self.assertRaises(MIRSemanticError):
                compile_rules(resolve=True)

    def test_project_rules_resolve_as_a_complete_program(self) -> None:
        source = (
            "@table registers\n"
            "| name | opcode |\n"
            "__\n"
            "| mov | 1 |\n"
            "__\n"
            "| add | 2 |\n"
            "@end\n"
            "@rule mov:\n"
            ". $registers.opcode, IDENT\n"
            ". KW \"mov\"\n"
            ". IDENT\n"
            ". bits 72 8\n"
            "@rule add:\n"
            ". $registers.opcode, NUMBER\n"
            ". KW \"add\"\n"
            ". bits 3 8\n"
            "@rule ret:\n"
            ". KW \"ret\"\n"
            ". bits 195 8\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.rif"
            path.write_text(source, encoding="utf-8")
            RIF_LANG_SESSION.load()
            tokens = RIF_LANG_SESSION.tokenize(source, str(path))
            ast = RIF_LANG_SESSION.parse(tokens, str(path))
            process(ast, source_path=path)

            program = compile_rules(resolve=True)
            self.assertEqual(set(program.rules), {"mov", "add", "ret"})
            self.assertGreater(len(program.rules["mov"].instructions), 0)


if __name__ == "__main__":
    unittest.main()
