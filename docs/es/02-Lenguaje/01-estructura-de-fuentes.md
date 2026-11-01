# Estructura de fuentes

El archivo raíz suele llamarse `main.rif` y es el centro de control del target.
Puede declarar objetos en cualquier orden; el procesador registra primero
configuración, linker, definiciones y soportes, y después resuelve tablas y
Rules.

## Comentarios y saltos de línea

```rif
; comentario RIF
@define mov ; comentario al final
```

Los saltos de línea son significativos dentro de una Rule:

```rif
@rule mov:
. IDENT
. eword 1
```

No existe una gramática de indentación para Rules.

## Declaraciones por alcance

La raíz puede contener `@block config`, `@block linker`, `@table`, `@stack`,
`@SUPPORTS`, `@ASMVARIANT`, `@define`, `@rule` y `@LOAD`.

Un archivo cargado con `@LOAD` solo puede contener `@define`, `@table`, `@rule`
y más `@LOAD`. Un archivo de variante solo puede contener `@define` y `@rule`.

La configuración solo puede materializarse desde la raíz. Si se separa en
`config.rif`, únicamente `main.rif` puede cargarlo directamente; ese archivo
solo puede contener `@block config` y `@block linker`. Un archivo incluido no
puede cargarlo, y declarar `config` o `linker` más de una vez es un error.

Así una fuente cargada no reemplaza silenciosamente la memoria ni la política
del target.

## Bloques genéricos

La forma genérica de declarar datos por bloques es:

```rif
@block config:
    format section ".section"
    section text ""
    word_size 8
@end
```

Cada línea contiene un nombre y cero, uno o dos valores antes del salto de
línea. No se aceptan prefijos de punto ni las antiguas cabeceras
`@config`/`@linker`; una línea con más de dos valores es inválida.

Los bloques `config` y `linker` alimentan directamente la semántica existente de RIF.
Los bloques con otros nombres se conservan como datos estructurados en
`program.context.blocks`, para que los consumidores especializados puedan
interpretarlos sin añadir una nueva regla al parser.

## Definiciones

```rif
@define mov
@define add
```

Una definición es una palabra registrada; no reserva slots, no emite bits y no
crea un valor runtime.

## Rules

```rif
@rule mov:
. IDENT
. nibbles 0000 0000
```

Una línea MIR que empieza con `mov` se despacha a esta Rule. Cada instrucción
de la Rule comienza con un punto; las flechas ya no forman parte de la
sintaxis.

## Stack de tokens

```rif
@stack 50
```

Solo puede existir un `@stack`. Sus instrucciones `save` y `load` trabajan con
tokens y es distinto del `datastack` de valores temporales.
