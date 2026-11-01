# Native functions

RIF does not load or execute `funcs.py`. Language functions must be
deterministic, registered inside RIF, and use primitive contracts so they can
be mirrored by the C backend.

## `calc`

The first native function is `#:calc`, available in `::RIF_PATCH` expressions:

```rif
::RIF_PATCH 0, 4, #:calc(4096 + 128)
::RIF_PATCH 4, 4, #:calc(8192 - 4096)
```

Only `+` and `-` are supported. The result width is the widest operand width.
Results outside signed `int64` are rejected before the patch is applied.

The canonical implementation lives in `MIR/functions/calc.py`; it does not
depend on runtime state, Rule state, or project modules.

## `reqsts`

`reqsts` downloads raw bytes from GitHub during the buffer's external phase.
The branch is mandatory and must be the final path segment:

```rif
::RIF_BUFFER SET 512
::RIF_BUFFER CLEAN
::RIF_REQSTS "github.com/GrandKenzy/RIFIMG/images/img.bin/main"
::RIF_BUFFER EXTRACT 0 8
```

Only `.bin` files, HTTPS, and official GitHub hosts are accepted. Size,
timeout, redirects, and HTTP responses are validated before returning bytes.
Failures are printed through Gram's `Diagnostics` and then propagated as
compilation errors; `DiagnosticsLite` remains reserved for the C AOT
lexer/parser.

## `#call[...]`

The `#call[name]` form is reserved for future closed native functions. It does
not load external Python, and an unregistered name produces a deterministic
error.
