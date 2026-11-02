from gram import combinators as cmb


_NAME = cmb.Alt(
    cmb.MatchToken("IDENT"),
    cmb.MatchGroup("keywords"),
)


class TABLE_ACCESS(cmb.RuleItem):
    nodeable = True
    description = "Acceso simple o indexado a una columna de tabla."
    entrypoint = cmb.Alt(
        cmb.Seq(
            cmb.MatchToken("DOLLAR"),
            _NAME,
            cmb.MatchToken("DOT"),
            _NAME,
            cmb.MatchToken("LBRACKET"),
            cmb.Alt(
                cmb.MatchToken("IDENT"),
                cmb.MatchToken("NUMBER"),
                cmb.MatchToken("DECIMAL"),
                cmb.MatchToken("STRING"),
                cmb.MatchToken("BOOL"),
            ),
            cmb.MatchToken("RBRACKET"),
            cmb.MatchToken("DOT"),
            _NAME,
        ),
        cmb.Seq(
            cmb.MatchToken("DOLLAR"),
            _NAME,
            cmb.MatchToken("DOT"),
            _NAME,
        ),
    )


class TABLE_OPERATION(cmb.RuleItem):
    nodeable = True
    description = "Operación de materialización o consulta de una tabla."
    entrypoint = cmb.Alt(
        cmb.Seq(
            cmb.MatchToken("PERCENT"),
            cmb.MatchToken("LBRACKET"),
            _NAME,
            cmb.MatchToken("RBRACKET"),
            cmb.MatchToken("ASSIGN"),
            _NAME,
            cmb.MatchToken("DOT"),
            _NAME,
            cmb.MatchToken("PERCENT"),
        ),
        cmb.Seq(
            cmb.MatchToken("PERCENT"),
            _NAME,
            cmb.MatchToken("DOT"),
            _NAME,
            cmb.MatchToken("LBRACKET"),
            cmb.Alt(
                cmb.MatchToken("IDENT"),
                cmb.MatchToken("NUMBER"),
                cmb.MatchToken("DECIMAL"),
                cmb.MatchToken("STRING"),
                cmb.MatchToken("BOOL"),
            ),
            cmb.MatchToken("RBRACKET"),
            cmb.MatchToken("DOT"),
            _NAME,
            cmb.MatchToken("PERCENT"),
        ),
    )


class RESERVATION_ACCESS(cmb.RuleItem):
    nodeable = True
    description = "Acceso sintáctico a una reserva por etiqueta."
    entrypoint = cmb.Seq(
        cmb.MatchToken("AND"),
        cmb.MatchToken("IDENT"),
    )


class CALL_VALUE(cmb.RuleItem):
    nodeable = True
    description = "Referencia sintáctica a una función nativa."
    entrypoint = cmb.Seq(
        cmb.MatchToken("HASH"),
        cmb.MatchKeyword("call"),
        cmb.MatchToken("LBRACKET"),
        _NAME,
        cmb.MatchToken("RBRACKET"),
    )


class SIZE_VALUE(cmb.RuleItem):
    nodeable = True
    description = "Posición física actual del buffer en bits."
    entrypoint = cmb.Seq(
        cmb.MatchToken("COLON"),
        cmb.MatchToken("COLON"),
        cmb.MatchKeyword("SIZE"),
    )


class VSIZE_VALUE(cmb.RuleItem):
    nodeable = True
    description = "Posición virtual actual del buffer en bits."
    entrypoint = cmb.Seq(
        cmb.MatchToken("COLON"),
        cmb.MatchToken("COLON"),
        cmb.MatchKeyword("VSIZE"),
    )


class ALIGNMENT_VALUE(cmb.RuleItem):
    nodeable = True
    description = "Alineamiento configurado para la sección actual."
    entrypoint = cmb.Seq(
        cmb.MatchToken("COLON"),
        cmb.MatchToken("COLON"),
        cmb.MatchKeyword("ALIGNMENT"),
    )


class DDEPTH_VALUE(cmb.RuleItem):
    nodeable = True
    description = "Número de valores en el datastack."
    entrypoint = cmb.Seq(
        cmb.MatchToken("COLON"),
        cmb.MatchToken("COLON"),
        cmb.MatchSeqSymbol(symbols=["ddepth"], case_sensitive=True),
    )


class DLOAD_VALUE(cmb.RuleItem):
    nodeable = True
    description = "Extrae el último valor del datastack."
    entrypoint = cmb.MatchSeqSymbol(symbols=["dget"], case_sensitive=True)


class DPEEK_VALUE(cmb.RuleItem):
    nodeable = True
    description = "Consulta el último valor del datastack sin extraerlo."
    entrypoint = cmb.MatchSeqSymbol(symbols=["dpeek"], case_sensitive=True)


def _reservation_value(name: str):
    return cmb.Seq(
        cmb.MatchKeyword(name),
        cmb.MatchToken("STRING"),
    )


class DIST_VALUE(cmb.RuleItem):
    nodeable = True
    description = "Distancia física desde una etiqueta hasta la posición actual."
    entrypoint = _reservation_value("dist")


class VDIST_VALUE(cmb.RuleItem):
    nodeable = True
    description = "Distancia virtual desde una etiqueta hasta la posición actual."
    entrypoint = _reservation_value("vdist")


class RESDIR_VALUE(cmb.RuleItem):
    nodeable = True
    description = "Dirección física de una reserva."
    entrypoint = _reservation_value("resdir")


class RESVDIR_VALUE(cmb.RuleItem):
    nodeable = True
    description = "Dirección virtual de una reserva."
    entrypoint = _reservation_value("resvdir")


class RESDIST_VALUE(cmb.RuleItem):
    nodeable = True
    description = "Distancia física hasta una reserva."
    entrypoint = _reservation_value("resdist")


class RESVDIST_VALUE(cmb.RuleItem):
    nodeable = True
    description = "Distancia virtual hasta una reserva."
    entrypoint = _reservation_value("resvdist")


class RESWIDTH_VALUE(cmb.RuleItem):
    nodeable = True
    description = "Ancho físico de una reserva en bits."
    entrypoint = _reservation_value("reswidth")


class VRESWIDTH_VALUE(cmb.RuleItem):
    nodeable = True
    description = "Ancho virtual de una reserva en bits."
    entrypoint = _reservation_value("vreswidth")


class VALUE(cmb.RuleItem):
    nodeable = True


__all__ = [
    "TABLE_ACCESS",
    "TABLE_OPERATION",
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
    "VALUE",
]
