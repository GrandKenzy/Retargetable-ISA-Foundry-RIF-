from __future__ import annotations

import re


IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


KNOWN_NEED_TYPES = {"TYPE", "REG", "SREG", "SYMBOL", "VALUE", "INT", "IDENT", "STACK", "LABEL"}


NEED_NORMALIZE = {"VALUE": "INT"}


CONDITION_NAMES = {"has_subset", "fits", "exists", "unbsize", "iarch", "narch", "this"}


EMIT_MODES = {"cbits", "lit", "addr", "fill", "jaddr"}


RESERVED_INSTRUCTION_NAMES = CONDITION_NAMES | {
    "need", "not", "emmit", "switch", "case", "on", "off", "error", 
    "call", "nonsfamily", "memskip", "mark", "multiple", "strict", "pending"
}


HEX_BYTE_RE = re.compile(r"^(?:[0-9A-Fa-f]{2})+$")
