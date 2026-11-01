from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rif_tools.target_scaffold import render_scaffold, write_scaffold


class TargetScaffoldTests(unittest.TestCase):
    def test_scaffold_is_deterministic_and_requires_force_to_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "My-Target.rif"
            output = root / "generated"
            target.write_text("@rule nop:\n. IDENT\n", encoding="utf-8")

            destination, first = render_scaffold(target, output)
            _, second = render_scaffold(target, output)
            self.assertEqual(first, second)
            self.assertEqual(destination.name, "test_my_target_generated.py")

            self.assertEqual(write_scaffold(target, output), destination)
            with self.assertRaises(FileExistsError):
                write_scaffold(target, output)
            self.assertEqual(write_scaffold(target, output, force=True), destination)
            self.assertIn("test_target_compiles", destination.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
