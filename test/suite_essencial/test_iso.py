from __future__ import annotations

from pathlib import Path
import unittest

from iso import ISOFile, build_iso_from_pcpi, validate_bios_iso
from pcpi_compiler import compile_pcpi_source


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "examples" / "probe" / "probe_minios" / "mini_os_iso_header.pci"


class ISOTests(unittest.TestCase):
    def test_pcpi_and_rif_boot_image_form_a_valid_bios_iso(self) -> None:
        template = compile_pcpi_source(TEMPLATE).image
        boot = bytearray(2048)
        boot[510:512] = b"\x55\xaa"
        image = build_iso_from_pcpi(
            template,
            boot,
            (ISOFile("README.TXT;1", b"RIF ISO test\r\n"),),
            volume_id="RIF_TEST",
        )
        report = validate_bios_iso(image)

        self.assertEqual(report.blocks, 25)
        self.assertEqual(report.boot_image_lba, 20)
        self.assertEqual(report.boot_image_sectors, 4)
        self.assertEqual(report.root_directory_lba, 23)
        self.assertEqual(report.root_directory_size, 2048)
        self.assertEqual(image[20 * 2048 + 510 : 20 * 2048 + 512], b"\x55\xaa")

    def test_iso_rejects_a_corrupt_el_torito_checksum(self) -> None:
        template = compile_pcpi_source(TEMPLATE).image
        image = bytearray(build_iso_from_pcpi(template, bytes(2048)))
        image[19 * 2048 + 28] ^= 1
        with self.assertRaisesRegex(ValueError, "suma de validación"):
            validate_bios_iso(image)


if __name__ == "__main__":
    unittest.main()
