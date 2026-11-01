# 02. Lenguaje

RIF es lineal. Gram conserva los tokens `NEWLINE` y las Rules usan una
instrucción por línea. Los comentarios comienzan con `;`.

| Guía | Resumen |
| :--- | :--- |
| [01. Estructura de fuentes](./01-estructura-de-fuentes.md) | Declaraciones raíz, orden, comentarios y forma básica. |
| [02. Configuración y linker](./02-configuracion-y-linker.md) | Secciones, formato de salida y descubrimiento de MIR. |
| [03. Tablas y cargas](./03-tablas-y-cargas.md) | Tablas inmutables indexadas, `@LOAD` y alcances. |
| [04. Rules y valores](./04-rules-y-valores.md) | Instrucciones, tokens, tablas y expresiones de valor. |

## Forma mínima

```rif
@block config:
    ; directivas del target
@end

@block linker:
    ; directivas del linker
@end

@table registers
| name | bits |
__
| rax | 64 |
@end

@rule mov:
. IDENT
. fit $registers.bits
```

Para compilar MIR, el bloque `@block config` debe incluir todas sus directivas
obligatorias.
