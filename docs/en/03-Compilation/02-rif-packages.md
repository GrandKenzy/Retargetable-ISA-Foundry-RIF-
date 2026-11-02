# RIF Packages

`.pack` is RIF's portable target package. It is a reproducible ZIP archive
containing the RIF source graph and, when requested, a precompiled SQLite
database.

## Creating a Package

```powershell
vnma run main.py --pack main.rif
vnma run main.py --pack main.rif -o targets/amd64.pack
```

The package includes:

```text
manifest.json
sources/main.rif
sources/other.rif
compiled/program.sqlite3 (when precompiled)
```

The actual compiled database path is `compiled/program.sqlite3`.

The manifest records the package format, contract version, source hashes, the
`@LOAD` graph, dependency order, referenced `.riflib` packages, and the
optional compiled database. The
contract identifies the compatible RIF, Gram/GIR, AOT FFI, SQLite, and runtime
combination; artifacts from another combination are rejected before MIR is
processed. External MIR directives
are not part of the package source graph; `::RIF_INSERT FILE` resolves its path
relative to the MIR file being compiled.

Reusable libraries can be created with `vnma run main.py --library
patterns/main.rif -o patterns.riflib` and consumed from a target with
`@LIBRARY "patterns.riflib"`.
When creating a `.pack`, RIF embeds and verifies those libraries under
`libraries/`. A complete `.pack` can also be exported into a declaration-only
`.riflib`:

```powershell
vnma run main.py --library base.pack -o reusable-patterns.riflib
```

That export keeps the package's explicitly loaded declaration sources and
discards its root `config`, `linker`, and generic blocks. The consuming target
therefore chooses its own output policy and platform metadata. A `.pack` is a
complete target and is not implicitly merged into another target.

## Why Use a Package?

A package resolves and validates the source graph before the target is used.
With precompilation enabled, it also stores the compiled Rule Set, configuration,
linker context, defines, and table rows in SQLite. Opening the package can then
load the target without parsing every source file again.

Packages are especially useful when:

- a target has many loaded `.rif` files;
- tables are large;
- multiple MIR programs use the same target;
- the target must be distributed as one artifact.

## Package Validation

RIF validates manifest paths and SHA-256 hashes. It rejects missing load
dependencies, load cycles, tampered source files, incompatible compiled schema
versions, and invalid package metadata.

The package remains a target definition. It does not contain the external MIR
program or the final binary unless the caller writes that output separately.

## Safe inspection

The package inspector always verifies the ZIP, hashes, limits, content
fingerprint, and compiled SQLite database. It does not execute Rules, activate
frontend globals, load plugins, or extract files:

```powershell
vnma run main.py --inspect-pack target.pack
vnma run main.py --inspect-pack target.pack --json
vnma run main.py --inspect-pack target.pack --verbose --max-items 200
```

The report includes package format and version, contract fingerprint, sources,
libraries, assets, Rules, tables, configuration, linker, variants, and accepted
MIR extensions.
`--json` emits stable machine-readable output; `--verbose` adds instructions
and rows, still bounded by `--max-items`. Creator absolute origin paths remain
hidden unless `--show-origins` is supplied.

MIR compilation can also emit an optional map without changing the binary:

```powershell
vnma run main.py target.pack program.mir -o program.bin --map program.map.json
```

The map records the contract, binary hash and sizes, sections, symbols,
executed Rules, and resolved relocations.
