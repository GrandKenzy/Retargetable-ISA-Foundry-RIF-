from gram import combinators as cmb
from gram import lexer

from .values import TABLE_OPERATION, VALUE


class CELL(cmb.RuleItem):
    nodeable = True
    entrypoint = cmb.Seq(
        cmb.MatchToken("OR"),
        cmb.Alt(
            cmb.Ref(TABLE_OPERATION),
            cmb.Ref(VALUE),
        ),
    )


class HEADER(cmb.RuleItem):
    nodeable = True
    entrypoint = cmb.Seq(
        cmb.Some(
            cmb.Seq(
                cmb.MatchToken("OR"),
                cmb.Alt(
                    cmb.MatchToken("IDENT"),
                    cmb.MatchGroup("keywords"),
                    cmb.Ref(TABLE_OPERATION),
                ),
            )
        ),
        cmb.MatchToken("OR"),
        cmb.MatchToken("NEWLINE"),
    )


class ROW(cmb.RuleItem):
    nodeable = True
    entrypoint = cmb.Seq(
        cmb.Some(cmb.Ref(CELL)),
        cmb.MatchToken("OR"),
        cmb.MatchToken("NEWLINE"),
    )


class SEPARATOR(cmb.RuleItem):
    nodeable = False
    entrypoint = cmb.MatchToken(lexer.Token.UNDERSCORES)


class COLUMNS(cmb.RuleItem):
    nodeable = False
    entrypoint = cmb.Seq(
        cmb.Ref(HEADER),
        cmb.Some(
            cmb.Seq(
                cmb.Ref(SEPARATOR),
                cmb.MatchToken("NEWLINE"),
                cmb.Ref(ROW),
            )
        ),
    )


class TABLE(cmb.RuleItem):
    nodeable = True
    entrypoint = cmb.Seq(
        cmb.MatchToken("AT"),
        cmb.MatchKeyword("table"),
        cmb.MatchToken("IDENT"),
        cmb.MatchToken("NEWLINE"),
        cmb.Ref(COLUMNS),
        cmb.MatchToken("AT"),
        cmb.MatchKeyword("end"),
        cmb.MatchToken("NEWLINE"),
    )


__all__ = ["TABLE"]
