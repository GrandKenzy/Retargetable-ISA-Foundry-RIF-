# AMD64 Friendly Syntax

This is the QEMU-independent full AMD64 bare-metal `.pack` target with a
readable input vocabulary. It demonstrates that RIF does not require the input
language to look like AMD64 assembly: the target Rules and extensible tables
define the syntax and emit raw bytes.

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

The friendly aliases use the names `R0` through `R15`; the architectural
mapping is kept in tables, so the names are not built into RIF. The copied
`amd64_*.rif` modules add the complete width-specific register and instruction
families, including the original architectural names.

`set` and `increase` immediate values use signed 32-bit operands. `load` and
`store` use an explicit base register and signed 32-bit displacement. The
target is raw and OS-neutral: it does not contain Linux, ELF, QEMU, VGA,
framebuffer, or host-ABI dependencies.

QEMU-specific video metadata and the MiniOS boot entry live in the separate
[AMD64 Friendly Syntax QEMU](../probe/probe_friendlysyntax_qemu/README.md) probe.

## Compile from source and from `.pack`

```powershell
vnma run main.py --pack examples/amd64-friendlysyntaxs/main.rif `
  -o examples/amd64-friendlysyntaxs/amd64-friendly.pack
vnma run main.py examples/amd64-friendlysyntaxs/main.rif `
  examples/probe/probe_friendlysyntax/demo.mir `
  -o examples/amd64-friendlysyntaxs/friendly.bin
vnma run main.py examples/amd64-friendlysyntaxs/amd64-friendly.pack `
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

The Friendly layer is intentionally independent from the RIF core. The
`amd64_*.rif` modules carry the complete raw AMD64 profile from
`AMD64_Baremetal`, while `friendly_registers.rif` and `friendly_rules.rif`
add the readable vocabulary above. Both vocabularies emit the same raw bytes.
The shared `profile.rif` load keeps `main.rif` and `main_rw.rif` aligned; their
root configuration remains separate only because the latter aligns `data`.

## Full AMD64 coverage

The target now carries the same declared scope as `AMD64_Baremetal`:

- 8-, 16-, 32- and 64-bit registers, immediates, arithmetic, shifts and bit operations;
- ModR/M, SIB, base/index addressing, displacement and address-size forms;
- conditional, indirect and symbolic branches, sections, reservations and fixups;
- `0x66`, `0x67`, `LOCK`, `REP`, `FS` and `GS` prefix families;
- raw `main.rif` and aligned `main_rw.rif` layouts without OS or QEMU dependencies.

The original AMD64 Rule names remain available for exhaustive coverage, while
the Friendly aliases provide the convenient surface for common programs.

## Syntax equivalence test

`equivalent.mir` is the same small bare-metal program as
`examples/probe/probe_amd64/main.mir`, rewritten with the friendly vocabulary. The
dedicated comparison compiles both targets from source and from `.pack`:

```powershell
vnma run examples/amd64-friendlysyntaxs/tests/test_syntax_equivalence.py `
  --rif-root .
```

The full raw-profile checks are also run against this target:

```powershell
vnma run examples/amd64-friendlysyntaxs/tests/test_encoding.py --rif-root .
vnma run examples/amd64-friendlysyntaxs/tests/test_profile_points.py --rif-root .
vnma run examples/amd64-friendlysyntaxs/tests/test_integer_prefixes.py --rif-root .
vnma run examples/amd64-friendlysyntaxs/tests/test_relocations.py --rif-root .
vnma run examples/amd64-friendlysyntaxs/tests/test_external_oracle.py --rif-root .
```
