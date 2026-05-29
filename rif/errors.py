from __future__ import annotations

"""Módulo de gestión de errores y excepciones del compilador RIF.

Define las excepciones del sistema para el lexer, parser y packer, además de un
acumulador global multilinea (`Errors`) utilizado por los plugins del compilador.
"""


class RIFError(Exception):
    """Excepción base para todos los errores dentro del compilador RIF."""


class LexError(RIFError):
    """Excepción lanzada cuando ocurre un error en el analizador léxico (Lexer)."""

    def __init__(self, message: str, line: int | None = None, col: int | None = None):
        self.message = message
        self.line = line
        self.col = col
        if line is None:
            super().__init__(message)
        elif col is None:
            super().__init__(f"{message} en línea {line}")
        else:
            super().__init__(f"{message} en {line}:{col}")


class ParseError(RIFError):
    """Excepción lanzada cuando ocurre un error de sintaxis en el analizador sintáctico (Parser)."""

    def __init__(self, message: str, line: int | None = None):
        self.message = message
        self.line = line
        if line is None:
            super().__init__(message)
        else:
            super().__init__(f"{message} en línea {line}")


class PackError(RIFError):
    """Excepción lanzada cuando ocurre un error durante el empaquetado o la compilación de reglas."""

    def __init__(self, message: str, line: int | None = None):
        self.message = message
        self.line = line
        if line is None:
            super().__init__(message)
        else:
            super().__init__(f"{message} en línea {line}")


class EndSignal(SystemExit):
    """Señal de control interna utilizada por los plugins para detener el flujo de compilación."""

    def __init__(self, code: int = 1):
        self.code = code
        super().__init__(code)


class Errors:
    """Acumulador global de errores multilínea utilizado por los plugins de RIF.

    Cada error añadido se guarda como una lista de líneas de texto. El último error
    registrado queda expuesto en `Errors.last` para que el plugin `raise` pueda
    lanzarlo y terminar la ejecución del programa.
    """

    items: list[list[str]] = []
    last: list[str] | None = None

    @classmethod
    def add(cls, error: list[str] | tuple[str, ...] | str) -> list[str]:
        """Añade un nuevo error multilínea al acumulador global."""
        if isinstance(error, str):
            normalized = [error]
        else:
            normalized = [str(line) for line in error]

        cls.items.append(normalized)
        cls.last = normalized
        return normalized

    @classmethod
    def clear(cls) -> None:
        """Limpia todos los errores acumulados."""
        cls.items.clear()
        cls.last = None


def end(code: int = 1) -> None:
    """Detiene inmediatamente el flujo de ejecución lanzando la señal EndSignal."""
    raise EndSignal(code)


