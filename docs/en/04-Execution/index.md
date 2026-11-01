# 04. Execution

The execution layer runs resolved Rules against MIR tokens and writes to a
sectioned, bit-addressable output image.

| Guide | Summary |
| :--- | :--- |
| [01. Bit Memory](./01-bit-memory.md) | Physical and virtual positions, emission, reservations, and rewrites. |
| [02. Datastack](./02-datastack.md) | Temporary value storage and table-driven widths. |
| [03. Variants](./03-variants.md) | Loading and delegating to ISA variants. |
| [04. Diagnostics and Testing](./04-diagnostics-and-testing.md) | Runtime errors, traces, and verification. |
| [05. Binary Artifacts](./05-binary-artifacts.md) | Inserts, final patches, native queries, and physical/virtual layout. |
| [06. Rule Operation ABI](./06-rule-operation-abi.md) | The closed C/AOT primitive contract used by Rules. |

## Runtime Objects

`RIFMachine` executes a `CompiledRuleSet`. It owns the current MIR token
stream, token position, Rule call stack, saved token storage, table selections,
datastack, reservations, and Rule traces. `BitEmitter` writes through a
`BitBuffer`, while `AssemblyImage` provides one buffer for each configured
section.
