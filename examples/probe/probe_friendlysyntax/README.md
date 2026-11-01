# Friendly Syntax probes

These MIR files are external programs for `examples/amd64-friendlysyntaxs/`.
They are kept outside the target definition so the target contains only its
Rules, tables, tests and compiled package.

- `demo.mir`: base Friendly Syntax demonstration.
- `equivalent.mir`: same 15-byte program as `probe_amd64/main.mir`.
- The full-profile Friendly tests reuse the raw programs in
  `examples/probe/probe_amd64/` so both targets exercise the same fixtures.
