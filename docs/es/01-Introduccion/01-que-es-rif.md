# ¿Qué es RIF?

RIF es un framework de compilación retargetable para describir conjuntos de
instrucciones, dialectos de ensamblador y formatos binarios. Una definición RIF
reconoce líneas de un MIR externo y emite campos en un buffer direccionable por
bits.

RIF separa tres fases:

- **Sintaxis:** Gram tokeniza y parsea la definición RIF.
- **Compilación:** RIF resuelve nombres, tablas, Rules y configuración.
- **Ejecución:** el runtime consume tokens y escribe el binario.

## Qué contiene una definición RIF

El `main.rif` raíz puede contener:

- `@block config`, para secciones, tamaño de palabra, byte_order, labels y políticas.
- `@block linker`, para descubrir el archivo MIR.
- `@table`, para metadatos de instrucciones y datos del target.
- `@define`, para registrar palabras con nombre.
- `@rule`, para describir el procesamiento de líneas MIR.
- `@stack`, para el stack de tokens de `save` y `load`.
- `@LOAD`, para cargar fuentes `.rif` adicionales.
- `@SUPPORTS` y `@ASMVARIANT`, para variantes del target.

Solo la raíz puede declarar configuración y tablas. Los archivos cargados pueden
aportar definiciones, tablas y Rules. Los archivos de variantes solo pueden
aportar definiciones y Rules, por lo que comparten el contexto raíz sin alterar
el layout del target.

## Flujo de procesamiento

```text
Fuente RIF (.rif)
       |
       v
Lexer y parser de Gram
       |
       v
Procesador frontend
       |
       v
CompiledRuleSet
       |
       +---- tokens del MIR externo
       v
RIFMachine
       |
       v
BitBuffer / AssemblyImage
       |
       v
Binario puro
```

Un `.pack` puede saltarse el parseo y la resolución semántica usando su base
SQLite precompilada.

## Neutralidad del target

RIF no asume un procesador ni un ancho de instrucción específicos. El autor del
target decide cómo se relacionan los tokens con las filas de tablas, cómo se
emiten los campos, cómo se parchean las reservas y cómo participan las
funciones nativas.
