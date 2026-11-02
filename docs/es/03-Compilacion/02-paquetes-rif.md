# Paquetes RIF

`.pack` es el paquete portable de un target RIF. Es un ZIP reproducible con
las fuentes RIF y, si se solicita, una base SQLite precompilada.

## Crear un paquete

```powershell
vnma run main.py --pack main.rif
vnma run main.py --pack main.rif -o targets/amd64.pack
```

Puede contener:

```text
manifest.json
sources/main.rif
sources/other.rif
compiled/program.sqlite3 (si se precompila)
```

La ruta real de la base precompilada es `compiled/program.sqlite3`.

El manifiesto registra formato, versión del contrato, hashes de fuentes, grafo
de `@LOAD`, orden de dependencias y la base compilada opcional. El contrato
identifica la combinación compatible de RIF, Gram/GIR, FFI AOT, SQLite y
runtime; un artefacto de otra combinación se rechaza antes de procesar MIR.

Las librerías reutilizables se crean con `vnma run main.py --library
patrones/main.rif -o patrones.riflib` y se consumen desde un target con
`@LIBRARY "patrones.riflib"`.
Al crear un `.pack`, RIF incluye y verifica esas librerías bajo `libraries/`.
También se puede exportar un `.pack` completo a una librería de declaraciones:

```powershell
vnma run main.py --library base.pack -o patrones-reutilizables.riflib
```

La exportación conserva las fuentes de declaraciones cargadas explícitamente
por el paquete y descarta su `config`, `linker` y bloques genéricos raíz. El
target consumidor elige así su propia política de salida y metadatos de
plataforma. Un `.pack` es un target completo y no se mezcla implícitamente con
otro target.
Las directivas del MIR externo no
forman parte del grafo de fuentes; `::RIF_INSERT FILE` resuelve su ruta
respecto al archivo MIR que se está compilando.

## Ventajas

El paquete valida y resuelve las cargas antes de usar el target. Con
`precompile=True` también guarda Rules, configuración, linker, definiciones y
filas de tablas. Así puede abrirse sin parsear todas las fuentes otra vez.

Es útil cuando hay muchas fuentes, tablas grandes, muchos MIR contra el mismo
target o se necesita distribuir un solo archivo.

## Validación

RIF valida rutas y hashes SHA-256. Rechaza dependencias ausentes, ciclos,
fuentes modificadas, esquemas SQLite incompatibles y metadatos inválidos.

El `.pack` contiene la definición del target, no el MIR externo ni el binario
final.

## Inspección segura

El inspector de paquetes valida siempre el ZIP, sus hashes, límites, la huella
de contenido y la base SQLite compilada. No ejecuta Rules, no activa globals del
frontend, no carga plugins y no extrae archivos:

```powershell
vnma run main.py --inspect-pack target.pack
vnma run main.py --inspect-pack target.pack --json
vnma run main.py --inspect-pack target.pack --verbose --max-items 200
```

La salida muestra el formato y versión del paquete, fingerprint y contrato,
fuentes, assets, Rules, tablas, configuración, linker, variantes y las extensiones MIR
aceptadas. `--json` produce un informe estable para herramientas; `--verbose`
añade instrucciones y filas, siempre acotadas por `--max-items`. Las rutas de
origen absolutas del creador permanecen ocultas salvo que se indique
`--show-origins`.

La compilación MIR puede producir un mapa opcional sin cambiar el binario:

```powershell
vnma run main.py target.pack program.mir -o program.bin --map program.map.json
```

El mapa registra contrato, hash y tamaños del binario, secciones, símbolos,
Rules ejecutadas y relocaciones resueltas.
