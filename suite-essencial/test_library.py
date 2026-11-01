from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from MIR import compile_pack, compile_source
from pack import PackReader, create_pack
from rif_library import LibraryReader, create_library


class LibraryTests(unittest.TestCase):
    def test_riflib_loads_reusable_rules_and_is_packaged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library_root = root / "patterns"
            library_root.mkdir()
            library_source = library_root / "patterns.rif"
            library_source.write_text(
                '@define LIB_PATTERN\n'
                '@rule library_rule:\n'
                '. KW "ok"\n',
                encoding="utf-8",
            )
            library_path = root / "patterns.riflib"
            create_library(library_source, library_path)

            target = root / "target.rif"
            target.write_text(
                '@LIBRARY "patterns.riflib"\n'
                '@rule local_rule:\n'
                '. KW "local"\n',
                encoding="utf-8",
            )
            program = compile_source(target, backend="python")
            self.assertEqual(set(program.rules), {"library_rule", "local_rule"})
            native = compile_source(target, backend="aot")
            self.assertEqual(set(native.rules), {"library_rule", "local_rule"})

            package = create_pack(target)
            with PackReader(package) as reader:
                self.assertEqual(len(reader.manifest.libraries), 1)
                self.assertTrue(reader.resolve_library(reader.virtual_path(), "patterns.riflib"))
            packed = compile_pack(package, backend="python")
            self.assertEqual(set(packed.rules), {"library_rule", "local_rule"})
            packed_native = compile_pack(package, backend="aot")
            self.assertEqual(set(packed_native.rules), {"library_rule", "local_rule"})

    def test_library_reader_rejects_zip_extras_and_exposes_virtual_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "lib.rif"
            source.write_text('@rule only_rule:\n. KW "ok"\n', encoding="utf-8")
            library = create_library(source)
            with LibraryReader(library) as reader:
                self.assertTrue(reader.virtual_path().startswith("riflib://"))
                self.assertIn("only_rule", reader.source_text())


if __name__ == "__main__":
    unittest.main()
