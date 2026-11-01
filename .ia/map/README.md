# Mapa del proyecto

Guía de orientación, no sustituto del código. Consulta solo las secciones
relevantes y verifica el comportamiento en los archivos y pruebas. Actualiza
este mapa cuando cambien responsabilidades o conexiones principales.

## Flujo de compilación

RIF trabaja en dos fases y requiere dos artefactos conceptualmente distintos:

1. La definición declarativa `.rif` describe el target: tablas, Rules,
   configuración, linker y variantes. `main.py --pack main.rif` la procesa a un
   `CompiledRuleSet`; el `.pack` agrupa las fuentes y, con `precompile=True`,
   serializa ese Rule Set, sus tablas y contexto en SQLite. El `.pack` no
   contiene el MIR externo ni el binario final.
2. El programa `.mir` es la entrada compatible con ese target. `main.py
   target.pack program.mir -o program.bin` carga el `.pack`, tokeniza y
   preprocesa el MIR, selecciona la Rule cuyo nombre inicia cada línea y la
   ejecuta para emitir bits, layout, símbolos, relocaciones y el binario. La
   ruta `.rif + .mir` es la equivalente de desarrollo; `.pack + .mir` es la
   ruta distribuible y rápida.

`MIR/pipeline.py` resuelve la primera fase para `.rif` o `.pack`; el runtime
`MIR/runtime.py` ejecuta las Rules sobre `BitBuffer`/`BitEmitter`; y
`MIR/external.py` posee la segunda fase, incluyendo preprocesador, secciones,
fixups, parches e imagen final. El MIR externo no es el `CompiledRuleSet`.

La composición entre targets usa una frontera explícita: `@LIBRARY` consume
`.riflib` con declaraciones reutilizables (`@define`, tablas y Rules). La CLI
puede exportar a esa forma la gráfica de declaraciones cargada por un `.pack`
con `--library target.pack`; no arrastra `config`, `linker` ni bloques del
target original. Un `.pack` sigue siendo un target completo y no se fusiona
implícitamente con otro.

Para PCP-I, `main.py --comp-pcpi` usa `rif_tools/pcpi_compiler.py`: compila una fuente
`.pci` directamente y serializa el contenedor validado con `rif_tools/pcpi.py`. PCP-I es
una salida especializada e independiente del frontend RIF; no ejecuta Rules
ni añade una segunda gramática al lenguaje `.rif`. En `@RAW`, `[N]` declara
un pit alineado y `ZERO N` emite ceros estáticos sin crear un pit. El
preprocesador MIR acepta `::RIF_PCPI FILL index "hex"` después de `SET` para
reemplazar cada pit con tamaño exacto y de forma transaccional; `PIT` sigue
siendo una consulta de dirección, no un relleno.

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
esquema SQLite 7 para reflejar ese contrato y almacenan además la huella de la
combinación RIF/Gram/GIR/AOT/runtime.

Las tablas son totalmente extensibles y no están limitadas a registros,
opcodes o arquitecturas concretas. Un target puede declarar tantas tablas como
necesite, con las columnas y tipos de datos que requiera. Se materializan como
matrices de tuplas inmutables. `TableData` preconstruye índices tipados para
todas las columnas y solo exige unicidad cuando una operación usa una columna
como selector; el `TargetContext` expone el mapa de tablas como solo lectura.

`main.rif` es el centro de control. Solo la fuente raíz puede materializar
`config` y `linker`; opcionalmente puede cargar directamente un `config.rif`
dedicado, que solo contiene esos dos bloques. Los includes no pueden cargarlo
y los bloques de configuración duplicados se rechazan.

Las instrucciones de una Rule usan un marcador `.` al inicio de cada línea
(`. bits 8 8`); el marcador `->` fue retirado de la sintaxis.

Las operaciones binarias usan los nombres canónicos `nibbles`, `emit`,
`eword`, `bits`, `frame`, `fit`, `fit_exact`, `pad`, `align`, `vpad`,
`valign`, `write_res`, `emit_res`, `read_bits`, `patch_bits`, `fit_not`,
`fit_signed`, `fit_signed_exact`, `fit_signed_not` y `drop_res`. `reserve` y
`vreserve` conservan sus nombres porque no recibieron un reemplazo en esta
revisión.

