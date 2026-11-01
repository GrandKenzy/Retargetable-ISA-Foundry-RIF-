# Mapa del proyecto

Guía de orientación, no sustituto del código. Consulta solo las secciones
relevantes y verifica el comportamiento en los archivos y pruebas. Actualiza
este mapa cuando cambien responsabilidades o conexiones principales.

## Flujo de compilación

`rif.py` recibe una definición `.rif` o `.pack` y delega en `MIR/pipeline.py`.
El pipeline tokeniza con Gram, procesa los nodos mediante
`Frontend/processor/`, captura el estado en `Frontend/globals.py`, resuelve
Rules y construye un `CompiledRuleSet`. El runtime `MIR/runtime.py` ejecuta
las Rules sobre `BitBuffer`/`BitEmitter`; `MIR/output.py` y `MIR/artifacts.py`
construyen imágenes, inserts y parches finales.

Para PCP-I, `rif.py --comp-pcpi` usa `pcpi_compiler.py`: compila una fuente
`.pci` directamente y serializa el contenedor validado con `pcpi.py`. PCP-I es
una salida especializada e independiente del frontend RIF; no ejecuta Rules
ni añade una segunda gramática al lenguaje `.rif`.

## Bloques genéricos

La única sintaxis de bloques es:

```rif
@block nombre:
    campo valor "opcional"
@end
```

`Frontend/syntax/items/blocks.py` conserva el cuerpo sin imponer semántica.
`Frontend/processor/visitors/block.py` normaliza cada línea a
`BlockEntryData` con cero, uno o dos valores y registra `BlockData` en el
contexto. `config` y `linker` se materializan directamente desde sus visitors;
otros nombres se preservan en `TargetContext.blocks` para consumidores
especializados. No se mantienen `@config`, `@linker`, terminadores dedicados,
ni prefijos de punto como aliases.

El bloque `config` usa la forma compacta `format`, `section`, `entry`,
`default`, `align`, `vaddr`, `word_size`, `address_size`, `byte_order` y
`bit_order`. Los flags viven en la propia línea `section`; las políticas
secundarias tienen defaults y los nombres anteriores no se aceptan como
aliases.

El bloque `linker` acepta únicamente `extension` y `search_path`. El antiguo
`name` se retiró porque no participaba en la resolución de archivos.
`search_path` puede repetirse y se prueba en orden; `false` desactiva la carga
de variantes y no se combina con carpetas. Los contextos compilados usan el
esquema SQLite 5 para reflejar ese contrato.

Las tablas se materializan como matrices de tuplas inmutables. `TableData`
preconstruye índices tipados para todas las columnas y solo exige unicidad
cuando una operación usa una columna como selector; el `TargetContext` expone
el mapa de tablas como solo lectura.

`main.rif` es el centro de control. Solo la fuente raíz puede materializar
`config` y `linker`; opcionalmente puede cargar directamente un `config.rif`
dedicado, que solo contiene esos dos bloques. Los includes no pueden cargarlo
y los bloques de configuración duplicados se rechazan.

Las instrucciones de una Rule usan un marcador `.` al inicio de cada línea
(`. bits 8 8`); el marcador `->` fue retirado de la sintaxis.

Las operaciones binarias usan los nombres canónicos `nibbles`, `emit`,
`eword`, `bits`, `frame`, `fit`, `fit_exact`, `pad`, `align`, `vpad`,
`valign`, `write_res`, `emit_res`, `read_bits`, `patch_bits`, `fit_not` y
`drop_res`. `reserve` y `vreserve` conservan sus nombres porque no recibieron
un reemplazo en esta revisión.

`mark` define un símbolo nativo en la posición actual sin consumir el token.
`RIFMachine.symbols` conserva sus offsets físico/virtual relativos y
`MIRCompilation.symbols` los expone como direcciones virtuales absolutas tras
el layout. Su matcher fijo usa `MatchSeqSymbol`, que forma parte del
subconjunto C/AOT de Gram. `fixup pc8|pc32|abs64 "reserva"` registra una
relocación diferida contra el símbolo actual; `MIR/external.py` la resuelve de
forma transaccional después de ejecutar todas las líneas MIR y antes de los
parches finales.

