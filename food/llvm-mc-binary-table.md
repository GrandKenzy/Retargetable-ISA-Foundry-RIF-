# Tabla de LLVM MC para emisión binaria

LLVM separa la representación de una instrucción de la emisión de sus bytes y
de la resolución de símbolos. Esta separación es la referencia conceptual más
útil para el pipeline MIR → RIF.

## Etapas

| Etapa LLVM MC | Entrada | Salida | Correspondencia en RIF |
| --- | --- | --- | --- |
| Parser / lowering | Assembly o MIR de alto nivel | `MCInst`, expresiones y directivas | MIR ya preprocesado y Rules resueltas |
| `MCStreamer` | `MCInst`, labels, símbolos y secciones | eventos de emisión | `AssemblyImage`, selección de sección y emisor |
| `MCCodeEmitter` | `MCInst` + subtarget | bytes y `MCFixup` | `BitEmitter` + `mark`/`fixup` |
| `MCFixup` | offset, expresión, kind y opcionalmente PC-relative | operación pendiente sobre bytes | `Fixup(kind, symbol, reservation, offset_bits, ...)` |
| assembler backend | bytes + fixups + layout | bytes parcheados o relocaciones de objeto | resolución final de fixups nativos de RIF |
| object streamer/writer | secciones, símbolos y relocaciones | `.o`/ELF u otro objeto | artefactos binarios de RIF; no es parte de la gramática `.rif` |

## Datos que deben acompañar un fixup

| Dato | Pregunta que responde | RIF |
| --- | --- | --- |
| Offset | ¿Dónde se escribe? | `offset_bits` de la reserva |
| Width/kind | ¿Cuántos bits y qué semántica? | `pc8`, `pc32`, `abs64` |
| Expression/symbol | ¿Contra qué se calcula? | `symbol` |
| PC-relative | ¿Se resta el punto de referencia? | `pc8` y `pc32` |
| Layout/section | ¿Qué base virtual aplica? | `section` + `virtual_bases` |
| Range check | ¿Cabe el resultado en el campo? | signed para PC-relative, unsigned para `abs64` |

## Regla de resolución

Para el contrato actual de RIF:

```text
target = virtual_base(symbol.section) + symbol.virtual_offset
next_ip = virtual_base(fixup.section) + fixup.next_virtual_bits / 8

pc8  = target - next_ip       # signed 8 bits
pc32 = target - next_ip       # signed 32 bits
abs64 = target                # unsigned 64 bits
```

El backend debe validar rango y solapes antes de escribir. Si falla una
validación, la aplicación debe conservar el buffer sin parches parciales.
Esto corresponde al modelo de LLVM en el que el encoder puede emitir bytes
provisionales y fixups, y el backend aplica los fixups o los convierte en
relocaciones cuando no pueden resolverse localmente.

## Observación de arquitectura

LLVM MC modela secciones, labels, símbolos e instrucciones en el nivel de
emisión. En RIF, la selección de sección (`::RIF_SECTION`) pertenece al
preprocesador MIR; `.rif` solo declara la generación de bits y las
relocaciones. Así se evita introducir en la definición binaria lógica de
linking que ya resolvió la entrada MIR.

