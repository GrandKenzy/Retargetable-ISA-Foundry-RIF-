# RIF 1.0.0 · Official stable release

**Release date:** 2026-11-01

RIF `1.0.0` is the official stable release and the canonical version of the
project. It defines a complete path from a retargetable `.rif` target
definition and external MIR to deterministic binary output.

## Added

- Gram-based RIF syntax with newline-delimited Rules and `;` comments.
- Generic `@block` configuration, linker metadata, variants, tables, Rules,
  definitions, loads, reusable libraries, and compile-time table joins.
- Explicit `CompilationSession` frontend state and immutable `TargetContext`
  results for isolated consecutive and concurrent target compilations.
- FFI AOT as the canonical public frontend route. Python remains an internal
  parity and diagnostic backend; GCC or Clang is used only to build or refresh
  the cached shared library.
- Reproducible `.pack` archives, declaration-only `.riflib` exports, source
  manifests, load graphs, hashes, limits, and safe package inspection.
- Bit-precise emission and rewriting, physical and virtual layouts, sections,
  padding, alignment, reservations, symbols, fixups, and output maps.
- Standalone PCP-I version 1 templates with fixed bytes, static `ZERO` regions,
  exact-size aligned pits, `.pcic` validation, `SET`, `FILL`, and `PIT` MIR
  directives.
- Standalone STORE versions 1 and 2 with labeled raw payloads, media items,
  typed fixed-width values, `@FILE`, bounded GitHub `@REQST`, `@CONTAINER`,
  storage aliases, and per-alias byte-layout configuration.
- Canonical `main.py` command dispatch for packaging, libraries, MIR, PCP-I,
  STORE, inspection, and diagnostics, plus the optional `rif.cmd` convenience
  launcher.
- AMD64 bare-metal, Friendly Syntax, ELF64, MiniOS, QEMU, and GBA probes that
  demonstrate target-owned semantics without turning them into RIF built-ins.

## Changed

- The CLI no longer exposes the removed executable parser route. Public command
  examples use `vnma run main.py`; `rif.cmd` is only a forwarding wrapper.
- The frontend no longer relies on process-wide pending tables, source lists,
  or manual global resets during normal compilation.
- PCP-I remains a binary-template layer and does not become an ISO builder,
  linker, assembler, or bootloader.
- STORE version 1 remains the simple raw/local format. Version 2 adds typed
  values and `@REQST`; version 3 is reserved for future functions and macros.
- The public documentation is organized in English and Spanish, with dedicated
  PCP-I and STORE tool guides and current command examples.

## Fixed

- `float32` values that exceed IEEE-754 single precision now produce a
  controlled STORE source error instead of leaking a native packing exception.
- STORE version 2 rejects alignment padding that cannot coexist safely with its
  inline type metadata.
- PCP-I and STORE documentation no longer presents payload insertion as
  automatic operand-symbol substitution.
- The obsolete duplicate launcher and legacy project copy were removed from
  the active PATH workflow.
- The ELF64 header probe filename was corrected from `litte` to `little`.

## Documentation

- Added structured English and Spanish PCP-I documentation.
- Added structured English and Spanish STORE documentation.
- Updated the root README and language indexes to identify `main.py` as the
  canonical entrypoint and `rif.cmd` as an optional wrapper.
- Documented the stable-version policy: patches may fix small non-semantic
  issues without changing compilation or emitted binary behavior.

## Verification

- The repository's standard test suite and dedicated storage/MIR coverage were
  validated during the release work.
- Markdown links, package documentation, PCP-I/STORE examples, and probe paths
  were audited against the current repository layout.

## Stable patch rule

The `1.0.0` contract remains stable. Future patch releases may correct small
errors only when the correction does not change compilation semantics, accepted
syntax, target resolution, binary layout, emitted bytes, package compatibility,
or storage format meaning. Changes across those boundaries require a new
versioned release.
