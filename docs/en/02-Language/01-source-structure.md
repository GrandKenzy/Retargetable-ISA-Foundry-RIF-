# Source Structure

The root file is conventionally named `main.rif` and is the target's control
center. It may declare objects in any order; the processor registers
configuration, linker settings, defines, and supports before resolving tables
and Rules.

## Comments and Newlines

```rif
; This is a RIF comment.
@define mov ; comments can follow a declaration
```

Newlines are significant inside Rule bodies. There is no indentation grammar
for Rules, so these two forms have the same structural meaning:

```rif
@rule mov:
. IDENT
. eword 1
```

## Root-Only Declarations

The root scope may contain `@block config`, `@block linker`, `@table`, `@stack`,
`@SUPPORTS`, `@ASMVARIANT`, `@define`, `@rule`, `@LOAD`, and `@LIBRARY`.

Included files loaded with `@LOAD` may contain only `@define`, `@table`,
`@rule`, and more `@LOAD` directives. A `.riflib` package is a reusable source
library loaded with `@LIBRARY`; its declarations use the same target context.
Variant files loaded through
`@ASMVARIANT` may contain only `@define` and `@rule`.

Configuration can only be materialized by the root. If it is split into
`config.rif`, only `main.rif` may load that exact file directly, and the file
may contain only `@block config` and `@block linker`. An included file cannot
load it, and declaring `config` or `linker` more than once is an error.

This scope rule prevents a loaded file from silently replacing the target's
memory layout or linker policy.

## Generic blocks

The generic block form for declaring structured data is:

```rif
@block config:
    format section ".section"
    section text ""
    word_size 8
@end
```

Each line contains a name and zero, one, or two values before the newline. Dot
prefixes and the former `@config`/`@linker` headers are not accepted; a line
with more than two values is invalid.

`config` and `linker` blocks feed RIF's existing semantics directly.
Blocks with other names are preserved as structured data in
`program.context.blocks`, so specialized consumers can interpret them without
adding another parser rule.

## Definitions

`@define` registers a named language word:

```rif
@define mov
@define add
```

Definitions are labels in the RIF language. They do not allocate stack slots,
emit bits, or create runtime values.

## Rules

Rules are named instruction procedures:

```rif
@rule mov:
. IDENT
. nibbles 0000 0000
```

An external MIR line beginning with `mov` dispatches to this Rule. Every Rule
instruction begins with a dot; arrows are no longer part of the syntax. The
Rule consumes tokens, emits fields, calls other Rules, and updates runtime
state.

## Stack Declaration

The token stack is declared once:

```rif
@stack 50
```

It supports `save` and `load` for token-oriented control flow. It is separate
from the runtime `datastack`, which stores temporary values.
