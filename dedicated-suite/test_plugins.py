from __future__ import annotations

import importlib.util
import struct
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from plugins import PluginError, convert_audio, convert_image


HAS_PILLOW = importlib.util.find_spec("PIL") is not None
HAS_AUDIO = (
    importlib.util.find_spec("soundfile") is not None
    and importlib.util.find_spec("numpy") is not None
)


class PluginInputTests(unittest.TestCase):
    def test_plugins_reject_urls_and_bytes(self) -> None:
        with self.assertRaises(PluginError):
            convert_image("https://example.com/image.png")
        with self.assertRaises(PluginError):
            convert_audio(b"local.wav")


@unittest.skipUnless(HAS_PILLOW, "Pillow no está instalado")
class ImagePluginTests(unittest.TestCase):
    def test_image_is_converted_to_row_major_rgba8888(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "pixel.png"
            Image.new("RGBA", (2, 1), (1, 2, 3, 4)).save(source)
            result = convert_image(source)

        self.assertIsInstance(result, bytes)
        self.assertEqual(result, bytes((1, 2, 3, 4)) * 2)

    def test_image_is_converted_to_bgrx8888_with_transparency_over_black(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "pixel.png"
            Image.new("RGBA", (2, 1), (10, 20, 30, 128)).save(source)
            result = convert_image(source, "BGRX8888")

        self.assertEqual(result, bytes((15, 10, 5, 0)) * 2)


@unittest.skipUnless(HAS_AUDIO, "soundfile/numpy no están instalados")
class AudioPluginTests(unittest.TestCase):
    def test_audio_is_converted_to_interleaved_pcm16le(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "tone.wav"
            with wave.open(str(source), "wb") as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(8000)
                stream.writeframes(struct.pack("<hh", -2, 3))
            result = convert_audio(source)

        self.assertIsInstance(result, bytes)
        self.assertEqual(result, struct.pack("<hh", -2, 3))

    def test_audio_rejects_containers_outside_wav_flac_and_ogg(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "audio.bin"
            source.write_bytes(b"placeholder")
            info = SimpleNamespace(format="MP3", frames=1, channels=1, samplerate=8000)
            with patch("soundfile.info", return_value=info):
                with self.assertRaisesRegex(PluginError, "WAV, FLAC u OGG"):
                    convert_audio(source)


if __name__ == "__main__":
    unittest.main()
