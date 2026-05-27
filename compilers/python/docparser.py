from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


TokenType = Literal["TEXT", "BAR", "END", "EOF"]
SectionType = Literal["text", "code"]


@dataclass(frozen=True)
class Token:
    type: TokenType
    value: str
    line: int
    column: int


class DocParseError(Exception):
    def __init__(self, message: str, token: Token) -> None:
        super().__init__(f"{message} at line {token.line}, column {token.column}")
        self.token = token


def lex(source: str) -> list[Token]:
    tokens: list[Token] = []

    source = source.replace("\r\n", "\n").replace("\r", "\n")
    lines = source.split("\n")

    for index, raw_line in enumerate(lines):
        line_number = index + 1
        stripped = raw_line.strip()

        if stripped == "|":
            tokens.append(
                Token(
                    type="BAR",
                    value="|",
                    line=line_number,
                    column=raw_line.index("|") + 1,
                )
            )
            continue

        if stripped == "@END":
            tokens.append(
                Token(
                    type="END",
                    value="@END",
                    line=line_number,
                    column=raw_line.index("@END") + 1,
                )
            )
            continue

        tokens.append(
            Token(
                type="TEXT",
                value=raw_line,
                line=line_number,
                column=1,
            )
        )

    tokens.append(
        Token(
            type="EOF",
            value="",
            line=len(lines) + 1,
            column=1,
        )
    )

    return tokens


class Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.index = 0

    def parse(self) -> dict[str, list[dict[str, str]]]:
        entries: dict[str, list[dict[str, str]]] = {}

        self._skip_blank_lines()

        while not self._is("EOF"):
            name, sections = self._parse_entry()

            if name in entries:
                raise DocParseError(
                    f'Duplicate documentation entry "{name}"',
                    self._current(),
                )

            entries[name] = sections
            self._skip_blank_lines()

        return entries

    def _parse_entry(self) -> tuple[str, list[dict[str, str]]]:
        name_token = self._consume("TEXT", "Expected entry name")
        name = name_token.value.strip()

        if not name:
            raise DocParseError("Entry name cannot be empty", name_token)

        self._consume("BAR", f'Expected "|" after entry name "{name}"')

        sections: list[dict[str, str]] = []
        current_type: SectionType = "text"
        buffer: list[str] = []

        while not self._is("EOF"):
            token = self._current()

            if token.type == "TEXT":
                buffer.append(token.value)
                self._advance()
                continue

            if token.type == "BAR":
                sections.append(
                    {
                        "type": current_type,
                        "content": self._normalize_block(buffer),
                    }
                )

                buffer.clear()
                current_type = self._toggle_type(current_type)
                self._advance()
                continue

            if token.type == "END":
                sections.append(
                    {
                        "type": current_type,
                        "content": self._normalize_block(buffer),
                    }
                )

                self._advance()
                self._validate_entry(name, sections, token)
                return name, sections

            raise DocParseError(f'Unexpected token "{token.type}"', token)

        raise DocParseError(f'Missing @END for entry "{name}"', self._current())

    def _validate_entry(
        self,
        name: str,
        sections: list[dict[str, str]],
        token: Token,
    ) -> None:
        if len(sections) < 2:
            raise DocParseError(
                f'Entry "{name}" must contain at least one text section and one code section',
                token,
            )

        if len(sections) % 2 != 0:
            raise DocParseError(
                f'Entry "{name}" has an incomplete text/code pair',
                token,
            )

        for index, section in enumerate(sections):
            expected_type = "text" if index % 2 == 0 else "code"

            if section["type"] != expected_type:
                raise DocParseError(
                    f'Invalid section order in "{name}". Expected "{expected_type}"',
                    token,
                )

    def _normalize_block(self, lines: list[str]) -> str:
        return "\n".join(self._trim_empty_edges(lines))

    def _trim_empty_edges(self, lines: list[str]) -> list[str]:
        start = 0
        end = len(lines)

        while start < end and lines[start].strip() == "":
            start += 1

        while end > start and lines[end - 1].strip() == "":
            end -= 1

        return lines[start:end]

    def _toggle_type(self, section_type: SectionType) -> SectionType:
        return "code" if section_type == "text" else "text"

    def _skip_blank_lines(self) -> None:
        while self._is("TEXT") and self._current().value.strip() == "":
            self._advance()

    def _consume(self, token_type: TokenType, message: str) -> Token:
        token = self._current()

        if token.type != token_type:
            raise DocParseError(message, token)

        self._advance()
        return token

    def _is(self, token_type: TokenType) -> bool:
        return self._current().type == token_type

    def _current(self) -> Token:
        return self.tokens[self.index]

    def _advance(self) -> Token:
        token = self._current()

        if token.type != "EOF":
            self.index += 1

        return token


def parse_documentation(source: str) -> dict[str, list[dict[str, str]]]:
    tokens = lex(source)
    parser = Parser(tokens)
    return parser.parse()


def parse_file(input_path: str | Path) -> dict[str, list[dict[str, str]]]:
    path = Path(input_path)
    source = path.read_text(encoding="utf-8")
    return parse_documentation(source)


def write_json(
    data: dict[str, list[dict[str, str]]],
    output_path: str | Path,
) -> None:
    path = Path(output_path)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python doc_parser.py <input-file> [output-file]", file=sys.stderr)
        raise SystemExit(1)

    input_path = Path(sys.argv[1])

    if len(sys.argv) >= 3:
        output_path = Path(sys.argv[2])
    else:
        output_path = input_path.with_suffix(".json")

    try:
        data = parse_file(input_path)
        write_json(data, output_path)
    except DocParseError as error:
        print(f"Parse error: {error}", file=sys.stderr)
        raise SystemExit(1)

    print(f"Generated {output_path}")


if __name__ == "__main__":
    main()