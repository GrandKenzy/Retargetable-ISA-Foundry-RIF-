# Tables and Loads

Tables are declared as a header row, separator row, and one or more data rows.
They are materialized as a matrix while keeping a constant-time column map.

```rif
@table registers
| name | opcode | bits |
________________________
| mov  | 1      | 32   |
________________________
| add  | 2      | 32   |
@end
```

The separator must contain at least two consecutive `_` characters. A
separator is required between rows, and each row must end with `|` before its
newline. With `ident_underscores = -2`, Gram emits it as
`Token.UNDERSCORES`.

## Table Access

The selected row can provide a value to an instruction:

```rif
. $registers.name, IDENT
. nibbles $registers.opcode 0000
```

The first form matches the current token against the `name` column and selects
that row. Later accesses to `$registers.bits` read from the selected row.

Static indexed access selects a row without consuming a MIR token:

```rif
. fit $registers.name[rax].bits
```

RIF materializes the table as an immutable matrix and builds constant-time
indexes for every column. Auxiliary columns may contain duplicates; a column
must be unique only when it is used to select a row.

## Table operations

Table declarations can derive columns from another table. The selector in
brackets is taken from the current row, and the source column becomes the
derived column name:

```rif
@table membase
| name | %[name]=registers.lo% | %[name]=registers.hi% | sib |
__
| rax | %othertable.name[r12].sib% |
@end
```

`%[name]=registers.lo%` looks up `registers.name` using the current row's
`name` and copies `registers.lo`. Derived columns are omitted from row cells;
the remaining cells fill the literal columns in header order. A cell lookup
such as `%othertable.name[r12].sib%` selects the unique row whose `name` is
`r12` and copies its `sib` value.

Operations are resolved while tables are materialized. Forward references are
allowed, but missing tables, missing columns, missing keys, duplicate selector
keys, and dependency cycles are errors. The resulting `.pack` stores only the
resolved immutable matrix, so the runtime and AOT backend do not need a second
table-expression evaluator.

## Loading Additional Sources

`@LOAD` includes another `.rif` source relative to the current source:

```rif
@LOAD "tables.rif"
@LOAD "rules.rif"
```

The loader requires the `.rif` extension, resolves paths canonically, detects
cycles, and preserves declaration scope. A loaded file can contain tables and
Rules, but it cannot redefine root configuration or linker settings.

For declarations shared across projects, create a `.riflib` and load it with
`@LIBRARY`:

```rif
@LIBRARY "common-patterns.riflib"
```

Unlike a local `@LOAD`, a library is a reproducible package with its own
manifest and content hash. It is embedded automatically when the consuming
target is packed.

## Tables in Packages

When a `.pack` is created, loaded source files are recorded in the package
manifest and their dependency order is resolved ahead of execution. Precompiled
packages store table rows in SQLite. The runtime recreates the immutable matrix
and its indexes when the package is opened.
