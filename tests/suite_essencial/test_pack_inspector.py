from __future__ import annotations

import json
import hashlib
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from rif_core.pack import create_pack
from rif_tools.pack_inspector import PackInspectionError, inspect_pack, render_pack_inspection
from main import main as rif_main


CONFIG = '''\
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
@end

@block linker:
    extension ".asm"
    search_path ""
@end
'''


class PackInspectorTests(unittest.TestCase):
    def _source(self) -> str:
        return CONFIG + '''\
@table registers
| name | opcode |
__
| "mov" | 1 |
__
| "add" | 3 |
@end

@rule nop:
. eword 0

@rule emit:
. eword 1
'''

    def test_inspector_reports_target_contract_without_executing_rules(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "main.rif"
            package = root / "target.pack"
            source.write_text(self._source(), encoding="utf-8")
            create_pack(source, package, precompile=True)

            report = inspect_pack(package)

            self.assertTrue(report["tool"]["verified"])
            self.assertEqual(report["package"]["format"], "RIF_PACK")
            self.assertEqual(
                report["package"]["contract"],
                report["compiled"]["contract"],
            )
            self.assertEqual(
                report["package"]["contract_fingerprint"],
                report["compiled"]["contract_fingerprint"],
            )
            self.assertEqual(report["compiled"]["schema_version"], 7)
            self.assertEqual(report["compiled"]["linker"]["extension"], ".asm")
            self.assertEqual(report["compiled"]["config"]["word_size"], 8)
            self.assertEqual(report["compiled"]["rules"]["count"], 2)
            self.assertEqual(report["compiled"]["tables"]["items"][0]["row_count"], 2)
            self.assertIn("RIF_INSERT", report["compiled"]["mir"]["preprocessor_directives"])

    def test_json_and_human_renderers_are_bounded_and_stable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "main.rif"
            package = root / "target.pack"
            source.write_text(self._source(), encoding="utf-8")
            create_pack(source, package, precompile=True)

            report = inspect_pack(package, verbose=True, max_items=1)
            encoded = render_pack_inspection(report, json_output=True)
            human = render_pack_inspection(report)

            self.assertEqual(json.loads(encoded), report)
            self.assertIn("RIF PACK INSPECT", human)
            self.assertIn("rules truncated by max_items", human)
            self.assertIn("rows_truncated", encoded)

    def test_source_only_package_is_inspectable_without_compiled_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "main.rif"
            package = root / "target.pack"
            source.write_text("@define safe\n", encoding="utf-8")
            create_pack(source, package, precompile=False)

            report = inspect_pack(package)

            self.assertFalse(report["compiled"]["present"])
            self.assertIn("source-only", render_pack_inspection(report))

    def test_cli_inspection_is_read_only_and_supports_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "main.rif"
            package = root / "target.pack"
            source.write_text(self._source(), encoding="utf-8")
            create_pack(source, package, precompile=True)

            import contextlib
            import io

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = rif_main(["--inspect-pack", str(package), "--json"])

            self.assertEqual(result, 0)
            payload = json.loads(stdout.getvalue())
            self.assertTrue(payload["tool"]["verified"])
            self.assertTrue(package.is_file())
            self.assertTrue(source.is_file())

    def test_inspector_rejects_structurally_corrupt_compiled_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "main.rif"
            package = root / "target.pack"
            tampered = root / "tampered.pack"
            source.write_text(self._source(), encoding="utf-8")
            create_pack(source, package, precompile=True)

            with zipfile.ZipFile(package, "r") as original:
                entries = {
                    info.filename: original.read(info)
                    for info in original.infolist()
                }
            connection = sqlite3.connect(":memory:")
            try:
                connection.deserialize(entries["compiled/program.sqlite3"])
                connection.execute(
                    "UPDATE table_columns SET column_index = 99 "
                    "WHERE table_name = 'registers' AND column_name = 'opcode'"
                )
                connection.commit()
                compiled = connection.serialize()
            finally:
                connection.close()

            manifest = json.loads(entries["manifest.json"])
            manifest["compiled"]["size"] = len(compiled)
            manifest["compiled"]["sha256"] = hashlib.sha256(compiled).hexdigest()
            entries["compiled/program.sqlite3"] = compiled
            entries["manifest.json"] = (
                json.dumps(manifest, sort_keys=True).encode("utf-8") + b"\n"
            )
            with zipfile.ZipFile(tampered, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, data in entries.items():
                    archive.writestr(name, data)

            with self.assertRaisesRegex(PackInspectionError, "índice de columnas"):
                inspect_pack(tampered)

    def test_inspector_wraps_malformed_zip_and_rejects_unbounded_report_limits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            malformed = Path(directory) / "malformed.pack"
            malformed.write_bytes(b"not a zip")

            with self.assertRaises(PackInspectionError):
                inspect_pack(malformed)
            with self.assertRaises(ValueError):
                inspect_pack(malformed, max_items=0)


if __name__ == "__main__":
    unittest.main()
