from __future__ import annotations

"""Módulo del analizador léxico (Lexer) del compilador RIF.

Se encarga de procesar el flujo de texto fuente de RIF y transformarlo en una
secuencia de objetos `Token` clasificados, soportando la configuración dinámica
de caracteres de comentarios, separadores y bloques.
"""

from .errors import LexError
from .models import LexerConfig, Token


class Lexer:
    """Analizador léxico configurable para la sintaxis RIF.

    La configuración del lexer se puede descubrir dinámicamente o inicializar
    mediante directivas de cabecera como:

        commit    ;
        separator |
        blocks    :
        encoding  utf-8

    Las cadenas literales utilizan comillas dobles y los comentarios solo se
    remueven fuera de las mismas.
    """

    def __init__(self, source: str, config: LexerConfig | None = None, comment_char: str | None = None):
        if config is None:
            config = LexerConfig(comment=comment_char or ";")
        config.validate()
        self.source = source
        self.config = config
        self.comment_char = config.comment

    @staticmethod
    def discover_config(source: str) -> LexerConfig:
        """Escanear las líneas iniciales del archivo para autodetectar la directiva de configuración."""
        comment = Lexer.discover_comment_char(source)
        cfg = LexerConfig(comment=comment)
        probe = Lexer(source, cfg)
        for _, _, _, tokens in probe.lex():
            if not tokens:
                continue
            if tokens[0].kind == "SECTION":
                break
            if tokens[0].kind != "IDENT":
                continue
            name = tokens[0].value
            args = tokens[1:]
            if name in ("commit", "comment"):
                if args:
                    cfg.comment = args[0].value
            elif name == "separator":
                if args:
                    cfg.separator = args[0].value
            elif name == "blocks":
                if args:
                    cfg.block = args[0].value
            elif name == "encoding":
                if args:
                    cfg.encoding = args[0].value
        cfg.validate()
        return cfg

    @staticmethod
    def discover_comment_char(source: str) -> str:
        """Descubre el carácter de comentario autodetectando la primera línea no vacía."""
        for raw in source.splitlines():
            stripped = raw.strip()
            if not stripped:
                continue
            if stripped in ("commit", "comment"):
                return ";"
            if stripped.startswith("commit"):
                rest = stripped[len("commit"):].strip()
            elif stripped.startswith("comment"):
                rest = stripped[len("comment"):].strip()
            else:
                break

            if not rest:
                return ";"
            if len(rest) >= 2 and rest[0] == rest[-1] == '"':
                value = rest[1:-1]
                if len(value) == 1:
                    return value
            if len(rest) >= 1:
                return rest[0]
            break
        return ";"

    def strip_comment(self, raw: str) -> str:
        """Remueve de forma segura el comentario de una línea de código fuente."""
        quote = False
        escaped = False
        out: list[str] = []
        for ch in raw:
            if escaped:
                out.append(ch)
                escaped = False
                continue
            if ch == "\\" and quote:
                out.append(ch)
                escaped = True
                continue
            if ch == '"':
                out.append(ch)
                quote = not quote
                continue
            if ch == self.comment_char and not quote:
                break
            out.append(ch)
        return "".join(out).rstrip()

    def lex_line(self, raw: str, line: int) -> list[Token]:
        """Procesa una única línea de texto y la convierte en una lista de tokens."""
        content = self.strip_comment(raw)
        tokens: list[Token] = []
        i = 0
        n = len(content)
        while i < n:
            ch = content[i]
            col = i + 1
            if ch.isspace():
                i += 1
                continue
            if ch == self.config.block:
                tokens.append(Token("BLOCK", ch, line, col, ch))
                i += 1
                continue
            if ch == self.config.separator:
                tokens.append(Token("SEP", ch, line, col, ch))
                i += 1
                continue
            if ch == ",":
                tokens.append(Token("COMMA", ch, line, col, ch))
                i += 1
                continue
            if ch == "=":
                if i + 1 < n and content[i + 1] == "=":
                    tokens.append(Token("OP", "==", line, col, "=="))
                    i += 2
                    continue
                tokens.append(Token("EQUAL", ch, line, col, ch))
                i += 1
                continue
            if ch == "!" and i + 1 < n and content[i + 1] == "=":
                tokens.append(Token("OP", "!=", line, col, "!="))
                i += 2
                continue
            if ch == "*":
                tokens.append(Token("STAR", ch, line, col, ch))
                i += 1
                continue
            if ch in "+/%&|^~()<>":
                if ch in "<>" and i + 1 < n and content[i + 1] in {ch, "="}:
                    value = ch + content[i + 1]
                    tokens.append(Token("OP", value, line, col, value))
                    i += 2
                    continue
                tokens.append(Token("OP", ch, line, col, ch))
                i += 1
                continue
            if ch == "\\":
                tokens.append(Token("BACKSLASH", ch, line, col, ch))
                i += 1
                continue
            if ch == '"':
                value, end = self._read_string(content, i, line, col)
                tokens.append(Token("STRING", value, line, col, content[i:end]))
                i = end
                continue
            if ch == ".":
                value, end = self._read_symbol(content, i)
                if value == ".":
                    tokens.append(Token("DOT", value, line, col, value))
                    i = end
                    continue
                tokens.append(Token("SECTION", value, line, col, value))
                i = end
                continue
            if self._is_word_start(ch):
                value, end = self._read_symbol(content, i)
                kind = "INT" if self._looks_int(value) else "IDENT"
                tokens.append(Token(kind, value, line, col, value))
                i = end
                continue
            raise LexError(f"unexpected character {ch!r}", line, col)
        return tokens

    def lex(self) -> list[tuple[int, int, str, list[Token]]]:
        """Procesa todo el código fuente del objeto y devuelve las líneas con sus correspondientes tokens."""
        out: list[tuple[int, int, str, list[Token]]] = []
        for line_no, raw in enumerate(self.source.splitlines(), 1):
            if not self.strip_comment(raw).strip():
                continue
            indent = len(raw) - len(raw.lstrip(" "))
            tokens = self.lex_line(raw, line_no)
            if tokens:
                out.append((line_no, indent, raw, tokens))
        return out

    def _read_string(self, content: str, i: int, line: int, col: int) -> tuple[str, int]:
        out: list[str] = []
        j = i + 1
        escaped = False
        while j < len(content):
            ch = content[j]
            if escaped:
                out.append(self._escape(ch))
                escaped = False
                j += 1
                continue
            if ch == "\\":
                escaped = True
                j += 1
                continue
            if ch == '"':
                return "".join(out), j + 1
            out.append(ch)
            j += 1
        raise LexError("unterminated string", line, col)

    def _escape(self, ch: str) -> str:
        return {
            "n": "\n",
            "r": "\r",
            "t": "\t",
            '"': '"',
            "\\": "\\",
        }.get(ch, ch)

    def _read_symbol(self, content: str, i: int) -> tuple[str, int]:
        j = i
        while j < len(content):
            ch = content[j]
            if ch == self.config.block:
                next_ch = content[j + 1] if j + 1 < len(content) else ""
                if not next_ch or next_ch.isspace():
                    break
            if ch.isspace() or ch in {self.config.separator, '"', ",", "="} or ch in {"*", "\\", "+", "/", "%", "&", "|", "^", "~", "(", ")", "<", ">"}:
                break
            j += 1
        return content[i:j], j

    def _is_word_start(self, ch: str) -> bool:
        return ch.isalnum() or ch in "_-"

    def _looks_int(self, value: str) -> bool:
        compact = value.replace("_", "")
        if compact.startswith(("0x", "0X")):
            return len(compact) > 2 and all(ch in "0123456789abcdefABCDEF" for ch in compact[2:])
        if compact.startswith(("0b", "0B")):
            return len(compact) > 2 and all(ch in "01" for ch in compact[2:])
        return compact.isdigit()
