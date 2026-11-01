"""Executable parity checks between RIF's Python and Gram/AOT frontends."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gram.core.ast.nodes import ASTRef, ASTTokenNode, ArrayNode, RawNode

from MIR.compiled import context_to_dict, program_to_dict
from MIR.pipeline import compile_source

from .aot import GIRAdapter
from .processor.parsing import SourceParser


def _sequence_items(value: Any) -> list[Any]:
    values = value.items if isinstance(value, ArrayNode) else value
    result: list[Any] = []
    for item in values:
        if isinstance(item, (ArrayNode, list, tuple)):
            result.extend(_sequence_items(item))
        else:
            result.append(item)
    return result


def ast_signature(value: Any) -> Any:
    """Normalize AST nodes without retaining object identity or source paths."""

    if isinstance(value, ASTRef):
        if value.name == "RULE" and len(value.nodes) == 6:
            children = tuple(ast_signature(node) for node in value.nodes[:5])
            instructions = tuple(ast_signature(node) for node in value.nodes[5])
            return ("ref", value.name, children + (("instructions", instructions),))
        children = _sequence_items(value.nodes)
        return ("ref", value.name, tuple(ast_signature(node) for node in children))
    if isinstance(value, ArrayNode):
        return ("sequence", tuple(ast_signature(node) for node in _sequence_items(value)))
    if isinstance(value, RawNode):
        return (
            "raw",
            tuple((token.token.name, token.value) for token in value.tokens),
        )
    if isinstance(value, (list, tuple)):
        return ("sequence", tuple(ast_signature(node) for node in _sequence_items(value)))
    if isinstance(value, ASTTokenNode):
        return ("token", value.token.token.name, value.token.value)
    raise TypeError(f"nodo AST no soportado: {type(value).__name__}")


def _context_signature(program: Any) -> dict[str, Any]:
    context = context_to_dict(program.context)
    context["tables"] = {
        name: {
            "headers": list(table.headers),
            "rows": [list(row) for row in table.matrix],
        }
        for name, table in sorted(program.context.tables.items())
    }
    return context


@dataclass(frozen=True)
class ParityReport:
    """Comparison result suitable for tests, diagnostics and JSON tooling."""

    path: str
    ast_equal: bool
    program_equal: bool
    context_equal: bool
    differences: tuple[str, ...]

    @property
    def equal(self) -> bool:
        return not self.differences

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "equal": self.equal,
            "ast_equal": self.ast_equal,
            "program_equal": self.program_equal,
            "context_equal": self.context_equal,
            "differences": list(self.differences),
        }


def compare_target(path: str | Path) -> ParityReport:
    """Compile one physical `.rif` with both frontends and compare contracts."""

    source_path = Path(path).expanduser().resolve()
    if source_path.suffix.lower() != ".rif":
        raise ValueError("La paridad de frontend requiere una fuente .rif física.")
    if not source_path.is_file():
        raise FileNotFoundError(source_path)

    python_ast = SourceParser(backend="python").parse_file(source_path)
    aot_ast = SourceParser(backend="aot").parse_file(source_path)
    python_program = compile_source(source_path, backend="python")
    aot_program = compile_source(source_path, backend="aot")
    source_root = source_path.parent
    python_rules = program_to_dict(python_program, source_root)
    aot_rules = program_to_dict(aot_program, source_root)
    python_context = _context_signature(python_program)
    aot_context = _context_signature(aot_program)

    differences: list[str] = []
    ast_equal = ast_signature(python_ast) == ast_signature(aot_ast)
    if not ast_equal:
        differences.append("ast")
    program_equal = python_rules == aot_rules
    if not program_equal:
        differences.append("program")
    context_equal = python_context == aot_context
    if not context_equal:
        differences.append("context")
    return ParityReport(
        path=str(source_path),
        ast_equal=ast_equal,
        program_equal=program_equal,
        context_equal=context_equal,
        differences=tuple(differences),
    )


__all__ = ["ParityReport", "ast_signature", "compare_target"]
