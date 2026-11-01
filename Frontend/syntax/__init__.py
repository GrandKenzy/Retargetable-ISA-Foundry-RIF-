from gram import combinators as cmb
from gram import sessions


RIF_LANG_SESSION = sessions.Session(
    "RIF_LANG_SESSION",
    "Many",
)
RIF_LANG_SESSION.clear_global()
RIF_LANG_SESSION.init()
# Gram exposes this setting as ``ident_underscores``; -2 makes runs of two or
# more standalone underscores arrive as the grouped Token.UNDERSCORES token.
RIF_LANG_SESSION.ident_underscores = -2

from . import keywords
from .items.declarations import (
    CONSUMER,
    BREAK,
    DEFINE,
    ERROR,
    EMIT,
    EWORD,
    PAD,
    ALIGN,
    FRAME,
    FRAMEEND,
    JUMP,
    JUMPIF,
    KW,
    LOAD,
    LOAD_FILE,
    LIBRARY,
    INSTRUCTION,
    DROP_RES,
    EMIT_RES,
    WRITE_RES,
    NIBBLES,
    RESERVE,
    RULE,
    SAVE,
    STORE,
    STACK,
    SUPPORTS,
    VARIANT_MODE,
    VARIANT_ENTER,
    VARIANT_EXIT,
    TABLE_MATCHER,
    TOKEN,
    ASMVARIANT,
)
from .items.table import TABLE
from .items.blocks import BLOCK
from .items.values import (
    ALIGNMENT_VALUE,
    CALL_VALUE,
    DIST_VALUE,
    DDEPTH_VALUE,
    DLOAD_VALUE,
    DPEEK_VALUE,
    RESDIR_VALUE,
    RESDIST_VALUE,
    RESERVATION_ACCESS,
    RESVDIR_VALUE,
    RESVDIST_VALUE,
    RESWIDTH_VALUE,
    VRESWIDTH_VALUE,
    SIZE_VALUE,
    TABLE_ACCESS,
    VALUE,
    VDIST_VALUE,
    VSIZE_VALUE,
)


VALUE.entrypoint = cmb.Alt(
    cmb.Ref(TABLE_ACCESS),
    cmb.Ref(RESERVATION_ACCESS),
    cmb.Ref(CALL_VALUE),
    cmb.Ref(SIZE_VALUE),
    cmb.Ref(VSIZE_VALUE),
    cmb.Ref(ALIGNMENT_VALUE),
    cmb.Ref(DDEPTH_VALUE),
    cmb.Ref(DLOAD_VALUE),
    cmb.Ref(DPEEK_VALUE),
    cmb.Ref(DIST_VALUE),
    cmb.Ref(VDIST_VALUE),
    cmb.Ref(RESDIR_VALUE),
    cmb.Ref(RESVDIR_VALUE),
    cmb.Ref(RESDIST_VALUE),
    cmb.Ref(RESVDIST_VALUE),
    cmb.Ref(RESWIDTH_VALUE),
    cmb.Ref(VRESWIDTH_VALUE),
    cmb.MatchToken("NUMBER"),
    cmb.MatchToken("DECIMAL"),
    cmb.MatchToken("IDENT"),
    cmb.MatchToken("STRING"),
    cmb.MatchToken("BOOL"),
)


class ENTRYPOINT(cmb.RuleItem):
    entrypoint = cmb.Alt(
        cmb.Ref(TABLE),
        cmb.Ref(SUPPORTS),
        cmb.Ref(ASMVARIANT),
        cmb.Ref(LOAD_FILE),
        cmb.Ref(LIBRARY),
        cmb.Ref(DEFINE),
        cmb.Ref(RULE),
        cmb.Ref(STACK),
        cmb.Ref(BLOCK),
    )


RIF_LANG_SESSION.entrypoint = ENTRYPOINT


RIF_LANG_SESSION.migrate()


__all__ = [
    "RIF_LANG_SESSION",
    "keywords",
    "TABLE",
    "SUPPORTS",
    "VARIANT_MODE",
    "VARIANT_ENTER",
    "VARIANT_EXIT",
    "ASMVARIANT",
    "LOAD_FILE",
    "LIBRARY",
    "INSTRUCTION",
    "DEFINE",
    "RULE",
    "TABLE_MATCHER",
    "CONSUMER",
    "STORE",
    "NIBBLES",
    "EMIT",
    "EWORD",
    "PAD",
    "ALIGN",
    "KW",
    "JUMP",
    "SAVE",
    "LOAD",
    "STACK",
    "RESERVE",
    "WRITE_RES",
    "DROP_RES",
    "EMIT_RES",
    "JUMPIF",
    "BREAK",
    "ERROR",
    "FRAME",
    "FRAMEEND",
    "TOKEN",
    "TABLE_ACCESS",
    "RESERVATION_ACCESS",
    "CALL_VALUE",
    "SIZE_VALUE",
    "VSIZE_VALUE",
    "ALIGNMENT_VALUE",
    "DDEPTH_VALUE",
    "DLOAD_VALUE",
    "DPEEK_VALUE",
    "DIST_VALUE",
    "VDIST_VALUE",
    "RESDIR_VALUE",
    "RESVDIR_VALUE",
    "RESDIST_VALUE",
    "RESVDIST_VALUE",
    "RESWIDTH_VALUE",
    "VRESWIDTH_VALUE",
    "ENTRYPOINT",
    "BLOCK",
]
