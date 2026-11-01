# RIF examples

This directory contains complete, runnable demonstrations of RIF targets. An
example is a target project, not a built-in architecture backend: its `.rif`
sources declare tables, Rules, matching, layout and emission policy; the RIF
core only executes those declarations.

External MIR programs and target probes live under `examples/probe/`; they are
kept separate from the core target catalog and grouped with their fixtures.

## The common model

Every target follows the same conceptual contract:

```text
target/main.rif + loaded sources
              │
              ├── compile target ──> target.pack
              │
              └── target + input.mir ──> raw bytes / image
```

- `.rif` is the declarative target definition.
- `.pack` is the reusable compiled target. It contains the target sources and,
  when requested, compiled SQLite data; it does not contain external MIR or a
  final program.
- `.mir` is the input program understood by that target's Rules. The vocabulary
  is target-defined and does not have to resemble a conventional assembler.
- The output may be raw bytes, an object-like image, a ROM, or an executable
  container, depending on the target's own Rules and preprocessor directives.

Run commands from the repository root through VNMA:

```powershell
# Compile directly from a target definition.
vnma run rif.py examples/<target>/main.rif examples/<target>/program.mir `
  -o examples/<target>/program.bin

# Compile the target once and reuse it.
vnma run rif.py --pack examples/<target>/main.rif `
  -o examples/<target>/<target>.pack
vnma run rif.py examples/<target>/<target>.pack `
  examples/<target>/program.mir -o examples/<target>/program-from-pack.bin
```

Generated `.pack`, `.bin`, ROM and executable outputs are local artifacts and
are ignored unless an example explicitly documents otherwise. Source `.rif`,
`.mir`, test scripts and documentation are the portable part of an example.

## Example catalog

| Example | Input vocabulary | Output | Main purpose |
| --- | --- | --- | --- |
| [AMD64 Baremetal](./AMD64_Baremetal/README.md) | Explicit AMD64 encoding Rules | Raw AMD64 images | Full raw AMD64 profile, memory, branches, relocations and external verification |
| [AMD64 Friendly Syntax](./amd64-friendlysyntaxs/README.md) | `set`, `copy`, `add`, `load`, `store`, `return` | Raw AMD64 bytes | QEMU-independent alternative syntax, `R0..R15` register tables and normal/friendly byte equivalence |
| [AMD64 Friendly Syntax QEMU](./probe/probe_friendlysyntax_qemu/README.md) | Friendly Syntax plus QEMU boot Rules | RIF-emitted El Torito boot image | VBE 0x118 banked framebuffer and centered cursor checkpoint |
| [MiniOS Probe](./probe/probe_minios/README.md) | PCP-I, external storage and ISO assembly | Bootable ISO-9660/El Torito image | Complete QEMU BIOS image build with RIF-emitted boot code and cursor data |
| [ELF64 Probe](./probe/probe_elf64/README.md) | AMD64-like assembly plus image directives | Linux ELF64 executable | Header templates, inserts and final patches; intentionally host-specific |
| [GBA Bouncing Ball](./GBA-Bouncing-Ball/README.md) | ARM/Thumb-oriented target vocabulary | GBA ROM | ARM7TDMI tables, Thumb variants, ROM assets and a complete generated cartridge demo |

## What each example proves

### AMD64 Baremetal

`AMD64_Baremetal` is the full raw AMD64 demonstration. Its Rules and tables
cover the explicitly declared `amd64-base-integer` profile, including:

- 8-, 16-, 32- and 64-bit register and immediate forms;
- REX, ModR/M, SIB, displacement and address-size forms;
- arithmetic, shifts, integer and bit operations;
- conditional and indirect branches;
- `0x66`, `0x67`, `LOCK`, `REP`, `FS` and `GS` forms;
- raw sections, symbols, virtual layout, reservations and generic fixups;
- `pc8`, `pc32`, `abs64` and RIP-relative relocation cases.

The profile deliberately excludes MMX, SSE, AVX, AVX-512, x87 and system
instructions. It is not a complete AMD64 assembler and does not generate ELF,
PLT/GOT, PIE, Linux code or an external object relocation table.

Its validation is intentionally layered:

- `test_encoding.py`: 13,072 raw encoding combinations;
- `test_profile_points.py`: independent width, addressing, branch and immediate
  checks;
- `test_integer_prefixes.py`: integer and prefix coverage;
- `test_relocations.py`: symbols, ranges, layout and fixups;
- `test_external_oracle.py`: 60 representative comparisons against LLVM's
  integrated assembler when Clang and `llvm-objcopy` are available.

### AMD64 Friendly Syntax

`amd64-friendlysyntaxs` proves that RIF does not prescribe the input language.
It declares its own register tables and Rules, using full-width `R0..R15`
names instead of architectural names. `SR0..SR15` are reserved for future
width-specific sub-register Rules.

The friendly program can use forms such as:

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

`examples/probe/probe_friendlysyntax/equivalent.mir` rewrites the existing
`examples/probe/probe_amd64/main.mir` program as:

```text
set R0 = 42
set R7 = 7
noop
```

`test_syntax_equivalence.py` compiles both versions from source and from
`.pack`; all four outputs must be identical. This is a syntax demonstration,
not a second AMD64 backend in the RIF core.

### ELF64 Probe

`probe_elf64` is intentionally different from the bare-metal examples. It emits a
minimal Linux x86-64 ELF image by combining RIF-generated instruction bytes
with an inline header template and `::RIF_PATCH` queries. It may be executed
on Linux, while Windows users can still inspect the generated bytes. The
Linux dependency belongs to this example, not to RIF's architecture model.

### GBA Bouncing Ball

`GBA-Bouncing-Ball` demonstrates a complete ROM-oriented workflow: an ARM7TDMI
target, a Thumb variant, a cartridge header asset, generated MIR, ROM padding
and a reduced verification CPU. `build.py` still calculates labels and ARM
branch offsets in Python, so this example is not a complete ARM assembler.
That limitation is documented deliberately; the example shows how RIF can be
embedded in a larger target-generation pipeline.

Rebuild and verify it with:

```powershell
vnma run examples/GBA-Bouncing-Ball/build.py rif.py
vnma run examples/GBA-Bouncing-Ball/verify_cpu.py
```

## Choosing an example

- Use `AMD64_Baremetal` for encoding, layout, relocations and raw-image
  validation.
- Use `amd64-friendlysyntaxs` when testing alternative input vocabulary or
  syntax equivalence.
- Use `probe_elf64` only when testing object/container construction and Linux-specific
  final patches.
- Use `probe_minios` for the PCP-I, cursor-storage, ISO and QEMU BIOS probe.
- Use `GBA-Bouncing-Ball` for variants, assets, ROM layout and a non-AMD64
  target-generation pipeline.

The external reference material under `foot/` is temporary input data for these
examples. It is not a RIF backend, not a package dependency, and not part of
the final example contract.
