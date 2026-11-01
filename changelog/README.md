# RIF · Changelog

<p align="center">
  <strong>Versioned release notes for RIF</strong><br>
  Retargetable definitions, MIR compilation, bit memory, and target packages.
</p>

---

## Current release

### Unreleased · Canonical generic blocks

RIF now materializes `config` and `linker` through the generic `@block` form.
The former dedicated block headers and dotted directive syntax are no longer
accepted, and arbitrary blocks remain available through the compiled target
context.

The temporary `foot/` directory records concise x86-64, LLVM MC, and native RIF
relocation reference tables used to feed and verify the examples. It is not a
runtime dependency or a final product artifact and can be removed after the
examples are stabilized.

The AMD64 v3 example is now an operating-system-neutral bare-metal raw target;
its fixtures and tests no longer require object headers or host execution.

### [`1.0.1`](changelog_1.0.1.md) · Security hardening and resource controls

RIF `1.0.1` strengthens path validation, resource controls, package safety,
concurrent compilation isolation, and verification coverage.

### [`1.0.0`](changelog_1.0.0.md) · Initial stable release

RIF `1.0.0` provides the complete definition-to-binary pipeline, including
external MIR compilation, bit-addressable output, target packages, tables,
variants, Python functions, and independent physical and virtual memory state.

## Release timeline

| Version | Date | Main focus | Notes |
| --- | --- | --- | --- |
| [`1.0.1`](changelog_1.0.1.md) | 2026-10-26 | Security hardening and resource controls | Current |
| [`1.0.0`](changelog_1.0.0.md) | 2026-10-26 | Complete RIF compilation pipeline | Superseded |

## How to read these notes

Each release has a `changelog_*.md` file. Entries are grouped by impact:

- **Added:** new public capabilities and language constructs.
- **Changed:** modifications to existing behavior.
- **Fixed:** corrected bugs and regressions.
- **Documentation:** synchronized English and Spanish guides.
- **Verification:** tests, stress runs, and compatibility checks.

Keep the version in the changelog filename, heading, and `vnma.toml` metadata
synchronized when preparing a release.
