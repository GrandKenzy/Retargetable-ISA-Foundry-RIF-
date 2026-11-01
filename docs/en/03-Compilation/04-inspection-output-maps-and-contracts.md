# Inspection, Output Maps, and Artifact Contracts

RIF provides read-only inspection and optional output maps for users who need
to understand a target or audit a generated image without changing its bytes.

## Inspecting a package

Inspect a package before using it:

```powershell
vnma run rif.py --inspect-pack build/target.pack
```

The inspector validates the ZIP structure, member paths, hashes, resource
limits, source graph, embedded libraries, and—when present—the SQLite compiled
target. It does not execute Rules, import target plugins, activate compiler
globals, or extract files.

Use JSON for build tools:

```powershell
vnma run rif.py --inspect-pack build/target.pack --json > build/target.inspect.json
```

Use `--verbose` for bounded Rule instructions and table rows, and
`--show-origins` only when creator paths are needed for a local diagnostic:

```powershell
vnma run rif.py --inspect-pack build/target.pack --verbose --max-items 200
vnma run rif.py --inspect-pack build/target.pack --json --show-origins
```

The report includes the package format and version, content fingerprint,
contract fingerprint, source and dependency counts, library and asset entries,
Rules, tables, configuration, linker metadata, variants, and accepted MIR
extensions.

## Output maps

An output map is optional and does not alter the binary:

```powershell
vnma run rif.py build/target.pack program.mir -o build/program.bin --map build/program.map.json
```

The map is a stable JSON document containing:

- target and MIR identities;
- final binary size and SHA-256 hash;
- every output section, its flags, alignment, file offsets, virtual bases,
  initialized size, and uninitialized size;
- symbols with physical and virtual offsets and absolute addresses;
- executed Rules with section, physical span, virtual span, and padding;
- relocations with kind, symbol, reservation, offset, width, next instruction
  address, target address, and resolved value.

The map is for diagnostics, loaders, tests, and build reports. The binary is
still the authoritative output artifact; a map is never required to load or
execute it.

The Python result exposes the same data:

```python
from MIR import compile_mir_file

result = compile_mir_file(
    "build/target.pack",
    "program.mir",
    output="build/program.bin",
)
report = result.output_map()
```

## Contracts and invalidation

RIF versions the compatibility contract shared by:

- the `.pack` manifest;
- the compiled SQLite target;
- Gram and its GIR format;
- the C/AOT frontend ABI;
- the runtime ABI and operation table;
- the production RIF compiler sources.

Consumers reject artifacts whose contract does not match the active toolchain.
The content fingerprint also covers target sources, assets, and referenced
libraries. A change to a library or to the compiler implementation therefore
cannot silently reuse an old derived target.

The AOT cache additionally records the generated parser inputs, native Gram
sources, and C compiler identity. Deleting `.rif-cache/aot` is safe when a
manual reset is needed; normal changes are detected automatically.

## Transactional output

RIF validates and plans output before committing it. Rule execution, section
layout, final patches, and fixups use transactional state. If any phase fails,
the requested output file is not replaced with a partially emitted image.

This makes it safe for a build system to treat a successful process exit and
the presence of the output file as a completed compilation, while still
preserving diagnostics from a failed attempt.

## API boundaries

Use target APIs for phase 1:

```python
from MIR import compile_source, compile_pack

program_from_source = compile_source("target/main.rif")
program_from_pack = compile_pack("build/target.pack")
```

Use MIR APIs for phase 2:

```python
from MIR import compile_mir_source, compile_mir_file

result = compile_mir_source("build/target.pack", "mov rax\n")
result = compile_mir_file("build/target.pack", "program.mir")
```

Do not treat `CompiledRuleSet` as an external MIR program. It is the compiled
target instruction set and context that the MIR phase consumes.
