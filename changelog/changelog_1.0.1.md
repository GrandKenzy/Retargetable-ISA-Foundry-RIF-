# RIF 1.0.1 · Security hardening and resource controls

## Correctness patches

- AMD64 displacement, branch, condition-code and signed-immediate Rules now use
  exact signed fitting. Negative values remain valid, while values outside the
  declared field range are rejected instead of being truncated.
- Friendly AMD64 `set`, `increase`, `load` and `store` now reject overflowing
  immediates and displacements.
- Configured `_start` entry Rules in the AMD64 examples call the native
  `mark` primitive, so the entry is present in the symbol map rather than only
  in target metadata.
- The Rule-operation C ABI is version `1.1`; relocation transport uses
  `uint64_t`, preserving the complete absolute 64-bit address domain while
  retaining signed relative values as two's-complement bit patterns.

## MiniOS asset checkpoint

- Completed the MiniOS QEMU artifact: `build_qemu_iso.py` now compiles the
  PCP-I/storage inputs, packages and runs the QEMU Friendly target through
  RIF, then uses the deterministic `rif_tools/iso.py` producer to create a valid
  ISO-9660/El Torito volume with path tables, a root directory and
  `README.TXT;1`. The final image is structurally validated and boots under
  QEMU 11 BIOS; the RIF boot checkpoint is a real-mode VBE/PS/2-mouse cursor
  stage, without a full kernel.

- Added `examples/probe/probe_minios/` with a PCP-I ISO/El Torito descriptor
  template, a
  public-domain 14x22 arrow cursor source, and a `.store` manifest compiled to
  an indexed `storage.bin` payload. The example documents the QEMU BIOS launch
  contract and clearly distinguishes descriptor pits from the separately
  emitted boot image, filesystem, and final ISO-9660 image. PCP-I `ZERO n` emits
  static zero bytes without declaring a fill pit. External MIR now provides
  `::RIF_PCPI FILL index "hex"` for exact-size transactional pit replacement;
  the QEMU Friendly variant now owns the boot image and cursor insertion;
  the generic Friendly target remains free of both.

- Added a separate `examples/probe/probe_friendlysyntax_qemu/` target that consumes
  Friendly Syntax through a declaration-only `friendly.riflib` exported from
  the base `.pack`, then loads its QEMU-only framebuffer dependency with
  `@LOAD "qemu/framebuffer.rif"`. The base
  `examples/amd64-friendlysyntaxs/` target now remains QEMU-independent;
  the QEMU variant owns the generic `framebuffer` block and
  `framebuffer_registers` table for std VGA/Bochs VBE at 640×480×32 with
  `BGRX8888` pixels. This is target metadata; the protected/long-mode
  transition remains boot-image code, not PCP-I data.
- Added a cursor-only QEMU display checkpoint to that target: `boot_stage_mouse`
  emits a 16-bit VBE `0x118` banked-window boot image, enables the PS/2 mouse,
  and moves the 14×22 cursor inside 640×480. `RIF_STORE` inserts the
  target-ready `cursor_arrow_bgrx8888` payload, and `boot_tail` pads the image
  to four 512-byte sectors. It intentionally has no kernel, PCI BAR0/LFB or
  long-mode transition.

## Suites de pruebas

- Separadas las pruebas en `tests/suite_essencial`, `tests/suite_aggressive` y
  `tests/dedicated_suite`. `vnma test` conserva la suite esencial por defecto;
  benchmarks, estrés e integraciones específicas requieren ejecución explícita.
- Reubicadas las suites y sus README bajo `tests/`, conservando sus carpetas
  internas y haciendo explícitas esas rutas en la CLI y la documentación. El
  lanzador rápido permanece en `tests/` para no alterar el descubrimiento por
  defecto de VNMA.

## Organización de ejemplos

- El demo declarativo general que estuvo bajo `examples/RIF-Core-Demo/` fue
  retirado al quedar cubierto por las suites de pruebas; la raíz del
  repositorio ya no contiene fuentes `.rif` de ejemplo ni el `main.pack`
  generado; `food/` sigue reservado para datos temporales de referencia.

- Añadido `examples/amd64-friendlysyntaxs/`, un paquete AMD64 raw que declara
  una sintaxis alternativa (`set`, `copy`, `load`, `store`, `return`, etc.) con
  tablas y Rules locales. El ejemplo demuestra que RIF no fija la sintaxis de
  entrada y que una misma arquitectura puede tener vocabularios distintos;
  usa `set R0 = 42`, la familia `R0..R15` y reserva `SR0..SR15` para futuras
  Rules de subregistros.
