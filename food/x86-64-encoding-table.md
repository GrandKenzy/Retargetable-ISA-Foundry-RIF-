# Tabla resumida de encoding x86-64

La codificación real de una instrucción depende del opcode, del modo, de los
operandos y de las extensiones habilitadas. La siguiente tabla es una guía de
campos para el emisor binario de RIF; no es una tabla exhaustiva de opcodes.

## Orden general de bytes

| Orden | Campo | Tamaño típico | Contenido |
| ---: | --- | --- | --- |
| 1 | Prefijos legacy | 0 o más bytes | `LOCK`, `REP`, segmento, operand-size o address-size. |
| 2 | REX | 0 o 1 byte | En modo 64-bit: `0100WRXB`; `W` amplía operandos a 64 bits y `R/X/B` extienden registros, índice o base. |
| 3 | Opcode | 1–3 bytes | Opcode primario y escapes como `0F`, `0F 38` o `0F 3A`. |
| 4 | ModR/M | 0 o 1 byte | `mod:2`, `reg/opcode:3`, `r/m:3`; selecciona registros o direccionamiento. |
| 5 | SIB | 0 o 1 byte | `scale:2`, `index:3`, `base:3`; aparece en formas de memoria que lo requieren. |
| 6 | Desplazamiento | 0, 1, 2 o 4 bytes | `disp8`, `disp16` o `disp32`, según modo y forma de direccionamiento. |
| 7 | Inmediato | 0, 1, 2, 4 u 8 bytes | Valor inmediato definido por el opcode y el tamaño del operando. |

No todos los campos aparecen en todas las instrucciones. El orden anterior es
estructural: un prefijo no reemplaza el opcode y un ModR/M no implica siempre
un SIB o un desplazamiento.

## Campos de direccionamiento

| Campo | Bits | Lectura |
| --- | ---: | --- |
| `ModR/M.mod` | 2 | `11` suele indicar registro directo; los otros valores seleccionan memoria y el tamaño del desplazamiento. |
| `ModR/M.reg` | 3 | Registro, extensión del registro mediante `REX.R` o selector `/digit` del opcode. |
| `ModR/M.r/m` | 3 | Registro o base de memoria; `REX.B` extiende el conjunto. |
| `SIB.scale` | 2 | Factor `1`, `2`, `4` u `8`. |
| `SIB.index` | 3 | Registro índice; `REX.X` lo extiende. |
| `SIB.base` | 3 | Registro base o forma especial de dirección; `REX.B` lo extiende. |

## Formas frecuentes de bytes

Estas filas son ejemplos de formas estables útiles para pruebas de emisión,
no una sustitución del manual de instrucciones.

| Instrucción / forma | Bytes estructurales | Campo variable | Uso de relocación |
| --- | --- | --- | --- |
| `NOP` | `90` | ninguno | ninguno |
| `RET` | `C3` | ninguno | ninguno |
| `JMP rel8` | `EB` + `rel8` | desplazamiento signed de 8 bits | `pc8` si el campo se genera como reserva |
| `JMP rel32` | `E9` + `rel32` | desplazamiento signed de 32 bits | `pc32` |
| `CALL rel32` | `E8` + `rel32` | desplazamiento signed de 32 bits | `pc32` |
| `MOV r64, imm64` | `REX.W` + `B8+rd` + `imm64` | registro en opcode y 8 bytes | `abs64` solo si el inmediato representa una dirección |
| `MOV r/m64, r64` | `REX.W` + `89` + `ModR/M` + opcional `SIB/disp` | operandos y direccionamiento | depende de la expresión de memoria |
| `MOV r64, r/m64` | `REX.W` + `8B` + `ModR/M` + opcional `SIB/disp` | operandos y direccionamiento | depende de la expresión de memoria |

## Rangos que debe verificar un emisor

| Campo | Rango signed | Representación |
| --- | ---: | --- |
| `rel8` / `pc8` | `-128 .. 127` | complemento a dos en un byte |
| `rel32` / `pc32` | `-2^31 .. 2^31-1` | complemento a dos en cuatro bytes |
| `imm64` / `abs64` | `0 .. 2^64-1` | ocho bytes little-endian |

Para un branch, el valor relativo se calcula contra la dirección del byte que
sigue al branch. Un `disp8` o `disp32` de memoria no es automáticamente un
`rel8`/`rel32`: el significado depende del opcode y del modo de direccionamiento.

