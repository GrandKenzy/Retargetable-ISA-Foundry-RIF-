# Rule Operation ABI

RIF Rules use generic operations to match tokens, select table data, emit
fields, reserve ranges, and resolve relocations. The current operation ABI
defines the small pure primitive layer that can be mirrored by a C/AOT
runtime.

## Design boundary

The ABI is not a second instruction set and it is not a Python plugin system.
It does not serialize callbacks, import `funcs.py`, or expose a live Python
`RIFMachine` to arbitrary code. A target still describes its semantics with
Rules and extensible tables.

The ABI exists so a primitive used by Rules has one stable contract in the
Python runtime and in a future native runtime.

## Current primitives

The public operation table currently contains:

| Operation | Inputs | Result |
| :--- | :--- | :--- |
| `fit_unsigned` | value, width, truncate | masked unsigned bit value |
| `fit_signed` | value, width, truncate | two's-complement bit value |
| `encode_relocation` | value, width, mode | encoded `pc` or `abs` value |

The Rules `fit`, `fit_signed*`, and generic relocation classes use these
primitive checks. Target-specific names and operand classes remain table data,
not hardcoded operation names in the core.

## Inspecting the ABI

```python
from MIR.operations import operation_abi, operation_abi_json

print(operation_abi())
abi_bytes = operation_abi_json()
```

Every descriptor includes its name, arity, result kind, C symbol, and whether
the operation is deterministic. The operation ABI version is independent from
the target's table contents and is included in the runtime contract.

## C surface

The C declarations and reference implementation are available as strings for
a native build system:

```python
from MIR.operations import operation_c_header, operation_c_source

header = operation_c_header()
source = operation_c_source()
```

The scalar C ABI returns zero for success and a non-zero validation error. Its
scalar representation supports widths from 1 through 64 bits. Wider dynamic
fields remain available to the Python bit-oriented runtime; a future byte-span
extension must use a new ABI version rather than silently changing scalar
signatures.

## Signed and relative values

Signed fitting checks the mathematical signed range before encoding:

```text
8-bit signed range: -128 .. 127
-1 encoded in 8 bits: 11111111
```

Relative relocations use the signed range and encode the resulting two's
complement bits. Absolute relocations require a non-negative value that fits
the declared width. A failed range check occurs before any output patch is
committed.

## `#call[...]` is not arbitrary Python

The syntax remains reserved for closed native operations. An unregistered
name is rejected deterministically. Use ordinary Rule primitives and the
operation ABI for target behavior; do not expect a Python callback to inspect
or mutate the runtime.

This restriction keeps `.pack` artifacts portable, lets the AOT path preserve
the same contract, and prevents an apparently declarative target from
executing untracked host code.
