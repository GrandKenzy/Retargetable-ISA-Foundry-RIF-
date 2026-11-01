from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
import unittest.mock
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from MIR import compile_definition, compile_mir_file, compile_mir_source, prepare_target
from MIR.artifacts import ArtifactError, _file_payload
from MIR.runtime import RIFRuntimeError
from Frontend.processor.sources import resolve_source
from pack import create_pack, read_pack
from rif_limits import resolve_limits, write_mib


CONFIG = '''\
@block config:
    format section ".section"
    section text ""
    format section_end ":"
    entry text "_start"
    comment ";"
    format label_end ":"
    default text
    word_size {wordsize}
    address_size 64
    byte_order "little"
    case_sensitive true
    symbol_prefix "_"
    local_prefix "."
    undefined_symbols "error"
    duplicate_symbols "error"
    strict true
    allow_empty_sections false
@end

@block linker:
    extension ".asm"
    search_path ""
@end
'''


class HardeningTests(unittest.TestCase):
    def test_limits_preserve_env_and_follow_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text("PYTHONPATH=./vendor;../Gram\n", encoding="utf-8")
            write_mib(2, env_path)
            self.assertIn("PYTHONPATH=./vendor;../Gram", env_path.read_text(encoding="utf-8"))
            with unittest.mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("RIF_PLIMIT_MIB", None)
                self.assertEqual(resolve_limits(env_path=env_path).bytes, 2 << 20)
                os.environ["RIF_PLIMIT_MIB"] = "3"
                self.assertEqual(resolve_limits(env_path=env_path).bytes, 3 << 20)

    def test_loose_loads_reject_absolute_and_escape_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            root.mkdir()
            main = root / "main.rif"
            main.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "rutas relativas"):
                resolve_source(str(root / "other.rif"), main, root)
            with self.assertRaisesRegex(ValueError, "salir"):
                resolve_source("../other.rif", main, root)

    def test_pack_manifest_records_origins_without_using_them(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "main.rif"
            package = root / "target.pack"
            target.write_text("@define safe\n", encoding="utf-8")
            create_pack(target, package)
            manifest = read_pack(package)
            self.assertEqual(manifest.origins["sources/main.rif"], str(target.resolve()))
            self.assertEqual(manifest.entrypoint, "sources/main.rif")

    def test_concurrent_compilations_keep_gram_contexts_isolated(self) -> None:
        first_source = CONFIG.format(wordsize=8) + '''\
@table bytes
| name | bits |
__
| byte | 8 |
@end
@rule emit_byte:
. IDENT
. eword $bytes.bits
'''
        second_source = CONFIG.format(wordsize=16) + '''\
@table words
| name | bits |
__
| word | 16 |
@end
@rule emit_word:
. IDENT
. eword $words.bits
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_path = root / "first.rif"
            second_path = root / "second.rif"
            first_path.write_text(first_source, encoding="utf-8")
            second_path.write_text(second_source, encoding="utf-8")

            with ThreadPoolExecutor(max_workers=2) as executor:
                first, second = tuple(
                    executor.map(compile_definition, (first_path, second_path))
                )

            self.assertEqual(first.context.config.wordsize, 8)
            self.assertEqual(second.context.config.wordsize, 16)
            self.assertIn("bytes", first.context.tables)
            self.assertIn("words", second.context.tables)
            self.assertIn("emit_byte", first.rules)
            self.assertIn("emit_word", second.rules)

    def test_prepared_targets_do_not_share_context(self) -> None:
        first_source = CONFIG.format(wordsize=8) + '''\
@table registers
| name | bits |
__
| rax | 8 |
@end
@rule mov:
. IDENT
. $registers.name, IDENT
. eword $registers.bits
'''
        second_source = CONFIG.format(wordsize=16) + '''\
@rule nop:
. IDENT
. eword 1
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_path = root / "first.rif"
            second_path = root / "second.rif"
            first_path.write_text(first_source, encoding="utf-8")
            second_path.write_text(second_source, encoding="utf-8")

            first = prepare_target(first_path)
            before = compile_mir_source(first, "mov rax\n").binary
            prepare_target(second_path)
            after = compile_mir_source(first, "mov rax\n").binary

            self.assertEqual(before, b"\x08")
            self.assertEqual(after, before)
            self.assertEqual(first.program.context.config.wordsize, 8)

    def test_rule_compiler_rejects_unconsumed_definition_tokens(self) -> None:
        source = CONFIG.format(wordsize=8) + "@rule bad:\n. IDENT garbage\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.rif"
            path.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "exactamente"):
                compile_definition(path)

    def test_virtual_label_query_uses_virtual_rule_address(self) -> None:
        source = CONFIG.format(wordsize=8) + '''\
@rule pad:
. IDENT
. vpad 8
@rule target:
. IDENT
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.rif"
            path.write_text(source, encoding="utf-8")
            result = compile_mir_source(
                path,
                '::RIF_INSERT BYTES "00000000000000000000"\n'
                '::RIF_PATCH 0, 1, #:qlsize(0, "target")\n'
                '::RIF_PATCH 1, 1, #:qvsize(0, "target")\n'
                "pad\ntarget\n",
            )
            self.assertEqual(result.binary[:2], b"\x0a\x0b")

    def test_final_patch_updates_section_and_render_views(self) -> None:
        source = CONFIG.format(wordsize=8) + '''\
