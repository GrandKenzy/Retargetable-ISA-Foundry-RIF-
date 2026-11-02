# 05.01. Crear plantillas PCP-I

Usa un archivo `.pci` como fuente legible de una plantilla PCP-I. El compilador
actual no exige una extensión concreta, por lo que proyectos existentes también
pueden usar `.pcpi`; `.pci` es el nombre recomendado.

## Fuente mínima

```text
MAGIC "pcpi"
VERSION 1
ENDIANNESS 1
BITORDER 1
SIGNATURE "Plantilla de cabecera"
PADDING 0

@RAW
AA BB CC
ZERO 5
[8]
10 20
@END
```

La cabecera va seguida de una sola región `@RAW`. `@END` termina la fuente y no
puede haber contenido después. Se ignoran los comentarios con punto y coma y
las líneas vacías.

## Campos de cabecera

| Campo | Valores | Significado |
| :--- | :--- | :--- |
| `MAGIC` | exactamente `"pcpi"` | Selecciona PCP-I. |
| `VERSION` | `1` | Selecciona el formato PCP-I actual. |
| `ENDIANNESS` | `1` o `2` | Metadato para consumidores little-endian o big-endian. No reescribe bytes. |
| `BITORDER` | `0` o `1` | Metadato para consumidores LSB-first o MSB-first. No invierte bytes. |
| `SIGNATURE` | cadena UTF-8 no vacía | Identidad legible, limitada al campo de firma PCP-I. |
| `PADDING` | entero no negativo | Bytes estáticos en cero antes de la imagen raw. Por defecto es `0`. |

El compilador guarda los metadatos, pero no reinterpreta los bytes literales
según `ENDIANNESS` o `BITORDER`. Si los bytes deben invertirse o codificarse,
escribe el orden final en la fuente o hazlo en el productor externo.

## Bytes raw y ceros estáticos

La región raw acepta tokens de bytes hexadecimales de dos dígitos, con prefijo
`0x` opcional:

```text
@RAW
7F 0x45 4C 46
ZERO 1024
00
@END
```

`ZERO n` emite exactamente `n` bytes fijos en cero. No crea un campo futuro, un
registro de índice ni un límite de alineación. Úsalo para espacio reservado,
padding de descriptores y sectores sin uso.

## Pits

`[n]` crea un pit rellenable de exactamente `n` bytes:

```text
@RAW
01 02 03
[8]
FF
@END
```

Los pits deben tener tamaño positivo. PCP-I alinea cada dirección de pit a ocho
bytes insertando ceros estáticos inmediatamente antes cuando es necesario.
Esos bytes de alineación no forman parte del pit. En el ejemplo, el pit empieza
en la dirección `8` de la imagen raw, tiene tamaño `8` y tiene `5` bytes de
padding de alineación.

La diferencia es intencional:

```text
ZERO 2048   ; bytes fijos en cero
[2048]      ; campo de 2048 bytes que se rellenará después
```

Cada pit recibe un índice según su orden en la fuente, empezando en `0`. El
consumidor posterior debe sustituir cada pit por exactamente su tamaño. PCP-I
nunca trunca, extiende ni infiere un reemplazo.

## Contenido del `.pcic` compilado

El contenedor compilado se valida antes de escribirse. Su disposición es:

```text
cabecera PCP-I fija (144 bytes)
bytes de PADDING
imagen de plantilla raw
alineación final generada (RPAD)
tabla de pits
```

Las direcciones de los pits son relativas al inicio de la imagen raw, no al
inicio del archivo `.pcic`. La cabecera y la tabla son útiles para herramientas
que inspeccionan o renderizan la plantilla; no forman parte del payload que
`::RIF_PCPI SET` emite en MIR.

## Reglas de diseño

- Mantén los metadatos de formato en `ENDIANNESS` y `BITORDER`; no asumas que
  transforman bytes automáticamente.
- Usa `ZERO` para espacio estático y `[n]` solo para un campo cuyo propietario
  sea un productor posterior.
- Mantén los pits pequeños y semánticamente claros. Un pit grande transfiere
  al productor posterior la responsabilidad de cada byte del rango.
- No introduzcas registros de filesystem, código de arranque, cursores o una
  ISO completa en una plantilla de cabecera si esos bytes pertenecen a otra
  capa.
- Trata el `.pcic` compilado como un artefacto intermedio, no como una imagen
  arrancable.
