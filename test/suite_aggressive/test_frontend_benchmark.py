"""Baseline benchmark for the Python RIF frontend.

This test intentionally has no timing threshold.  Its output is the baseline
The AOT frontend is measured separately by ``tests/test_aot.py``.
"""

from __future__ import annotations

import time
import unittest
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from Frontend.aot import AOTParser, GIRAdapter
from Frontend import RIF_LANG_SESSION
from Frontend import globals as rif_globals
from Frontend.processor import process
from gram.core.lexer import Token


def _reset_frontend() -> None:
    rif_globals.STACK = None
    rif_globals.STACK_SIZE = None
    rif_globals.CONFIG = None
    rif_globals.LINKER = None
    rif_globals.DEFINES.clear()
    rif_globals.TABLES.clear()
    rif_globals.RULES.clear()
    rif_globals.SUPPORTS.clear()
    rif_globals.ASM_VARIANTS.clear()
    rif_globals.LOADED_SOURCES.clear()
    rif_globals.ACTIVE_SOURCES.clear()
    rif_globals.BLOCKS.clear()
    rif_globals.VARIANT_STACK.clear()


class FrontendBenchmarkTests(unittest.TestCase):
    def test_complete_rif_frontend_baseline(self) -> None:
        root = Path(__file__).resolve().parents[2]
        source_path = root / "examples" / "RIF-Core-Demo" / "main.rif"
        source = source_path.read_text(encoding="utf-8")

        measurements: list[tuple[float, float, float, int]] = []
        for iteration in range(3):
            _reset_frontend()
            RIF_LANG_SESSION.load()

            lex_started = time.perf_counter()
            tokens = RIF_LANG_SESSION.tokenize(source, str(source_path))
            lex_elapsed = time.perf_counter() - lex_started

            parse_started = time.perf_counter()
            ast = RIF_LANG_SESSION.parse(tokens, str(source_path))
            parse_elapsed = time.perf_counter() - parse_started

            process_started = time.perf_counter()
            process(ast, source_path=source_path, load_variants=False)
            process_elapsed = time.perf_counter() - process_started

            token_count = sum(token.token != Token.EOF for token in tokens)
            measurements.append((lex_elapsed, parse_elapsed, process_elapsed, token_count))

        average = tuple(sum(row[index] for row in measurements) / len(measurements) for index in range(3))
        token_count = measurements[0][3]
        print(
            "[benchmark] frontend_python "
            f"bytes={len(source.encode('utf-8'))} tokens={token_count} "
            f"lex={average[0]:.6f}s parse={average[1]:.6f}s "
            f"process={average[2]:.6f}s total={sum(average):.6f}s"
        )

        self.assertIsNotNone(ast)
        self.assertGreater(token_count, 0)
        self.assertIn("mov", rif_globals.RULES)

    @unittest.skipUnless(
        shutil.which("gcc") or shutil.which("clang"),
        "se requiere gcc o clang para medir el frontend AOT",
    )
    def test_complete_rif_aot_benchmark(self) -> None:
        root = Path(__file__).resolve().parents[2]
        source_path = root / "examples" / "RIF-Core-Demo" / "main.rif"
        source_size = source_path.stat().st_size

        with TemporaryDirectory(prefix="rif-aot-benchmark-"):
            build_started = time.perf_counter()
            parser = AOTParser.build(AOTParser.default_cache_dir(), RIF_LANG_SESSION)
            build_elapsed = time.perf_counter() - build_started
            cache_started = time.perf_counter()
            cached_parser = AOTParser.build(AOTParser.default_cache_dir(), RIF_LANG_SESSION)
            cache_elapsed = time.perf_counter() - cache_started

            measurements: list[tuple[float, float, float, int]] = []
            for _ in range(3):
                _reset_frontend()

                parse_started = time.perf_counter()
                document = parser.parse_file(source_path)
                parse_elapsed = time.perf_counter() - parse_started

                adapt_started = time.perf_counter()
                ast = GIRAdapter(document).ast()
                adapt_elapsed = time.perf_counter() - adapt_started

                process_started = time.perf_counter()
                process(
                    ast,
                    source_path=source_path,
                    load_variants=False,
                    backend="aot",
                )
                process_elapsed = time.perf_counter() - process_started
                measurements.append(
                    (parse_elapsed, adapt_elapsed, process_elapsed, len(document.nodes))
                )

            average = tuple(
                sum(row[index] for row in measurements) / len(measurements)
                for index in range(3)
            )
            gir_nodes = measurements[0][3]
            warm_total = sum(average)
            print(
                "[benchmark] frontend_aot "
                f"bytes={source_size} gir_nodes={gir_nodes} "
                f"build_check={build_elapsed:.6f}s parse_gir={average[0]:.6f}s "
                f"adapt={average[1]:.6f}s process={average[2]:.6f}s "
                f"cache_hit={cache_elapsed:.6f}s "
                f"warm_total={warm_total:.6f}s "
                f"cached_total={build_elapsed + warm_total:.6f}s"
            )

        self.assertIsNotNone(ast)
        self.assertEqual(parser.executable, cached_parser.executable)
        self.assertIn("mov", rif_globals.RULES)

    @unittest.skipUnless(
        shutil.which("gcc") or shutil.which("clang"),
        "se requiere gcc o clang para medir el target AMD64 AOT",
    )
    def test_amd64_target_frontend_benchmark(self) -> None:
        root = Path(__file__).resolve().parents[2]
        source_path = root / "examples" / "AMD64_Baremetal" / "main.rif"
        source = source_path.read_text(encoding="utf-8")

        python_measurements: list[tuple[float, float, float, int]] = []
        for _ in range(3):
            _reset_frontend()
            RIF_LANG_SESSION.load()

            lex_started = time.perf_counter()
            tokens = RIF_LANG_SESSION.tokenize(source, str(source_path))
            lex_elapsed = time.perf_counter() - lex_started

            parse_started = time.perf_counter()
            ast = RIF_LANG_SESSION.parse(tokens, str(source_path))
            parse_elapsed = time.perf_counter() - parse_started

            process_started = time.perf_counter()
            process(ast, source_path=source_path, load_variants=False, backend="python")
            process_elapsed = time.perf_counter() - process_started
            python_measurements.append(
                (lex_elapsed, parse_elapsed, process_elapsed, len(tokens))
            )

        parser = AOTParser.build(AOTParser.default_cache_dir(), RIF_LANG_SESSION)
        aot_measurements: list[tuple[float, float, float, int]] = []
        for _ in range(3):
            _reset_frontend()

            parse_started = time.perf_counter()
            document = parser.parse_file(source_path)
            parse_elapsed = time.perf_counter() - parse_started

            adapt_started = time.perf_counter()
            ast = GIRAdapter(document).ast()
            adapt_elapsed = time.perf_counter() - adapt_started

            process_started = time.perf_counter()
            process(ast, source_path=source_path, load_variants=False, backend="aot")
            process_elapsed = time.perf_counter() - process_started
            aot_measurements.append(
                (parse_elapsed, adapt_elapsed, process_elapsed, len(document.nodes))
            )

        python_average = tuple(
            sum(row[index] for row in python_measurements) / len(python_measurements)
            for index in range(3)
        )
        aot_average = tuple(
            sum(row[index] for row in aot_measurements) / len(aot_measurements)
            for index in range(3)
        )
        python_total = sum(python_average)
        aot_total = sum(aot_average)
        print(
            "[benchmark] amd64_python "
            f"bytes={len(source.encode('utf-8'))} tokens={python_measurements[0][3]} "
            f"lex={python_average[0]:.6f}s parse={python_average[1]:.6f}s "
            f"process={python_average[2]:.6f}s total={python_total:.6f}s"
        )
        print(
            "[benchmark] amd64_aot "
            f"bytes={source_path.stat().st_size} gir_nodes={aot_measurements[0][3]} "
            f"parse_gir={aot_average[0]:.6f}s adapt={aot_average[1]:.6f}s "
            f"process={aot_average[2]:.6f}s total={aot_total:.6f}s"
        )

        self.assertIn("mov", rif_globals.RULES)

    @unittest.skipUnless(
        shutil.which("gcc") or shutil.which("clang"),
        "se requiere gcc o clang para medir el target GBA AOT",
    )
    def test_gba_target_frontend_benchmark(self) -> None:
        root = Path(__file__).resolve().parents[2]
        source_path = root / "examples" / "GBA-Bouncing-Ball" / "main.rif"
        source = source_path.read_text(encoding="utf-8")

        python_measurements: list[tuple[float, float, float, int]] = []
        for _ in range(3):
            _reset_frontend()
            RIF_LANG_SESSION.load()

            lex_started = time.perf_counter()
            tokens = RIF_LANG_SESSION.tokenize(source, str(source_path))
            lex_elapsed = time.perf_counter() - lex_started

            parse_started = time.perf_counter()
            ast = RIF_LANG_SESSION.parse(tokens, str(source_path))
            parse_elapsed = time.perf_counter() - parse_started

            process_started = time.perf_counter()
            process(ast, source_path=source_path, load_variants=True, backend="python")
            process_elapsed = time.perf_counter() - process_started
            python_measurements.append(
                (lex_elapsed, parse_elapsed, process_elapsed, len(tokens))
            )

        parser = AOTParser.build(AOTParser.default_cache_dir(), RIF_LANG_SESSION)
        aot_measurements: list[tuple[float, float, float, int]] = []
        for _ in range(3):
            _reset_frontend()

            parse_started = time.perf_counter()
            document = parser.parse_file(source_path)
            parse_elapsed = time.perf_counter() - parse_started

            adapt_started = time.perf_counter()
            ast = GIRAdapter(document).ast()
            adapt_elapsed = time.perf_counter() - adapt_started

            process_started = time.perf_counter()
            process(ast, source_path=source_path, load_variants=True, backend="aot")
            process_elapsed = time.perf_counter() - process_started
            aot_measurements.append(
                (parse_elapsed, adapt_elapsed, process_elapsed, len(document.nodes))
            )

        python_average = tuple(
            sum(row[index] for row in python_measurements) / len(python_measurements)
            for index in range(3)
        )
        aot_average = tuple(
            sum(row[index] for row in aot_measurements) / len(aot_measurements)
            for index in range(3)
        )
        python_total = sum(python_average)
        aot_total = sum(aot_average)
        print(
            "[benchmark] gba_python "
            f"bytes={len(source.encode('utf-8'))} tokens={python_measurements[0][3]} "
            f"lex={python_average[0]:.6f}s parse={python_average[1]:.6f}s "
            f"process={python_average[2]:.6f}s total={python_total:.6f}s"
        )
        print(
            "[benchmark] gba_aot "
            f"bytes={source_path.stat().st_size} gir_nodes={aot_measurements[0][3]} "
            f"parse_gir={aot_average[0]:.6f}s adapt={aot_average[1]:.6f}s "
            f"process={aot_average[2]:.6f}s total={aot_total:.6f}s"
        )

        self.assertIn("thumb_present", rif_globals.DEFINES)


if __name__ == "__main__":
    unittest.main()
