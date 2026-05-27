from __future__ import annotations

import re
from typing import Callable

from .ast_nodes import (
    InstructionNode,
    MacroNode,
    Program,
    RegisterInfo,
    RESERVED_INSTRUCTION_NAMES,
    RuleNode,
    SubRegisterInfo,
    TypeInfo,
    WordInfo,
    alias_name,
    indentation,
)
from .errors import FieldError, MacroSyntaxError, RuleSyntaxError
from .lexer import Lexer, Token


class Parser:
    allowed = {"world", "types", "words", "regs", "macros", "rules"}
    ident_re = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    section_re = re.compile(r"^\.([A-Za-z_][A-Za-z0-9_]*)$")

    def __init__(self, source: str):
        self.source = source

    def parse(self) -> Program:
        sections = self._sections()
        types = self._parse_types(sections["types"])
        words = self._parse_words(sections["words"])
        registers, sregs = self._parse_regs(sections["regs"])
        macros = self._parse_macros(sections["macros"])
        rules = self._parse_rules(sections["rules"])
        program = Program(self._parse_world(sections["world"]), types, words, registers, sregs, rules, macros)
        for rule in program.rules.values():
            rule.compile(program.macros)
        return program

    def _sections(self) -> dict[str, list[tuple[int, str]]]:
        sections: dict[str, list[tuple[int, str]]] = {name: [] for name in self.allowed}
        current: str | None = None
        for line_no, raw in enumerate(self.source.splitlines(), 1):
            head = raw.split(";", 1)[0].strip()
            m = self.section_re.fullmatch(head)
            if m:
                name = m.group(1).lower()
                current = name if name in self.allowed else None
                continue
            if current is not None:
                sections[current].append((line_no, raw))
        return sections

    def _strip_comment(self, raw: str) -> str:
        return raw.split(";", 1)[0].strip()

    def _parse_world(self, lines: list[tuple[int, str]]) -> dict[str, str | list[str]]:
        out: dict[str, str | list[str]] = {}
        for line_no, raw in lines:
            line = self._strip_comment(raw)
            if not line:
                continue
            parts = line.split()
            if len(parts) < 2 or not self.ident_re.fullmatch(parts[0]):
                raise FieldError("invalid .world line", line_no)
            key = parts[0]
            if key in out:
                raise FieldError(f"duplicate .world key {key!r}", line_no)
            out[key] = parts[1] if len(parts) == 2 else parts[1:]
        return out

    def _parse_types(self, lines: list[tuple[int, str]]) -> dict[str, TypeInfo]:
        out: dict[str, TypeInfo] = {}
        for line_no, raw in lines:
            line = self._strip_comment(raw)
            if not line:
                continue
            fields_ = self._fields(line, 4, line_no, ".types")
            name = self._name(fields_[0], line_no)
            if name in out:
                raise FieldError(f"duplicate type {name!r}", line_no)
            out[name] = TypeInfo(name, self._int(fields_[1], line_no), self._int(fields_[2], line_no), self._int(fields_[3], line_no))
        return out

    def _parse_words(self, lines: list[tuple[int, str]]) -> dict[str, WordInfo]:
        specs: dict[str, tuple[int, str, int, int]] = {}
        for line_no, raw in lines:
            line = self._strip_comment(raw)
            if not line:
                continue
            name, data_source, align, pad = self._word_fields(line, line_no)
            if name in specs:
                raise FieldError(f"duplicate word {name!r}", line_no)
            specs[name] = (line_no, data_source, align, pad)
        resolved: dict[str, bytes] = {}
        resolving: set[str] = set()

        def resolve(name: str) -> bytes:
            if name in resolved:
                return resolved[name]
            if name not in specs:
                raise FieldError(f"unknown word {name!r}")
            line_no, source, _, _ = specs[name]
            if name in resolving:
                raise FieldError(f"cyclic word reference {name!r}", line_no)
            resolving.add(name)
            data = self._word_bytes(source, specs, resolve, line_no)
            resolving.remove(name)
            resolved[name] = data
            return data

        out: dict[str, WordInfo] = {}
        for name, (line_no, _, align, pad) in specs.items():
            out[name] = WordInfo(name, resolve(name), align, pad)
        return out

    def _word_fields(self, line: str, line_no: int) -> tuple[str, str, int, int]:
        fields_ = [x.strip() for x in line.split("|")]
        if len(fields_) == 2:
            name, data_source = fields_
            align = 0
            pad = 0
        elif len(fields_) == 4:
            name, data_source = fields_[0], fields_[1]
            align = self._int(fields_[2], line_no)
            pad = self._int(fields_[3], line_no)
        elif len(fields_) == 3:
            name, middle, pad_source = fields_
            pieces = middle.split()
            if not pieces:
                raise FieldError("invalid .words field count", line_no)
            data_source = " ".join(pieces[:-1])
            align = self._int(pieces[-1], line_no)
            pad = self._int(pad_source, line_no)
        else:
            raise FieldError("invalid .words field count", line_no)
        name = self._name(name, line_no)
        if align < 0:
            raise FieldError("invalid word ALIGN", line_no)
        if pad < 0 or pad > 255:
            raise FieldError("invalid word PAD", line_no)
        return name, data_source.strip(), align, pad

    def _word_bytes(self, source: str, specs: dict[str, tuple[int, str, int, int]], resolve: Callable[[str], bytes], line_no: int) -> bytes:
        if not source:
            return b""
        compact = source.replace("_", "").replace(" ", "")
        if re.fullmatch(r"[01]+", compact) and len(compact) % 8 == 0:
            return bytes(int(compact[i:i + 8], 2) for i in range(0, len(compact), 8))
        out = bytearray()
        for atom in re.split(r"[\s,]+", source.strip()):
            if not atom:
                continue
            cleaned = atom.replace("_", "")
            if cleaned in specs:
                out.extend(resolve(cleaned))
                continue
            if re.fullmatch(r"0[xX][0-9A-Fa-f]{1,2}", cleaned):
                out.append(int(cleaned, 16))
                continue
            if re.fullmatch(r"[0-9A-Fa-f]{2}", cleaned):
                out.append(int(cleaned, 16))
                continue
            if re.fullmatch(r"[01]+", cleaned):
                if len(cleaned) % 8 != 0:
                    raise FieldError("word binary length must be byte aligned", line_no)
                out.extend(int(cleaned[i:i + 8], 2) for i in range(0, len(cleaned), 8))
                continue
            if self.ident_re.fullmatch(cleaned):
                raise FieldError(f"unknown word reference {cleaned!r}", line_no)
            raise FieldError(f"invalid word byte source {atom!r}", line_no)
        return bytes(out)

    def _parse_regs(self, lines: list[tuple[int, str]]) -> tuple[dict[str, RegisterInfo], dict[str, SubRegisterInfo]]:
        regs: dict[str, RegisterInfo] = {}
        sregs: dict[str, SubRegisterInfo] = {}
        for line_no, raw in lines:
            line = self._strip_comment(raw)
            if not line:
                continue
            fields_ = self._fields(line, 6, line_no, ".regs")
            name = self._name(fields_[0], line_no)
            if name in regs:
                raise FieldError(f"duplicate register {name!r}", line_no)
            code = fields_[1]
            if not re.fullmatch(r"[01]+", code):
                raise FieldError("invalid register code", line_no)
            bits = self._int(fields_[2], line_no)
            ext = self._bit(fields_[3], line_no)
            rex8 = self._bit(fields_[4], line_no)
            parts = self._subset_parts(fields_[5], line_no)
            subregs = self._expand_subsets(name, code, bits, ext, rex8, parts, line_no)
            regs[name] = RegisterInfo(name, code, bits, ext, rex8, len(subregs), subregs)
            for sub in subregs.values():
                if sub.name in sregs:
                    raise FieldError(f"duplicate subregister {sub.name!r}", line_no)
                sregs[sub.name] = sub
        return regs, sregs

    def _parse_macros(self, lines: list[tuple[int, str]]) -> dict[str, MacroNode]:
        macros: dict[str, MacroNode] = {}
        current: MacroNode | None = None
        stack: list[tuple[int, InstructionNode]] = []
        for line_no, raw in lines:
            if not raw.strip() or raw.lstrip().startswith(";"):
                continue
            indent = indentation(raw)
            body = raw.strip()
            tokens = tuple(t for t in Lexer(body).lex() if t.kind not in {"EOF", "NEWLINE", "COMMENT"})
            if not tokens:
                continue
            if indent == 0:
                name, params = self._macro_header(tokens, line_no)
                if name in macros:
                    raise MacroSyntaxError(f"duplicate macro {name!r}", line_no)
                current = MacroNode(name, params, line_no, [])
                macros[name] = current
                stack.clear()
                continue
            if current is None:
                raise MacroSyntaxError("instruction outside macro", line_no)
            while stack and indent <= stack[-1][0]:
                stack.pop()
            instruction = self._instruction(tokens, line_no, indent, body)
            if instruction.kind == "need":
                raise MacroSyntaxError("macros cannot declare rule operands with need", line_no)
            if stack:
                stack[-1][1].children.append(instruction)
            else:
                current.instructions.append(instruction)
            if self._is_block(tokens):
                stack.append((indent, instruction))
        return macros

    def _macro_header(self, tokens: tuple[Token, ...], line_no: int) -> tuple[str, tuple[str, ...]]:
        if len(tokens) < 5 or tokens[0].kind != "IDENT" or tokens[0].value.lower() != "macro":
            raise MacroSyntaxError("expected macro header", line_no)
        if tokens[1].kind != "IDENT":
            raise MacroSyntaxError("macro name must be an identifier", line_no)
        name = self._name(tokens[1].value, line_no).lower()
        if name in RESERVED_INSTRUCTION_NAMES:
            raise MacroSyntaxError(f"macro name {name!r} conflicts with a built-in instruction", line_no)
        if tokens[2].kind != "LPAREN" or tokens[-2].kind != "RPAREN" or tokens[-1].kind != "COLON":
            raise MacroSyntaxError("macro header must use: macro name(param, ...):", line_no)
        inner = tokens[3:-2]
        if not inner:
            return name, ()
        params: list[str] = []
        expect_ident = True
        for token in inner:
            if expect_ident:
                if token.kind != "IDENT":
                    raise MacroSyntaxError("macro parameter must be an identifier", line_no, token.col)
                param = self._name(token.value, line_no)
                if param in params:
                    raise MacroSyntaxError(f"duplicate macro parameter {param!r}", line_no, token.col)
                params.append(param)
                expect_ident = False
            else:
                if token.kind != "COMMA":
                    raise MacroSyntaxError("expected ',' between macro parameters", line_no, token.col)
                expect_ident = True
        if expect_ident:
            raise MacroSyntaxError("macro parameter list cannot end with ','", line_no)
        return name, tuple(params)


    def _parse_rules(self, lines: list[tuple[int, str]]) -> dict[str, RuleNode]:
        rules: dict[str, RuleNode] = {}
        current: RuleNode | None = None
        stack: list[tuple[int, InstructionNode]] = []
        for line_no, raw in lines:
            if not raw.strip() or raw.lstrip().startswith(";"):
                continue
            indent = indentation(raw)
            body = raw.strip()
            tokens = tuple(t for t in Lexer(body).lex() if t.kind not in {"EOF", "NEWLINE", "COMMENT"})
            if not tokens:
                continue
            if indent == 0:
                if len(tokens) == 2 and tokens[0].kind == "IDENT" and tokens[1].kind == "COLON":
                    name = self._name(tokens[0].value, line_no)
                    if name in rules:
                        raise RuleSyntaxError(f"duplicate rule {name!r}", line_no)
                    current = RuleNode(name, line_no, [])
                    rules[name] = current
                    stack.clear()
                    continue
                raise RuleSyntaxError("expected rule header", line_no)
            if current is None:
                raise RuleSyntaxError("instruction outside rule", line_no)
            while stack and indent <= stack[-1][0]:
                stack.pop()
            instruction = self._instruction(tokens, line_no, indent, body)
            if stack:
                stack[-1][1].children.append(instruction)
            else:
                current.instructions.append(instruction)
            if self._is_block(tokens):
                stack.append((indent, instruction))
        return rules

    def _instruction(self, tokens: tuple[Token, ...], line_no: int, indent: int, body: str) -> InstructionNode:
        first = tokens[0]
        if first.kind != "IDENT":
            raise RuleSyntaxError("instruction must start with an identifier", line_no, first.col)
        kind = first.value.lower()
        return InstructionNode(kind, tokens[1:], line_no, indent, body)

    def _is_block(self, tokens: tuple[Token, ...]) -> bool:
        return bool(tokens and tokens[-1].kind == "COLON")

    def _fields(self, line: str, count: int, line_no: int, section: str) -> list[str]:
        fields_ = [x.strip() for x in line.split("|")]
        if len(fields_) != count or any(x == "" for x in fields_[:-1]):
            raise FieldError(f"invalid {section} field count", line_no)
        return fields_

    def _name(self, value: str, line_no: int) -> str:
        if not self.ident_re.fullmatch(value):
            raise FieldError(f"invalid identifier {value!r}", line_no)
        return value

    def _int(self, value: str, line_no: int) -> int:
        if not re.fullmatch(r"[0-9]+", value):
            raise FieldError(f"invalid integer {value!r}", line_no)
        return int(value)

    def _bit(self, value: str, line_no: int) -> int:
        n = self._int(value, line_no)
        if n not in (0, 1):
            raise FieldError(f"invalid bit {value!r}", line_no)
        return n

    def _subset_parts(self, value: str, line_no: int) -> tuple[str, ...]:
        parts = tuple(x.strip() for x in value.split(","))
        if not parts or any(not re.fullmatch(r"(?:\.\.)?[0-9]+", x) for x in parts):
            raise FieldError("invalid subset list", line_no)
        return parts

    def _expand_subsets(self, reg: str, code: str, reg_bits: int, ext: int, rex8: int, parts: tuple[str, ...], line_no: int) -> dict[str, SubRegisterInfo]:
        usable = list(parts)
        if usable and not usable[0].startswith("..") and int(usable[0]) == reg_bits:
            usable = usable[1:]
        out: dict[str, SubRegisterInfo] = {}
        next_range_start = 0
        for idx, part in enumerate(usable):
            alias = alias_name(idx)
            if part.startswith(".."):
                width = int(part[2:])
                if width <= 0:
                    raise FieldError("invalid subset width", line_no)
                start = next_range_start
                end = start + width - 1
                if end >= reg_bits:
                    raise FieldError("subset range overflows register", line_no)
                next_range_start = end + 1
            else:
                width = int(part)
                if width <= 0 or width > reg_bits:
                    raise FieldError("invalid subset width", line_no)
                start = 0
                end = width - 1
                next_range_start = width
            name = f"{reg}[{alias}]"
            out[alias] = SubRegisterInfo(name, alias, width, reg, code, ext, rex8, start, end)
        return out
