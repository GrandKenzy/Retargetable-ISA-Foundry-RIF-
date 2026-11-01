# 02. Language

RIF source is line-oriented. Gram preserves newline tokens, and Rule bodies use
one instruction per line. Comments begin with `;`.

| Guide | Summary |
| :--- | :--- |
| [01. Source Structure](./01-source-structure.md) | Root declarations, ordering, comments, and the basic file shape. |
| [02. Configuration and Linker](./02-configuration-and-linker.md) | Target sections, output policy, and MIR file discovery. |
| [03. Tables and Loads](./03-tables-and-loads.md) | Immutable indexed tables, `@LOAD`, and source scopes. |
| [04. Rules and Values](./04-rules-and-values.md) | Rule instructions, token references, table access, and value expressions. |
| [05. Reusable Pattern Libraries](./05-reusable-pattern-libraries.md) | Portable `.riflib` packages and `@LIBRARY`. |

## Minimal Shape

```rif
@block config:
    ; target directives go here
@end

@block linker:
    ; linker directives go here
@end

@table registers
| name | bits |
__
| rax | 64 |
@end

@rule mov:
. IDENT
. fit $registers.bits
```

The complete target must provide the required configuration directives before
it is used to compile external MIR.
