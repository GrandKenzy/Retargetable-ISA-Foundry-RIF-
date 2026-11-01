# AMD64 probes

These MIR files are external programs and fixtures, not part of the AMD64
target definition. The target itself lives in `examples/AMD64_Baremetal/` and
its compiled packages are `amd64.pack` and `amd64-rw.pack`.

- `main.mir`: minimal conventional `mov`/`nop` program.
- `symbols.mir`: forward/backward branch and relocation fixture.
- `sections.mir`: text/data layout and virtual reservation fixture.
- `advanced.mir`, `conditional.mir`, `runtime.mir`, `smoke.mir`: raw AMD64
  instruction-family probes.
