from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pcpi import (
    BITORDER_MSB,
    ENDIAN_LITTLE,
    PCPIError,
    PCPIPit,
    load_pcpi_file,
    parse_pcpi,
)
from pcpi_compiler import compile_pcpi_source, compile_pcpi_source_file
from rif import main as rif_main


SOURCE = '''\
MAGIC "pcpi"
VERSION 1
ENDIANNESS 1
BITORDER 1
SIGNATURE "Grand Kenzy Tools"
PADDING 0

@RAW
7F 44
[2]
00 01
@END
'''


class PCPITests(unittest.TestCase):
    def test_declarative_source_emits_raw_and_aligned_pit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "header.pci"
            source.write_text(SOURCE, encoding="utf-8")

            result = compile_pcpi_source(source)

            self.assertEqual(result.source, source.resolve())
            self.assertEqual(result.image.signature, b"Grand Kenzy Tools")
            self.assertEqual(result.image.endianness, ENDIAN_LITTLE)
            self.assertEqual(result.image.bitorder, BITORDER_MSB)
            self.assertEqual(result.image.image, b"\x7fD" + b"\0" * 6 + b"\0\0" + b"\0\1")
            self.assertEqual(result.image.image_size, 12)
            self.assertEqual(result.image.pits, (PCPIPit(8, 2, 6),))
            self.assertEqual(len(result.image.rpad), 4)

    def test_cli_compiles_text_source_to_derived_pcic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "header.pci"
            source.write_text(SOURCE, encoding="utf-8")

            self.assertEqual(rif_main(["--comp-pcpi", str(source)]), 0)
            output = source.with_suffix(".pcic")
            self.assertTrue(output.is_file())
            self.assertEqual(load_pcpi_file(output).image_size, 12)

    def test_source_compiler_accepts_explicit_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "header.pci"
            output = Path(directory) / "build" / "header.pcic"
            source.write_text(SOURCE, encoding="utf-8")

            result = compile_pcpi_source_file(source, output)

            self.assertEqual(result, output.resolve())
            self.assertTrue(output.is_file())

    def test_fill_requires_exact_pit_size(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "header.pci"
            source.write_text(SOURCE, encoding="utf-8")
            image = compile_pcpi_source(source).image

            self.assertEqual(image.fill(0, b"AB")[8:10], b"AB")
            with self.assertRaisesRegex(PCPIError, "requiere 2 bytes"):
                image.fill(0, b"A")

    def test_binary_validator_rejects_overlapping_pits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "header.pci"
            source.write_text(SOURCE, encoding="utf-8")
            compiled = compile_pcpi_source(source).image
            malformed = compiled.__class__(
                version=compiled.version,
                signature=compiled.signature,
                image_size=compiled.image_size,
                padding=compiled.padding,
                rpad=compiled.rpad,
                bitorder=compiled.bitorder,
                endianness=compiled.endianness,
                image=compiled.image,
                pits=(PCPIPit(8, 4, 6), PCPIPit(8, 2)),
            )

            with self.assertRaisesRegex(PCPIError, "solaparse"):
                parse_pcpi(malformed.to_bytes())

    def test_rejects_invalid_source_byte_and_trailing_content(self) -> None:
        bad_byte = SOURCE.replace("7F 44", "7F 4G")
        trailing = SOURCE + "\nAF\n"
        with tempfile.TemporaryDirectory() as directory:
            bad_path = Path(directory) / "bad-byte.pci"
            bad_path.write_text(bad_byte, encoding="utf-8")
            with self.assertRaisesRegex(PCPIError, "Byte o pit"):
                compile_pcpi_source(bad_path)

            trailing_path = Path(directory) / "trailing.pci"
            trailing_path.write_text(trailing, encoding="utf-8")
            with self.assertRaisesRegex(PCPIError, "después de @END"):
                compile_pcpi_source(trailing_path)

    def test_rejects_empty_signature_and_bad_endianness(self) -> None:
        invalid_signature = SOURCE.replace('SIGNATURE "Grand Kenzy Tools"', 'SIGNATURE ""')
        invalid_endianness = SOURCE.replace("ENDIANNESS 1", "ENDIANNESS 3")
        with tempfile.TemporaryDirectory() as directory:
            for name, text, message in (
                ("signature.pci", invalid_signature, "SIGNATURE"),
                ("endianness.pci", invalid_endianness, "ENDIANNESS"),
            ):
                path = Path(directory) / name
                path.write_text(text, encoding="utf-8")
                with self.assertRaisesRegex(PCPIError, message):
                    compile_pcpi_source(path)


if __name__ == "__main__":
    unittest.main()
