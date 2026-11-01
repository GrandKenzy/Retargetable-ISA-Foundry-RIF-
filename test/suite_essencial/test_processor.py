from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from Frontend import RIF_LANG_SESSION
from Frontend import globals as rif_globals
from Frontend.processor import process
from Frontend.processor.parsing import SourceParser
from Frontend.syntax.items.instructions import RawInstruction


class StackProcessorTests(unittest.TestCase):
    def setUp(self) -> None:
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

    def tearDown(self) -> None:
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

    def parse(self, source: str):
        RIF_LANG_SESSION.load()
        tokens = RIF_LANG_SESSION.tokenize(source, "processor.rif")
        return RIF_LANG_SESSION.parse(tokens, "processor.rif")

    @staticmethod
    def process_file(path: Path) -> None:
        parser = SourceParser(backend="python")
        process(
            parser.parse_file(path),
            source_path=path,
            project_root=path.parent,
            backend="python",
            parser=parser,
        )

    def test_stack_creates_shared_empty_dictionary(self) -> None:
        process(self.parse("@stack 50\n"))

        self.assertEqual(rif_globals.STACK, {})
        self.assertEqual(rif_globals.STACK_SIZE, 50)

    def test_second_stack_is_fatal(self) -> None:
        ast = self.parse("@stack 4\n")
        process(ast)

        with self.assertRaises(RuntimeError):
            process(self.parse("@stack 8\n"))

    def test_stack_requires_positive_size(self) -> None:
        with self.assertRaises(RuntimeError):
            process(self.parse("@stack 0\n"))

        with self.assertRaises(RuntimeError):
            process(self.parse("@stack -1\n"))

    def test_define_is_registered_outside_stack(self) -> None:
        process(self.parse("@define mov\n"))

        self.assertEqual(rif_globals.DEFINES, {"mov"})
        self.assertIsNone(rif_globals.STACK)

    def test_defines_are_registered_before_other_nodes(self) -> None:
        process(self.parse("@stack 4\n@define mov\n"))

        self.assertEqual(rif_globals.DEFINES, {"mov"})

    def test_duplicate_define_is_fatal(self) -> None:
        with self.assertRaises(RuntimeError):
            process(self.parse("@define mov\n@define mov\n"))

    def test_table_is_stored_as_matrix_with_constant_column_index(self) -> None:
        process(
            self.parse(
                "@table registers\n"
                "| name | opcode | active |\n"
                "__\n"
                '| mov | 1 | true |\n'
                "__\n"
                '| add | 2 | false |\n'
                "@end\n"
            )
        )

        table = rif_globals.TABLES["registers"]
        self.assertEqual(table.headers, ("name", "opcode", "active"))
        self.assertEqual(table.columns, {"name": 0, "opcode": 1, "active": 2})
        self.assertEqual(table.matrix, (("mov", 1, True), ("add", 2, False)))
        self.assertEqual(set(table.indexes), {"name", "opcode", "active"})

        with self.assertRaises((AttributeError, TypeError)):
            table.matrix += (("sub", 3, True),)
        with self.assertRaises(TypeError):
            table.columns["new"] = 3
        with self.assertRaises(TypeError):
            context = rif_globals.snapshot_target_context()
            context.tables["new"] = table

    def test_table_indexes_keep_literal_types_distinct(self) -> None:
        table = rif_globals.TableData(
            name="typed",
            headers=("key",),
            matrix=((1,), (True,), (1.0,)),
            columns={"key": 0},
        )

        self.assertEqual(table.lookup_unique("key", 1), 0)
        self.assertEqual(table.lookup_unique("key", True), 1)
        self.assertEqual(table.lookup_unique("key", 1.0), 2)

    def test_duplicate_table_is_fatal(self) -> None:
        ast = self.parse(
            "@table values\n"
            "| value |\n"
            "__\n"
            "| 1 |\n"
            "@end\n"
        )
        process(ast)

        with self.assertRaises(RuntimeError):
            process(ast)

    def test_rule_is_registered_with_its_instruction_ast(self) -> None:
        process(
            self.parse(
                "@rule mov:\n"
                ". COMMA\n"
                ". IDENT\n"
            )
        )

        rule = rif_globals.RULES["mov"]
        self.assertEqual(rule.name, "mov")
        self.assertEqual(len(rule.instructions), 2)
        self.assertIsInstance(rule.instructions[0], RawInstruction)
        self.assertEqual(rule.instructions[0].opcode, "consumer")

    def test_duplicate_rule_is_fatal(self) -> None:
        ast = self.parse("@rule mov:\n. IDENT\n")
        process(ast)

        with self.assertRaises(RuntimeError):
            process(ast)

    def test_config_is_materialized_and_validated(self) -> None:
        process(
            self.parse(
                "@block config:\n"
                'format section ".section"\n'
                'section data "rw"\n'
                'section text "rx"\n'
                'section bss "rw"\n'
                'format section_end ":"\n'
                'entry text "_start"\n'
                ''
                'comment ";"\n'
                'format label_end ":"\n'
                ''
                'default text\n'
                ''
                ''
                ''
                'align text 4\n'
                'align data 4\n'
                'align bss 4\n'
                'word_size 32\n'
                'address_size 32\n'
                'byte_order "little"\n'
                'bit_order "lsb"\n'
                'case_sensitive true\n'
                'symbol_prefix "_"\n'
                'local_prefix "."\n'
                'undefined_symbols "error"\n'
                'duplicate_symbols "error"\n'
                'strict true\n'
                'allow_empty_sections false\n'
                "@end\n"
            )
        )

        self.assertEqual(rif_globals.CONFIG.sectiondef, ".section")
        self.assertEqual(rif_globals.CONFIG.sections, ("data", "text", "bss"))
        self.assertEqual(rif_globals.CONFIG.entrysection, "text")
        self.assertEqual(rif_globals.CONFIG.entrylabel, "_start")
        self.assertEqual(rif_globals.CONFIG.comment, ";")
        self.assertEqual(rif_globals.CONFIG.labelend, ":")
        self.assertEqual(rif_globals.CONFIG.datasection, "text")
        self.assertEqual(rif_globals.CONFIG.bitorder, "lsb")

    def test_config_rejects_removed_legacy_names(self) -> None:
        source = (
            "@block config:\n"
            'sectiondef ".section"\n'
            "@end\n"
        )

        with self.assertRaisesRegex(RuntimeError, "desconocida"):
            process(self.parse(source))

    def test_config_requires_declared_entry_and_default_sections(self) -> None:
        source = (
            "@block config:\n"
            'format section ".section"\n'
            'section text "rx"\n'
            'format section_end ":"\n'
            'entry missing "_start"\n'
            ''
            'comment ";"\n'
            'format label_end ":"\n'
            ''
            'default text\n'
            'word_size 32\n'
            'address_size 32\n'
            'byte_order "little"\n'
            'case_sensitive true\n'
            'symbol_prefix "_"\n'
            'local_prefix "."\n'
            'undefined_symbols "error"\n'
            'duplicate_symbols "error"\n'
            'strict true\n'
            'allow_empty_sections false\n'
            "@end\n"
        )

        with self.assertRaises(RuntimeError):
            process(self.parse(source))

    def test_config_rejects_duplicate_directives_and_sections(self) -> None:
        source = (
            "@block config:\n"
            'format section ".section"\n'
            'format section ".segment"\n'
            'section text "rx"\n'
            'section text "rx"\n'
            'format section_end ":"\n'
            'entry text "_start"\n'
            ''
            'comment ";"\n'
            'format label_end ":"\n'
            ''
            'default text\n'
            'word_size 32\n'
            'address_size 32\n'
            'byte_order "little"\n'
            'case_sensitive true\n'
            'symbol_prefix "_"\n'
            'local_prefix "."\n'
            'undefined_symbols "error"\n'
            'duplicate_symbols "error"\n'
            'strict true\n'
            'allow_empty_sections false\n'
            "@end\n"
        )

        with self.assertRaises(RuntimeError):
            process(self.parse(source))

    def test_root_can_load_the_dedicated_config_file(self) -> None:
        config = (
            "@block config:\n"
            'section text "rx"\n'
            "@end\n"
        )
        main = '@LOAD "config.rif"\n@rule nop:\n. IDENT\n'
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.rif").write_text(config, encoding="utf-8")
            main_path = root / "main.rif"
            main_path.write_text(main, encoding="utf-8")

            self.process_file(main_path)

            self.assertEqual(rif_globals.CONFIG.sections, ("text",))
            self.assertIn(str((root / "config.rif").resolve()), rif_globals.LOADED_SOURCES)

    def test_config_file_is_only_loadable_directly_by_root(self) -> None:
        config = '@block config:\nsection text "rx"\n@end\n'
        root_source = '@LOAD "rules.rif"\n'
        rules_source = '@LOAD "config.rif"\n'
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.rif").write_text(config, encoding="utf-8")
            (root / "rules.rif").write_text(rules_source, encoding="utf-8")
            main_path = root / "main.rif"
            main_path.write_text(root_source, encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "no permite estas declaraciones"):
                self.process_file(main_path)

    def test_root_and_config_file_cannot_duplicate_configuration(self) -> None:
        config = '@block config:\nsection text "rx"\n@end\n'
        main = (
            '@block config:\n'
            'section text "rx"\n'
            '@end\n'
            '@LOAD "config.rif"\n'
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.rif").write_text(config, encoding="utf-8")
            main_path = root / "main.rif"
            main_path.write_text(main, encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "Solo puede declararse"):
                self.process_file(main_path)

    def test_linker_is_materialized_without_dag(self) -> None:
        process(
            self.parse(
                "@block linker:\n"
                'extension ".asm"\n'
                ''
                'search_path "variants"\n'
                'search_path "fallback"\n'
                "@end\n"
            )
        )

        self.assertEqual(rif_globals.LINKER.extension, ".asm")
        self.assertEqual(rif_globals.LINKER.search_path, ("variants", "fallback"))

    def test_linker_false_disables_variant_loading(self) -> None:
        process(
            self.parse(
                "@block linker:\n"
                'extension ".asm"\n'
                ''
                "search_path false\n"
                "@end\n"
            )
        )

        self.assertIs(rif_globals.LINKER.search_path, False)

    def test_linker_rejects_mixed_search_paths_and_false(self) -> None:
        source = (
            "@block linker:\n"
            'extension ".asm"\n'
            'search_path "variants"\n'
            "search_path false\n"
            "@end\n"
        )

        with self.assertRaisesRegex(RuntimeError, "no puede combinarse"):
            process(self.parse(source))

    def test_linker_rejects_removed_legacy_names(self) -> None:
        source = (
            "@block linker:\n"
            'ext ".asm"\n'
            'name "main"\n'
            'searching ""\n'
            "@end\n"
        )

        with self.assertRaisesRegex(RuntimeError, "desconocida"):
            process(self.parse(source))


if __name__ == "__main__":
    unittest.main()
