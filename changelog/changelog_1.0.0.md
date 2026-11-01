# RIF `1.0.0`

**Release date:** 2026-10-26

This is the first stable RIF release. It provides a complete path from a
retargetable `.rif` definition to a pure binary produced from external MIR.

## Added

- Gram-based RIF syntax with newline-delimited Rules and `;` comments.
- Target configuration through `@config` and linker metadata through
  `@linker`.
- Root tables, lazy column indexes, `@LOAD` source resolution, definitions,
  Rules, token storage, Rule calls, conditions, and ISA variants.
- External MIR compilation through the CLI and direct Python APIs.
- Reproducible `.pack` archives with source manifests, load graphs, SHA-256
  verification, optional `funcs.py`, and precompiled SQLite target data.
- Fixed-width emission with `nibbles`, `emit`, `eword`, and multiline `frame`.
- Arbitrary bit emission, reading, and rewriting with `bits`, `read_bits`,
  and `patch_bits`.
- Physical and virtual cursors, padding, alignment, reservations, reservation
  queries, and per-Rule physical and virtual traces.
- Independent `datastack` for temporary values and table-driven `dload`.
- Python extension functions with a validated `handler(name, context)`
  contract.
- Binary `@insert` preludes, opaque `.pack` assets, transactional `@before`
  patches, native image queries, arithmetic, and physical/virtual section
  layout.

## Changed

- Tables retain their matrix representation while building indexes only for
  columns used as lookup keys.
- The compiled Rule Set and external MIR remain separate public concepts.
- `.pack` files can load precompiled targets without reparsing every source.
- Direct token compilation avoids a second MIR lexing and parsing pass.

## Fixed

- Physical reservations now preserve their independent virtual offset after
  virtual padding.
- Out-of-range bit rewrites fail before modifying the buffer.
- Failed exact fits leave a datastack width available for recovery logic.

## Documentation

- Added synchronized English and Spanish documentation under `docs/en` and
  `docs/es`.
- Added versioned release notes under `changelog`.
- Documented syntax, configuration, linker behavior, tables, packages, MIR,
  Python functions, memory, datastack, variants, diagnostics, and tests.

## Verification

- RIF test suite: 100 tests passed.
- Documentation link audit: 33 relative links validated.
