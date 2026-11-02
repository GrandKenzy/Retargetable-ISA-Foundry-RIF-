# RIF · Changelog

<p align="center">
  <strong>Versioned release notes for RIF</strong><br>
  Retargetable definitions, MIR compilation, bit memory, and target packages.
</p>

---

## Current release

### [`1.0.0`](changelog_1.0.0.md) · Official stable release

RIF `1.0.0` is the canonical official stable version. It is the reference
contract for the current frontend, MIR compiler, packages, PCP-I tools, STORE
containers, examples, and documentation.

This release includes the complete definition-to-binary workflow, the explicit
frontend session model, the FFI AOT CLI route, reusable `.pack` and `.riflib`
artifacts, AMD64 and Friendly Syntax probes, PCP-I templates, versioned STORE
containers, and the documented `main.py` entrypoint.

## Patch policy

RIF remains version `1.0.0` while patches are released for small corrections
that do not change compilation behavior. A patch may correct documentation,
diagnostics, launcher behavior, cleanup, test robustness, or an internal error
that cannot alter accepted syntax, target resolution, layout, emitted bytes,
package compatibility, or storage format semantics.

A change that modifies the compiler contract, accepted language, Rule
resolution, binary output, package format, or target semantics requires a new
versioned release instead of being treated as a `1.0.0` patch.

## Release timeline

| Version | Date | Main focus | Notes |
| --- | --- | --- | --- |
| [`1.0.0`](changelog_1.0.0.md) | 2026-11-01 | Official stable RIF contract | Current |

## How to read these notes

The release file uses these sections:

- **Added:** new public capabilities and language constructs.
- **Changed:** intentional behavior or architecture changes within the release.
- **Fixed:** corrected defects that preserve the stable compilation contract.
- **Documentation:** synchronized English and Spanish guides.
- **Verification:** tests, probes, benchmarks, and audits used during release work.

Keep the version in the changelog filename, heading, `vnma.toml` metadata, and
the public contract synchronized.
