import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from Frontend.aot import AOTParser, GIRAdapter
from Frontend.parity import compare_target
from Frontend import globals as rif_globals
from Frontend.processor import process
from Frontend.syntax import RIF_LANG_SESSION
from gram.core.ast.nodes import ASTRef, ASTTokenNode, ArrayNode, RawNode
from MIR import compile_definition


def _sequence_items(value):
    values = value.items if isinstance(value, ArrayNode) else value
    result = []
    for item in values:
        if isinstance(item, (ArrayNode, list, tuple)):
            result.extend(_sequence_items(item))
        else:
            result.append(item)
    return result


def _ast_signature(value):
    if isinstance(value, ASTRef):
        if value.name == "RULE" and len(value.nodes) == 6:
            children = tuple(_ast_signature(node) for node in value.nodes[:5])
            instructions = tuple(_ast_signature(node) for node in value.nodes[5])
            return ("ref", value.name, children + (("instructions", instructions),))
        children = _sequence_items(value.nodes)
        return ("ref", value.name, tuple(_ast_signature(node) for node in children))
    if isinstance(value, ArrayNode):
        return ("sequence", tuple(_ast_signature(node) for node in _sequence_items(value)))
    if isinstance(value, RawNode):
        return (
            "raw",
            tuple((token.token.name, token.value) for token in value.tokens),
        )
    if isinstance(value, (list, tuple)):
        return ("sequence", tuple(_ast_signature(node) for node in _sequence_items(value)))
    if isinstance(value, ASTTokenNode):
        return ("token", value.token.token.name, value.token.value)
    raise TypeError(f"nodo AST no soportado: {type(value).__name__}")


