from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from Frontend import RIF_LANG_SESSION
from Frontend import globals as rif_globals
from Frontend.processor import enter_variant, exit_variant, load_variants, process


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


class VariantProcessorTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_globals()

    def tearDown(self) -> None:
        reset_globals()

    def parse(self, source: str, path: Path):
        RIF_LANG_SESSION.load()
        tokens = RIF_LANG_SESSION.tokenize(source, str(path))
        return RIF_LANG_SESSION.parse(tokens, str(path))

    @staticmethod
    def declaration(name: str, mode: str = "SWITCH") -> str:
        return (
            f"@SUPPORTS {name}\n"
            f"@ASMVARIANT {name}:\n"
            f".MODE {mode}\n"
            f'.ENTER "ENTER_{name}"\n'
            f'.EXIT "EXIT_{name}"\n'
            "@END\n"
        )

    @staticmethod
    def variant_rules(name: str) -> str:
        return (
            f"@rule ENTER_{name}:\n"
            ". $registers.name, IDENT\n"
            f"@rule EXIT_{name}:\n"
            ". $registers.name, IDENT\n"
        )

    def test_variant_file_is_loaded_with_shared_global_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "main.rif"
            variant = Path(directory) / "thumb.rif"
            root.write_text(
                "@define root_label\n"
                "@table registers\n"
                "| name | opcode |\n"
                "__\n"
                "| mov | 1 |\n"
                "@end\n"
                + self.declaration("thumb"),
                encoding="utf-8",
            )
            variant.write_text(
                "@define thumb_label\n" + self.variant_rules("thumb"),
                encoding="utf-8",
            )

            process(self.parse(root.read_text(encoding="utf-8"), root), root)

            self.assertEqual(rif_globals.DEFINES, {"root_label", "thumb_label"})
            self.assertEqual(rif_globals.TABLES["registers"].matrix, (("mov", 1),))
            self.assertEqual(
                set(rif_globals.RULES), {"ENTER_thumb", "EXIT_thumb"}
            )
            self.assertEqual(rif_globals.RULES["ENTER_thumb"].source_path, str(variant.resolve()))
            self.assertEqual(rif_globals.ASM_VARIANTS["thumb"].mode, "SWITCH")
            self.assertIn(str(variant.resolve()), rif_globals.LOADED_SOURCES)

    def test_variant_files_accept_only_rules_and_defines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "main.rif"
            variant = Path(directory) / "thumb.rif"
            root.write_text(self.declaration("thumb"), encoding="utf-8")
            variant.write_text(
                "@table forbidden\n"
                "| name |\n"
                "__\n"
                "| 1 |\n"
                "@end\n",
                encoding="utf-8",
            )

            with self.assertRaises(RuntimeError):
                process(self.parse(root.read_text(encoding="utf-8"), root), root)

    def test_load_includes_tables_and_rules_relative_to_main(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "main.rif"
            table = Path(directory) / "table.rif"
            rules = Path(directory) / "rules.rif"
            root.write_text(
                '@LOAD "table.rif"\n'
                '@LOAD "rules.rif"\n',
                encoding="utf-8",
            )
            table.write_text(
                "@table registers\n"
                "| name | opcode |\n"
                "__\n"
                "| mov | 1 |\n"
                "@end\n",
                encoding="utf-8",
            )
            rules.write_text(
                "@define loaded_word\n"
                "@rule loaded_rule:\n"
                ". $registers.name, IDENT\n",
                encoding="utf-8",
            )

            process(self.parse(root.read_text(encoding="utf-8"), root), root)

            self.assertEqual(rif_globals.TABLES["registers"].matrix, (("mov", 1),))
            self.assertEqual(rif_globals.DEFINES, {"loaded_word"})
            self.assertEqual(rif_globals.RULES["loaded_rule"].source_path, str(rules.resolve()))
            self.assertIn(str(table.resolve()), rif_globals.LOADED_SOURCES)
            self.assertIn(str(rules.resolve()), rif_globals.LOADED_SOURCES)

    def test_load_requires_rif_and_detects_cycles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "main.rif"
            root.write_text('@LOAD "a.txt"\n', encoding="utf-8")

            with self.assertRaises(RuntimeError):
                process(self.parse(root.read_text(encoding="utf-8"), root), root)

            reset_globals()
            root.write_text('@LOAD "a.rif"\n', encoding="utf-8")
            (Path(directory) / "a.rif").write_text('@LOAD "b.rif"\n', encoding="utf-8")
            (Path(directory) / "b.rif").write_text('@LOAD "a.rif"\n', encoding="utf-8")

            with self.assertRaises(RuntimeError):
                process(self.parse(root.read_text(encoding="utf-8"), root), root)

    def test_search_path_controls_variant_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "main.rif"
            folder = Path(directory) / "variants"
            folder.mkdir()
            variant = folder / "thumb.rif"
            root.write_text(
                "@block linker:\n"
                'extension ".rif"\n'
                ''
                'search_path "variants"\n'
                "@end\n"
                + self.declaration("thumb"),
                encoding="utf-8",
            )
            variant.write_text(self.variant_rules("thumb"), encoding="utf-8")

            process(self.parse(root.read_text(encoding="utf-8"), root), root)

            self.assertIn(str(variant.resolve()), rif_globals.LOADED_SOURCES)

    def test_search_paths_use_declared_priority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "main.rif"
            first = Path(directory) / "first"
            second = Path(directory) / "second"
            first.mkdir()
            second.mkdir()
            first_variant = first / "thumb.rif"
            second_variant = second / "thumb.rif"
            first_variant.write_text(self.variant_rules("thumb"), encoding="utf-8")
            second_variant.write_text(self.variant_rules("thumb"), encoding="utf-8")
            root.write_text(
                "@block linker:\n"
                'extension ".rif"\n'
                'search_path "first"\n'
                'search_path "second"\n'
                "@end\n"
                + self.declaration("thumb"),
                encoding="utf-8",
            )

            process(self.parse(root.read_text(encoding="utf-8"), root), root)

            self.assertIn(str(first_variant.resolve()), rif_globals.LOADED_SOURCES)
            self.assertNotIn(str(second_variant.resolve()), rif_globals.LOADED_SOURCES)

    def test_search_path_false_rejects_automatic_loading(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "main.rif"
            root.write_text(
                "@block linker:\n"
                'extension ".rif"\n'
                ''
                "search_path false\n"
                "@end\n"
                + self.declaration("thumb"),
                encoding="utf-8",
            )

            with self.assertRaises(RuntimeError):
                process(self.parse(root.read_text(encoding="utf-8"), root), root)

    def test_variant_requires_support_declaration_and_existing_rules(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "main.rif"
            root.write_text(
                "@ASMVARIANT thumb:\n"
                ".MODE SWITCH\n"
                '.ENTER "ENTER_thumb"\n'
                '.EXIT "EXIT_thumb"\n'
                "@END\n",
                encoding="utf-8",
            )

            with self.assertRaises(RuntimeError):
                process(self.parse(root.read_text(encoding="utf-8"), root), root)

    def test_variant_file_cannot_define_global_config_or_linker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "main.rif"
            variant = Path(directory) / "thumb.rif"
            root.write_text(self.declaration("thumb"), encoding="utf-8")
            variant.write_text(
                "@block linker:\n"
                'extension ".rif"\n'
                'search_path ""\n'
                "@end\n",
                encoding="utf-8",
            )

            with self.assertRaises(RuntimeError):
                process(self.parse(root.read_text(encoding="utf-8"), root), root)

    def test_variant_requires_entry_and_exit_rules(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "main.rif"
            variant = Path(directory) / "thumb.rif"
            root.write_text(self.declaration("thumb"), encoding="utf-8")
            variant.write_text("@define only_a_label\n", encoding="utf-8")

            with self.assertRaises(RuntimeError):
                process(self.parse(root.read_text(encoding="utf-8"), root), root)

    def test_variant_runtime_stack_preserves_return_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "main.rif"
            variant = Path(directory) / "thumb.rif"
            root.write_text(self.declaration("thumb"), encoding="utf-8")
            variant.write_text(self.variant_rules("thumb"), encoding="utf-8")
            process(self.parse(root.read_text(encoding="utf-8"), root), root)

            frame = enter_variant("thumb", root, 17, return_rule="resume")
            self.assertEqual(frame.return_rule, "resume")
            self.assertEqual(rif_globals.VARIANT_STACK[-1], frame)
            closed = exit_variant("thumb")
            self.assertEqual(closed, frame)
            self.assertFalse(rif_globals.VARIANT_STACK)

    def test_many_variant_files_load_without_cross_contamination(self) -> None:
        count = 100
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "main.rif"
            root.write_text(
                "".join(self.declaration(f"v{index}") for index in range(count)),
                encoding="utf-8",
            )
            for index in range(count):
                (Path(directory) / f"v{index}.rif").write_text(
                    self.variant_rules(f"v{index}"),
                    encoding="utf-8",
                )

            process(self.parse(root.read_text(encoding="utf-8"), root), root)

            # El caché de rutas permite volver a resolver sin reparsear ni
            # volver a registrar las Rules ya cargadas.
            load_variants(root)

            self.assertEqual(len(rif_globals.SUPPORTS), count)
            self.assertEqual(len(rif_globals.ASM_VARIANTS), count)
            self.assertEqual(len(rif_globals.LOADED_SOURCES), count + 1)
            self.assertEqual(len(rif_globals.RULES), count * 2)


if __name__ == "__main__":
    unittest.main()
