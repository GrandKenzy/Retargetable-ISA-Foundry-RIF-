"""Lanza el último error acumulado por `error`.

Sintaxis:

    raise
"""

from __future__ import annotations

from rif import Line, Err, Errors, end


def main():
    if Line.elements != 1:
        return Err("La instrucción raise no espera argumentos")

    Line.Advance()  # consumir "raise"
    Line.expects(" ", "\n")

    if Errors.last is None:
        return Err("No hay errores para lanzar")

    for line in Errors.last:
        print(line)

    end()


def _start():
    return main()