Los controles de Rule usan `JUMP`, `JUMPIF`, `BREAK`, `ERROR`, `save`, `load`,
`dpush`, `dget`, `dpop`, `dpeek` y `ddepth`. La instrucción `CALL` fue retirada;
`#call[...]` queda reservado para funciones nativas cerradas.

## Directorios y archivos

- `rif.py`: CLI para compilar definiciones, ejecutar MIR, producir PCP-I y
  revisar artefactos con `--doctor-pcpi`/`--doctor-storage`.
- `Frontend/syntax/`: sesión Gram, keywords y reglas de entrada; `blocks.py`
  contiene el bloque genérico.
- `Frontend/processor/`: orden de pasadas y visitors para config, linker,
  tablas, Rules, variantes, inserts y bloques.
- `Frontend/globals.py`: dataclasses y estado temporal de frontend; el estado
  se copia a `TargetContext` para que programas compilados sean independientes.
- `MIR/pipeline.py`: reseteo de contexto, parseo, procesamiento y compilación.
  `MIR/compiled.py` serializa contextos y programas en bases SQLite de packs.
- `MIR/runtime.py`, `MIR/emitter.py`, `MIR/bitbuffer.py` y `MIR/output.py`:
  ejecución de Rules, emisión bit a bit, símbolos, relocaciones nativas y
  layout de secciones.
- `MIR/functions/`: funciones nativas con contratos compatibles con C;
  `calc.py` contiene la aritmética de `#:calc` y `reqsts.py` descarga bytes
  `.bin` desde rutas GitHub validadas.
- `plugins/`: conversiones locales previas a la compilación. `image.py`
  produce bytes RGBA8888 y `audio.py` produce bytes PCM_S16LE desde WAV, FLAC
  u OGG; ambos rechazan URLs y bytes en memoria. Todo plugin debe devolver
  exclusivamente `bytes`; no se incluye conversión de vídeo.
- `MIR/storage.py`: contenedor `RIFSTOR` versionado para payloads de plugins;
  guarda el raw y un índice de entradas con dirección relativa `u64`, tamaño
  `u64`, padding `u32` y tamaño de label `u32`; los bytes UTF-8 del label viven
  junto al payload dentro del raw. Se genera
  desde fuentes independientes `.store`, no desde el flujo `.rif`. Su cargador
  seguro alimenta `rif --doctor-storage`.
- `store.py`: parser y compilador de fuentes `.store`; valida `MAGIC`,
  `VERSION`, bloques `@ITEM IMAGE`/`@ITEM AUDIO`, rutas locales y labels.
- `MIR/external.py`: consumo de entradas MIR externas y validación del linker.
- `MIR/preprocessor.py`: reconoce directivas cerradas de metaprogramación
  (`::RIF_PCPI` y `::RIF_STORE`) antes del despacho de Rules; `RIF_PCPI SET`
  inserta contenedores `.pcic` y `RIF_PCPI PIT` calcula offsets absolutos,
  mientras `RIF_STORE` valida `ENDIANNESS`/`BITORDER`, extrae payloads raw
  etiquetados y los inserta en la sección actual.
- `pcpi.py` y `pcpi_compiler.py`: formato PCP-I v1, parser declarativo de
  fuentes `.pci` y compilación de pits alineados.
- `pack.py`: creación y lectura segura de paquetes `.pack`.
- `tests/`: pruebas rápidas de parser, semántica, runtime, packs y PCP-I.
  `examples/`: targets AMD64, ELF64 y GBA que documentan usos completos.
- `docs/en/` y `docs/es/`: documentación del lenguaje, compilación y memoria.
  `changelog/`: notas versionadas de cambios importantes.

## Dónde empezar según el cambio

