# Directivas binarias del MIR externo

Los preámbulos binarios y los parches finales pertenecen al programa MIR
externo, no a la definición `.rif`. El preprocesador consume estas líneas
antes de despachar Rules y nunca las entrega a una Rule.

## `::RIF_INSERT`

Inserta bytes, cadenas binarias o un archivo local en una sección configurada:

```asm
::RIF_INSERT BYTES "7f454c46" SECTION text
::RIF_INSERT BINARY "00000001" SECTION text
::RIF_INSERT FILE "header.bin" SECTION text
```

`BYTES` exige bytes hexadecimales completos. `BINARY` solo acepta `0` y `1`.
`FILE` acepta una ruta relativa que permanezca dentro del proyecto del MIR.
La directiva se aplica antes de la primera línea externa de una Rule.

## `::RIF_PATCH`

Los parches se evalúan después de todas las Rules y cuando ya existe el layout
final de las secciones:

```asm
::RIF_PATCH 24, 8, #:calc(4194304 + #:qlsize(0, "_start"))
::RIF_PATCH 96, 8, #:qssize(0, "text")
::RIF_PATCH 104, 8, #:calc(#:qvssize(0, "text") - 4194304)
```

El ancho opcional se expresa en bytes. Las expresiones nativas se limitan a
literales, `+`, `-`, `#:calc`, `#:query`, `#:qssize`, `#:qlsize`, `#:qvsize` y
`#:qvssize`. Las llamadas arbitrarias `#call[...]` se rechazan. Todos los
parches se validan antes de confirmar los bytes finales.

## Storage y adquisición

`.store` es un manifiesto de payloads nombrados, no solo un manifiesto de
medios. Además de `IMAGE` y `AUDIO`, acepta variables binarias opacas mediante
`BINARY`; el payload se copia byte por byte y no invoca ningún plugin:

```text
MAGIC "store"
VERSION 1

@ITEM BINARY
: "config.bin"
: "bin"
: "RAW"
: config_blob
@end
```

El label es el nombre estable que usa `::RIF_STORE`. Así los datos binarios
quedan separados de las tablas RIF, pero cabeceras, datos de consulta,
firmware y otras variables del target pueden compartir el mismo contenedor
indexado y limitado.

Los `store` también pueden declarar variables de bytes exactos. El tipo fija
el ancho y la representación; enteros y flotantes usan little-endian, los
flotantes usan IEEE-754 y los strings son UTF-8 sin terminador NUL implícito:

```text
MAGIC "store"
VERSION 2

str greeting = "Hola, mundo"
uint8 edad = 30
int32 contador = -2
float32 decimal = 13.0000
```

También se aceptan como alias cortos `i8`/`i16`/`i32`/`i64`,
`u8`/`u16`/`u32`/`u64` y `f32`/`f64`. Los valores son literales; el compilador
del store no ejecuta expresiones ni añade lógica de runtime.

Los archivos raw se pueden cargar usando un label derivado del nombre o un
alias explícito:

```text
@FILE "myfile.bin"
@FILE "headers/boot.dat" AS boot_header
```

`@REQST` es una operación de store VERSION 2. Reutiliza el descargador
binario acotado que ya usa MIR y conserva las mismas reglas: solo HTTPS/GitHub
y con límite de tamaño:

```text
@REQST algo "github.com/owner/repository/path/data.bin/main"
```

También se pueden seleccionar labels de otro contenedor `RIFSTOR` validado.
El `@end` es opcional cuando el contenedor es el último bloque del archivo:

```text
@CONTAINER "variables/vars.bin":
    get etiqueta1
    get etiqueta2
@end
```

La ruta del contenedor debe permanecer dentro de la carpeta del `.store` y
los labels seleccionados se copian al nuevo storage conservando sus bytes.

El preprocesador externo también reconoce `::RIF_BUFFER`, `::RIF_REQSTS` y
`::RIF_STORE`. Estas directivas adquieren bytes con capacidad limitada, cargan
un payload etiquetado desde un contenedor `.bin` validado o extraen un rango
del buffer. Sus reglas se documentan junto al MIR externo.

Los bloques antiguos `@insert`, `@before`, `.bytes`, `.binary`, `.file` y
`.patch` no son sintaxis válida de `.rif` ni aliases de compatibilidad.
