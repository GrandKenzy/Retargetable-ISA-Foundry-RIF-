from __future__ import annotations

from typing import Sequence

from ..errors import NeedSyntaxError
from ..lexer import Token


def split_token_groups(tokens: Sequence[Token], separator_kind: str) -> list[list[Token]]:
    groups: list[list[Token]] = [[]]
    for token in tokens:
        if token.kind == separator_kind:
            groups.append([])
        else:
            groups[-1].append(token)
    if any(len(group) == 0 for group in groups):
        line = tokens[0].line if tokens else None
        raise NeedSyntaxError("empty comma group", line)
    return groups


def indentation(raw: str) -> int:
    n = 0
    for ch in raw:
        if ch == " ":
            n += 1
        elif ch == "\t":
            n += 4
        else:
            break
    return n


def alias_name(idx: int) -> str:
    chars: list[str] = []
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        chars.append(chr(97 + rem))
    return "".join(reversed(chars))


def unsigned_int_bits(value: int) -> int:
    if value == 0:
        return 1
    return value.bit_length()


def signed_int_bits(value: int) -> int:
    if value >= 0:
        return unsigned_int_bits(value)
    return (-value).bit_length() + 1


def token_raw(token: Token) -> str:
    return token.value
