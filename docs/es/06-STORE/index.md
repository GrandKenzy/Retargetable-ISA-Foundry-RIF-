# 06. Herramientas STORE

STORE es la herramienta independiente de RIF para payloads indexados. Una
fuente `.store` nombra payloads binarios y valores de ancho fijo; el compilador
produce un contenedor `RIFSTOR` validado con labels y rangos de bytes.

Sirve para constantes de firmware, tablas de consulta, imágenes, audio,
archivos binarios opacos y payloads pequeños propiedad del target. No crea
variables con comportamiento en runtime: una declaración tipada es un payload
exacto de bytes.

## Flujo completo

```text
assets.store --comp-store--> build/assets.storage.bin --RIF_STORE--> bytes MIR
```

Compilar una fuente:

```powershell
vnma run main.py --comp-store assets.store -o build/assets.storage.bin
```

Validar e inspeccionar el contenedor:

```powershell
vnma run main.py --doctor-storage build/assets.storage.bin
```

Insertar un payload etiquetado desde MIR externo:

```asm
::RIF_STORE "build/assets.storage.bin" title 1 0
```

Para reutilizar la ruta, declara un alias y configúralo una vez:

```asm
::RIF_STORE AS assets "build/assets.storage.bin"
assets.ORDER 1
assets.ENDIANNESS 1

::RIF_STORE assets title
::RIF_STORE assets palette
```

## Guías

| Guía | Propósito |
| :--- | :--- |
| [01. Crear fuentes STORE](./01-crear-fuentes-store.md) | Items raw, literales tipados, archivos, requests remotos, contenedores y versiones. |
| [02. Compilar y consumir storage](./02-compilar-y-consumir-storage.md) | CLI, layout, aliases, orden de bytes e inserción MIR. |

## Política de versiones

| Versión | Funciones disponibles |
| :---: | :--- |
| `1` | Media local, `BINARY` opaco, `@FILE` y selección de entradas raw de contenedores. Sin declaraciones tipadas ni `@REQST`. |
| `2` | Todo lo de la versión 1, más literales tipados y `@REQST` acotado. El índice conserva el tipo. |

RIF acepta actualmente solo las versiones `1` y `2`. La versión `3` no es un
formato actual; queda reservada para futuras funciones o macros.

## Límite del formato

`RIF_STORE` inserta los bytes del payload seleccionado. No inserta la cabecera,
la región raw ni el índice del storage en la salida MIR. Las imágenes y el audio
se convierten mediante el formato declarado; `BINARY`, `@FILE`, los valores
tipados y las entradas raw importadas se copian o codifican de forma
determinista.
