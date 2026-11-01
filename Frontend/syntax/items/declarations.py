from gram import combinators as cmb
from gram import lexer

from .values import CALL_VALUE, TABLE_ACCESS, VALUE
from .instructions import INSTRUCTION


def _integer():
    return cmb.Alt(
        cmb.MatchToken("NUMBER"),
        cmb.MatchToken("DECIMAL"),
    )


class TOKEN(cmb.RuleItem):
    nodeable = True
    description = "Referencia sintáctica a un token por nombre o número."
    entrypoint = cmb.Alt(
        cmb.MatchGroup("token_names"),
        _integer(),
    )


class TABLE_MATCHER(cmb.RuleItem):
    nodeable = True
    description = "Relaciona una columna de tabla con un token esperado."
    entrypoint = cmb.Seq(
        cmb.MatchToken("DOT"),
        cmb.Ref(TABLE_ACCESS),
        cmb.MatchToken("COMMA"),
        cmb.Ref(TOKEN),
        cmb.MatchToken("NEWLINE"),
    )


class CONSUMER(cmb.RuleItem):
    nodeable = False
    description = "Consume un token declarado por nombre o número."
    entrypoint = cmb.Seq(
        cmb.MatchToken("DOT"),
        cmb.Ref(TOKEN),
        cmb.MatchToken("NEWLINE"),
    )


class STORE(cmb.RuleItem):
    nodeable = True
    description = "Declara una lista de tokens candidatos para almacenar."
    entrypoint = cmb.Seq(
        cmb.MatchToken("DOT"),
        cmb.Enclosed(
            open=lexer.Token.LBRACKET,
            content=cmb.Separator(
                values=[cmb.Ref(TOKEN)],
                sep=lexer.Token.COMMA,
                min=1,
                allow_trailing=False,
            ),
            close=lexer.Token.RBRACKET,
            allow_empty=False,
        ),
        cmb.MatchToken("NEWLINE"),
    )


class NIBBLES(cmb.RuleItem):
    nodeable = True
    description = "Declara dos valores consecutivos para una operación nibbles."
    entrypoint = cmb.Seq(
        cmb.MatchToken("DOT"),
        cmb.MatchKeyword("nibbles"),
        cmb.Ref(VALUE),
        cmb.Ref(VALUE),
        cmb.MatchToken("NEWLINE"),
    )


class EMIT(cmb.RuleItem):
    nodeable = True
    entrypoint = cmb.Seq(
        cmb.MatchToken("DOT"),
        cmb.MatchKeyword("emit"),
        cmb.Ref(VALUE),
        cmb.Ref(VALUE),
        cmb.Ref(VALUE),
        cmb.Ref(VALUE),
        cmb.Ref(VALUE),
        cmb.Ref(VALUE),
        cmb.Ref(VALUE),
        cmb.Ref(VALUE),
        cmb.MatchToken("NEWLINE"),
    )


class EWORD(cmb.RuleItem):
    nodeable = True
    description = "Emite un único valor."
    entrypoint = cmb.Seq(
        cmb.MatchToken("DOT"),
        cmb.MatchKeyword("eword"),
        cmb.Ref(VALUE),
        cmb.MatchToken("NEWLINE"),
    )


class PAD(cmb.RuleItem):
    nodeable = True
    description = "Inserta una cantidad explícita de ceros y la registra como padding."
    entrypoint = cmb.Seq(
        cmb.MatchToken("DOT"),
        cmb.MatchKeyword("pad"),
        _integer(),
        cmb.MatchToken("NEWLINE"),
    )


class ALIGN(cmb.RuleItem):
    nodeable = True
    description = "Alinea la posición actual insertando el padding necesario."
    entrypoint = cmb.Seq(
        cmb.MatchToken("DOT"),
        cmb.MatchKeyword("align"),
        _integer(),
        cmb.MatchToken("NEWLINE"),
    )


class DEFINE(cmb.RuleItem):
    nodeable = True
    description = "Declara un nombre reutilizable del lenguaje."
    entrypoint = cmb.Seq(
        cmb.MatchToken("AT"),
        cmb.MatchKeyword("define"),
        cmb.Alt(cmb.MatchToken("IDENT"), cmb.MatchGroup("keywords")),
        cmb.MatchToken("NEWLINE"),
    )


class KW(cmb.RuleItem):
    nodeable = True
    description = "Declara un keyword literal que debe coincidir exactamente."
    entrypoint = cmb.Seq(
        cmb.MatchToken("DOT"),
        cmb.MatchKeyword("KW"),
        cmb.MatchToken("STRING"),
        cmb.MatchToken("NEWLINE"),
    )


