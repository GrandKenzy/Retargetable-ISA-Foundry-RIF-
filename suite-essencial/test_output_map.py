from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from MIR import compile_definition, compile_mir_source


TARGET = '''\
@block config:
    format section ".section"
    section text "rx"
    entry text "_start"
    default text
    word_size 8
    address_size 8
    byte_order "little"
    case_sensitive true
    undefined_symbols "error"
    duplicate_symbols "error"
    strict true
    allow_empty_sections false
@end

@block linker:
    extension ".mir"
    search_path ""
@end

@rule emit:
. IDENT
. bits 144 8
'''


class OutputMapTests(unittest.TestCase):
    def test_map_is_optional_and_contains_finalized_image_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.rif"
            output_map = root / "result.map.json"
            target.write_text(TARGET, encoding="utf-8")
            program = compile_definition(target)

            result = compile_mir_source(
                program,
                "emit\n",
                map_output=output_map,
            )

            self.assertEqual(result.binary, b"\x90")
            report = json.loads(output_map.read_text(encoding="utf-8"))
            self.assertEqual(report["format"], "RIF_OUTPUT_MAP")
            self.assertEqual(report["binary"]["size"], 1)
            self.assertEqual(report["sections"][0]["file_size"], 1)
            self.assertEqual(report["mir"]["executed_rules"][0]["rule"], "emit")
            self.assertEqual(report["rules"][0]["name"], "emit")
            self.assertEqual(result.output_map(), report)


if __name__ == "__main__":
    unittest.main()