| Área | Código principal | Pruebas relacionadas |
| --- | --- | --- |
| Sintaxis de bloques | `Frontend/syntax/items/blocks.py`, `Frontend/syntax/__init__.py` | `tests/test_blocks.py`, `tests/test_declarations.py` |
| Semántica config/linker | `Frontend/processor/visitors/config.py`, `linker.py` | `tests/test_processor.py`, `tests/test_pipeline.py`, `tests/test_variants.py` |
| Reglas y valores | `Frontend/syntax/items/declarations.py`, `Frontend/processor/visitors/rule.py`, `MIR/` | `tests/test_runtime.py`, `tests/test_mir.py` |
| Packs y serialización | `pack.py`, `MIR/compiled.py` | `tests/test_pack.py`, `tests/test_blocks.py` |
| PCP-I | `pcpi.py`, `pcpi_compiler.py`, `rif.py` | `tests/test_pcpi.py` |
| Diagnóstico de artefactos | `rif.py`, `pcpi.py`, `MIR/storage.py` | `tests/test_doctor.py` |
| Inserts y parches | `Frontend/processor/visitors/artifacts.py`, `MIR/artifacts.py` | `tests/test_artifacts.py` |

El preprocesador del MIR externo usa `::RIF_INSERT` para bytes, binarios o
archivos y `::RIF_PATCH` para correcciones finales. Sus expresiones tienen un
despacho nativo cerrado (`#:query`, `#:qssize`, `#:qlsize`, `#:qvsize`,
`#:qvssize` y `#:calc`); no ejecutan callbacks `#call[...]`.

`@block buffer` es una fase externa de adquisición. Declara una capacidad fija
en KiB y permite `clean`, `call reqsts ".../archivo.bin/branch"` y
`extract inicio fin` con rango `[inicio, fin)`. No se ejecuta dentro de una
Rule ni durante el parseo de `.rif`; su resultado queda disponible durante la
compilación MIR externa.
Sus fallos se publican mediante `gram.utilities.Diagnostics` en la consola y
después se propagan como error de compilación. `DiagnosticsLite` queda
reservado para el lexer/parser AOT en C.

Una característica puede cruzar gramática, semántica, contexto serializado y
backend. Sigue ese recorrido antes de modificar una sola capa.

## Herramientas y pruebas

- `vnma run rif.py ...` ejecuta la CLI del proyecto.
- `vnma test` ejecuta la suite rápida; `vnma test tests/<archivo>` permite una
  comprobación enfocada.
- Los `.pack`, binarios y logs generados no son puntos de partida para cambios
  de código. Conserva `.vscode/` y cualquier artefacto local no relacionado.

### Baseline del frontend Python

El benchmark `tests/test_frontend_benchmark.py` procesa `main.rif` completo y
mide lexing, parsing y procesamiento semántico por separado. Baseline del 31
de octubre de 2026, con Gram 3.0.0 y tres iteraciones promedio:

| Métrica | Resultado |
| --- | ---: |
| Bytes de entrada | 1.649 |
| Tokens sin `EOF` | 412 |
| Lexing | 0,012409 s |
| Parsing | 0,081186 s |
| Procesamiento | 0,002650 s |
| Total | 0,096245 s |

Este registro es la referencia antes de migrar el frontend a AOT/C; no es un
umbral de aceptación de las pruebas.

### Frontera AOT

`Frontend/aot.py` es el puente experimental al backend C/AOT de Gram. Exporta
la gramática declarativa de RIF, compila el parser nativo con GCC o Clang y
lee su salida GIR mediante el lector oficial `gram.ir.load_gir`. La
exportación actual contiene 38 Rules y ya procesa `main.rif` completo en C.

El GIR es todavía una frontera de representación: `AOTParser` entrega nodos
GIR, pero la semántica de RIF continúa en Python. `GIRAdapter` ya traduce los
terminales, arrays, bloques raw y reglas al AST que consumen los visitors;
además recompone las instrucciones que el emisor C aplana dentro de `RULE`.
Los terminales normales y los tokens de `CaptureRaw` se obtienen mediante la
API de Gram; RIF ya no re-tokeniza la fuente con el lexer Python.

