from __future__ import annotations

import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from pack import PackReader, create_pack, read_pack


class PackStressTests(unittest.TestCase):
    def _make_chain(self, root: Path, count: int) -> Path:
        project = root / "project"
        nodes = project / "nodes"
        nodes.mkdir(parents=True)
        for index in range(count - 1, -1, -1):
            body = f"@define node_{index}\n"
            if index + 1 < count:
                body = f'@LOAD "node_{index + 1:04d}.rif"\n' + body
            (nodes / f"node_{index:04d}.rif").write_text(body, encoding="utf-8")
        main = project / "main.rif"
        main.write_text('@LOAD "nodes/node_0000.rif"\n', encoding="utf-8")
        return main

    def test_large_dependency_chain_is_indexed_and_read_without_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            main = self._make_chain(root, 256)
            package = root / "chain.pack"
            create_pack(main, package)

            project = root / "project"
            shutil.rmtree(project)

            manifest = read_pack(package)
            self.assertEqual(len(manifest.files), 257)
            self.assertEqual(len(manifest.load_graph), 257)
            self.assertEqual(len(manifest.dependency_order), 257)
            self.assertEqual(
                manifest.dependency_order[0], "sources/nodes/node_0255.rif"
            )
            self.assertEqual(manifest.dependency_order[-1], "sources/main.rif")
            with PackReader(package) as reader:
                self.assertIn("@define node_255", reader.source_text("nodes/node_0255.rif"))
                self.assertEqual(
                    reader.dependencies("main.rif"), ("sources/nodes/node_0000.rif",)
                )

    def test_large_sources_preserve_bytes_and_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            main = root / "main.rif"
            payload = "@define large\n" + ("; payload\n" * 50_000)
            main.write_text(payload, encoding="utf-8")
            package = create_pack(main)

            manifest = read_pack(package)
            entry = next(item for item in manifest.files if item.path == "sources/main.rif")
            self.assertEqual(entry.size, len(main.read_bytes()))
            with PackReader(package) as reader:
                self.assertEqual(reader.source_bytes(), main.read_bytes())

    def test_pack_does_not_include_unrelated_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            main = root / "main.rif"
            main.write_text("@define main\n", encoding="utf-8")
            (root / "notes.txt").write_text("not RIF", encoding="utf-8")
            (root / "source.py").write_text("print('no')", encoding="utf-8")
            (root / "nested").mkdir()
            (root / "nested" / "also.rif").write_text("@define nested\n", encoding="utf-8")

            package = create_pack(main)
            with zipfile.ZipFile(package) as archive:
                names = set(archive.namelist())
            self.assertIn("sources/main.rif", names)
            self.assertIn("sources/nested/also.rif", names)
            self.assertNotIn("notes.txt", names)
            self.assertNotIn("sources/notes.txt", names)
            self.assertNotIn("source.py", names)

    def test_manifest_graph_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            main = self._make_chain(root, 3)
            package = create_pack(main)
            tampered = root / "tampered.pack"

            with zipfile.ZipFile(package, "r") as source:
                manifest = json.loads(source.read("manifest.json"))
                manifest["dependency_order"] = list(reversed(manifest["dependency_order"]))
                with zipfile.ZipFile(tampered, "w", compression=zipfile.ZIP_DEFLATED) as target:
                    for info in source.infolist():
                        data = source.read(info.filename)
                        if info.filename == "manifest.json":
                            data = (json.dumps(manifest, sort_keys=True) + "\n").encode()
                        target.writestr(info, data)

            with self.assertRaises(ValueError):
                read_pack(tampered)

    def test_load_cycle_is_rejected_even_when_deep(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            count = 128
            for index in range(count):
                next_index = (index + 1) % count
                (project / f"node{index}.rif").write_text(
                    f'@LOAD "node{next_index}.rif"\n', encoding="utf-8"
                )

            with self.assertRaisesRegex(ValueError, "Ciclo de @LOAD"):
                create_pack(project / "node0.rif")


if __name__ == "__main__":
    unittest.main()
