# RIF Packages

`.pack` is RIF's portable target package. It is a reproducible ZIP archive
containing the RIF source graph and, when requested, a precompiled SQLite
database.

## Creating a Package

```powershell
rif --pack main.rif
rif --pack main.rif -o targets/amd64.pack
```

The package includes:

```text
manifest.json
sources/main.rif
sources/other.rif
compiled.sqlite          (when precompiled)
```

The manifest records the package format, source hashes, `@LOAD` graph,
dependency order, and the optional compiled database. External MIR directives
are not part of the package source graph; `::RIF_INSERT FILE` resolves its path
relative to the MIR file being compiled.

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