- Añadida una prueba de equivalencia que compila el mismo programa AMD64 normal
  y amigable desde fuente y desde `.pack`; los cuatro resultados deben coincidir
  byte a byte.
- Separados los MIR externos de Friendly Syntax: `demo.mir` y `equivalent.mir`
  viven en `examples/probe/probe_friendlysyntax/`, fuera de la definición del
  target.

## Contrato de target y primitivas declarativas

- Formalizado el flujo de dos fases: `.rif` se compila a un `CompiledRuleSet`
  distribuible como `.pack`, y `.pack + .mir` produce la imagen binaria.
- Centralizada la selección tipada de filas de tablas extensibles y reutilizada
  por `table_matcher`, `dget` y consultas de campos.
- Añadidas las variantes `fit_signed`, `fit_signed_exact` y `fit_signed_not`
  para rangos signed y emisión en complemento a dos.
- Añadida validación del target antes de aceptar MIR: Rules, secciones,
  políticas de salida, tablas, variantes y contrato del linker.

## Diagnósticos, layout y relocaciones

- Unificados los diagnósticos de frontend, Rules, MIR, layout y fixups con
  contexto estructurado de archivo, línea, Rule, sección y token.
- Las ejecuciones de Rules y los inserts son transaccionales sobre memoria
  física y virtual; un fallo no deja bytes, reservas o símbolos parciales.
- El layout expone tamaños inicializados/no inicializados, valida solapes
  virtuales y conserva las regiones `vreserve` fuera del archivo.
- Las relocaciones usan especificaciones genéricas; además de las clases
  estándar, un target puede declarar clases `pc` y `abs` en `@block relocations`.

## FFI AOT y contrato de artefactos

- La FFI C/AOT de Gram es el frontend canónico en memoria: recibe texto o
  bytes, devuelve GIR y no crea archivos `.gir` temporales.
- La caché AOT versiona su formato y registra el contrato activo, Gram/GIR,
  ABI del parser C, fuentes nativas y compilador para invalidar artefactos
  obsoletos.
- Los manifiestos `.pack` (formato 7) y las bases SQLite compiladas (esquema
  7) incluyen la misma huella de contrato; los consumidores rechazan
  combinaciones incompatibles antes de procesar MIR.

## Caches, mapas y paridad

- La huella del contrato incluye las fuentes Python de producción de RIF, por
  lo que cambios en el compilador, serializador, runtime o lector de paquetes
  invalidan artefactos derivados junto con los hashes de fuentes, Gram y C/AOT.
- Añadido `MIRCompilation.output_map()`, `map_output=` y `main.py --map` para
  producir mapas JSON opcionales con binario, secciones, símbolos, Rules y
  relocaciones resueltas.
- Añadido `Frontend.parity.compare_target()` para comparar AST, Rules y
  contexto Python/AOT, junto con `rif_tools.target_scaffold` para generar
  fixtures de pruebas de targets.

## Librerías, oráculos y ABI de Rules

- Añadido el formato fuente reproducible `.riflib`, creado con
  `rif_library.create_library()` y consumido desde `.rif` mediante
  `@LIBRARY "archivo.riflib"`. Las librerías se incluyen y validan dentro de
  `.pack` sin extracción ni rutas absolutas.
- Añadido `rif_tools.oracles` para comparar bytes opcionalmente con NASM o
  LLVM MC, con timeout y límites de salida, y `rif_tools.properties` para
  property testing/fuzzing determinista sin dependencia de Hypothesis.
- Añadida `MIR.operations`, una tabla cerrada y versionada de primitivas
  C/AOT (`fit_unsigned`, `fit_signed` y `encode_relocation`) con descriptores,
  JSON, header e implementación C. El runtime de Rules consume la misma implementación pura;
  los callbacks Python dinámicos siguen fuera del contrato.

## Inspector de paquetes

- Añadido `main.py --inspect-pack`, con salida humana o JSON, para revisar de forma
  segura formato, versión, fingerprint, fuentes, assets, Rules, tablas,
  configuración, linker, variantes y extensiones MIR aceptadas.
- El inspector verifica siempre el ZIP y la base SQLite compilada en memoria,
  valida integridad, esquema, índices y filas, no activa globals, no ejecuta
  Rules ni extrae archivos, y limita los elementos repetidos del informe.

## Símbolos nativos

