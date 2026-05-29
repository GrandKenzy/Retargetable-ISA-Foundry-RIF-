"""Interfaz de Línea de Comandos (CLI) de RIF.

Este módulo expone la CLI oficial de RIF, permitiendo realizar tareas de
análisis léxico, parseo de reglas, empaquetado preliminar, enlace (linking),
compilación de instrucciones individuales y construcción de imágenes binarias
directamente desde la terminal.
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

from .errors import RIFError
from .linker import build_file, link_file
from .packer import pack_file
from .parser import Parser, parse_packer_config
from .compiler import Compiler


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada principal para el parsing de argumentos y ejecución de comandos de la CLI.

    Soporta los subcomandos:
    - lex: Imprime la secuencia de tokens resultantes del análisis léxico.
    - parse: Muestra la información AST estructurada y las configuraciones del .pack.
    - pack: Empaqueta el archivo fuente de entrada en su formato temporal consolidado.
    - link: Enlaza los fragmentos locales a las secciones de ensamblador.
    - compile: Compila y emite el stream de bits para una única línea de instrucción de hardware.
    - build: Enlaza y genera un binario ejecutable estructurado.

    Args:
        argv: Lista opcional de argumentos pasados por terminal.

    Returns:
        Código de estado de la aplicación (0 para éxito, 1 para error controlado, 2 para comando no reconocido).
    """
    parser = argparse.ArgumentParser(prog="rif", description="RIF lexer/parser/packer tools")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_lex = sub.add_parser("lex", help="lex a source file")
    p_lex.add_argument("source")

    p_parse = sub.add_parser("parse", help="parse a source file")
    p_parse.add_argument("source")

    p_pack = sub.add_parser("pack", help="create source.pack.temp")
    p_pack.add_argument("source")
    p_pack.add_argument("-o", "--output")

    p_link = sub.add_parser("link", help="link fragments and reparse the linked source")
    p_link.add_argument("source")
    p_link.add_argument("-o", "--output")

    p_compile = sub.add_parser("compile", help="compile one instruction using a RIF rule file")
    p_compile.add_argument("source", help="RIF rule file, for example store.amd64.pack")
    p_compile.add_argument("instruction", nargs="+", help="instruction to compile, for example: copy rax = rbx")

    p_build = sub.add_parser("build", help="build a linked binary from a RIF file")
    p_build.add_argument("source", help="RIF rule/link file")
    p_build.add_argument("-o", "--output")
    p_build.add_argument("-s", "--source-text", default="", help="optional assembly source text")

    p_help = sub.add_parser("help", help="show local RIF help")
    p_help.add_argument("topic", nargs="?", help="markdown topic name")
    p_help.add_argument("--open", action="store_true", help="open help/index.html")

    args = parser.parse_args(argv)

    try:
        if args.cmd == "help":
            return _run_help(args.topic, args.open)

        if args.cmd == "lex":
            text = Path(args.source).read_text(encoding="utf-8")
            p = Parser(text, args.source)
            cfg = p.lexer_config
            print(f"config.comment={cfg.comment!r}")
            print(f"config.separator={cfg.separator!r}")
            print(f"config.block={cfg.block!r}")
            print(f"config.encoding={cfg.encoding!r}")
            for line, indent, _, tokens in p.lexer.lex():
                values = " ".join(f"{t.kind}:{t.value}" for t in tokens)
                print(f"{line}:{indent}: {values}")
            return 0

        if args.cmd == "parse":
            text = Path(args.source).read_text(encoding="utf-8")
            program = Parser(text, args.source).parse()
            config = parse_packer_config(program)
            cfg = program.lexer_config
            print(f"comment={cfg.comment!r}")
            print(f"separator={cfg.separator!r}")
            print(f"block={cfg.block!r}")
            print(f"encoding={cfg.encoding!r}")
            print(f"sections={list(program.sections)}")
            print(f"world={program.world.values}")
            print(f"objects={list(program.objects)}")
            if program.regs.registers:
                print(f"regs.hiddesubs={program.regs.hiddesubs}")
                print(f"regs.order_column={program.regs.order_column}")
                print(f"regs.registers={[r.name for r in program.regs.registers]}")
                print(f"regs.aliases={program.regs.aliases}")
            if program.vars:
                print(f"vars={{{', '.join(f'{name}: {var.bits}' for name, var in program.vars.items())}}}")
            if program.type_defs.definitions:
                print(f"types={program.type_defs.order}")
                for name in program.type_defs.order:
                    type_def = program.type_defs.definitions[name]
                    print(f"type[{name}].size={type_def.size} values={type_def.values}")
            if program.data_definition.pattern:
                print(f"data_definition.pattern={program.data_definition.pattern}")
                print(f"data_definition.options={program.data_definition.options}")
            if program.memory.regions:
                print(f"memory={program.memory.order}")
                for name in program.memory.order:
                    region = program.memory.regions[name]
                    print(
                        f"memory[{name}].kind={region.kind} section={region.section} "
                        f"bytes={region.bytes} type={region.type_token} count={region.count}"
                    )
            if program.headers.blocks:
                print(f"headers={program.headers.order}")
                for name in program.headers.order:
                    header = program.headers.blocks[name]
                    table_rows = list(header.table.rows) if header.table else []
                    print(f"header[{name}].size={header.size} rows={table_rows}")
            for section, table in program.tables.items():
                print(f"table[{section}].fields={table.fields}")
                for name, row in table.rows.items():
                    print(f"table[{section}].{name}={row.values}")
            print(f"packer.enabled={config.enabled}")
            print(f"packer.fsystem={config.fsystem}")
            print(f"packer.ext={config.ext}")
            print(f"packer.sectpre={config.sectpre}")
            print(f"packer.subpre={config.subpre}")
            print(f"packer.definesec={sorted(config.defined_sections)}")
            print(f"packer.setpre={config.prefix_to_section}")
            print(f"packer.needsect={sorted(config.required_prefixes)}")
            print(f"packer.plugext={config.plugext}")
            print(f"packer.plugins={config.plugins}")
            print(f"packer.precompile={config.precompilers}")
            print(f"packer.types={config.types}")
            return 0

        if args.cmd == "pack":
            result = pack_file(args.source, args.output)
            print(result.output_path)
            for fragment in result.fragments:
                print(f"+ {fragment}")
            return 0

        if args.cmd == "link":
            result = link_file(args.source, args.output)
            print(result.output_path)
            print(f"sections={list(result.program.sections)}")
            for fragment in result.fragments:
                print(f"+ {fragment}")
            return 0

        if args.cmd == "compile":
            instruction = " ".join(args.instruction)
            compiler = Compiler.from_file(args.source)
            result = compiler.compile_line(instruction)
            print(f"rule={result.rule_name}")
            print(f"bits={result.bits}")
            if result.hex is not None:
                print(f"hex={result.hex}")
            else:
                print("hex=<placeholder>")
                for resolved in result.resolved_placeholders:
                    placeholder = resolved.placeholder
                    print(f"resolved={placeholder.name}:{placeholder.kind}:{resolved.value}")
                for placeholder in result.placeholders:
                    print(f"placeholder={placeholder.name}:{placeholder.kind}:{placeholder.reason or ''}")
            return 0

        if args.cmd == "build":
            result = build_file(args.source, args.output, args.source_text, write=args.output is not None)
            print(f"bytes={len(result.data)}")
            print(f"hex={result.hex}")
            for block in result.blocks:
                print(
                    f"block={block.name}:{block.kind}:off={block.physical_offset}:"
                    f"voff={block.virtual_offset}:size={block.physical_size}:vsize={block.virtual_size}"
                )
            for placeholder in result.placeholders:
                print(f"placeholder={placeholder.name}:{placeholder.kind}:{placeholder.reason or ''}")
            return 0

    except RIFError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 2


def _help_root() -> Path:
    source_root = Path(__file__).resolve().parents[1] / "help"
    if source_root.exists():
        return source_root
    return Path(sys.prefix) / "share" / "rif" / "help"


def _help_topics() -> dict[str, Path]:
    root = _help_root()
    if not root.exists():
        return {}
    return {path.stem: path for path in sorted((root / "resources").rglob("*.md"))}


def _run_help(topic: str | None, open_index: bool) -> int:
    root = _help_root()
    index = root / "index.html"

    if open_index:
        webbrowser.open(index.resolve().as_uri())
        print(index)
        return 0

    topics = _help_topics()
    if topic:
        path = topics.get(topic)
        if path is None:
            print(f"help topic not found: {topic}", file=sys.stderr)
            _print_help_topics(topics)
            return 1
        print(path.read_text(encoding="utf-8"))
        return 0

    print(index)
    _print_help_topics(topics)
    return 0


def _print_help_topics(topics: dict[str, Path]) -> None:
    for name in sorted(topics):
        print(name)


def run() -> None:
    """Punto de entrada de bootstrap de la CLI de RIF.

    Lanza SystemExit con el código de retorno devuelto por main().
    """
    raise SystemExit(main())


if __name__ == "__main__":
    run()
