# 05. Herramientas PCP-I

PCP-I es la herramienta independiente de RIF para describir plantillas
binarias. Define una imagen determinista de bytes con bytes fijos, regiones de
ceros estáticos y regiones rellenables explícitas llamadas *pits*.

PCP-I es útil cuando el envoltorio binario ya es estable, pero una etapa
posterior todavía debe calcular el valor final de algunos campos. No es un
ensamblador, linker, constructor de sistemas de archivos, generador de ISO ni
bootloader.

## Flujo completo

```text
header.pci --comp-pcpi--> header.pcic --SET/FILL--> bytes en la salida MIR
```

Compilar una plantilla:

```powershell
vnma run main.py --comp-pcpi header.pci -o build/header.pcic
```

Validar una plantilla compilada:

```powershell
vnma run main.py --doctor-pcpi build/header.pcic
```

Usarla desde un programa MIR externo:

```asm
::RIF_PCPI SET "build/header.pcic"
::RIF_PCPI FILL 0 "0102030405060708"
```

`SET` materializa el payload PCP-I en la sección MIR actual. `FILL` sustituye
un pit con exactamente el número de bytes declarado. La cabecera de 144 bytes
del contenedor PCP-I y la tabla de pits son metadatos: no se insertan en la
salida MIR.

## Guías

| Guía | Propósito |
| :--- | :--- |
| [01. Crear plantillas PCP-I](./01-crear-plantillas.md) | Sintaxis fuente, bytes fijos, `ZERO`, pits, alineación y contenedor compilado. |
| [02. Compilar, inspeccionar y rellenar](./02-compilar-inspeccionar-y-rellenar.md) | CLI, API Python, directivas MIR, orden y límites de la imagen final. |

## Límite del formato

PCP-I versión 1 es independiente de las definiciones de targets RIF y del
versionado de STORE. Un archivo `.pcic` es una plantilla intermedia validada.
Una ISO, ROM, ejecutable o imagen de firmware real todavía necesita un
productor que ensamble la plantilla con sus payloads y metadatos específicos.

El contrato binario completo también está descrito en la [guía PCP-I de
compilación en inglés](../../en/03-Compilation/06-pcp-i.md).
