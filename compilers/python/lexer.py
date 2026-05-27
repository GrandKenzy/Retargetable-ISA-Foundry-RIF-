from __future__ import annotations

from dataclasses import dataclass

from .errors import CompileError


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    line: int
    col: int


class Lexer:
    def __init__(self, source: str):
        self.source = source
        self.i = 0
        self.line = 1
        self.col = 1
        self.n = len(source)

    def lex(self) -> list[Token]:
        out: list[Token] = []
        while self.i < self.n:
            ch = self.source[self.i]
            if ch in " \t\r":
                self._advance()
                continue
            if ch == "\n":
                out.append(Token("NEWLINE", "\n", self.line, self.col))
                self._advance_line()
                continue
            if ch == ";":
                start_line, start_col = self.line, self.col
                out.append(Token("COMMENT", self._read_until_newline(), start_line, start_col))
                continue
            if ch == '"':
                out.append(self._read_string())
                continue
            if ch == ".":
                start_line, start_col = self.line, self.col
                if self._peek(1) == ".":
                    self._advance()
                    self._advance()
                    out.append(Token("RANGE", "..", start_line, start_col))
                else:
                    self._advance()
                    out.append(Token("DOT", ".", start_line, start_col))
                continue
            if ch.isalpha() or ch == "_":
                out.append(self._read_ident())
                continue
            if ch.isdigit():
                out.append(self._read_number())
                continue
            kind = {
                "|": "PIPE",
                ",": "COMMA",
                ":": "COLON",
                "=": "EQUAL",
                "-": "MINUS",
                "+": "PLUS",
                "[": "LBRACKET",
                "]": "RBRACKET",
                "(": "LPAREN",
                ")": "RPAREN",
            }.get(ch)
            if kind is None:
                raise CompileError(f"invalid token {ch!r}", self.line, self.col)
            out.append(Token(kind, ch, self.line, self.col))
            self._advance()
        out.append(Token("EOF", "", self.line, self.col))
        return out

    def _peek(self, offset: int) -> str:
        j = self.i + offset
        return self.source[j] if j < self.n else ""

    def _advance(self) -> None:
        self.i += 1
        self.col += 1

    def _advance_line(self) -> None:
        self.i += 1
        self.line += 1
        self.col = 1

    def _read_until_newline(self) -> str:
        start = self.i
        while self.i < self.n and self.source[self.i] != "\n":
            self._advance()
        return self.source[start:self.i]

    def _read_ident(self) -> Token:
        start_i, start_line, start_col = self.i, self.line, self.col
        while self.i < self.n and (self.source[self.i].isalnum() or self.source[self.i] == "_"):
            self._advance()
        return Token("IDENT", self.source[start_i:self.i], start_line, start_col)

    def _read_number(self) -> Token:
        start_i, start_line, start_col = self.i, self.line, self.col
        while self.i < self.n and (self.source[self.i].isalnum() or self.source[self.i] == "_"):
            self._advance()
        return Token("NUMBER", self.source[start_i:self.i], start_line, start_col)

    def _read_string(self) -> Token:
        start_line, start_col = self.line, self.col
        self._advance()
        chars: list[str] = []
        while self.i < self.n:
            ch = self.source[self.i]
            if ch == '"':
                self._advance()
                return Token("STRING", "".join(chars), start_line, start_col)
            if ch == "\\":
                self._advance()
                if self.i >= self.n:
                    raise CompileError("unterminated string", start_line, start_col)
                esc = self.source[self.i]
                chars.append({"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}.get(esc, esc))
                self._advance()
                continue
            if ch == "\n":
                raise CompileError("unterminated string", start_line, start_col)
            chars.append(ch)
            self._advance()
        raise CompileError("unterminated string", start_line, start_col)
