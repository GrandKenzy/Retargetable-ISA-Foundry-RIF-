"""Generate a safe, repeatable unittest scaffold for a RIF target."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path


_NAME_RE = re.compile(r"[^A-Za-z0-9_]+")


def _identifier(value: str) -> str:
    result = _NAME_RE.sub("_", value).strip("_").lower()
    if not result:
        raise ValueError("El nombre del target no puede quedar vacío.")
    if result[0].isdigit():
        result = f"target_{result}"
    return result


def render_scaffold(target: str | Path, output_dir: str | Path) -> tuple[Path, str]:
    """Return the destination and template for one target test scaffold."""

    target_path = Path(target).expanduser().resolve()
    if target_path.suffix.lower() != ".rif":
        raise ValueError("El target del scaffold debe terminar en .rif.")
    if not target_path.is_file():
        raise FileNotFoundError(target_path)
    destination_dir = Path(output_dir).expanduser().resolve()
    name = _identifier(target_path.stem)
    relative_target = Path(os.path.relpath(target_path, destination_dir))
    target_literal = relative_target.as_posix()
    destination = destination_dir / f"test_{name}_generated.py"
    template = f'''"""Generated RIF target tests for {target_path.name}.

Fill the marked MIR cases and expected bytes before moving this file into the
appropriate project suite. The target compilation test is ready immediately.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from MIR import compile_definition, compile_mir_source


TARGET = (Path(__file__).resolve().parent / r"{target_literal}").resolve()
VALID_MIR = """\\
# TODO: add one valid MIR program for the target.
"""
EXPECTED_BYTES_HEX = ""  # TODO: expected raw bytes for VALID_MIR.


class GeneratedTargetTests(unittest.TestCase):
    def test_target_compiles(self) -> None:
        program = compile_definition(TARGET)
        self.assertTrue(program.rules, "el target debe declarar al menos una Rule")

    def test_valid_mir_and_expected_bytes(self) -> None:
        if not EXPECTED_BYTES_HEX.strip() or VALID_MIR.lstrip().startswith("# TODO"):
            self.skipTest("rellenar VALID_MIR y EXPECTED_BYTES_HEX")
        result = compile_mir_source(compile_definition(TARGET), VALID_MIR)
        self.assertEqual(result.binary, bytes.fromhex(EXPECTED_BYTES_HEX))

    def test_symbol_and_relocation_cases(self) -> None:
        self.skipTest("añadir MIR con símbolos y relocaciones del perfil")

    def test_boundary_cases(self) -> None:
        self.skipTest("añadir valores mínimo/máximo y anchos del perfil")

    def test_invalid_cases_are_rejected(self) -> None:
        self.skipTest("añadir MIR inválido y el diagnóstico esperado")


if __name__ == "__main__":
    unittest.main()
'''
    return destination, template


def write_scaffold(
    target: str | Path,
    output_dir: str | Path,
    *,
    force: bool = False,
) -> Path:
    destination, template = render_scaffold(target, output_dir)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not force:
        raise FileExistsError(
            f"El scaffold ya existe: {destination}; usa --force para reemplazarlo."
        )
    destination.write_text(template, encoding="utf-8", newline="\n")
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Genera un scaffold unittest para un target .rif"
    )
    parser.add_argument("target", type=Path, help="target .rif")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("test/dedicated_suite"),
        help="directorio del scaffold (default: test/dedicated_suite)",
    )
    parser.add_argument("--force", action="store_true", help="reemplaza el archivo existente")
    args = parser.parse_args(argv)
    print(write_scaffold(args.target, args.output_dir, force=args.force))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
