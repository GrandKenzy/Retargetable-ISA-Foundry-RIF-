from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import tempfile
import unittest
from pathlib import Path

from MIR.storage import StorageBuilder
from rif_tools.pcpi_compiler import compile_pcpi_source_file
from main import main as rif_main


PCPI_SOURCE = '''\
MAGIC "pcpi"
VERSION 1
ENDIANNESS 1
BITORDER 1
SIGNATURE "doctor"

@RAW
AA
[4]
@END
'''


class DoctorCLITests(unittest.TestCase):
    def test_doctor_pcpi_reports_valid_container_and_pits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "image.pci"
            source.write_text(PCPI_SOURCE, encoding="utf-8")
            output = compile_pcpi_source_file(source)
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                status = rif_main(["--doctor-pcpi", str(output)])

            self.assertEqual(status, 0)
            self.assertIn("OK PCP-I version=1", stdout.getvalue())
            self.assertIn("endianness=1", stdout.getvalue())
            self.assertIn("pits=1", stdout.getvalue())
            self.assertIn("pit[0] address=8 size=4 padding=7", stdout.getvalue())

    def test_doctor_storage_reports_entries_and_labels(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = Path(directory) / "storage.bin"
            builder = StorageBuilder()
            builder.add(b"raw", label="payload")
            storage.write_bytes(builder.build())
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                status = rif_main(["--doctor-storage", str(storage)])

            self.assertEqual(status, 0)
            self.assertIn("OK STORAGE version=3", stdout.getvalue())
            self.assertIn("entries=1", stdout.getvalue())
            self.assertIn("label=payload", stdout.getvalue())

    def test_doctor_returns_failure_for_corrupt_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "broken.pcic"
            artifact.write_bytes(b"not a pcpi")
            stderr = io.StringIO()

            with redirect_stderr(stderr):
                status = rif_main(["--doctor-pcpi", str(artifact)])

            self.assertEqual(status, 1)
            self.assertIn("rif: error:", stderr.getvalue())

    def test_doctor_returns_failure_for_corrupt_storage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "broken.storage.bin"
            artifact.write_bytes(b"not a storage")
            stderr = io.StringIO()

            with redirect_stderr(stderr):
                status = rif_main(["--doctor-storage", str(artifact)])

            self.assertEqual(status, 1)
            self.assertIn("rif: error:", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
