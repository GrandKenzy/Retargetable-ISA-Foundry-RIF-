# Paquetes RIF

`.pack` es el paquete portable de un target RIF. Es un ZIP reproducible con
las fuentes RIF y, si se solicita, una base SQLite precompilada.

## Crear un paquete

```powershell
rif --pack main.rif
rif --pack main.rif -o targets/amd64.pack
```

Puede contener:

```text
manifest.json
sources/main.rif
sources/other.rif
compiled.sqlite          (si se precompila)
```

El manifiesto registra formato, hashes de fuentes, grafo de `@LOAD`, orden de
dependencias y la base compilada opcional. Las directivas del MIR externo no
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
