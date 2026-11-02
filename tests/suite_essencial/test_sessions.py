from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from Frontend import globals
from Frontend.processor import process
from Frontend.processor.parsing import SourceParser
from Frontend.processor.visitors.table import resolve_pending_tables
from Frontend.session import CompilationSession
from MIR import compile_rules


def _parse(source: str, path: Path):
    parser = SourceParser(backend="python")
    return parser, parser.parse_text(source, str(path))


def _compile_session(source: str, path: Path):
    parser, ast = _parse(source, path)
    session = CompilationSession(
        backend="python",
        parser=parser,
        project_root=path.parent,
    )
    session.source_texts[str(path.resolve())] = source
    process(
        ast,
        source_path=path,
        project_root=path.parent,
        backend="python",
        parser=parser,
        session=session,
        load_variants=False,
    )
    resolve_pending_tables(session)
    return session, compile_rules(session=session, resolve=True)


class CompilationSessionTests(unittest.TestCase):
    def test_consecutive_sessions_do_not_share_tables_or_rules(self) -> None:
        first_source = (
            "@table first\n| name | value |\n__\n| one | 1 |\n@end\n"
            "@rule first_rule:\n. eword 1\n"
        )
        second_source = (
            "@table second\n| name | value |\n__\n| two | 2 |\n@end\n"
            "@rule second_rule:\n. eword 2\n"
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first_session, first = _compile_session(first_source, root / "first.rif")
            second_session, second = _compile_session(second_source, root / "second.rif")

        self.assertEqual(set(first.context.tables), {"first"})
        self.assertEqual(set(second.context.tables), {"second"})
        self.assertEqual(set(first.rules), {"first_rule"})
        self.assertEqual(set(second.rules), {"second_rule"})
        self.assertIsNot(first_session.tables, second_session.tables)
        self.assertNotIn("second", first.context.tables)
        self.assertNotIn("first", second.context.tables)

        explicit = compile_rules(
            tuple(first_session.rules.values()),
            context=first.context,
            source_texts=first_session.source_texts,
            resolve=True,
        )
        self.assertEqual(set(explicit.rules), {"first_rule"})

    def test_sessions_can_compile_in_parallel_without_frontend_globals(self) -> None:
        sources = {
            "left.rif": "@table left\n| value |\n__\n| 11 |\n@end\n@rule left_rule:\n. eword 11\n",
            "right.rif": "@table right\n| value |\n__\n| 22 |\n@end\n@rule right_rule:\n. eword 22\n",
        }
        with TemporaryDirectory() as directory:
            root = Path(directory)
            parsed = [_parse(source, root / name) for name, source in sources.items()]

            def build(item):
                (parser, ast), (name, source) = item
                path = root / name
                session = CompilationSession(
                    backend="python",
                    parser=parser,
                    project_root=root,
                )
                session.source_texts[str(path.resolve())] = source
                process(
                    ast,
                    source_path=path,
                    project_root=root,
                    backend="python",
                    parser=parser,
                    session=session,
                    load_variants=False,
                )
                resolve_pending_tables(session)
                return compile_rules(session=session, resolve=True)

            with ThreadPoolExecutor(max_workers=2) as executor:
                programs = list(executor.map(build, zip(parsed, sources.items())))

        self.assertEqual({next(iter(program.context.tables)) for program in programs}, {"left", "right"})
        self.assertEqual({next(iter(program.rules)) for program in programs}, {"left_rule", "right_rule"})

    def test_load_uses_the_parent_session(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            child = root / "child.rif"
            main = root / "main.rif"
            child_source = "@table child_table\n| value |\n__\n| 7 |\n@end\n@rule child_rule:\n. eword 7\n"
            main_source = '@LOAD "child.rif"\n@rule root_rule:\n. eword 1\n'
            child.write_text(child_source, encoding="utf-8")
            main.write_text(main_source, encoding="utf-8")
            session, program = _compile_session(main_source, main)

        self.assertEqual(set(program.rules), {"child_rule", "root_rule"})
        self.assertIn(str(child.resolve()), session.loaded_sources)
        self.assertEqual(session.active_sources, [])

    def test_failed_processing_clears_pending_state(self) -> None:
        source = (
            "@table duplicate\n| value |\n__\n| 1 |\n@end\n"
            "@table duplicate\n| value |\n__\n| 2 |\n@end\n"
        )
        parser, ast = _parse(source, Path("duplicate.rif"))
        session = CompilationSession(backend="python", parser=parser)

        with self.assertRaises(RuntimeError):
            process(ast, source_path="duplicate.rif", backend="python", parser=parser, session=session)

        self.assertEqual(session.pending_tables, {})
        self.assertEqual(session.active_sources, [])
        self.assertEqual(len(session.diagnostics), 1)

    def test_context_is_detached_and_immutable(self) -> None:
        flags = {"text": "rx"}
        config = globals.ConfigData(
            sectiondef=".section",
            sections=("text",),
            sectionend=":",
            entrysection="text",
            entrylabel="_start",
            comment=";",
            labelend=":",
            datasection="text",
            defaultsection="text",
            sectionflags=flags,
            sectionalign={"text": 4},
            wordsize=8,
            addresssize=64,
            endianness="little",
            casesensitive=True,
            symbolprefix="",
            localprefix=".",
            undefinedsymbols="error",
            duplicatesymbols="error",
            strict=True,
            allowemptysections=False,
        )
        session = CompilationSession(
            config=config,
            linker=globals.LinkerData(extension=".asm", search_path=("",)),
            supports={"thumb": globals.SupportData("thumb", "thumb.rif")},
            asm_variants={
                "thumb": globals.AsmVariantData(
                    "thumb", "SWITCH", "enter", "exit", "thumb.rif"
                )
            },
            blocks={
                "metadata": [
                    globals.BlockData(
                        "metadata",
                        (globals.BlockEntryData("kind", (globals.BlockValueData("string", "test"),)),),
                    )
                ]
            },
            tables={
                "values": globals.TableData(
                    "values", ("value",), ((1,),), {"value": 0}
                )
            },
        )
        context = session.freeze()
        flags["data"] = "rw"

        self.assertNotIn("data", context.config.sectionflags)
        with self.assertRaises(TypeError):
            context.tables["other"] = context.tables["values"]
        with self.assertRaises(TypeError):
            context.config.sectionflags["text"] = "rw"
        with self.assertRaises(TypeError):
            context.blocks["metadata"] = ()
        with self.assertRaises(TypeError):
            context.tables["values"].columns["other"] = 1


if __name__ == "__main__":
    unittest.main()
