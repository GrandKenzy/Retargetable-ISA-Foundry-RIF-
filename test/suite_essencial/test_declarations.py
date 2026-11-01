from __future__ import annotations

import unittest

from Frontend import RIF_LANG_SESSION


class DeclarationTests(unittest.TestCase):
    def parse(self, source: str):
        RIF_LANG_SESSION.load()
        tokens = RIF_LANG_SESSION.tokenize(source, "declarations.rif")
        return RIF_LANG_SESSION.parse(tokens, "declarations.rif")

    def test_define_and_rule_declarations(self) -> None:
        ast = self.parse(
            "@define mov\n"
            "@define add\n"
            "@rule mov:\n"
            "      . $registros.name, DOT\n"
            ". COMMA\n"
            ". AT\n"
            ". IDENT\n"
            ". [NUMBER, STRING]\n"
            "@rule add:\n"
            ". $registros.name, AT\n"
            ". $registros.name, 7\n"
            ". nibbles 0000 0000\n"
            ". nibbles $register.opcode 0000\n"
            ". emit 0 0 0 0 0 0 0 0\n"
            ". emit $register.bits 0 0 0 0 0 0 0\n"
            ". eword 83847483\n"
            ". eword $register.value\n"
            '. KW "ret"\n'
            ". JUMPIF add, true\n"
            ". JUMPIF add, True\n"
            ". JUMPIF add, #call[mifuncion]\n"
            ". eword #call[mifuncion]\n"
            ". BREAK\n"
            '. ERROR, "cualquier cosa"\n'
            ". JUMP add\n"
            '. save "name"\n'
            '. load "name"\n'
            '. reserve "buffer" 16\n'
            '. write_res "buffer" 0028383\n'
            '. write_res "buffer" $register.value\n'
            '. write_res "buffer" &buffer\n'
            ". nibbles &buffer 0000\n"
            ". eword &buffer\n"
            '. drop_res "buffer"\n'
            '. emit_res "buffer"\n'
            ". frame 0000 $register.word 0\n"
            "0\n"
            "&buffer\n"
            "\n"
            "0000\n"
            "0\n"
            "0000\n"
            "0000000\n"
            "0000\n"
            ". frameend\n"
            "@stack 50\n"
        )

        self.assertIsNotNone(ast)
        self.assertEqual(len(ast), 5)

    def test_declarations_and_table_can_share_entrypoint(self) -> None:
        ast = self.parse(
            "@define mov\n"
            "@rule mov:\n"
            "@table example\n"
            "| name | age |\n"
            "__\n"
            '| "Ken" | 23 |\n'
            "@end\n"
        )

        self.assertIsNotNone(ast)
        self.assertEqual(len(ast), 3)

    def test_config_can_share_entrypoint(self) -> None:
        ast = self.parse(
            "@block config:\n"
            'format section ".section"\n'
            'section data ""\n'
            'format section_end ":"\n'
            'entry data "_start"\n'
            ''
            'comment ";"\n'
            'format label_end ":"\n'
            ''
            'default data\n'
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

        self.assertIsNotNone(ast)
        self.assertEqual(len(ast), 1)
        self.assertEqual(ast[0].name, "BLOCK")

    def test_linker_can_share_entrypoint(self) -> None:
        ast = self.parse(
            "@block linker:\n"
            'extension ".asm"\n'
            ''
            'search_path "lib"\n'
            "@end\n"
        )

        self.assertIsNotNone(ast)
        self.assertEqual(len(ast), 1)
        self.assertEqual(ast[0].name, "BLOCK")

    def test_legacy_config_syntax_is_not_accepted(self) -> None:
        with self.assertRaises(SystemExit):
            self.parse(
                "@config:\n"
                'format section ".section"\n'
                "@configend\n"
            )


if __name__ == "__main__":
    unittest.main()
