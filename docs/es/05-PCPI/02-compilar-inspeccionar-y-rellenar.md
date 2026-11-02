# 05.02. Compilar, inspeccionar y rellenar PCP-I

PCP-I tiene dos operaciones separadas: compilar una plantilla textual a un
`.pcic` validado y renderizar sus pits durante una etapa posterior que produce
el binario.

## Compilar una fuente

```powershell
vnma run main.py --comp-pcpi examples/headers/header.pci `
  -o build/header.pcic
```

Si no se indica `-o`, el compilador cambia el sufijo de la fuente a `.pcic`:

```powershell
vnma run main.py --comp-pcpi header.pci
# escribe header.pcic junto a header.pci
```

La salida no puede sobrescribir la fuente. La compilación valida cabecera,
imagen raw, alineación y límites de pits, campos reservados y tamaños finales
antes de escribir atómicamente el archivo.

## Inspeccionar un contenedor

```powershell
vnma run main.py --doctor-pcpi build/header.pcic
```

El doctor valida el artefacto sin modificarlo e informa versión, firma,
metadatos de orden de bytes, tamaño de imagen raw, padding, RPAD y registros de
pits. Cada pit incluye índice, dirección relativa, tamaño exacto y padding de
alineación.

## Usar PCP-I desde MIR externo

El preprocesador MIR reconoce tres directivas cerradas:

```asm
::RIF_PCPI SET "build/header.pcic"
::RIF_PCPI FILL 0 "0102030405060708"
::RIF_PCPI PIT 0
```

### `SET`

`SET` debe ser la primera línea MIR no vacía. Carga un `.pcic` relativo al MIR,
lo valida y reserva su payload renderizado en la sección actual. Solo se permite
un `SET` y la sección debe estar alineada a bytes.

`SET` emite:

```text
PADDING + imagen raw resuelta + RPAD
```

No emite la cabecera de 144 bytes ni la tabla de pits. Primero se usan bytes de
relleno en cero para mantener estables los offsets posteriores.

### `FILL`

```asm
::RIF_PCPI FILL 0 "0102030405060708"
```

El índice empieza en cero. El valor son bytes hexadecimales; se aceptan
espacios, guiones bajos y un prefijo `0x` opcional. El valor decodificado debe
tener exactamente el tamaño declarado por el pit. Faltas, duplicados, hex
inválido, tamaños cortos, tamaños largos e índices inexistentes son errores.
Todos los pits deben rellenarse antes de confirmar la salida final.

`FILL` no emite bytes adicionales ni modifica el archivo `.pcic`.

### `PIT`

```asm
::RIF_PCPI PIT 0
::RIF_PCPI PIT 0 SECTION text
```

`PIT` no emite bytes. Informa la dirección final del pit seleccionado a través
del resultado de compilación MIR y de los diagnósticos de la CLI. La dirección
considera el offset de la sección, la posición de inserción PCP-I, `PADDING` y
la dirección del pit dentro de la imagen raw. No incluye la cabecera ni la
tabla del contenedor `.pcic`.

La forma `SECTION name` consulta el offset final de una sección concreta.

## API Python

Para un productor externo que no use MIR:

```python
from rif_tools.pcpi_compiler import compile_pcpi_source

compiled = compile_pcpi_source("header.pci").image
raw_image = compiled.fill(0, bytes.fromhex("0102030405060708"))
rendered = compiled.render({0: bytes.fromhex("0102030405060708")})
```

`fill()` devuelve la imagen raw. `render()` devuelve el payload completo:
`PADDING` inicial, imagen raw resuelta y `RPAD` final. Ambas operaciones validan
el tamaño exacto de cada pit y no mutan el objeto compilado.

## Límite de la imagen final

PCP-I no crea un filesystem ISO-9660, catálogo El Torito, ejecutable, ROM ni
disco para QEMU. Un productor posterior debe ensamblar el payload renderizado
con los registros y datos específicos del formato.

El flujo MIR es:

```text
cargar .pcic -> reservar payload -> rellenar todos los pits -> emitir bytes
```

No es:

```text
.pcic -> imagen arrancable automática
```

## Errores comunes

| Error | Causa | Corrección |
| :--- | :--- | :--- |
| `SET` es rechazado | No es la primera línea no vacía o se usó más de uno | Mueve un único `SET` al inicio del MIR. |
| Un fill tiene tamaño incorrecto | Los campos PCP-I tienen tamaño exacto | Codifica exactamente `pit.size` bytes. |
| Queda un pit sin resolver | Falta un `FILL` | Rellena cada pit exactamente una vez. |
| La dirección parece incorrecta | Se mezclaron direcciones raw y de archivo final | Considera sección, inserción y `PADDING`; nunca agregues la cabecera del contenedor. |
| QEMU no arranca el resultado | `.pcic` es una plantilla, no una ISO | Ensambla una imagen real después de renderizar PCP-I. |
