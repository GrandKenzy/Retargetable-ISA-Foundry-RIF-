# RIF Core Demo

This small target demonstrates the declarative RIF frontend and its emitter
without depending on a host operating system or a concrete machine ISA. It
contains a 32-bit section configuration, an extensible table, and Rules that
exercise matching, emission, reservations, frames, jumps, and diagnostics.

- `main.rif` is the target definition used by the frontend and pack tests.
- `table.rif` is a standalone table-data example for the generic table syntax.

Compile its target package with:

```powershell
vnma run rif.py --pack examples/RIF-Core-Demo/main.rif `
  -o examples/RIF-Core-Demo/core-demo.pack
```

The complete-program behavior is covered by the essential pipeline and MIR
tests. This example is intended for frontend/runtime work, not for validating
an instruction-set encoding.

The files are intentionally kept under `examples/`; `foot/` is reserved for
temporary external reference data used while developing the richer examples.
