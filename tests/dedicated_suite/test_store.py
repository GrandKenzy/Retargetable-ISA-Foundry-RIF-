from __future__ import annotations

import struct
import tempfile
import unittest
import wave
from unittest.mock import patch
from pathlib import Path

from MIR.storage import StorageBuilder, parse_storage
from rif_tools.store import StoreError, compile_store, compile_store_file, parse_store


class StoreTests(unittest.TestCase):
    def _write_sources(self, root: Path) -> Path:
        from PIL import Image

        Image.new("RGBA", (1, 1), (1, 2, 3, 4)).save(root / "pixel.png")
        with wave.open(str(root / "tone.wav"), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(8000)
            stream.writeframes(struct.pack("<h", 7))
        source = root / "datos.store"
        source.write_text(
            'MAGIC "store"\n'
            "VERSION 1\n\n"
            "@ITEM IMAGE\n"
            ': "pixel.png"\n'
            ': "png"\n'
            ': "RGB888"\n'
            ": miImage\n"
            "@end\n\n"
            "@ITEM AUDIO\n"
            ': "tone.wav"\n'
            ': "wav"\n'
            ': "PCM_S16LE"\n'
            ": miAudio\n"
            "@end\n",
            encoding="utf-8",
        )
        return source

    def test_store_compiles_labeled_raw_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = self._write_sources(Path(directory))
            definition = parse_store(source)
            result = compile_store(source)
            storage = parse_storage(result.storage)

        self.assertEqual(definition.version, 1)
        self.assertEqual([item.label for item in definition.items], ["miImage", "miAudio"])
        self.assertEqual(storage.payload("miImage"), bytes((1, 2, 3)))
        self.assertEqual(storage.payload("miAudio"), struct.pack("<h", 7))

    def test_store_rejects_duplicate_labels(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "bad.store"
            source.write_text(
                'MAGIC "store"\nVERSION 1\n'
                '@ITEM IMAGE\n: "a.png"\n: "png"\n: "RGB888"\n: same\n@end\n'
                '@ITEM IMAGE\n: "b.png"\n: "png"\n: "RGB888"\n: same\n@end\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(StoreError, "duplicado"):
                parse_store(source)

    def test_store_copies_opaque_binary_payloads_without_a_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = bytes((0, 1, 2, 0xFF, 0x52, 0x49, 0x46))
            (root / "variables.bin").write_bytes(payload)
            source = root / "variables.store"
            source.write_text(
                'MAGIC "store"\n'
                "VERSION 1\n"
                "@ITEM BINARY\n"
                ': "variables.bin"\n'
                ': "bin"\n'
                ': "RAW"\n'
                ": config_blob\n"
                "@end\n",
                encoding="utf-8",
            )

            result = compile_store(source)
            storage = parse_storage(result.storage)

        self.assertEqual(storage.payload("config_blob"), payload)

    def test_store_encodes_typed_values_without_runtime_logic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "values.store"
            source.write_text(
                'MAGIC "store"\n'
                "VERSION 2\n"
                'str greeting = "Hola, mundo"\n'
                "uint8 age = 30\n"
                "int32 count = -2\n"
                "float32 decimal = 13.0000\n",
                encoding="utf-8",
            )

            storage = parse_storage(compile_store(source).storage)

        self.assertEqual(storage.payload("greeting"), b"Hola, mundo")
        self.assertEqual(storage.payload("age"), b"\x1e")
        self.assertEqual(storage.payload("count"), b"\xfe\xff\xff\xff")
        self.assertEqual(storage.payload("decimal"), struct.pack("<f", 13.0))
        self.assertEqual(storage.value_type("age"), "uint8")
        self.assertEqual(storage.value_type("count"), "int32")
        self.assertEqual(storage.value_type("greeting"), "str")

    def test_store_loads_files_and_reuses_selected_container_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "myfile.bin").write_bytes(b"file")
            other = StorageBuilder()
            other.add(b"one", label="etiqueta1")
            other.add(b"two", label="etiqueta2")
            (root / "variables.bin").write_bytes(other.build())
            source = root / "imports.store"
            source.write_text(
                'MAGIC "store"\n'
                "VERSION 1\n"
                '@FILE "myfile.bin"\n'
                '@CONTAINER "variables.bin":\n'
                "    get etiqueta1\n"
                "    get etiqueta2\n",
                encoding="utf-8",
            )

            storage = parse_storage(compile_store(source).storage)

        self.assertEqual(storage.payload("myfile"), b"file")
        self.assertEqual(storage.payload("etiqueta1"), b"one")
        self.assertEqual(storage.payload("etiqueta2"), b"two")

    def test_store_reqst_uses_the_bounded_binary_fetcher(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "remote.store"
            source.write_text(
                'MAGIC "store"\n'
                "VERSION 2\n"
                '@REQST algo "github.com/example/repo/data.bin/main"\n',
                encoding="utf-8",
            )

            with patch("rif_tools.store.reqsts", return_value=b"remote") as fetch:
                storage = parse_storage(compile_store(source).storage)

        fetch.assert_called_once_with("github.com/example/repo/data.bin/main")
        self.assertEqual(storage.payload("algo"), b"remote")

    def test_store_output_is_written_as_storage_bin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._write_sources(root)
            output = root / "storage.bin"
            result = compile_store_file(source, output)
            self.assertEqual(result, output.resolve())
            self.assertEqual(parse_storage(output.read_bytes()).payload("miImage"), bytes((1, 2, 3)))


if __name__ == "__main__":
    unittest.main()
