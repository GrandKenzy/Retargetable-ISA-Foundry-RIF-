# AMD64 Friendly Syntax

This is the QEMU-independent AMD64 bare-metal `.pack` target with a readable
input vocabulary. It demonstrates that RIF does not require the input language
to look like AMD64 assembly: the target Rules and extensible tables define the
syntax and emit raw bytes.

The accepted forms in `examples/probe/probe_friendlysyntax/demo.mir` are:

```text
set R0 = 42
copy R8, R0
add R8, R7
increase R8, 5
store R8, R4, 256
load R9, R4, 256
noop
return
```

General-purpose registers use the friendly names `R0` through `R15`; the
architectural mapping is kept in tables, so the names are not built into RIF.
`SR0` through `SR15` are reserved for future width-specific sub-register Rules;
this package intentionally emits only full-width registers.

`set` and `increase` immediate values use signed 32-bit operands. `load` and
`store` use an explicit base register and signed 32-bit displacement. The
target is raw and OS-neutral: it does not contain Linux, ELF, QEMU, VGA,
framebuffer, or host-ABI dependencies.

QEMU-specific video metadata and the MiniOS boot entry live in the separate
[AMD64 Friendly Syntax QEMU](../amd64-friendlysyntaxs-qemu/README.md) target.

## Compile from source and from `.pack`

```powershell
vnma run rif.py --pack examples/amd64-friendlysyntaxs/main.rif `
  -o examples/amd64-friendlysyntaxs/amd64-friendly.pack
vnma run rif.py examples/amd64-friendlysyntaxs/main.rif `
  examples/probe/probe_friendlysyntax/demo.mir `
  -o examples/amd64-friendlysyntaxs/friendly.bin
vnma run rif.py examples/amd64-friendlysyntaxs/amd64-friendly.pack `
  examples/probe/probe_friendlysyntax/demo.mir `
  -o examples/amd64-friendlysyntaxs/friendly-from-pack.bin
```

The source and packed paths must produce identical raw bytes. The expected
image for `examples/probe/probe_friendlysyntax/demo.mir` is:

```text
48 C7 C0 2A 00 00 00
48 C7 C7 07 00 00 00
4C 8B C0
4C 03 C7
49 81 C0 05 00 00 00
4C 89 84 24 00 01 00 00
4C 8B 8C 24 00 01 00 00
90 C3
```

The source is intentionally independent from `AMD64_Baremetal`: it uses
the same RIF model but declares its own tables and Rules, proving that the
syntax is target data rather than a built-in parser mode.

## Syntax equivalence test

`equivalent.mir` is the same small bare-metal program as
`examples/probe/probe_amd64/main.mir`, rewritten with the friendly vocabulary. The
dedicated comparison compiles both targets from source and from `.pack`:

```powershell
vnma run examples/amd64-friendlysyntaxs/tests/test_syntax_equivalence.py `
  --rif-root .
```
