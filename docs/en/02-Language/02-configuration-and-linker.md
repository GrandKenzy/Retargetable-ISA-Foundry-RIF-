# Configuration and Linker

The `@block config` block describes the output format. The `@block linker`
block describes the external MIR input.

## Configuration

```rif
@block config:
    format section ".section"
    section text "rx"
    section data "rw"
    section bss "rw"
    format section_end ":"
    entry text "_start"
    format label_end ":"
    default text
    align text 4
    align data 4
    align bss 4
    word_size 32
    address_size 32
    byte_order little
    case_sensitive true
    symbol_prefix "_"
    local_prefix "."
    undefined_symbols "error"
    duplicate_symbols "error"
    strict true
    allow_empty_sections false
    bit_order msb
@end
```

The main entries are:

| Entry | Meaning |
| :--- | :--- |
| `format section` | Prefix used to render an output section. |
| `format section_end` | Terminates a rendered section header. |
| `format label_end` | Label terminator. |
| `section` | Declares a section and its output flags. |
| `entry` | Defines the entry section and label. |
| `default` | Section selected when no section is supplied. |
| `align` | Physical and virtual section alignment in bytes. |
| `vaddr` | Explicit virtual base for a section. |
| `word_size` | Width used by `eword`, in bits. |
| `address_size` | Target address width, in bits. |
| `byte_order` | `little` or `big`. |
| `bit_order` | `msb` or `lsb`. |
| `case_sensitive` | Controls case matching for external Rule names. |
| `symbol_prefix` | Prefix for rendered symbols. |
| `local_prefix` | Prefix for local symbols. |
| `undefined_symbols` | `error`, `warn`, or `ignore`. |
| `duplicate_symbols` | `error`, `warn`, or `ignore`. |
| `strict` | Enables strict target policy. |
| `allow_empty_sections` | Controls empty section rendering. |

`format section`, `format section_end`, `format label_end`, `entry`, `default`,
`word_size`, `address_size`, and `byte_order` have useful defaults when
omitted. At least one `section` must be declared.

## Linker

```rif
@block linker:
    extension ".asm"
    search_path "variants"
    search_path "fallback"
@end
```

`extension` is the accepted external MIR extension. `search_path` controls
automatic file discovery used by linker features and variants. It may be
repeated; paths are tried in declaration order:

- `""` searches beside the main file.
- A folder string searches below that folder.
- `false` disables automatic searching.

The first folder containing the requested variant wins. `false` cannot be
combined with folder entries.

There is no separate main-source `name`: it did not participate in resolution
and has been removed from the linker model.

The linker configuration is target metadata; it does not itself compile the
MIR. The external compiler API validates the MIR extension before processing.