class AOTFrontendTests(unittest.TestCase):
    def setUp(self):
        self._clear_globals()

    def tearDown(self):
        self._clear_globals()

    @staticmethod
    def _clear_globals():
        rif_globals.STACK = None
        rif_globals.STACK_SIZE = None
        rif_globals.CONFIG = None
        rif_globals.LINKER = None
        for collection in (
            rif_globals.DEFINES,
            rif_globals.TABLES,
            rif_globals.RULES,
            rif_globals.SUPPORTS,
            rif_globals.ASM_VARIANTS,
            rif_globals.LOADED_SOURCES,
            rif_globals.ACTIVE_SOURCES,
            rif_globals.VARIANT_STACK,
            rif_globals.BLOCKS,
        ):
            collection.clear()

    @unittest.skipUnless(
        shutil.which("gcc") or shutil.which("clang"),
        "se requiere gcc o clang para probar el frontend AOT",
    )
    def test_builds_and_reads_gir_for_complete_rif(self):
        source_path = (
            Path(__file__).resolve().parents[2]
            / "examples"
            / "RIF-Core-Demo"
            / "main.rif"
        )
        with TemporaryDirectory(prefix="rif-aot-") as temporary:
            parser = AOTParser.build(AOTParser.default_cache_dir(), RIF_LANG_SESSION)
            document = parser.parse_file(source_path)
            native_ast = GIRAdapter(document).ast()

            source = source_path.read_text(encoding="utf-8")
            python_ast = RIF_LANG_SESSION.parse(
                RIF_LANG_SESSION.tokenize(source, str(source_path)),
                str(source_path),
            )

        self.assertEqual(document.header.source_size, source_path.stat().st_size)
        self.assertEqual(document.root.kind_name, "ARRAY")
        self.assertGreater(len(document.nodes), 1)
        self.assertGreater(sum(node.is_raw for node in document.nodes), 0)
        self.assertEqual(len(native_ast), 10)
        self.assertEqual(native_ast[0].name, "BLOCK")
        self.assertEqual(native_ast[3].name, "TABLE")
        self.assertEqual(_ast_signature(native_ast), _ast_signature(python_ast))
        process(native_ast, source_path=source_path)
        native_context = rif_globals.snapshot_target_context()
        native_rules = {
            name: tuple(instruction.opcode for instruction in rule.instructions)
            for name, rule in rif_globals.RULES.items()
        }

        self._clear_globals()
        process(python_ast, source_path=source_path)
        python_context = rif_globals.snapshot_target_context()
        python_rules = {
            name: tuple(instruction.opcode for instruction in rule.instructions)
            for name, rule in rif_globals.RULES.items()
        }

        self.assertEqual(native_context, python_context)
        self.assertEqual(native_rules, python_rules)

        compiled = compile_definition(source_path, backend="aot")
        self.assertEqual(set(compiled.rules), {"mov", "add", "ret"})
        self.assertIsNotNone(compiled.context.config)

    def test_ast_and_context_parity_for_table_and_declaration_fixture(self):
        source_text = (
            "@define mov\n"
            "@table registers\n"
            "| name | opcode |\n"
            "__\n"
            "| mov | 1 |\n"
            "@end\n"
            "@rule mov:\n"
            ". $registers.name, IDENT\n"
            "@rule mark:\n"
            ". IDENT\n"
            ". mark\n"
            ". IDENT\n"
            "@rule jmp:\n"
            ". IDENT\n"
            ". reserve \"fix32\" 32\n"
            ". fixup pc32 \"fix32\"\n"
            ". drop_res \"fix32\"\n"
            ". IDENT\n"
        )
        with TemporaryDirectory(prefix="rif-aot-parity-") as directory:
            root = Path(directory)
            source_path = root / "fixture.rif"
            source_path.write_text(source_text, encoding="utf-8")
            parser = AOTParser.build(AOTParser.default_cache_dir(), RIF_LANG_SESSION)
            native_ast = GIRAdapter(parser.parse_file(source_path)).ast()

            RIF_LANG_SESSION.load()
            python_ast = RIF_LANG_SESSION.parse(
                RIF_LANG_SESSION.tokenize(source_text, str(source_path)),
                str(source_path),
            )
            self.assertEqual(_ast_signature(native_ast), _ast_signature(python_ast))

            self._clear_globals()
            process(native_ast, source_path=source_path)
            native_context = rif_globals.snapshot_target_context()
            native_rules = {
                name: tuple(item.opcode for item in rule.instructions)
                for name, rule in rif_globals.RULES.items()
            }

            self._clear_globals()
            process(python_ast, source_path=source_path)
            python_context = rif_globals.snapshot_target_context()
            python_rules = {
                name: tuple(item.opcode for item in rule.instructions)
                for name, rule in rif_globals.RULES.items()
            }

        self.assertEqual(native_context, python_context)
        self.assertEqual(native_rules, python_rules)

    def test_aot_backend_propagates_through_load(self):
        with TemporaryDirectory(prefix="rif-aot-load-") as directory:
            root = Path(directory)
            main = root / "main.rif"
            included = root / "defs.rif"
            main.write_text('@LOAD "defs.rif"\n', encoding="utf-8")
            included.write_text(
                "@define loaded\n"
                "@rule loaded_rule:\n"
                ". IDENT\n",
                encoding="utf-8",
            )

            with patch(
                "Frontend.processor.parsing.SourceParser.parse_text",
                side_effect=AssertionError("la ruta AOT no debe re-tokenizar en Python"),
            ):
                compiled = compile_definition(main, backend="aot")

        self.assertEqual(set(compiled.rules), {"loaded_rule"})
        self.assertEqual(compiled.context.defines, frozenset({"loaded"}))

    @unittest.skipUnless(
        shutil.which("gcc") or shutil.which("clang"),
        "se requiere gcc o clang para probar el frontend AOT",
    )
    def test_aot_parse_uses_in_memory_ffi_without_gir_files(self):
        with TemporaryDirectory(prefix="rif-aot-gir-") as directory:
            root = Path(directory)
            source_path = root / "fixture.rif"
            source_path.write_text("@define transient\n", encoding="utf-8")
            parser = AOTParser.build(AOTParser.default_cache_dir(), RIF_LANG_SESSION)

            parser.parse_file(source_path)

            gir_dir = root / ".rif-cache" / "gir"
            self.assertFalse(gir_dir.exists())

    def test_aot_parser_reuses_compiled_cache(self):
        output = AOTParser.default_cache_dir()
        first = AOTParser.build(output, RIF_LANG_SESSION)
        first_mtime = first.executable.stat().st_mtime_ns
        second = AOTParser.build(output, RIF_LANG_SESSION)
        second_mtime = second.executable.stat().st_mtime_ns

        self.assertEqual(first.executable, second.executable)
        self.assertEqual(first_mtime, second_mtime)
        manifest = json.loads(
            (output / "rif_aot_build.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["aot_mode"], "ffi-memory")
        self.assertEqual(manifest["cache_format_version"], 2)
        self.assertEqual(manifest["contract"]["aot_mode"], "ffi-memory")
        self.assertEqual(len(manifest["contract"]["compiler_source_fingerprint"]), 64)

    @unittest.skipUnless(
        shutil.which("gcc") or shutil.which("clang"),
        "se requiere gcc o clang para probar la paridad completa",
    )
    def test_full_semantic_parity_for_amd64_fixture(self):
        target = Path(__file__).resolve().parents[2] / "examples" / "AMD64_Baremetal" / "main.rif"
        report = compare_target(target)
        self.assertTrue(report.equal, report.as_dict())

    def test_ast_and_context_parity_for_variant_fixture(self):
        source_text = (
            "@SUPPORTS thumb\n"
            "@ASMVARIANT thumb:\n"
            ".MODE SWITCH\n"
            '.ENTER "ENTER_thumb"\n'
            '.EXIT "EXIT_thumb"\n'
            "@END\n"
        )
        with TemporaryDirectory(prefix="rif-aot-variant-") as directory:
            root = Path(directory)
            source_path = root / "variant.rif"
            source_path.write_text(source_text, encoding="utf-8")
            (root / "thumb.rif").write_text(
                "@rule ENTER_thumb:\n"
                ". IDENT\n"
                "@rule EXIT_thumb:\n"
                ". IDENT\n",
                encoding="utf-8",
            )
            parser = AOTParser.build(AOTParser.default_cache_dir(), RIF_LANG_SESSION)
            native_ast = GIRAdapter(parser.parse_file(source_path)).ast()

            RIF_LANG_SESSION.load()
            python_ast = RIF_LANG_SESSION.parse(
                RIF_LANG_SESSION.tokenize(source_text, str(source_path)),
                str(source_path),
            )
            self.assertEqual(_ast_signature(native_ast), _ast_signature(python_ast))

            self._clear_globals()
            process(native_ast, source_path=source_path)
            native_context = rif_globals.snapshot_target_context()
            native_rules = set(rif_globals.RULES)

            self._clear_globals()
            process(python_ast, source_path=source_path)
            python_context = rif_globals.snapshot_target_context()
            python_rules = set(rif_globals.RULES)

        self.assertEqual(native_context, python_context)
        self.assertEqual(native_rules, python_rules)

if __name__ == "__main__":
    unittest.main()
