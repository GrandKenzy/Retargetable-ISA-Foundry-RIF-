from __future__ import annotations

import tempfile
import unittest
import zipfile
import json
import sqlite3
from dataclasses import replace
from pathlib import Path

from MIR import (
    MIRInputError,
    build_database,
    compile_definition,
    compile_mir_file,
    compile_mir_source,
    current_contract,
    load_database,
)
from rif_core.pack import PackReader, create_pack


TARGET = '''\
@block config:
    format section ".section"
    section text "rx"
    entry text "_start"
    default text
    word_size 8
    address_size 8
    byte_order "little"
    case_sensitive true
    undefined_symbols "error"
    duplicate_symbols "error"
    strict true
    allow_empty_sections false
@end

@block linker:
    extension ".mir"
    search_path ""
@end

@rule emit_byte:
. IDENT
. bits 144 8
'''


class TargetContractTests(unittest.TestCase):
    def test_rif_pack_and_pack_mir_are_the_two_explicit_compilation_phases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "main.rif"
            mir = root / "program.mir"
            package = root / "main.pack"
            direct_output = root / "direct.bin"
            packed_output = root / "packed.bin"
            target.write_text(TARGET, encoding="utf-8")
            mir.write_text("emit_byte\n", encoding="utf-8")

            create_pack(target, package, precompile=True)
            with PackReader(package) as reader:
                self.assertTrue(reader.has_compiled_database)
            with zipfile.ZipFile(package) as archive:
                self.assertNotIn("program.mir", archive.namelist())

            direct = compile_mir_file(target, mir, output=direct_output)
            packed = compile_mir_file(package, mir, output=packed_output)
            self.assertEqual(direct.binary, b"\x90")
            self.assertEqual(direct.binary, packed.binary)
            self.assertEqual(direct_output.read_bytes(), packed_output.read_bytes())

    def test_mir_is_rejected_before_execution_when_target_has_no_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "incomplete.rif"
            target.write_text("@rule emit_byte:\n. IDENT\n", encoding="utf-8")
            program = compile_definition(target)

            with self.assertRaisesRegex(MIRInputError, "@block config"):
                compile_mir_source(program, "emit_byte\n")

    def test_mir_is_rejected_when_target_has_no_executable_rules(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "incomplete.rif"
            target.write_text(
                "@block config:\n"
                "    section text \"rx\"\n"
                "    entry text \"_start\"\n"
                "    default text\n"
                "@end\n",
                encoding="utf-8",
            )
            program = compile_definition(target)

            with self.assertRaisesRegex(MIRInputError, "ninguna Rule"):
                compile_mir_source(program, "emit_byte\n")

    def test_sqlite_rejects_a_contract_from_another_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target.rif"
            target.write_text(TARGET, encoding="utf-8")
            program = compile_definition(target)
            database = build_database(program)

            connection = sqlite3.connect(":memory:")
            try:
                connection.deserialize(database)
                stale = replace(current_contract(), runtime_abi_version="0.0")
                connection.execute(
                    "UPDATE meta SET value = ? WHERE key = 'contract'",
                    (json.dumps(stale.as_dict(), sort_keys=True),),
                )
                connection.execute(
                    "UPDATE meta SET value = ? WHERE key = 'contract_fingerprint'",
                    (stale.fingerprint(),),
                )
                connection.commit()
                stale_database = connection.serialize()
            finally:
                connection.close()

            with self.assertRaisesRegex(ValueError, "incompatible"):
                load_database(stale_database)


if __name__ == "__main__":
    unittest.main()
