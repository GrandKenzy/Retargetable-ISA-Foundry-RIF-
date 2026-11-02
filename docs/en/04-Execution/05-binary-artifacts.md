# External MIR binary directives

Binary preludes and final image patches belong to the external MIR program,
not to the `.rif` target definition. The preprocessor consumes these lines
before Rule dispatch and never sends them to a Rule.

## `::RIF_INSERT`

Insert bytes, binary strings, or a local file into a configured section:

```asm
::RIF_INSERT BYTES "7f454c46" SECTION text
::RIF_INSERT BINARY "00000001" SECTION text
::RIF_INSERT FILE "header.bin" SECTION text
```

`BYTES` requires complete hexadecimal bytes. `BINARY` accepts only `0` and
`1`; `FILE` accepts a relative path that stays below the MIR project root.
The directive is applied before the first external Rule line.

## `::RIF_PATCH`

Patches are evaluated after all Rule lines and after the final section layout
exists:

```asm
::RIF_PATCH 24, 8, #:calc(4194304 + #:qlsize(0, "_start"))
::RIF_PATCH 96, 8, #:qssize(0, "text")
::RIF_PATCH 104, 8, #:calc(#:qvssize(0, "text") - 4194304)
```

The optional width is measured in bytes. Native expressions are limited to
literal values, `+`, `-`, `#:calc`, `#:query`, `#:qssize`, `#:qlsize`,
`#:qvsize`, and `#:qvssize`. Arbitrary `#call[...]` callbacks are rejected.
All patches are validated before the final bytes are committed.

## Storage and acquisition

`.store` is a named byte-payload manifest, not only a media manifest. In
addition to `IMAGE` and `AUDIO`, it accepts opaque binary variables through
`BINARY`; the payload is copied byte-for-byte and no plugin is invoked:

```text
MAGIC "store"
VERSION 1

@ITEM BINARY
: "config.bin"
: "bin"
: "RAW"
: config_blob
@end
```

The label is the stable name used by `::RIF_STORE`. This keeps binary data
separate from RIF tables while allowing headers, lookup data, firmware blobs,
and other target-owned variables to share the same bounded indexed container.

Stores can also declare exact byte variables. The type fixes the width and
representation; integers and floats are little-endian, floats use IEEE-754,
and strings are UTF-8 without an implicit NUL terminator:

```text
MAGIC "store"
VERSION 2

str greeting = "Hello, world"
uint8 age = 30
int32 count = -2
float32 ratio = 13.0000
```

`i8`/`i16`/`i32`/`i64`, `u8`/`u16`/`u32`/`u64`, and `f32`/`f64` are accepted
as short aliases. Values are literals only; the store compiler does not run
expressions or attach runtime behavior.

Raw files can be added with a label derived from the filename, or with an
explicit alias:

```text
@FILE "myfile.bin"
@FILE "headers/boot.dat" AS boot_header
```

`@REQST` is a VERSION 2 store operation. It reuses the bounded binary fetcher
already used by MIR and keeps the same HTTPS/GitHub-only and size-limit rules:

```text
@REQST algo "github.com/owner/repository/path/data.bin/main"
```

Entries from another validated `RIFSTOR` container can be selected by label.
The `@end` is optional when the container is the final block in the file:

```text
@CONTAINER "variables/vars.bin":
    get etiqueta1
    get etiqueta2
@end
```

Container paths remain relative to the current `.store` directory, and the
selected labels are copied into the new storage with their original bytes.

The external preprocessor also recognizes `::RIF_BUFFER`, `::RIF_REQSTS`, and
`::RIF_STORE`. These directives acquire bounded bytes, load a labeled payload
from a validated `.bin` storage container, or extract a buffer range. Their
syntax and safety rules are documented with the external MIR interface.

The old `@insert`, `@before`, `.bytes`, `.binary`, `.file`, and `.patch` blocks
are not valid `.rif` syntax and are not compatibility aliases.
