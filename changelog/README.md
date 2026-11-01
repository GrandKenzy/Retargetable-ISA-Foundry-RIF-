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

The temporary `food/` directory records concise x86-64, LLVM MC, and native RIF
relocation reference tables used to feed and verify the examples. It is not a
runtime dependency or a final product artifact and can be removed after the
examples are stabilized.

The AMD64 v3 example is now an operating-system-neutral bare-metal raw target;
its fixtures and tests no longer require object headers or host execution.

`.pack` targets can now publish their explicitly loaded Rules and tables as a
declaration-only `.riflib` with `main.py --library target.pack`. The Friendly QEMU
example consumes that layer and keeps its QEMU blocks and boot Rules local.

`main.py` is the canonical and only entrypoint for packaging, MIR compilation,
PCP-I, storage, inspection, and library operations. `rif_tools/cli.py` owns the
dispatch implementation.

The ELF64 and MiniOS test examples now live under `examples/probe/` with the
other target probes.

The obsolete `RIF-Core-Demo` example was removed; frontend and runtime
coverage remains in the essential, aggressive and dedicated suites.

The QEMU-independent Friendly AMD64 example now carries the complete raw
AMD64 profile from `AMD64_Baremetal` and validates it with the same encoding,
relocation, integer/prefix and external-oracle checks, while retaining its
readable aliases.

The AMD64 targets now keep shared BSWAP and 32-bit address-register metadata in
the canonical register tables instead of repeating those rows in integer and
prefix sources; the CL-only shift-count table remains intentionally narrow.
The two AMD64 image roots now share their declaration load through `profile.rif`;
only root configuration and the optional data alignment remain layout-specific.

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
