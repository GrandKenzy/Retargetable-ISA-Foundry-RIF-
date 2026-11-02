# 06.01. Crear fuentes STORE

Un archivo `.store` es un manifiesto de payloads etiquetados. Cada label debe
ser único dentro de la fuente y cada entrada puede seleccionarse después por
ese nombre.

## Cabecera

Toda fuente comienza con el magic exacto y una versión soportada:

```text
MAGIC "store"
VERSION 1
```

Usa `VERSION 1` para payloads locales/raw. Usa `VERSION 2` cuando haya
declaraciones tipadas o `@REQST`:

```text
MAGIC "store"
VERSION 2
```

Solo las versiones `1` y `2` están soportadas actualmente. La versión `3` queda
reservada para futuras funciones del lenguaje, como funciones o macros.

## Items de media y binarios opacos

La forma por bloque tiene exactamente cuatro campos, en este orden:

```text
@ITEM BINARY
: "config.bin"       ; ruta relativa a la carpeta del .store
: "bin"               ; formato de origen
: "RAW"               ; formato de salida/datos
: config_blob         ; label
@end
```

Los tipos de item soportados son `IMAGE`, `AUDIO` y `BINARY`.

| Tipo | Formatos locales | Comportamiento |
| :--- | :--- | :--- |
| `IMAGE` | `png`, `jpg`, `jpeg`, `bmp`, `gif`, `tga`, `webp` | Usa el plugin de imagen con el formato de salida declarado. |
| `AUDIO` | `wav`, `flac`, `ogg` | Usa el plugin de audio con el formato de salida declarado. MP3 no es una entrada de audio STORE. |
| `BINARY` | `bin`, `dat`, `raw` | Copia el archivo byte por byte. El formato de datos debe ser `RAW` o `BYTES`; no ejecuta plugins de media. |

Para `IMAGE` y `AUDIO`, el tercer campo es el formato de salida del plugin,
como el formato soportado por el conversor seleccionado. La extensión del
archivo debe coincidir con el formato declarado. En `BINARY`, `raw` significa
bytes opacos, no un parser ni un ensamblador.

## Valores tipados de bytes exactos

Los valores tipados requieren `VERSION 2`:

```text
MAGIC "store"
VERSION 2

str greeting = "Hello, world"
uint8 age = 30
int32 count = -2
float32 decimal = 13.0000
```

| Tipo canónico | Alias | Ancho | Codificación |
| :--- | :--- | ---: | :--- |
| `str` | — | variable | Bytes UTF-8, sin NUL implícito |
| `int8`, `int16`, `int32`, `int64` | `i8`, `i16`, `i32`, `i64` | 1, 2, 4, 8 bytes | Entero little-endian con signo |
| `uint8`, `uint16`, `uint32`, `uint64` | `u8`, `u16`, `u32`, `u64` | 1, 2, 4, 8 bytes | Entero little-endian sin signo |
| `float32`, `float64` | `f32`, `f64` | 4, 8 bytes | Float IEEE-754 little-endian |

Los valores son únicamente literales. No hay expresiones, asignaciones,
actualizaciones en runtime ni conversiones de tipos. Los rangos enteros se
comprueban según el ancho y los floats deben ser finitos.

El tipo declarado se conserva en el índice de un storage versión 2 para que el
consumidor pueda aplicar después un layout de bytes. El payload ya está
codificado en la forma canónica little-endian.

## Añadir un archivo local

`@FILE` copia un archivo local arbitrario como bytes raw:

```text
@FILE "myfile.bin"
@FILE "headers/boot.dat" AS boot_header
```

Sin `AS`, el label es el nombre base del archivo (`myfile` en el primer
ejemplo). La ruta es relativa al `.store` y debe permanecer dentro de su
carpeta: se rechazan rutas absolutas y recorridos con `..`.

## Solicitar un binario acotado de GitHub

`@REQST` requiere `VERSION 2` y un archivo `.bin` alojado en GitHub:

```text
@REQST algorithm "github.com/owner/repository/path/algorithm.bin/main"
```

También se acepta `https://github.com/...`. La ruta debe terminar en una rama,
contener una ruta de archivo `.bin` y no puede incluir credenciales, query
strings, fragmentos ni recorridos. Solo se siguen hosts HTTPS de GitHub. La
petición tiene timeout de 15 segundos y está limitada a 16 MiB, o al límite
global configurado si es menor.

`@REQST` adquiere bytes raw, no ejecuta código. El archivo descargado se guarda
con el label declarado sin usar plugins de imagen o audio.

## Importar entradas de otro contenedor

Usa `@CONTAINER` para copiar entradas etiquetadas de un storage validado:

```text
@CONTAINER "variables/vars.storage.bin":
    get etiqueta1
    get etiqueta2
@end
```

La ruta es local a la carpeta del `.store` actual y tiene las mismas
restricciones de seguridad que `@FILE`. Las entradas conservan sus labels y
bytes originales. Se recomienda escribir `@end`; solo puede omitirse cuando el
bloque es el último de la fuente.

Si una entrada seleccionada tiene metadatos tipados de la versión 2, la fuente
que importa también debe ser `VERSION 2`; la versión 1 solo puede contener
entradas raw.

## Restricciones

- Los labels deben ser identificadores como `config_blob` o `MODE_3` y ser
  únicos.
- Las rutas se resuelven desde la carpeta del `.store`, no desde el directorio
  de trabajo del proceso.
- Un item `BINARY` no es un entero tipado; usa una declaración tipada cuando
  importe el ancho y la representación numérica.
- Una declaración tipada no es una variable de runtime: es un payload fijo.
- La conversión de `IMAGE` y `AUDIO` es explícita. Usa `BINARY` o `@FILE` si
  el origen debe conservarse byte por byte.
