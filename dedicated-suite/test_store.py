from __future__ import annotations

import struct
import tempfile
import unittest
import wave
from pathlib import Path

from MIR.storage import parse_storage
from store import StoreError, compile_store, compile_store_file, parse_store


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
