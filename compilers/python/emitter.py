from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from typing import Any

from .ast_nodes import Program
from .lexer import Token


class Emitter:
    ops = {
        "save_world": 1,
        "save_type": 2,
        "save_words": 3,
        "save_register": 4,
        "save_rule": 5,
    }

    def emit(self, program: Program) -> bytes:
        out = bytearray()
        self._record(out, "save_world", program.world)
        self._record(out, "save_type", program.types)
        self._record(out, "save_words", program.words)
        self._record(out, "save_register", {"registers": program.registers, "sregs": program.sregs})
        self._record(out, "save_rule", program.compile_rules())
        return bytes(out)

    def _record(self, out: bytearray, op: str, payload: Any) -> None:
        body = json.dumps(to_plain(payload), ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        out.append(self.ops[op])
        out.extend(len(body).to_bytes(4, "little"))
        out.extend(body)


def to_plain(value: Any) -> Any:
    if isinstance(value, Token):
        return {"kind": value.kind, "value": value.value, "line": value.line, "col": value.col}
    if isinstance(value, bytes):
        return list(value)
    if is_dataclass(value):
        result: dict[str, Any] = {}
        for item in fields(value):
            result[item.name] = to_plain(getattr(value, item.name))
        result["node"] = type(value).__name__
        return result
    if isinstance(value, dict):
        return {str(k): to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_plain(v) for v in value]
    return value
