# Reusable Pattern Libraries

A `.riflib` is a portable source library for RIF declarations. It is useful
when several targets share patterns such as register metadata, common field
layouts, token definitions, or generic Rules, but the library must not force a
particular processor or output policy on its users.

## Creating a library

Place the reusable `.rif` sources in a small project directory and choose one
source as its entry point:

```powershell
vnma run main.py --library patterns/main.rif -o build/patterns.riflib
```

The command creates a reproducible ZIP archive containing a manifest and the
library's `.rif` source graph. The archive is source data, not a second
executable compiler.

The Python API is also available:

```python
from rif_library import create_library

create_library("patterns/main.rif", "build/patterns.riflib")
```

For a complete target package, the CLI can export the explicitly loaded
declaration sources without carrying over target policy:

```powershell
vnma run main.py --library base.pack -o build/base-declarations.riflib
```

The export omits the package root's `config`, `linker`, and generic blocks.
Use this boundary when a new target should reuse Rules or tables but select a
different memory layout or platform contract.

The manifest records the entry point, source sizes, SHA-256 hashes, `@LOAD`
dependencies, dependency order, and one content fingerprint for the complete
library.

## Consuming a library

Load a library from the root target source:

```rif
@LIBRARY "patterns.riflib"

@rule mov:
. IDENT
. JUMP encode_register
```

The declarations from the library enter the same target context as local
declarations. A library can provide `@define`, `@table`, `@rule`, and local
`@LOAD` declarations. It cannot replace the consuming target's `config` or
`linker` policy.

The path is relative to the source that contains `@LIBRARY`. Paths must stay
inside the project or package boundary, must end in `.riflib`, and are checked
before source processing.

## Library design rules

Good library contents are target-neutral building blocks:

```rif
@table fields
| name | width | kind |
_____________________
| "opcode" | 8 | "bits" |
_____________________
| "modrm" | 8 | "bits" |
@end

@define register
@define immediate
```

The consuming target decides how those values are interpreted. Keep output
sections, entry metadata, address bases, linker extensions, and platform
policy in the target itself unless the library is intentionally a complete
target family.

Tables are fully extensible. A library does not need to create a special
register schema: it can declare any number of tables with any columns that
its Rules use. The consuming target can add other tables and use them in the
same Rules.

## Local loads inside a library

The library can split its declarations:

```rif
@LOAD "tables.rif"
@LOAD "rules.rif"
```

Those paths are indexed into the `.riflib` manifest. Cycles, missing files,
duplicate archive members, invalid hashes, and paths outside the library are
rejected. A library is loaded once per target compilation, even if multiple
source files request it.

## Packaging a target that uses a library

When a target is packed, referenced libraries are embedded under `libraries/`
and included in the package content fingerprint:

```powershell
vnma run main.py --pack target/main.rif -o build/target.pack
```

The resulting package is portable. Compilation from the package does not need
the original creator's absolute library path or an external extraction step.
Changing the library bytes changes the package fingerprint and invalidates a
precompiled target cache that depended on them.

## Name collisions

Definitions, tables, and Rules share the target's normal uniqueness rules.
Loading two libraries that declare the same name is therefore an error unless
the declarations are moved or renamed. RIF does not silently choose one
library's definition over another.

## What libraries do not do

`.riflib` does not:

- add a hidden instruction set to RIF;
- execute Python code;
- install a host assembler or linker;
- define a second configuration or memory image automatically;
- bypass target validation or package integrity checks.

It is a reusable source layer. The final semantics still come from the target
that consumes the library.
