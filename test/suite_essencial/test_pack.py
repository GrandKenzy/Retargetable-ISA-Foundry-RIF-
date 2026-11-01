from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from rif_core.pack import PackReader, create_pack, read_pack
from main import main as rif_main
from rif_core.contract import current_contract


class PackTests(unittest.TestCase):
    def test_pack_omits_legacy_python_functions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            main = root / "main.rif"
            main.write_text("@define main\n", encoding="utf-8")
            (root / "funcs.py").write_text(
                "def handler(name, context):\n    return True\n",
                encoding="utf-8",
            )

            package = create_pack(main)
            with zipfile.ZipFile(package) as archive:
                manifest = json.loads(archive.read("manifest.json"))
                self.assertNotIn("funcs.py", archive.namelist())
                self.assertNotIn("functions", manifest)

    def test_pack_contains_all_rif_sources_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            main = root / "main.rif"
            nested = root / "variants" / "thumb.rif"
            table = root / "tables" / "registers.rif"
            nested.parent.mkdir()
            table.parent.mkdir()
            main.write_text('@LOAD "tables/registers.rif"\n', encoding="utf-8")
            nested.write_text("@define thumb\n", encoding="utf-8")
            table.write_text("@define registers\n", encoding="utf-8")

            package = create_pack(main)
            manifest = read_pack(package)

            self.assertEqual(package, root / "main.pack")
            self.assertEqual(manifest.entrypoint, "sources/main.rif")
            self.assertEqual(
                {entry.path for entry in manifest.files},
                {
                    "sources/main.rif",
                    "sources/tables/registers.rif",
                    "sources/variants/thumb.rif",
                },
            )
            self.assertEqual(
                manifest.load_graph["sources/main.rif"],
                ("sources/tables/registers.rif",),
            )
            self.assertEqual(
                manifest.dependency_order,
                (
                    "sources/tables/registers.rif",
                    "sources/main.rif",
                    "sources/variants/thumb.rif",
                ),
            )
            with zipfile.ZipFile(package) as archive:
                self.assertEqual(
                    set(archive.namelist()),
                    {"manifest.json", *{entry.path for entry in manifest.files}},
                )

            with PackReader(package) as reader:
                self.assertEqual(reader.source_bytes(), main.read_bytes())
                self.assertEqual(
                    reader.dependencies(), ("sources/tables/registers.rif",)
                )
                self.assertEqual(reader.ordered_sources(), manifest.dependency_order)

    def test_pack_variant_search_paths_respect_priority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            main = root / "main.rif"
            first = root / "first" / "thumb.rif"
            second = root / "second" / "thumb.rif"
            first.parent.mkdir()
            second.parent.mkdir()
            main.write_text("@define main\n", encoding="utf-8")
            first.write_text("@define first\n", encoding="utf-8")
            second.write_text("@define second\n", encoding="utf-8")

            package = create_pack(main)

            with PackReader(package) as reader:
                selected = reader.resolve_variant("thumb", ("first", "second"))
                self.assertTrue(selected.endswith("sources/first/thumb.rif"))
                with self.assertRaises(ValueError):
                    reader.resolve_variant("thumb", False)

    def test_pack_is_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            main = root / "main.rif"
            main.write_text("@define main\n", encoding="utf-8")
            first = create_pack(main, root / "first.pack").read_bytes()
            second = create_pack(main, root / "second.pack").read_bytes()

            self.assertEqual(first, second)

            compiled_first = create_pack(
                main,
                root / "compiled-first.pack",
                precompile=True,
            ).read_bytes()
            compiled_second = create_pack(
                main,
                root / "compiled-second.pack",
                precompile=True,
            ).read_bytes()
            self.assertEqual(compiled_first, compiled_second)

    def test_precompiled_pack_stores_tables_in_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            main = root / "main.rif"
            main.write_text(
                "@table registers\n"
                "| name | opcode |\n"
                "__\n"
                '| "mov" | 1 |\n'
                "@end\n"
                "@rule sample:\n"
                ". $registers.opcode, NUMBER\n",
                encoding="utf-8",
            )
            package = create_pack(main, precompile=True)
            manifest = read_pack(package)
            self.assertEqual(manifest.contract, current_contract())

            with PackReader(package) as reader:
                database = reader.compiled_database()
                self.assertIsNotNone(database)
                connection = sqlite3.connect(":memory:")
                try:
                    connection.deserialize(database)
                    self.assertEqual(
                        connection.execute(
                            "SELECT headers_json FROM table_defs WHERE name = 'registers'"
                        ).fetchone()[0],
                        '["name", "opcode"]',
                    )
                    row = connection.execute(
                        "SELECT values_json FROM table_rows "
                        "WHERE table_name = 'registers' AND row_index = 0"
                    ).fetchone()
                    self.assertIsNotNone(row)
                    self.assertIn("mov", row[0])
                    self.assertEqual(
                        connection.execute(
                            "SELECT value FROM meta WHERE key = 'contract_fingerprint'"
                        ).fetchone()[0],
                        manifest.contract.fingerprint(),
                    )
                finally:
                    connection.close()

    def test_read_pack_detects_tampered_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            main = root / "main.rif"
            main.write_text("@define main\n", encoding="utf-8")
            package = create_pack(main)
            rewritten = root / "tampered.pack"
            with zipfile.ZipFile(package, "r") as source, zipfile.ZipFile(
                rewritten, "w", compression=zipfile.ZIP_DEFLATED
            ) as target:
                for info in source.infolist():
                    data = source.read(info.filename)
                    if info.filename == "sources/main.rif":
                        data = b"@define changed\n"
                    target.writestr(info, data)

            with self.assertRaises(ValueError):
                read_pack(rewritten)

    def test_pack_rejects_missing_load_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            main = root / "main.rif"
            main.write_text('@LOAD "missing.rif"\n', encoding="utf-8")

            with self.assertRaises(FileNotFoundError):
                create_pack(main)

    def test_pack_rejects_load_cycles_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            main = root / "main.rif"
            other = root / "other.rif"
            main.write_text('@LOAD "other.rif"\n', encoding="utf-8")
            other.write_text('@LOAD "main.rif"\n', encoding="utf-8")

            with self.assertRaises(ValueError):
                create_pack(main)

    def test_cli_pack_accepts_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            main = root / "main.rif"
            output = root / "amd64.pack"
            main.write_text("@define main\n", encoding="utf-8")

            self.assertEqual(rif_main(["--pack", str(main), "--output", str(output)]), 0)
            self.assertTrue(output.is_file())
            self.assertEqual(read_pack(output).entrypoint, "sources/main.rif")


if __name__ == "__main__":
    unittest.main()