- Añadido el opcode AOT-safe `mark`, basado en `MatchSeqSymbol`, para registrar
  el identificador MIR actual en la posición física y virtual del emisor.
- Las compilaciones MIR exponen `RIFMachine.symbols` con offsets relativos y
  `MIRCompilation.symbols` con direcciones virtuales absolutas tras el layout;
  las consultas de labels nativas reutilizan esos símbolos y los duplicados se
  rechazan.
- Añadida la cola de relocaciones diferidas `fixup pc8`, `fixup pc32` y
  `fixup abs64`, con resolución transaccional después del MIR para soportar
  referencias adelantadas y validación de rangos sin parches parciales.
- Añadida la directiva MIR `::RIF_SECTION nombre` para cambiar el emisor
  activo entre secciones de una `AssemblyImage`; el ejemplo AMD64 ya no usa
  `select_text`, `select_data` ni `link_image` mediante Python.

## Perfil AMD64 bare metal

- El ejemplo `AMD64_Baremetal` declara en `.rif` las familias de registros
  de 8/16/32/64 bits, inmediatos `imm8`/`imm32`/`imm64`, memoria sin
  desplazamiento/`disp8`/`disp32`, las 16 condiciones en ramas cortas y largas,
  y branches indirectos por registro y memoria.
- Estas extensiones permanecen dentro de las tablas y Rules del target; el
  núcleo RIF sigue siendo agnóstico de ISA. `test_profile_points.py` conserva
  un oráculo raw independiente para esas cinco familias.
- Añadidas Rules de enteros para operaciones unarias, `mul`/`imul`/`div`/`idiv`,
  shifts por `CL`, bit operations, `bsf`/`bsr`, `popcnt` y `bswap`.
- Declarado el alcance `amd64-base-integer`: `0x66`, `0x67`, `LOCK`, `REP`,
  `FS` y `GS` están probados; MMX, SSE, AVX, AVX-512, x87 y system
  instructions permanecen fuera del perfil.
- Ampliado el cross-check externo a 60 formas representativas contra el
  ensamblador integrado de LLVM. El diferencial detectó y corrigió el ModR/M
  `/2` de `callmem64_*`, que estaba reutilizando erróneamente el `/4` de los
  saltos indirectos. NASM y LLVM MC siguen siendo oráculos opcionales, sin
  convertirse en dependencias de RIF.
- Separados los programas MIR externos del target: los probes AMD64 viven en
  `examples/probe/probe_amd64/` y `examples/AMD64_Baremetal/` conserva solo
  sus definiciones, pruebas y paquetes.

## Syntax

- Made the root `main.rif` the target control center: configuration blocks are
  root-only, an optional `config.rif` may be loaded directly by the root, and
  duplicate `config`/`linker` declarations are rejected.
- Replaced the Rule instruction arrow marker with a leading dot; `.` is now
  the canonical start of every Rule instruction and `->` is no longer valid.
- Renamed final `@before` patches from `.rplc` to canonical `.patch`; the old
  directive is rejected without a compatibility alias.
- Closed `@before` expressions to the native `#:` operations and rejected
  arbitrary `#call[...]` callbacks there; explicit MIR calls and `@insert`
  payload calls remain separate trusted escape hatches.
- Simplified `@block config`: sections, entry metadata, output formatting,
  alignment, byte order, and bit order now use compact canonical names; the
  former configuration directives are rejected instead of retained as aliases.
- Simplified `@block linker` to `extension` and `search_path`; removed the
  unused `name` field and bumped the compiled-context schema to version 6.
- `search_path` may now be repeated; variant resolution uses the first matching
  directory, while `false` remains an exclusive disable switch.
- Tables are now immutable, type-aware, and preindexed across every column;
  compiled contexts no longer build shared lazy indexes at runtime.
- Renamed the binary Rule operations to the canonical vocabulary `nibbles`,
  `emit`, `eword`, `bits`, `frame`, `fit`, `fit_exact`, `pad`, `align`,
  `vpad`, `valign`, `write_res`, `emit_res`, `read_bits`, `patch_bits`,
  `fit_not`, and `drop_res`;
  the old spellings are no longer accepted.
- Removed the `. CALL` instruction and the dynamic `funcs.py` extension path.
  `#:calc` now delegates to the pure, C-portable implementation in
  `MIR/functions/calc.py`; `#call[...]` remains reserved for closed native
  functions.