`mark` define un símbolo nativo en la posición actual sin consumir el token.
`RIFMachine.symbols` conserva sus offsets físico/virtual relativos y
`MIRCompilation.symbols` los expone como direcciones virtuales absolutas tras
el layout. Su matcher fijo usa `MatchSeqSymbol`, que forma parte del
subconjunto C/AOT de Gram. La directiva MIR `::RIF_SECTION nombre` cambia el
emisor activo dentro de una `AssemblyImage`. `fixup pc8|pc32|abs64 "reserva"` registra una
relocación diferida contra el símbolo actual; el núcleo incluye anchos
`pc8|pc16|pc32|pc64` y `abs8|abs16|abs32|abs64`, y los targets pueden añadir
clases `pc`/`abs` en `@block relocations`. `MIR/external.py` las resuelve de
forma transaccional después de ejecutar todas las líneas MIR y antes de los
parches finales.

Las Rules y las imágenes usan checkpoints físicos y virtuales. Un fallo
restaura buffers, reservas, cursores virtuales, símbolos, fixups, datastack y
sección activa. El layout conserva por separado `file_size` y `virtual_size`,
expone el espacio no inicializado y rechaza solapes virtuales.

Los errores se normalizan mediante `MIR/diagnostics.py`: frontend, Rules, MIR,
layout y fixups comparten fase, ubicación, Rule, sección y token cuando esos
datos existen.

Los controles de Rule usan `JUMP`, `JUMPIF`, `BREAK`, `ERROR`, `save`, `load`,
`dpush`, `dget`, `dpop`, `dpeek` y `ddepth`. La instrucción `CALL` fue retirada;
`#call[...]` queda reservado para funciones nativas cerradas.

## Directorios y archivos

- `main.py`: CLI para empaquetar definiciones, ejecutar MIR compatible, producir PCP-I y
  revisar artefactos con `--doctor-pcpi`/`--doctor-storage`.
- `rif_tools/cli.py`: implementación del despacho de todas las operaciones de la CLI;
  `main.py` es la única entrada pública. Los módulos `rif_core/pack.py`,
  `rif_tools/pack_inspector.py`, `rif_tools/pcpi.py`, `rif_tools/pcpi_compiler.py`,
  `rif_core/contract.py`, `rif_core/library.py`, `rif_core/limits.py`, `rif_tools/store.py` e `rif_tools/iso.py` son
  bibliotecas de implementación, no entradas CLI independientes.
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
  seguro alimenta `main.py --doctor-storage`.
- `rif_tools/store.py`: parser y compilador de fuentes `.store`; valida `MAGIC`,
  `VERSION`, bloques `@ITEM IMAGE`/`@ITEM AUDIO`, rutas locales y labels.
- `MIR/external.py`: consumo de entradas MIR externas y validación del linker.
- `MIR/preprocessor.py`: reconoce directivas cerradas de metaprogramación
  (`::RIF_PCPI` y `::RIF_STORE`) antes del despacho de Rules; `RIF_PCPI SET`
  materializa `PADDING + RAW + RPAD` sin el header ni la tabla `.pcic`,
  `RIF_PCPI FILL` resuelve todos los pits y `RIF_PCPI PIT` calcula offsets absolutos,
  mientras `RIF_STORE` valida `ENDIANNESS`/`BITORDER`, extrae payloads raw
  etiquetados y los inserta en la sección actual.
- `foot/`: material temporal resumido y machine-readable usado para alimentar
  y verificar los ejemplos de `examples/`; no es una dependencia del núcleo ni
  un artefacto final. Las fuentes completas de Intel y NASM permanecen
  enlazadas, no vendorizadas.
- `rif_tools/pcpi.py` y `rif_tools/pcpi_compiler.py`: formato PCP-I v1, parser declarativo de
  fuentes `.pci` y compilación de pits alineados.
- `rif_tools/iso.py`: productor determinista ISO-9660/El Torito. Consume el boot image
  emitido por RIF y una plantilla PCP-I validada, completa los campos de layout,
  genera tablas de ruta/directorio y valida el contrato BIOS sin introducir
  semántica ISO en el parser o runtime de RIF.
