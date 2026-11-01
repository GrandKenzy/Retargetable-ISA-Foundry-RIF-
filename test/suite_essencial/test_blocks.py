from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from MIR import compile_source
from rif_core.pack import create_pack


CONFIG_BLOCK = '''\
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
    bit_order "msb"
@end

@block metadata:
    kind "pcpi" "source"
    version 1
@end

@rule sample:
. eword 1
'''


class GenericBlockTests(unittest.TestCase):
    def test_compact_config_uses_defaults(self) -> None:
        source = (
            "@block config:\n"
            'format section ".section"\n'
            'section text "rx"\n'
            'entry text "_start"\n'
            "default text\n"
            "word_size 32\n"
            "address_size 32\n"
            "byte_order little\n"
            "@end\n"
            "@rule nop:\n"
            ". eword 0\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "compact.rif"
            path.write_text(source, encoding="utf-8")

            program = compile_source(path)

        config = program.context.config
        self.assertEqual(config.sections, ("text",))
        self.assertEqual(config.sectionflags, {"text": "rx"})
        self.assertEqual(config.sectionend, ":")
        self.assertEqual(config.comment, ";")
        self.assertEqual(config.bitorder, "msb")
        self.assertEqual(config.allowemptysections, False)

    def test_generic_config_and_unknown_blocks_are_materialized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "generic.rif"
            source.write_text(CONFIG_BLOCK, encoding="utf-8")

            program = compile_source(source)

            self.assertIsNotNone(program.context.config)
            self.assertEqual(program.context.config.wordsize, 8)
            self.assertEqual(
                program.context.blocks["metadata"][0].entries[0].name,
                "kind",
            )
            self.assertEqual(
                [value.value for value in program.context.blocks["metadata"][0].entries[0].values],
                ["pcpi", "source"],
            )

    def test_generic_block_rejects_more_than_two_values(self) -> None:
        source = CONFIG_BLOCK.replace(
            'kind "pcpi" "source"',
            'kind "pcpi" "source" "extra"',
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.rif"
            path.write_text(source, encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "como máximo dos valores"):
                compile_source(path)

    def test_generic_block_rejects_legacy_dot_prefix(self) -> None:
        source = CONFIG_BLOCK.replace(
            'format section ".section"',
            '.format ".section"',
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.rif"
            path.write_text(source, encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "sin prefijo"):
                compile_source(path)

    def test_generic_blocks_survive_precompiled_pack_loading(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "generic.rif"
            package = Path(directory) / "generic.pack"
            source.write_text(CONFIG_BLOCK, encoding="utf-8")

            create_pack(source, package, precompile=True)
            loaded = compile_source(package)

            self.assertEqual(
                loaded.context.blocks["metadata"][0].entries[1].values[0].value,
                1,
            )


if __name__ == "__main__":
    unittest.main()
