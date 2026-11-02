# Documentación de RIF

> **Versión:** `1.0.0`
> **Runtime:** Python 3.10+ con Gram

RIF es un framework retargetable para describir conjuntos de instrucciones,
formatos de ensamblador y diseños binarios. Una definición RIF describe cómo
se reconoce un programa MIR externo, cómo se consultan sus datos y cómo se
emite el binario puro final.

RIF usa [Gram](https://github.com/GrandKenzy/Gram) para el análisis léxico y
el parseo sintáctico. El frontend convierte una definición `.rif` en Rules
compiladas; el runtime de MIR ejecuta esas Rules contra un programa externo.

Consulta el [changelog de RIF](../../changelog/README.md) para las notas
versionadas.

## Índice de documentación

### [01. Introducción](./01-Introduccion/index.md)

Conceptos, instalación, estructura del proyecto y flujo completo.

- [01. Qué es RIF](./01-Introduccion/01-que-es-rif.md)
- [02. Instalación](./01-Introduccion/02-instalacion.md)
- [03. Arquitectura](./01-Introduccion/03-arquitectura.md)

### [02. Lenguaje](./02-Lenguaje/index.md)

El lenguaje `.rif`: declaraciones, configuración, tablas, Rules, valores y
cargas externas.

- [01. Estructura de fuentes](./02-Lenguaje/01-estructura-de-fuentes.md)
- [02. Configuración y linker](./02-Lenguaje/02-configuracion-y-linker.md)
- [03. Tablas y cargas](./02-Lenguaje/03-tablas-y-cargas.md)
- [04. Rules y valores](./02-Lenguaje/04-rules-y-valores.md)

### [03. Compilación](./03-Compilacion/index.md)

Compilación de MIR, paquetes `.pack` y funciones nativas.

- [01. MIR externo](./03-Compilacion/01-mir-externo.md)
- [02. Paquetes RIF](./03-Compilacion/02-paquetes-rif.md)
- [03. Funciones nativas](./03-Compilacion/03-funciones-nativas.md)

### [04. Ejecución](./04-Ejecucion/index.md)

Memoria de bits, datastack, variantes, trazas, diagnóstico y pruebas.

- [01. Memoria de bits](./04-Ejecucion/01-memoria-de-bits.md)
- [02. Datastack](./04-Ejecucion/02-datastack.md)
- [03. Variantes](./04-Ejecucion/03-variantes.md)
- [04. Diagnóstico y pruebas](./04-Ejecucion/04-diagnostico-y-pruebas.md)
- [05. Inserts y parches](./04-Ejecucion/05-inserts-y-parches.md)

### [05. Herramientas PCP-I](./05-PCPI/index.md)

Plantillas binarias declarativas, pits rellenables, inspección y uso desde MIR.

- [01. Crear plantillas PCP-I](./05-PCPI/01-crear-plantillas.md)
- [02. Compilar, inspeccionar y rellenar](./05-PCPI/02-compilar-inspeccionar-y-rellenar.md)

### [06. Herramientas STORE](./06-STORE/index.md)

Valores tipados, payloads raw, media, archivos, contenedores y consumo desde
MIR.

- [01. Crear fuentes STORE](./06-STORE/01-crear-fuentes-store.md)
- [02. Compilar y consumir storage](./06-STORE/02-compilar-y-consumir-storage.md)

## Inicio rápido

```text
main.rif + program.asm -> program.bin
```

```powershell
vnma run main.py main.rif program.asm
vnma run main.py --pack main.rif -o main.pack
vnma run main.py main.pack program.asm
```

La salida es un archivo binario puro. Si no se especifica `-o`, el nombre se
deriva del archivo MIR y usa la extensión `.bin`.

`main.py` es la entrada canónica. `rif.cmd` es únicamente un lanzador opcional
para usar RIF desde cualquier carpeta cuando la raíz del repositorio está en
`PATH`.
