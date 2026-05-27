from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TypeInfo:
    name: str
    bits: int
    buffmode: int = 0
    autofill: int = 0

    def attr(self, key: str) -> Any:
        return getattr(self, key)


@dataclass
class SubRegisterInfo:
    name: str
    alias: str
    bits: int
    family: str
    code: str
    ext: int
    rex8: int
    from_bit: int
    to_bit: int

    def attr(self, key: str) -> Any:
        if key == "from":
            return self.from_bit
        return getattr(self, key)


@dataclass
class RegisterInfo:
    name: str
    code: str
    bits: int
    ext: int
    rex8: int
    subsets: int
    subregs: dict[str, SubRegisterInfo]

    def attr(self, key: str) -> Any:
        return getattr(self, key)


@dataclass
class SymbolInfo:
    name: str
    bits: int
    addrs: int
    empty: int = 0

    def attr(self, key: str) -> Any:
        return getattr(self, key)


@dataclass
class WordInfo:
    name: str
    data: bytes
    align: int = 0
    pad: int = 0

    def attr(self, key: str) -> Any:
        if key == "bytes":
            return self.data
        return getattr(self, key)


@dataclass
class StackInfo:
    name: str
    bottom: int = 0
    top: int = 0
    reserve: int = 0

    def attr(self, key: str) -> Any:
        return getattr(self, key)