class JUMP(cmb.RuleItem):
    nodeable = True
    description = "Salta sintácticamente a otra regla por nombre."
    entrypoint = cmb.Seq(
        cmb.MatchToken("DOT"),
        cmb.MatchSeqSymbol(symbols=["JUMP"], case_sensitive=True),
        cmb.Alt(cmb.MatchToken("IDENT"), cmb.MatchGroup("keywords")),
        cmb.MatchToken("NEWLINE"),
    )


class SAVE(cmb.RuleItem):
    nodeable = True
    description = "Guarda sintácticamente el token actual bajo una etiqueta."
    entrypoint = cmb.Seq(
        cmb.MatchToken("DOT"),
        cmb.MatchKeyword("save"),
        cmb.MatchToken("STRING"),
        cmb.MatchToken("NEWLINE"),
    )


class LOAD(cmb.RuleItem):
    nodeable = True
    description = "Carga sintácticamente un token identificado por etiqueta."
    entrypoint = cmb.Seq(
        cmb.MatchToken("DOT"),
        cmb.MatchKeyword("load"),
        cmb.MatchToken("STRING"),
        cmb.MatchToken("NEWLINE"),
    )


class RESERVE(cmb.RuleItem):
    nodeable = True
    description = "Reserva un espacio etiquetado con un tamaño declarado."
    entrypoint = cmb.Seq(
        cmb.MatchToken("DOT"),
        cmb.MatchKeyword("reserve"),
        cmb.MatchToken("STRING"),
        _integer(),
        cmb.MatchToken("NEWLINE"),
    )


class WRITE_RES(cmb.RuleItem):
    nodeable = True
    description = "Carga un valor en una reserva etiquetada."
    entrypoint = cmb.Seq(
        cmb.MatchToken("DOT"),
        cmb.MatchKeyword("write_res"),
        cmb.MatchToken("STRING"),
        cmb.Ref(VALUE),
        cmb.MatchToken("NEWLINE"),
    )


class DROP_RES(cmb.RuleItem):
    nodeable = True
    description = "Elimina una reserva del espacio de nombres."
    entrypoint = cmb.Seq(
        cmb.MatchToken("DOT"),
        cmb.MatchKeyword("drop_res"),
        cmb.MatchToken("STRING"),
        cmb.MatchToken("NEWLINE"),
    )


class EMIT_RES(cmb.RuleItem):
    nodeable = True
    description = "Inserta una reserva etiquetada en el flujo actual."
    entrypoint = cmb.Seq(
        cmb.MatchToken("DOT"),
        cmb.MatchKeyword("emit_res"),
        cmb.MatchToken("STRING"),
        cmb.MatchToken("NEWLINE"),
    )


class JUMPIF(cmb.RuleItem):
    nodeable = True
    description = "Salta a una regla cuando una condición booleana o nativa es verdadera."
    entrypoint = cmb.Seq(
        cmb.MatchToken("DOT"),
        cmb.MatchSeqSymbol(symbols=["JUMPIF"], case_sensitive=True),
        cmb.Alt(cmb.MatchToken("IDENT"), cmb.MatchGroup("keywords")),
        cmb.MatchToken("COMMA"),
        cmb.Alt(
            cmb.MatchToken("BOOL"),
            cmb.Ref(CALL_VALUE),
        ),
        cmb.MatchToken("NEWLINE"),
    )


class BREAK(cmb.RuleItem):
    nodeable = True
    description = "Rompe el flujo actual y retorna al contexto de salto."
    entrypoint = cmb.Seq(
        cmb.MatchToken("DOT"),
        cmb.MatchSeqSymbol(symbols=["BREAK"], case_sensitive=True),
        cmb.MatchToken("NEWLINE"),
    )


class ERROR(cmb.RuleItem):
    nodeable = True
    description = "Declara un mensaje de error literal."
    entrypoint = cmb.Seq(
        cmb.MatchToken("DOT"),
        cmb.MatchSeqSymbol(symbols=["ERROR"], case_sensitive=True),
        cmb.MatchToken("COMMA"),
        cmb.MatchToken("STRING"),
        cmb.MatchToken("NEWLINE"),
    )


class FRAME_LINE(cmb.RuleItem):
    nodeable = False
    description = "Línea de valores de un frame de emisión."
    entrypoint = cmb.Seq(
        cmb.Some(cmb.Ref(VALUE)),
        cmb.MatchToken("NEWLINE"),
    )


class FRAMEEND(cmb.RuleItem):
    nodeable = False
    description = "Cierre sintáctico de un frame de emisión."
    entrypoint = cmb.Seq(
        cmb.MatchToken("DOT"),
        cmb.MatchKeyword("frameend"),
        cmb.MatchToken("NEWLINE"),
    )


