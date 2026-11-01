# Variants

Variants allow one root RIF target to delegate syntax to another RIF file, for
example an ARM state and a Thumb state.

## Declaration in the Root

```rif
@SUPPORTS thumb

@ASMVARIANT thumb:
.MODE SWITCH
.ENTER "ENTER_thumb"
.EXIT "EXIT_thumb"
@END
```

The variant file is named `thumb.rif` and is resolved according to the linker
`search_path` directories, in declaration order. A variant file may contain
only definitions and Rules:

```rif
@define thumb_word

@rule ENTER_thumb:
. KW "thumb"

@rule EXIT_thumb:
. KW "endthumb"
```

The root tables, configuration, linker, and other global context remain shared.
The variant does not create a second Gram session or an independent symbol
space.

## Modes

`SWITCH` describes a state change in the target assembler. `ENCAPSULATE`
describes a nested syntax region. Both modes use `.ENTER` and `.EXIT` Rules to
define how the transition is emitted and closed.

RIF detects duplicate variant loads and cycles. Before execution, it validates
that every `.ENTER` and `.EXIT` Rule exists in the shared Rule set.

## Package Variants

When a target is packed, variant source files are included in the source graph.
The package's dependency order allows the variant files to be loaded without
filesystem lookups at runtime.
