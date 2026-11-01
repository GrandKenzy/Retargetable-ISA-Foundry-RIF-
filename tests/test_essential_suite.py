"""Expose the essential suite through VNMA's conventional ``tests/`` target."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]
_ESSENTIAL_DIR = _ROOT / "tests" / "suite_essencial"


def _load_modules() -> list[object]:
    modules: list[object] = []
    for path in sorted(_ESSENTIAL_DIR.glob("test_*.py")):
        module_name = f"rif_essential_{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"No se pudo cargar la prueba esencial {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)
        for name, value in vars(module).items():
            if isinstance(value, type) and issubclass(value, unittest.TestCase):
                globals().setdefault(name, value)
    return modules


_MODULES = _load_modules()


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    """Aggregate the essential files for standard unittest discovery."""
    suite = unittest.TestSuite()
    for module in _MODULES:
        suite.addTests(loader.loadTestsFromModule(module))
    return suite