- `rif_core/pack.py`: creación y lectura segura de paquetes `.pack`.
- `rif_core/library.py`: creación, exportación desde `.pack` y lectura segura de
  librerías `.riflib` de declaraciones reutilizables.
- `rif_tools/pack_inspector.py`: inspección de solo lectura de `.pack`; verifica el
  contenedor y SQLite en memoria, y expone Rules, tablas, configuración,
  linker, variantes, fingerprint, versión y extensiones MIR sin ejecutar el
  target. `main.py --inspect-pack` ofrece salida humana o JSON acotada.
- `tests/suite_essencial/`: pruebas fundamentales de parser, semántica, MIR,
  runtime y empaquetado; se ejecuta en cada cambio.
- `tests/suite_aggressive/`: benchmarks y pruebas de estrés; se ejecuta de forma
  explícita cuando el cambio afecta rendimiento, volumen o límites.
- `tests/dedicated_suite/`: pruebas específicas de AOT, formatos, CLI, plugins,
  hardening e integraciones que pueden requerir adaptación ante cambios de API.
- `tests/`: contiene el lanzador de `vnma test` y todas las suites organizadas
  por nivel.
  `examples/`: targets y demostraciones completas, incluyendo el demo
  agnóstico `RIF-Core-Demo`, `amd64-friendlysyntaxs` y sus probes QEMU,
  AMD64 bare metal, ELF64 y GBA. Los ejemplos ELF64 y MiniOS viven bajo
  `examples/probe/`. El target
  `AMD64_Baremetal` emite imágenes raw y no asume un sistema operativo,
  formato de objeto ni ABI externo. Los `.rif` de ejemplo no viven en la raíz
  del repositorio. Sus programas MIR externos y fixtures están en
  `examples/probe/probe_amd64/`; el target conserva la definición `.rif`, las
pruebas y los paquetes compilados. `profile.rif` concentra las cargas comunes
de `main.rif` y `main_rw.rif`; ambos conservan solo su configuración raíz y el
alineamiento diferencial de `data`. Los programas MIR del target base Friendly
  Syntax están en `examples/probe/probe_friendlysyntax/`; el target QEMU
  completo y sus probes están en `examples/probe/probe_friendlysyntax_qemu/`.

El perfil `AMD64_Baremetal` mantiene sus decisiones de ISA fuera del núcleo:
`registers.rif` concentra los datos canónicos por familia; `integer.rif` y
`prefixes.rif` reutilizan esas columnas para BSWAP y direcciones de 32 bits,
mientras `shiftcl` conserva una tabla restringida a CL. `main.rif` conserva un
bloque `isa_scope` que excluye MMX, SSE, AVX, AVX-512, x87 y system
instructions. Sus pruebas raw y el cross-check LLVM viven junto al target; no
son capacidades generales de RIF.
- `docs/en/` y `docs/es/`: documentación del lenguaje, compilación y memoria.
  `changelog/`: notas versionadas de cambios importantes.

## Dónde empezar según el cambio

| Área | Código principal | Pruebas relacionadas |
| --- | --- | --- |
| Sintaxis de bloques | `Frontend/syntax/items/blocks.py`, `Frontend/syntax/__init__.py` | `tests/suite_essencial/test_blocks.py`, `tests/suite_essencial/test_declarations.py` |
| Semántica config/linker | `Frontend/processor/visitors/config.py`, `linker.py` | `tests/suite_essencial/test_processor.py`, `tests/suite_essencial/test_pipeline.py`, `tests/suite_essencial/test_variants.py` |
| Reglas y valores | `Frontend/syntax/items/declarations.py`, `Frontend/processor/visitors/rule.py`, `MIR/` | `tests/suite_essencial/test_runtime.py`, `tests/suite_essencial/test_mir.py` |
| Packs y serialización | `rif_core/pack.py`, `MIR/compiled.py` | `tests/suite_essencial/test_pack.py`, `tests/suite_essencial/test_blocks.py` |
| PCP-I | `rif_tools/pcpi.py`, `rif_tools/pcpi_compiler.py`, `main.py` | `tests/dedicated_suite/test_pcpi.py` |
| Diagnóstico de artefactos | `main.py`, `rif_tools/pcpi.py`, `MIR/storage.py` | `tests/dedicated_suite/test_doctor.py` |
| Inserts y parches | `Frontend/processor/visitors/artifacts.py`, `MIR/artifacts.py` | `tests/suite_essencial/test_artifacts.py` |

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