@rule nop:
. IDENT
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.rif"
            path.write_text(source, encoding="utf-8")
            result = compile_mir_source(
                path,
                '::RIF_INSERT BYTES "00"\n'
                "::RIF_PATCH 0, 1, 187\n"
                "nop\n",
            )
            self.assertEqual(result.binary, b"\xbb")
            self.assertEqual(result.image.binary("text"), result.binary)
            self.assertIn("0xbb", result.image.render())

    @unittest.skip("legacy: callbacks Python serán migrados a funciones nativas")
    def test_funcs_module_is_not_executed_until_call(self) -> None:
        source = CONFIG.format(wordsize=8) + '''\
@rule nop:
. IDENT
@rule invoke:
. IDENT
. eword #call[value]
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "main.rif"
            marker = root / "loaded.txt"
            path.write_text(source, encoding="utf-8")
            (root / "funcs.py").write_text(
                "from pathlib import Path\n"
                "Path(__file__).with_name('loaded.txt').write_text('loaded')\n"
                "def handler(name, context):\n"
                "    return '00000001'\n",
                encoding="utf-8",
            )

            prepared = prepare_target(path)
            self.assertFalse(marker.exists())
            compile_mir_source(prepared, "nop\n")
            self.assertFalse(marker.exists())
            self.assertEqual(compile_mir_source(prepared, "invoke\n").binary, b"\x01")
            self.assertTrue(marker.exists())

    def test_portable_pack_asset_never_falls_back_to_host_filesystem(self) -> None:
        with self.assertRaisesRegex(ArtifactError, "no está incluido"):
            _file_payload("vnma.toml", "sources/main.rif", {})

    def test_binary_output_cannot_overwrite_an_input(self) -> None:
        source = CONFIG.format(wordsize=8) + "@rule nop:\n. IDENT\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "main.rif"
            mir = root / "program.asm"
            target.write_text(source, encoding="utf-8")
            mir.write_text("nop\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "sobrescribir"):
                compile_mir_file(target, mir, output=mir)
            self.assertEqual(mir.read_text(encoding="utf-8"), "nop\n")

    def test_recursive_rules_have_a_hard_depth_limit(self) -> None:
        source = CONFIG.format(wordsize=8) + "@rule loop:\n. JUMP loop\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.rif"
            path.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(RIFRuntimeError, "profundidad"):
                compile_mir_source(path, "loop\n")

    def test_compiled_database_is_bound_to_package_sources(self) -> None:
        source = CONFIG.format(wordsize=8) + "@rule nop:\n. IDENT\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "main.rif"
            package = root / "target.pack"
            tampered = root / "tampered.pack"
            target.write_text(source, encoding="utf-8")
            create_pack(target, package, precompile=True)

            with zipfile.ZipFile(package, "r") as original:
                entries = {info.filename: original.read(info) for info in original.infolist()}
                manifest = json.loads(entries["manifest.json"])
            connection = sqlite3.connect(":memory:")
            try:
                connection.deserialize(entries["compiled/program.sqlite3"])
                connection.execute(
                    "UPDATE meta SET value = ? WHERE key = 'source_fingerprint'",
                    ("0" * 64,),
                )
                connection.commit()
                compiled = connection.serialize()
            finally:
                connection.close()
            entries["compiled/program.sqlite3"] = compiled
            manifest["compiled"]["size"] = len(compiled)
            manifest["compiled"]["sha256"] = hashlib.sha256(compiled).hexdigest()
            entries["manifest.json"] = (json.dumps(manifest, sort_keys=True) + "\n").encode()
            with zipfile.ZipFile(tampered, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, data in entries.items():
                    archive.writestr(name, data)

            with self.assertRaisesRegex(ValueError, "no corresponde"):
                read_pack(tampered)

    def test_pack_rejects_undeclared_members(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "main.rif"
            package = root / "target.pack"
            tampered = root / "tampered.pack"
            target.write_text("@define safe\n", encoding="utf-8")
            create_pack(target, package)
            with zipfile.ZipFile(package, "r") as original, zipfile.ZipFile(
                tampered, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                for info in original.infolist():
                    archive.writestr(info, original.read(info))
                archive.writestr("hidden.py", b"raise SystemExit")
            with self.assertRaisesRegex(ValueError, "no coincide"):
                read_pack(tampered)


if __name__ == "__main__":
    unittest.main()
