"""Structured diagnostics shared by frontend, MIR and binary phases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Diagnostic:
    """One stable diagnostic independent of the backend that produced it."""

    message: str
    phase: str = "unknown"
    severity: str = "error"
    path: str | None = None
    line: int | None = None
    column: int | None = None
    rule: str | None = None
    section: str | None = None
    token_index: int | None = None
    code: str | None = None

    def format(self) -> str:
        location = ""
        if self.path:
            location = self.path
            if self.line is not None:
                location += f":{self.line}"
                if self.column is not None:
                    location += f":{self.column}"
        context = [self.phase]
        if self.rule:
            context.append(f"rule={self.rule}")
        if self.section:
            context.append(f"section={self.section}")
        if self.token_index is not None:
            context.append(f"token={self.token_index}")
        if self.code:
            context.append(self.code)
        prefix = f"{location}: " if location else ""
        return f"{prefix}{self.severity} [{', '.join(context)}]: {self.message}"


class DiagnosticBag:
    """Ordered diagnostic collector usable by APIs and command-line tools."""

    def __init__(self, diagnostics: Iterable[Diagnostic] = ()) -> None:
        self._items = list(diagnostics)

    @property
    def items(self) -> tuple[Diagnostic, ...]:
        return tuple(self._items)

    @property
    def has_errors(self) -> bool:
        return any(item.severity == "error" for item in self._items)

    def add(self, diagnostic: Diagnostic) -> Diagnostic:
        self._items.append(diagnostic)
        return diagnostic

    def error(self, message: str, **context: object) -> Diagnostic:
        return self.add(Diagnostic(message=message, severity="error", **context))

    def warning(self, message: str, **context: object) -> Diagnostic:
        return self.add(Diagnostic(message=message, severity="warning", **context))

    def add_exception(
        self,
        error: BaseException,
        *,
        phase: str | None = None,
        path: str | None = None,
        rule: str | None = None,
        section: str | None = None,
    ) -> Diagnostic:
        return self.add(exception_diagnostic(
            error,
            phase=phase,
            path=path,
            rule=rule,
            section=section,
        ))

    def format(self) -> str:
        return "\n".join(item.format() for item in self._items)

    def __bool__(self) -> bool:
        return bool(self._items)

    def __iter__(self):
        return iter(self.items)


def _phase_for(error: BaseException) -> str:
    explicit = getattr(error, "phase", None)
    if isinstance(explicit, str) and explicit:
        return explicit
    name = type(error).__name__
    if name in {"AOTError", "ParserError", "SyntaxError"}:
        return "frontend"
    if name == "MIRSemanticError":
        return "rules"
    if name == "RIFRuntimeError":
        return "rules"
    if name in {"ArtifactError", "LayoutError"}:
        return "layout"
    if name in {"FixupError", "RelocationError"}:
        return "fixups"
    if name in {"MIRInputError", "BufferError", "StorageError"}:
        return "mir"
    return "unknown"


def exception_diagnostic(
    error: BaseException,
    *,
    phase: str | None = None,
    path: str | None = None,
    rule: str | None = None,
    section: str | None = None,
) -> Diagnostic:
    """Convert an existing exception without changing its public type."""

    span = getattr(error, "span", None)
    resolved_path = getattr(span, "path", None) or path or getattr(error, "path", None)
    line = getattr(span, "line", None)
    column = getattr(span, "column", None)
    return Diagnostic(
        message=str(getattr(error, "detail", str(error))),
        phase=phase or _phase_for(error),
        path=resolved_path,
        line=line,
        column=column,
        rule=rule or getattr(error, "rule", None),
        section=section or getattr(error, "section", None),
        token_index=getattr(error, "token_index", None),
        code=getattr(error, "code", None),
    )


def format_exception(error: BaseException, *, phase: str | None = None) -> str:
    """Render one exception through the shared diagnostic contract."""

    return exception_diagnostic(error, phase=phase).format()


__all__ = [
    "Diagnostic",
    "DiagnosticBag",
    "exception_diagnostic",
    "format_exception",
]
