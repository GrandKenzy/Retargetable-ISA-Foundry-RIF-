from pathlib import Path
import unittest

from rif.compiler import Compiler
from rif.parser import Parser, collect_codegen, parse_packer_config


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "examples" / "minimal.pack"


class ExamplePackTests(unittest.TestCase):
    def test_ast_and_codegen_are_separate(self):
        text = PACK.read_text(encoding="utf-8")
        program = Parser(text, PACK).parse_ast()

        self.assertEqual(program.codegen.expressions, [])
        self.assertEqual(program.operator_bindings, {})

        collect_codegen(program)

        self.assertIn("byte", program.codegen.expressions_by_rule)
        self.assertIn("imm", program.operator_bindings["byte"])

    def test_config_and_world(self):
        program = Parser(PACK.read_text(encoding="utf-8"), PACK).parse()
        config = parse_packer_config(program)

        self.assertEqual(program.world.values["arch"], "example8")
        self.assertEqual(config.plugins, ["basics"])
        self.assertEqual(program.type_map["REG"], ".regs")
        self.assertIn("callstack", program.memory.regions)
        self.assertIn("arena", program.memory.regions)

    def test_compile_rules(self):
        compiler = Compiler.from_file(PACK)

        self.assertEqual(compiler.compile_line("byte 0x2a").hex, "2a")
        self.assertEqual(compiler.compile_line("byte 0xf").hex, "0f")
        self.assertEqual(compiler.compile_line("regbyte a").hex, "00")
        self.assertEqual(compiler.compile_line("regbyte b").hex, "01")
        self.assertEqual(compiler.compile_line("pair").hex, "f0")
        self.assertEqual(compiler.compile_line("branchfalse").hex, "00")
        self.assertEqual(compiler.compile_line("callsite").hex, "cc")
        self.assertEqual(compiler.compile_line("stop").hex, "00")

    def test_data_memory_and_relocations(self):
        compiler = Compiler.from_file(PACK)

        data = compiler.compile_line("msg char[2] = Hi")
        self.assertEqual(data.hex, "4869")
        self.assertIn("msg[0]", compiler.program.objects)
        self.assertIn("msg[1]", compiler.program.objects)

        self.assertEqual(compiler.compile_line("stack temp b8 4 bss 1 0").hex, "")
        self.assertEqual(compiler.program.memory.regions["temp"].bytes, 4)

        reloc = compiler.compile_line("relocabs")
        self.assertEqual(reloc.hex, "00")
        self.assertEqual([(r.kind, r.target, r.width) for r in reloc.relocations], [("abs", "external_symbol", 8)])

    def test_program_source_compiles(self):
        compiler = Compiler.from_file(PACK)
        source = (ROOT / "examples" / "program.rif").read_text(encoding="utf-8")
        results = compiler.compile_lines(source)

        self.assertEqual(results[0].hex, "2a")
        self.assertTrue(any(result.rule_name == "data" for result in results))
        self.assertIn("temp", compiler.program.memory.regions)
        self.assertIn("bag", compiler.program.memory.regions)


if __name__ == "__main__":
    unittest.main()
