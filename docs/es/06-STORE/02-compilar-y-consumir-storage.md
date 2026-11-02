# 06.02. Compilar y consumir storage

STORE tiene una etapa de fuente y una etapa de consumo. La primera construye un
contenedor indexado validado; la segunda selecciona un label y emite únicamente
su payload.

## Compilar una fuente `.store`

```powershell
vnma run main.py --comp-store assets.store `
  -o build/assets.storage.bin
```

Sin `-o`, el compilador escribe la salida junto a la fuente con sufijo
`.storage.bin`:

```powershell
vnma run main.py --comp-store assets.store
# escribe assets.storage.bin
```

La compilación valida la fuente, mantiene labels únicos, resuelve payloads
locales desde la carpeta de la fuente, ejecuta solo los conversores de media
declarados y escribe el resultado atómicamente. Nunca evalúa los valores
tipados como lógica de programa.

## Inspeccionar un contenedor

```powershell
vnma run main.py --doctor-storage build/assets.storage.bin
```

El doctor valida magic `RIFSTOR`, versión, cabecera, región raw, índice,
alineación, límites, labels y, en la versión 2, metadatos de tipo. Informa
versión, cantidad de bytes raw, entradas, dirección relativa, tamaño, padding,
tamaño del label y label de cada entrada.

## Layout del storage

El archivo compilado contiene:

```text
cabecera RIFSTOR fija (48 bytes)
región raw alineada
índice de entradas de ancho fijo
```

El registro actual de entrada tiene 24 bytes. Cada entrada apunta a la región
raw y puede colocar su label UTF-8 inmediatamente después del payload. El índice
no forma parte del payload devuelto por `RIF_STORE`.

La versión 1 conserva el formato raw original. La versión 2 guarda el código de
tipo declarado en los metadatos existentes de la entrada y conserva los mismos
tamaños de cabecera y registro. El loader acepta ambas versiones; las
herramientas actuales no emiten ni aceptan una versión 3.

## Uso directo de `RIF_STORE`

La forma directa selecciona ruta, label, endianness y orden:

```asm
::RIF_STORE "build/assets.storage.bin" title 1 0
```

| Posición | Valores | Significado |
| :--- | :--- | :--- |
| Primer número | `1` o `2` | `1` little-endian, `2` big-endian. |
| Segundo número | `0` o `1` | `0` orden LSB, `1` orden MSB. |

La posición de inserción debe estar alineada a bytes. El label debe existir y la
ruta debe tener sufijo `.bin`. Nunca se emiten la cabecera ni el índice.

## Alias y layout por storage

Un alias evita repetir la ruta:

```asm
::RIF_STORE AS GBA "build/gba.storage.bin"
GBA.ORDER 1
GBA.ENDIANNESS 1

::RIF_STORE GBA MODE_3
::RIF_STORE GBA DIR_VRAM
::RIF_STORE GBA DISPCNT
```

La forma con ruta primero sigue aceptándose para MIR existente:

```asm
::RIF_STORE "build/gba.storage.bin" AS GBA
```

Declara el alias antes de configurarlo o consumirlo. `ORDER` acepta `0` o `1`;
`ENDIANNESS` acepta `1` o `2`. El alias y su configuración pertenecen a una
compilación MIR y no son estado global del proyecto.

Para un escalar tipado de la versión 2, `ENDIANNESS 2` invierte cada elemento
completo a big-endian al insertarlo. Strings, imágenes, audio, `BINARY`,
`@FILE`, `@REQST` y demás entradas opacas permanecen byte por byte. Los tipos
escalares actuales están alineados a bytes, por lo que `ORDER` se valida y se
conserva como metadato de layout, pero por sí solo no cambia los bytes emitidos.

Los argumentos numéricos explícitos sobrescriben la configuración del alias
para ese uso:

```asm
::RIF_STORE GBA MODE_3 2 0
```

La forma con alias y sin números es la recomendada cuando varios labels
comparten el mismo layout.

## Ejemplo completo

`assets.store`:

```text
MAGIC "store"
VERSION 2

uint32 MODE_3 = 0x04000000
uint32 DIR_VRAM = 0x06000000
uint16 DISPCNT = 0x0403
str title = "RIF GBA"
@FILE "assets/ball_palette.bin" AS palette
```

Construirlo y consumirlo:

```powershell
vnma run main.py --comp-store assets.store -o build/gba.storage.bin
vnma run main.py --doctor-storage build/gba.storage.bin
```

```asm
::RIF_STORE AS GBA "build/gba.storage.bin"
GBA.ORDER 1
GBA.ENDIANNESS 1

; Consumo real de STORE en una posición MIR alineada a bytes.
::RIF_STORE GBA MODE_3
::RIF_STORE GBA DIR_VRAM
::RIF_STORE GBA DISPCNT
```

`RIF_STORE` no sustituye actualmente `GBA.MODE_3` dentro de un operando de
instrucción normal. Para eso haría falta una característica separada de
resolución de símbolos u operandos.

## Errores y límites

| Error | Significado |
| :--- | :--- |
| `VERSION de .store debe ser 1 o 2` | La fuente seleccionó una versión no soportada. |
| Valores tipados o `@REQST` en versión 1 | Cambia la fuente a `VERSION 2`. |
| Label inexistente | La entrada no existe o no es única. |
| `ORDER`/`ENDIANNESS` inválidos | Usa `ORDER 0/1` y `ENDIANNESS 1/2`. |
| Inserción desalineada | `RIF_STORE` emite bytes completos y requiere posición MIR alineada a bytes. |
| QEMU o un formato de arranque rechaza el resultado | STORE es un contenedor de payloads, no una ISO, ROM, ejecutable ni filesystem. |