- `vnma run main.py ...` ejecuta la CLI del proyecto.
- `vnma test` ejecuta la suite esencial; `vnma test tests/suite_essencial/<archivo>`
  permite una comprobación enfocada.
- `vnma test tests/suite_aggressive` ejecuta benchmarks y estrés.
- `vnma test tests/dedicated_suite` ejecuta las pruebas específicas e integraciones.
- Los `.pack`, binarios y logs generados no son puntos de partida para cambios
  de código. Conserva `.vscode/` y cualquier artefacto local no relacionado.

### Baseline del frontend Python

El benchmark `tests/suite_aggressive/test_frontend_benchmark.py` procesa `main.rif` completo y
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

`Frontend/aot.py` es el puente al backend C/AOT de Gram. Exporta
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
el segundo con `main.py --backend aot`. El parser generado se guarda bajo
`.rif-cache/aot/`; AOT es ahora el backend predeterminado. La FFI AOT en
memoria es el camino canónico: la biblioteca compartida vive en ese cache, su
construcción se serializa con un lock entre procesos y
`gram_compile_source_to_ir` entrega GIR que se copia y adapta sin crear
archivos `.gir` temporales. Python se conserva como ruta explícita de
comparación mediante `--backend python`; los `.pack` fuente-only también
pueden usar AOT porque sus bytes entran directamente por la misma FFI.

El cache AOT guarda formato, modo, huella del contrato, Gram/GIR, ABI del
parser C, fuentes nativas y compilador. El contrato compartido en
`rif_core/contract.py` también se serializa en el manifiesto `.pack` (formato 7) y
en SQLite compilado (esquema 7); `read_pack` y `load_database` rechazan
artefactos de otra combinación de RIF, Gram, AOT, MIR o runtime.

La huella del contrato incluye las fuentes Python de producción bajo `Frontend/`
y `MIR/`, además de los módulos raíz que participan en compilación, empaquetado
y runtime. Cambiar el compilador invalida los artefactos derivados aunque las
fuentes `.rif` permanezcan iguales.
La prueba `tests/dedicated_suite/test_aot.py` verifica compilación nativa, lectura de GIR y
procesamiento semántico de `main.rif`, sin alterar el camino predeterminado.
También compara el AST normalizado y el `TargetContext` resultante contra el
backend Python, incluyendo los opcodes de las Rules.

El benchmark AOT de `tests/suite_aggressive/test_frontend_benchmark.py` se ejecutó el 31 de
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

El benchmark también procesa `examples/AMD64_Baremetal/main.rif`, incluyendo
sus quince archivos `@LOAD`, tablas de registros, reglas REX/ModRM/SIB,
memoria, condiciones, enteros, prefijos y relocaciones. Se ejecutaron tres iteraciones con el
parser AOT ya cacheado:

| Métrica | Python | AOT |
| --- | ---: | ---: |
| Entrada | 1.092 bytes / 126 tokens | 1.137 bytes / 72 nodos GIR |
| Lexer + parser / GIR + adaptación | 0,026598 s | 0,027903 s |
| Recepción de incluidos + semántica | 10,235511 s | 0,956841 s |
| Total | 10,262110 s | 0,984744 s |

En este target AOT reduce el total aproximadamente 87,7% en la medición
anterior; la semántica sigue
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

La ruta AOT ya está activada como predeterminada; queda ampliar la cobertura
de diagnósticos y fixtures conforme evolucione Gram.

`Frontend.parity.compare_target()` compara un target físico con ambos
frontends y verifica AST, Rules y `TargetContext`, incluyendo tablas y cargas.
`MIRCompilation.output_map()` y la opción `main.py --map mapa.json` producen un
mapa opcional del binario final con secciones, símbolos, trazas de Rules y
relocaciones resueltas. `rif_tools.target_scaffold` genera la plantilla
reutilizable de pruebas válidas, límites, símbolos y errores para un target.

### Librerías, oráculos y operaciones AOT

