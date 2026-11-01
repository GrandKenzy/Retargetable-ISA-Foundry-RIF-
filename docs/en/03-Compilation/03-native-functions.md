# Native Operations

RIF does not load or execute an arbitrary `funcs.py` module. Operations that
participate in the RIF toolchain are closed, explicit, bounded, and expressed
through primitive contracts so they can be reproduced by the C/AOT side.

The operation ABI used by Rule primitives is documented in
[Rule Operation ABI](../04-Execution/06-rule-operation-abi.md). It is not a
general Python extension mechanism.

## `calc`

The built-in arithmetic operation `#:calc` is available in `::RIF_PATCH`
expressions:

```rif
::RIF_PATCH 0, 4, #:calc(4096 + 128)
::RIF_PATCH 4, 4, #:calc(8192 - 4096)
```

Only `+` and `-` are supported. The result width is the widest operand width.
Results outside signed `int64` are rejected before the patch is applied.

The canonical implementation is deterministic and does not depend on runtime
state, Rule state, or project modules. It is intended for external binary
patch expressions, not as a way to inject host code into a Rule.

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
compilation errors.

## `#call[...]`

## Rule operations and `#call[...]`

The Rule operation table currently covers the pure checks used by `fit`,
`fit_signed*`, and generic relocation encoding. The table can be inspected
through the public Python API and mirrored by a C implementation, but it does
not expose the live runtime as a callback interface.

The `#call[name]` form remains reserved for closed native operations. It does
not load external Python, and an unregistered name produces a deterministic
error. Use tables and ordinary Rule instructions for target behavior.
