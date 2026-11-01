from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from Frontend import globals as rif_globals
from MIR import DiagnosticBag, compile_project, compile_source
from pack import create_pack, read_pack


DEMO_TARGET = (
    Path(__file__).resolve().parents[2]
    / "examples"
    / "RIF-Core-Demo"
    / "main.rif"
)


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


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_globals()

    def tearDown(self) -> None:
        reset_globals()

    def test_compile_source_runs_the_full_frontend_pipeline(self) -> None:
        program = compile_source(DEMO_TARGET)

        self.assertEqual(set(program.rules), {"mov", "add", "ret"})
        self.assertIsNotNone(rif_globals.CONFIG)
        self.assertEqual(rif_globals.CONFIG.sections, ("data", "text", "bss"))

    def test_assembly_image_renders_configured_sections_and_bytes(self) -> None:
        compilation = compile_project(DEMO_TARGET)
        emitter = compilation.image.emitter("text")
        emitter.nibbles("1010", "0101")

        output = compilation.image.render()

        self.assertIn(".section text:", output)
        self.assertIn("_start:", output)
        self.assertIn(".byte 0xa5", output)
        self.assertNotIn(".section data:", output)

    def test_compile_source_accepts_pack_and_resolves_loads_from_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            main = root / "main.rif"
            rules = root / "rules.rif"
            main.write_text('@LOAD "rules.rif"\n', encoding="utf-8")
            rules.write_text(
                "@rule sample:\n"
                ". nibbles 0000 0000\n",
                encoding="utf-8",
            )
            package = create_pack(main)

            direct = compile_source(main)
            reset_globals()
            packed = compile_source(package)

            self.assertEqual(set(direct.rules), {"sample"})
            self.assertEqual(set(packed.rules), set(direct.rules))
            self.assertEqual(
                packed.rules["sample"].instructions[0].operands[0].width,
                4,
            )
            self.assertIn("sources/rules.rif", read_pack(package).load_graph["sources/main.rif"])

            compiled_package = create_pack(
                main,
                root / "compiled.pack",
                precompile=True,
            )
            reset_globals()
            compiled = compile_source(compiled_package)
            self.assertEqual(set(compiled.rules), {"sample"})
            self.assertEqual(
                compiled.rules["sample"].instructions[0].operands[0].width,
                4,
            )

    def test_frontend_errors_use_the_shared_diagnostic_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "broken.rif"
            source.write_text("@rule broken:\n. unknown_opcode\n", encoding="utf-8")
            diagnostics = DiagnosticBag()
            with self.assertRaises(Exception):
                compile_source(source, backend="python", diagnostics=diagnostics)

        self.assertEqual(len(diagnostics.items), 1)
        self.assertEqual(diagnostics.items[0].phase, "frontend")
        self.assertEqual(diagnostics.items[0].path, str(source))


if __name__ == "__main__":
    unittest.main()