`rif_core/library.py` define el formato `.riflib`: un ZIP reproducible de fuentes
`.rif` con manifiesto, índice de `@LOAD`, límites y huella. La directiva
canónica `@LIBRARY "patrones.riflib"` procesa sus declaraciones en el mismo
contexto de tablas, defines y Rules del target. `create_library()` crea el
paquete; `create_pack()` incluye las librerías referenciadas bajo `libraries/`
y `PackReader` las sirve sin extraerlas al filesystem. Una librería no crea un
ISA ni un registro rígido: solo reutiliza declaraciones extensibles.

`rif_tools.oracles` integra NASM y LLVM MC como oráculos opcionales. Cada
proceso tiene timeout y límite de salida; su ausencia produce un skip/estado
explícito y nunca vuelve obligatoria la dependencia. `rif_tools.properties`
ofrece fuzzing determinista por seed para operandos y primitivas.

`MIR.operations` es la frontera C/AOT para operaciones puras dentro de Rules.
`operation_abi()`/`operation_abi_json()` describen la tabla cerrada y
`operation_c_header()` y `operation_c_source()` devuelven las firmas e
implementación C portables. La ABI actual es `1.1` y cubre fit unsigned, fit
signed y encoding de relocaciones. `rif_op_encode_relocation` usa `uint64_t`
como transporte: los relativos se interpretan como patrones signed en
complemento a dos y los absolutos conservan el dominio completo de 64 bits.
El runtime Python usa esas mismas primitivas; no se serializan callbacks
Python en `.pack`.

Los targets AMD64 que declaran `entry text "_start"` también deben exponer una
Rule `_start` con `. mark` antes de consumir el identificador. La configuración
declara el entrypoint, mientras `mark` materializa el símbolo nativo que llega
al mapa de salida y a las relocaciones.

### MiniOS probe

`examples/probe/probe_minios/` es el primer sistema operativo AMD64 arrancable.
`mini_os_iso_header.pci` usa PCP-I para declarar el área de sistema, los cuatro
sectores de cabecera ISO/El Torito y tres pits para volumen, raíz y entrada de
boot. `ZERO n` representa bytes estáticos cero y no crea un pit; `[n]` sigue
siendo exclusivamente una región rellenable. El target QEMU emite el boot
image con RIF y `rif_tools/iso.py` ensambla la ISO-9660 final con tablas de ruta,
directorio raíz y `README.TXT;1`. `build_qemu_iso.py` es el recorrido canónico
y deja `build/mini_os.iso`, que QEMU BIOS arranca en LBA 20.
`cursor_assets.store` demuestra la ruta de media externa y produce un
`storage.bin` indexado con los cursores RGBA y BGRX etiquetados. El boot stage
de la variante QEMU selecciona VBE 0x118, sondea el mouse PS/2 y redibuja el
cursor dentro de 640x480 sobre fondo negro; no requiere construir un kernel.

### Friendly Syntax QEMU

`examples/amd64-friendlysyntaxs/` es deliberadamente independiente de QEMU:
no declara framebuffer, registros Bochs VBE ni un contrato de dispositivo. La
variante conserva ahora el perfil completo de `AMD64_Baremetal` mediante los
módulos `amd64_*.rif` y añade la capa de aliases Friendly en
`friendly_registers.rif`/`friendly_rules.rif`; sus pruebas raw completas
reutilizan los probes de `probe_amd64`. La
variante `examples/probe/probe_friendlysyntax_qemu/` consume la capa Friendly desde
`friendly.riflib` y añade `@LOAD "qemu/framebuffer.rif"` y sus Rules de boot,
además del bloque raíz `framebuffer`. La tabla `framebuffer_registers` y el bloque describen metadata
extensible para las Rules de boot de QEMU std VGA/Bochs VBE a 640×480×32,
`BGRX8888`, puertos índice/datos y PCI BAR0; no inicializan el dispositivo ni
añaden código protected/long mode a PCP-I. La variante ya tiene un primer
checkpoint de boot emitido por la Rule `boot_stage_mouse`: modo VBE `0x118` con
ventana bancaria `A000:0000`, cursor `BGRX8888` desde `RIF_STORE` y sondeo de
mouse PS/2 con límites de pantalla. El código sigue en real mode; PCI BAR0,
LFB, kernel y long mode quedan fuera del alcance de este ejemplo.
