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

The external preprocessor also recognizes `::RIF_BUFFER`, `::RIF_REQSTS`, and
`::RIF_STORE`. These directives acquire bounded bytes, load a labeled payload
from a validated `.bin` storage container, or extract a buffer range. Their
syntax and safety rules are documented with the external MIR interface.

The old `@insert`, `@before`, `.bytes`, `.binary`, `.file`, and `.patch` blocks
are not valid `.rif` syntax and are not compatibility aliases.