- Reworked PCP-I into a standalone declarative `.pci` source format. Sources
  declare `MAGIC`, `VERSION`, `ENDIANNESS`, `BITORDER`, `SIGNATURE`, optional
  `PADDING`, and an `@RAW` region where `[N]` creates an aligned pit and
  `ZERO N` emits static zero bytes. The v1
  compiled container has a fixed 144-byte header, generated `RPAD`, and 20-byte
  pit records containing 64-bit relative address, 64-bit size, and 32-bit
  alignment padding; the old RIF Rule entry path and `--pcpi-entry` were
  removed.
- Added read-only CLI doctors: `--doctor-pcpi` validates a compiled `.pcic`
  container and reports its header and pits; `--doctor-storage` validates an
  indexed `storage.bin` and reports its entries and labels. Both return a
  non-zero status for missing or corrupt artifacts.
- Added the external-MIR metaprogramming markers `::RIF_PCPI` and
  `::RIF_STORE`. `::RIF_STORE "storage.bin" label endianness bitorder` now
  resolves a relative storage path, validates the per-item layout values,
  extracts the labeled raw payload, and inserts it at the current byte-aligned
  position. `::RIF_PCPI SET "image.pcic"` is the first MIR directive and
  materializes only `PADDING + RAW + RPAD`; `::RIF_PCPI FILL index "hex"`
  resolves every pit transactionally, while `::RIF_PCPI PIT index [SECTION
  name]` reports the absolute rendered-payload offset without emitting bytes.

## Security

- Restricted `@LOAD`, `.file`, `.searching`, and packaged paths to relative
  locations bounded by the project or package root.
- Prevented package execution from using the creator machine's absolute paths.
  Absolute origins are retained only as diagnostic metadata and are excluded
  from content hashes and resolution.
- Added validation for symlinks, package members, compressed-size ratios, and
  declared package contents before execution.
- Bumped the `.pack` manifest format to version 5 and removed `funcs.py`
  metadata and payloads from packages.
- Added the external `@block buffer` phase with `call reqsts
  "github.com/owner/repo/path.bin/branch"` for bounded raw `.bin` downloads
  from GitHub, with strict host, branch, redirect, timeout, and size validation.
  Acquisition failures are now published through Gram `Diagnostics` before
  propagating as compilation errors; console rendering is safe on Windows
  code pages.
- Added local media plugins: Pillow converts images to RGB888, RGBA8888 or
  framebuffer-ready BGRX8888 and
  `soundfile`/NumPy converts WAV, FLAC, and OGG audio to interleaved
  PCM_S16LE. They accept only local paths; URL and in-memory byte inputs are
  rejected. Video conversion is out of scope.
- Added standalone `.store` sources compiled with `--comp-store`; their
  payloads are written to indexed `RIFSTOR` storage with relative `u64`
  addresses, `u64` payload sizes, `u32` alignment padding, and `u32` label
  sizes; UTF-8 label bytes are stored inline after each payload.

## Resource limits

- Added configurable MiB limits through `--plimit N`, with precedence from the
  command line, process environment, `.env`, and built-in defaults.
- Applied the effective limit to RIF sources, MIR input, assets, package
  contents, binary output, field widths, dynamic operations, and temporary
  conversion buffers.
- Added early rejection before reading oversized files, creating oversized
  packages, or evaluating unbounded widths.

## Concurrency and correctness

- Serialized the RIF compilation phase with a reentrant lock so Gram's global
  registries and `Frontend.globals` cannot mix simultaneous compilations.
- Kept compiled runtime machines and their buffers independent, allowing
  execution after compilation to remain concurrent.
- Preserved origin-independent package fingerprints and validated package
  metadata before loading compiled databases or assets.

## Performance

- Deduplicated real paths while collecting project files and avoided repeated
  conversions for aligned binary data.
- Added a bulk byte-append path for aligned output and reduced unnecessary
  temporary buffers during artifact processing.
- Reused one AOT parser across physical `@LOAD` and variant sources, persisted
  its Gram compiler cache under `.rif-cache/aot/`, serialized cache builds
  across processes, and removed intermediate GIR files after loading them.
- Made the in-memory Gram FFI the canonical path for source-only `.pack`
  traversal; virtual `pack://` sources now enter the same native parser API as
  physical files.

## Verification

- Added hardening tests for resource-limit precedence, path traversal,
  package origins, and concurrent Gram compilations.
- `vnma test` passes 121 essential tests; the dedicated suite passes 65 tests
  with 6 optional skips and the aggressive suite passes 12 tests.
- `python -m compileall -q .`, `vnma run main.py ...`, and direct
  `python main.py ...` execution were verified.