class FRAME(cmb.RuleItem):
    nodeable = True
    description = "Emite un frame multilinea delimitado de valores."
    entrypoint = cmb.Seq(
        cmb.MatchToken("DOT"),
        cmb.MatchKeyword("frame"),
        cmb.Some(cmb.Ref(VALUE)),
        cmb.MatchToken("NEWLINE"),
        cmb.Many(cmb.Ref(FRAME_LINE)),
        cmb.Ref(FRAMEEND),
    )


class RULE(cmb.RuleItem):
    nodeable = True
    description = "Declara una regla con operaciones delimitadas por líneas."
    entrypoint = cmb.Seq(
        cmb.MatchToken("AT"),
        cmb.MatchKeyword("rule"),
        cmb.Alt(cmb.MatchToken("IDENT"), cmb.MatchGroup("keywords")),
        cmb.MatchToken("COLON"),
        cmb.MatchToken("NEWLINE"),
        cmb.Many(cmb.Ref(INSTRUCTION)),
    )


class STACK(cmb.RuleItem):
    nodeable = True
    description = "Declara sintácticamente el tamaño del array de slots."
    entrypoint = cmb.Seq(
        cmb.MatchToken("AT"),
        cmb.MatchKeyword("stack"),
        cmb.Alt(
            _integer(),
            cmb.Seq(
                cmb.MatchToken("MINUS"),
                _integer(),
            ),
        ),
        cmb.MatchToken("NEWLINE"),
    )


class SUPPORTS(cmb.RuleItem):
    nodeable = True
    description = "Declara una variante ISA disponible para delegación."
    entrypoint = cmb.Seq(
        cmb.MatchToken("AT"),
        cmb.MatchKeyword("SUPPORTS"),
        cmb.MatchToken("IDENT"),
        cmb.MatchToken("NEWLINE"),
    )


class VARIANT_MODE(cmb.RuleItem):
    nodeable = True
    description = "Define el modo de delegación de una variante ISA."
    entrypoint = cmb.Seq(
        cmb.MatchToken("DOT"),
        cmb.MatchKeyword("MODE"),
        cmb.Alt(
            cmb.MatchKeyword("SWITCH"),
            cmb.MatchKeyword("ENCAPSULATE"),
        ),
        cmb.MatchToken("NEWLINE"),
    )


class VARIANT_ENTER(cmb.RuleItem):
    nodeable = True
    description = "Referencia la Rule que activa una variante."
    entrypoint = cmb.Seq(
        cmb.MatchToken("DOT"),
        cmb.MatchKeyword("ENTER"),
        cmb.MatchToken("STRING"),
        cmb.MatchToken("NEWLINE"),
    )


class VARIANT_EXIT(cmb.RuleItem):
    nodeable = True
    description = "Referencia la Rule que devuelve al contexto padre."
    entrypoint = cmb.Seq(
        cmb.MatchToken("DOT"),
        cmb.MatchKeyword("EXIT"),
        cmb.MatchToken("STRING"),
        cmb.MatchToken("NEWLINE"),
    )


class ASMVARIANT(cmb.RuleItem):
    nodeable = True
    description = "Configura la delegación sintáctica a otra variante ISA."
    entrypoint = cmb.Seq(
        cmb.MatchToken("AT"),
        cmb.MatchKeyword("ASMVARIANT"),
        cmb.MatchToken("IDENT"),
        cmb.MatchToken("COLON"),
        cmb.MatchToken("NEWLINE"),
        cmb.Many(
            cmb.Alt(
                cmb.Ref(VARIANT_MODE),
                cmb.Ref(VARIANT_ENTER),
                cmb.Ref(VARIANT_EXIT),
            )
        ),
        cmb.MatchToken("AT"),
        cmb.MatchKeyword("END"),
        cmb.MatchToken("NEWLINE"),
    )


class LOAD_FILE(cmb.RuleItem):
    nodeable = True
    description = "Carga declaraciones desde otro archivo RIF en esta posición."
    entrypoint = cmb.Seq(
        cmb.MatchToken("AT"),
        cmb.MatchKeyword("LOAD"),
        cmb.MatchToken("STRING"),
        cmb.MatchToken("NEWLINE"),
    )


__all__ = [
    "DEFINE",
    "RULE",
    "TABLE_MATCHER",
    "CONSUMER",
    "STORE",
    "NIBBLES",
    "EMIT",
    "EWORD",
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
    "SUPPORTS",
    "VARIANT_MODE",
    "VARIANT_ENTER",
    "VARIANT_EXIT",
    "ASMVARIANT",
    "LOAD_FILE",
    "INSTRUCTION",
]
