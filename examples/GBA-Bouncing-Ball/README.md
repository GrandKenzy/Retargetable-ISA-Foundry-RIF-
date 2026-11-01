# RIF: Game Boy Advance (ARM7TDMI) — pelota que rebota

El ejemplo genera una ROM GBA pequeña y una versión opcional acolchada a
256 KiB. Las ROMs, el pack y el MIR se generan localmente y no forman parte
del repositorio.

Demo experimental de RIF que genera un cartucho GBA con pantalla verde y una
pelota blanca redondeada, que rebota contra los bordes de una pantalla
**240×160**, Mode 3 (BGR555). Se actualiza aproximadamente una vez por VBlank
(~60 Hz). Sin C, sin LLVM ni ensamblador externo para crear la ROM; el script
`build.py` contiene un codificador reducido de instrucciones ARM en Python para
preparar el MIR.

**Alcance exacto de la prueba:** el MIR externo carga la cabecera GBA con `::RIF_INSERT FILE`, emite palabras ARM little-endian con `fit_exact 32`, codifica `arm_mov_imm` desde una tabla de registros, usa la variante experimental `@ASMVARIANT thumb` para emitir `movs` y `bx lr` Thumb, y emite los **20 bytes de datos** que describen el contorno de la pelota mediante `byte`/`fit_exact 8`. El código realiza un interworking ARM→Thumb→ARM mediante `BX` reales.

Importante: las referencias a etiquetas, la selección de instrucciones y los branch offsets de ARM se calculan actualmente en `build.py` (Python), **no** directamente por RIF ni por el runtime de Variants. Por eso esto NO equivale a un ensamblador ARM7TDMI completo. `ENTER_thumb` y `EXIT_thumb` en el MIR son selectores declarativos; no cambian el estado de la CPU por sí mismos.

## Ejecutarlo en GBA

Abre `rif_ball.gba` en **mGBA** (https://mgba.io/downloads.html) o en otro emulador GBA. Si el emulador prefiere un archivo ROM más grande, utiliza `rif_ball_256k.gba`. Tras arrancar debería aparecer un fondo verde intenso con una pelota blanca de unos diez píxeles, moviéndose en diagonal y rebotando en los bordes. No necesita mandos ni archivos auxiliares.

**Advertencia de verificación:** no había un emulador GBA completo disponible en el entorno de construcción. La ROM se validó estructuralmente y se ejecutaron 300 fotogramas en un intérprete limitado escrito para esta prueba; **no** se ha confirmado todavía en mGBA ni en hardware original. Las imágenes `preview_simulated.png` y `preview_bouncing_simulated.gif` proceden de esa simulación, no de capturas de una consola.

## Recompilar con RIF

Necesitas tener RIF instalado con VNMA y Gram disponible según `vnma.toml`.
Desde la raíz del repositorio:

```powershell
vnma run examples/GBA-Bouncing-Ball/build.py main.py
```

El script genera `main.asm`, crea `gba.pack` mediante el backend AOT
predeterminado y produce `rif_ball.gba`. El pack contiene la cabecera GBA, la
gramática ARM y la variante Thumb.

Para verificar la ROM con el intérprete ARM7TDMI reducido:

```powershell
vnma run examples/GBA-Bouncing-Ball/verify_cpu.py
```

La ejecución en mGBA o hardware GBA requiere Linux/Windows con un emulador
compatible; el intérprete local no sustituye a mGBA.

## Benchmark Python/AOT

El benchmark de frontend procesa `main.rif` y carga la variante `thumb.rif`.
Sobre tres iteraciones, con el parser AOT cacheado, produjo:

| Métrica | Python | AOT |
|---|---:|---:|
| Entrada | 1.600 bytes / 365 tokens | 1.600 bytes / 426 nodos GIR |
| Lexer + parser / GIR + adaptación | 0,182061 s | 0,028504 s |
| Recepción de variante + semántica | 0,150703 s | 0,104176 s |
| Total | 0,332764 s | 0,132681 s |

El AOT reduce aproximadamente un **60%** el tiempo total. La semántica sigue
siendo Python; la mejora adicional proviene de recibir `thumb.rif` también con
el parser AOT reutilizado.

## Benchmark del frontend

El benchmark de RIF incluye este target y compara tres iteraciones de Python
contra AOT sobre `main.rif`, incluyendo la carga de `thumb.rif` y el
procesamiento semántico. Ejecuta:

```powershell
vnma test tests/test_frontend_benchmark.py
```

## Archivos

| Archivo | Papel |
|---|---|
| `main.rif` | Configuración 32-bit little-endian, tabla de registros ARM, reglas `arm32`, `byte`, `arm_mov_imm`, declaración de variante Thumb e insert del header |
| `thumb.rif` | Reglas `thumb_mov_imm`, `thumb_bx_lr`, `ENTER_thumb`, `EXIT_thumb` |
| `gba_header.bin` | 192 bytes del encabezado cartucho GBA compatible: logo exigido por el BIOS, nombre, código y checksum |
| `main.asm` | MIR generado localmente por `build.py`, incluyendo código ARM, Thumb, geometría y valores literales |
| `build.py` | Codificador ARM mínimo en Python, cálculo de saltos y direcciones, generación de MIR, compilación mediante RIF y verificación |
| `gba.pack` | Pack generado localmente con fuentes, asset y reglas |
| `rif_ball.gba` | ROM generada localmente por RIF |
| `rif_ball_256k.gba` | ROM opcional, rellena a 256 KiB con `FF` |
| `verify_cpu.py` | Intérprete reducido de instrucciones ARM/Thumb y memoria GBA para esta prueba; NO emulador GBA completo |
| `test_bounce.py` | Prueba del movimiento de 300 fotogramas, sin necesidad de hardware GBA |
| `preview_*.png/gif` | Previsualización generada a partir de la VRAM simulada |

## Resultados comprobados

- Cabecera GBA: branch a offset `0xC0`, 156 bytes de logo, campo fijo `0x96` y complemento de control válido.
- Todas las palabras de instrucción ARM emitidas por RIF coinciden byte por byte con el codificador reducido; Thumb y los datos también coinciden.
- Construcción de `.pack` y generación de la ROM **sin errores**.
- El pack funciona sin archivos fuente externos, probado en directorio temporal.
- Intérprete ARM7TDMI mínimo: 300 fotogramas, más de 3.600.000 instrucciones ejecutadas, cambios de signo en ambas velocidades y bola dentro de límites `x=0..230`, `y=0..150`, con 76 píxeles blancos y 38.324 verdes.

## Próximos pasos útiles para RIF

1. Resolver etiquetas y referencias PC-relative mediante reservas, `::RIF_PATCH` y enlaces nativos de RIF, sin calcularlas en Python.
2. Despacho de reglas según la variante ARM/Thumb activa, sin nombres globales compartidos.
3. Garantizar que las reglas de datos y las instrucciones pueden coexistir sin colisiones entre variantes.
4. Prueba real en mGBA o consola GBA para validar VBlank, interworking y acceso al VRAM frente a un emulador completo.

Esta demo no altera Gram, VNMA ni el código del motor RIF.