El pipeline expone `backend="python"` y `backend="aot"`; la CLI selecciona
el segundo con `rif.py --backend aot`. El parser generado se guarda bajo
`.rif-cache/aot/`; AOT es ahora el backend predeterminado. El ejecutable AOT
vive en el cache persistente de RIF y su construcción se serializa con un
lock entre procesos. Cada fuente usa un GIR temporal y único bajo su propio
`.rif-cache/gir/`, que se elimina después de cargarlo en memoria. RIF
reutiliza el ejecutable cuando coinciden los hashes de Gram, del lexer nativo y
del compilador. Python se conserva como ruta explícita de comparación mediante
`--backend python`; los `.pack` fuente-only usan ese backend porque sus rutas
`pack://` no pueden entrar al CLI nativo.
La prueba `tests/test_aot.py` verifica compilación nativa, lectura de GIR y
procesamiento semántico de `main.rif`, sin alterar el camino predeterminado.
También compara el AST normalizado y el `TargetContext` resultante contra el
backend Python, incluyendo los opcodes de las Rules.

El benchmark AOT de `tests/test_frontend_benchmark.py` se ejecutó el 31 de
octubre de 2026 sobre tres iteraciones. La compilación inicial se mide aparte;
el tamaño AOT cuenta los saltos de línea físicos y el baseline Python usa el
texto normalizado por `read_text()`.

| Métrica AOT | Resultado |
| --- | ---: |
| Bytes físicos de entrada | 1.744 |
| Nodos GIR | 269 |
| Comprobación de construcción cacheada | 0,081033 s |
| Cache hit de construcción | 0,081505 s |
| Parseo nativo + lectura GIR | 0,022974 s |
| Adaptación GIR→AST | 0,020626 s |
| Procesamiento semántico Python | 0,002013 s |
| Total cálido | 0,045613 s |
| Total con compilador cacheado | 0,126646 s |

La medición anterior de primera generación sin cache fue de 7,175775 s; ya no
forma parte del camino normal.

### Benchmark del target AMD64 amplio

El benchmark también procesa `examples/AMD64-Linux-v3/main.rif`, incluyendo
sus nueve archivos `@LOAD`, tablas de registros, reglas REX/ModRM/SIB,
memoria, condiciones y relocaciones. Se ejecutaron tres iteraciones con el
parser AOT ya cacheado:

| Métrica | Python | AOT |
| --- | ---: | ---: |
| Entrada | 1.894 bytes / 252 tokens | 1.894 bytes / 86 nodos GIR |
| Lexer + parser / GIR + adaptación | 0,036330 s | 0,025539 s |
| Recepción de incluidos + semántica | 6,392521 s | 0,623583 s |
| Total | 6,428852 s | 0,649122 s |

En este target AOT reduce el total aproximadamente 87,7%. La semántica sigue
en Python; la mejora restante proviene de que los nueve `@LOAD` ya no vuelven
a tokenizarse y parsearse con Python, sino que reutilizan el parser AOT.

El ejemplo `examples/GBA-Bouncing-Ball/main.rif` también se midió con su
variante `thumb.rif` activa:

| Métrica | Python | AOT |
| --- | ---: | ---: |
| Lexer + parser / GIR + adaptación | 0,256243 s | 0,034425 s |
| Recepción de variante + semántica | 0,196038 s | 0,104822 s |
| Total | 0,452281 s | 0,139247 s |

El frontend AOT reduce el total de este target GBA aproximadamente 60%; la
semántica permanece en Python y la diferencia restante corresponde a la
recepción de `thumb.rif`.

La ruta AOT ya está activada como predeterminada; queda mantener la paridad
de diagnósticos y ampliar la cobertura de fixtures conforme evolucione Gram.
