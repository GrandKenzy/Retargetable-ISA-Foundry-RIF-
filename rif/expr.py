from __future__ import annotations

import ast
from typing import Any, Callable

from .errors import PackError

NameResolver = Callable[[str], Any]


class UnresolvedExpression(Exception):
    def __init__(self, name: str):
        self.name = name
        super().__init__(name)


def eval_int_expr(expr: Any, resolver: NameResolver | None = None) -> int:
    text = str(expr).strip()
    if not text:
        raise PackError("expresion numerica vacia")
    try:
        return int(text.replace("_", ""), 0)
    except ValueError:
        pass
    compact = text.replace("_", "")
    if len(compact) > 1 and compact.startswith("0") and all(ch in "01" for ch in compact):
        return int(compact, 2)

    tree = ast.parse(text, mode="eval")
    evaluator = _Evaluator(resolver or _missing)
    value = evaluator.visit(tree.body)
    if not isinstance(value, int):
        raise PackError(f'expresion "{text}" no produce entero')
    return value


class _Evaluator(ast.NodeVisitor):
    def __init__(self, resolver: NameResolver):
        self.resolver = resolver

    def visit_Constant(self, node: ast.Constant) -> int:
        if isinstance(node.value, bool):
            return int(node.value)
        if isinstance(node.value, int):
            return node.value
        raise PackError(f"literal no numerico en expresion: {node.value!r}")

    def visit_Name(self, node: ast.Name) -> int:
        return _as_int(self.resolver(node.id), node.id)

    def visit_Attribute(self, node: ast.Attribute) -> int:
        name = _name_from_node(node)
        return _as_int(self.resolver(name), name)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> int:
        value = self.visit(node.operand)
        if isinstance(node.op, ast.UAdd):
            return value
        if isinstance(node.op, ast.USub):
            return -value
        if isinstance(node.op, ast.Invert):
            return ~value
        raise PackError("operador unario no soportado")

    def visit_BinOp(self, node: ast.BinOp) -> int:
        left = self.visit(node.left)
        right = self.visit(node.right)
        op = node.op
        if isinstance(op, ast.Add):
            return left + right
        if isinstance(op, ast.Sub):
            return left - right
        if isinstance(op, ast.Mult):
            return left * right
        if isinstance(op, ast.FloorDiv):
            return left // right
        if isinstance(op, ast.Div):
            if left % right != 0:
                raise PackError("division no entera en expresion numerica")
            return left // right
        if isinstance(op, ast.Mod):
            return left % right
        if isinstance(op, ast.LShift):
            return left << right
        if isinstance(op, ast.RShift):
            return left >> right
        if isinstance(op, ast.BitAnd):
            return left & right
        if isinstance(op, ast.BitOr):
            return left | right
        if isinstance(op, ast.BitXor):
            return left ^ right
        raise PackError("operador binario no soportado")

    def visit_Call(self, node: ast.Call) -> int:
        raise PackError("llamadas no soportadas en expresiones numericas")

    def generic_visit(self, node: ast.AST) -> int:
        raise PackError(f"expresion numerica no soportada: {type(node).__name__}")


def _name_from_node(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_name_from_node(node.value)}.{node.attr}"
    raise PackError("referencia no soportada en expresion")


def _as_int(value: Any, name: str) -> int:
    if value in (None, ""):
        raise UnresolvedExpression(name)
    if isinstance(value, int):
        return value
    text = str(value).strip().replace("_", "")
    return int(text, 0)


def _missing(name: str) -> Any:
    raise UnresolvedExpression(name)
