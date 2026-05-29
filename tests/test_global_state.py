from pathlib import Path
import textwrap
import unittest

from rif.compiler import Compiler
from rif.parser import Parser


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "examples" / "minimal.pack"


class GlobalStateTests(unittest.TestCase):
    def test_program_keeps_own_plugin_state(self):
        first = Parser(PACK.read_text(encoding="utf-8"), PACK).parse()
        other = textwrap.dedent(
            """
            .pack
            plugin "basics"
            types:
                from ".things" as THING

            .things
            | NAME | bits |
            | item | 8 |

            .rules
            noop:
                emit 00000000
            """
        )
        Parser(other, PACK).parse()

        compiler = Compiler(first)

        self.assertEqual(compiler.compile_line("byte 0xf").hex, "0f")
        self.assertEqual(first.type_map["REG"], ".regs")
        self.assertIn("imm", first.operator_bindings["byte"])


if __name__ == "__main__":
    unittest.main()
