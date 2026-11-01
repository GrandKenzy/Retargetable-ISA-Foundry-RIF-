"""Shared source reception for the Python and Gram AOT frontends."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from Frontend.aot import AOTParser, GIRAdapter


@dataclass
class SourceParser:
    """Receive RIF sources while reusing one frontend per compilation."""

    backend: str = "aot"
    session: Any | None = None
    aot_parser: AOTParser | None = None

    def __post_init__(self) -> None:
        if self.backend not in {"python", "aot"}:
            raise ValueError(f"Backend de RIF desconocido: {self.backend!r}.")
        if self.session is None:
            from Frontend import RIF_LANG_SESSION

            self.session = RIF_LANG_SESSION

    def _get_aot_parser(self) -> AOTParser:
        if self.aot_parser is None:
            self.aot_parser = AOTParser.build(
                AOTParser.default_cache_dir(),
                self.session,
            )
        return self.aot_parser

    def parse_file(self, path: str | Path) -> list[Any]:
        source_path = Path(path).expanduser().resolve()
        if self.backend == "aot":
            document = self._get_aot_parser().parse_file(source_path)
            return GIRAdapter(document).ast()
        return self.parse_text(
            source_path.read_text(encoding="utf-8"),
            str(source_path),
        )

    def parse_text(self, source: str, name: str) -> list[Any]:
        if self.backend == "aot":
            document = self._get_aot_parser().parse_source(source, name)
            return GIRAdapter(document).ast()
        self.session.load()
        tokens = self.session.tokenize(source, name)
        return self.session.parse(tokens, name)


__all__ = ["SourceParser"]
