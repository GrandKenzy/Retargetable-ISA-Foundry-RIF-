# Verification, Oracles, and Property Testing

RIF's verification tools are optional layers around the normal compiler. They
help compare emitted bytes and exercise boundary cases without making NASM,
LLVM, or a third-party fuzzing framework a runtime dependency.

## Test layers

Run the always-required suite first:

```powershell
vnma test
```

Run the additional suites explicitly:

```powershell
vnma test suite-aggressive
vnma test dedicated-suite
```

The essential suite is intended for every change. It covers the target
contract, parser and AOT boundary, tables, Rules, packages, layout, MIR
execution, fixups, and failure paths. The aggressive suite contains stress,
benchmark, and property cases. The dedicated suite contains external-tool,
format, plugin, and API-specific checks that may need attention when a public
API changes.

## NASM and LLVM MC oracles

The external encoders are discovered only when a test or user script asks for
them. Their absence is a clear unavailable result; it does not prevent RIF
from compiling.

```python
from rif_tools.oracles import (
    assemble_llvm_mc,
    assemble_nasm,
    compare_bytes,
    oracle_status,
)

print(oracle_status())

nasm = assemble_nasm("nop")
compare_bytes(b"\x90", nasm, label="NASM nop")

llvm = assemble_llvm_mc("nop\n")
compare_bytes(b"\x90", llvm, label="LLVM MC nop")
```

Each oracle process has a timeout and an output limit. NASM is invoked in flat
binary mode. LLVM MC is invoked with `-show-encoding` and its encoding comments
are parsed into bytes. The helper returns the tool name, command, bytes, and
diagnostic output so a mismatch can be reproduced.

An oracle is a comparison aid, not the source of RIF semantics. If the target
intentionally describes a raw format or a custom encoding, the target's
contract and independent expected bytes remain authoritative.

## Deterministic properties

Property tests use a local pseudo-random generator and an explicit seed:

```python
from rif_tools.properties import integer_cases, run_property

generator = integer_cases(
    minimum=-128,
    maximum=127,
    edge_values=(-128, -1, 0, 1, 127),
)

run_property(
    generator,
    lambda value: -128 <= value <= 127,
    cases=500,
    seed=0x524946,
    name="signed-input-range",
)
```

When a property fails, the failure contains the property name, seed, case
index, input value, and reason. Re-run the same seed to reproduce it exactly.
Use edge values deliberately: zero, maximum and minimum widths, signed
boundaries, empty sections, alignment boundaries, and forward references are
usually more valuable than an unbounded stream of random text.

## What to fuzz

For a target author, useful generated cases include:

- register and table keys, including duplicate and unknown keys;
- immediate values at `2^n - 1`, `2^n`, `-2^(n-1)`, and `2^(n-1)`;
- valid and invalid ModR/M, SIB, prefix, and displacement combinations;
- symbol orderings with forward and backward references;
- section alignments, zero-length sections, and virtual-only reservations;
- MIR lines with missing, extra, or incorrectly typed operands.

Keep expensive executable-generation or host-assembler tests outside the
essential suite. A property that depends on NASM or LLVM should be skipped
explicitly when the tool is not installed.

## Independent expected bytes

An oracle comparison is strongest when the test has three clear pieces:

1. a target-generated binary;
2. a separately defined expected byte sequence or external encoding;
3. a diagnostic that identifies the first differing offset.

Do not make the test derive both the expected value and the RIF value from the
same table row. That can reproduce a table mistake without detecting it.
