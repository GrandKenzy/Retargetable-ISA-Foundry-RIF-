from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .ast_nodes import Program, SymbolInfo
from .emitter import Emitter
from .errors import CompileError
from .lexer import Lexer
from .parser import Parser


def compile_text(source: str) -> tuple[Program, bytes]:
    Lexer(source).lex()
    program = Parser(source).parse()
    return program, Emitter().emit(program)


def compile_file(input_path: str | Path, output_path: str | Path) -> tuple[Program, bytes]:
    path = Path(output_path)
    try:
        source = Path(input_path).read_text(encoding="utf-8")
        program, data = compile_text(source)
        path.write_text(" ".join(f"{x:02X}" for x in data) + "\n", encoding="utf-8")
        return program, data
    except CompileError:
        if path.exists():
            path.unlink()
        raise


def emit_rule_file(input_path: str | Path, rule_name: str, operands: Sequence[str], output_path: str | Path) -> bytes:
    path = Path(output_path)
    try:
        source = Path(input_path).read_text(encoding="utf-8")
        program, _ = compile_text(source)
        rule = program.compile_rules()[rule_name]
        data = rule.emit(operands, program)
        path.write_text(" ".join(f"{x:02X}" for x in data) + "\n", encoding="utf-8")
        return data
    except CompileError:
        if path.exists():
            path.unlink()
        raise
