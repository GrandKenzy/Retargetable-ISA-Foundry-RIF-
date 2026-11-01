# RIF 1.0.1 · Security hardening and resource controls

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
  unused `name` field and bumped the compiled-context schema to version 5.
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
  `PADDING`, and an `@RAW` region where `[N]` creates an aligned pit. The v1
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
  position. `::RIF_PCPI SET "image.pcic"` inserts a complete PCP-I container
  as the first MIR directive, while `::RIF_PCPI PIT index [SECTION name]`
  reports the absolute payload offset without emitting bytes.

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
- Added local media plugins: Pillow converts images to RGBA8888 and
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
- Kept source-only `.pack` traversal on the explicit Python backend because
  its `pack://` paths are not valid inputs for Gram's native CLI.

## Verification

- Added hardening tests for resource-limit precedence, path traversal,
  package origins, and concurrent Gram compilations.
- `vnma test` passes all 137 tests.
- `python -m compileall -q .`, `vnma run rif.py ...`, and direct
  `python rif.py ...` execution were verified.
