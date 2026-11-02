# 05.01. Authoring PCP-I Templates

Use a `.pci` source file for a human-readable PCP-I template. The current
compiler does not require a particular filename suffix, so existing projects
may also use `.pcpi`; `.pci` is the documented source name.

## Minimal source

```text
MAGIC "pcpi"
VERSION 1
ENDIANNESS 1
BITORDER 1
SIGNATURE "Example header"
PADDING 0

@RAW
AA BB CC
ZERO 5
[8]
10 20
@END
```

The header is followed by exactly one `@RAW` region. `@END` terminates the
source, and no content may follow it. Semicolon comments and blank lines are
ignored.

## Header fields

| Field | Values | Meaning |
| :--- | :--- | :--- |
| `MAGIC` | exactly `"pcpi"` | Selects PCP-I. |
| `VERSION` | `1` | Selects the current PCP-I format. |
| `ENDIANNESS` | `1` or `2` | Metadata for little- or big-endian consumers. It does not rewrite raw bytes. |
| `BITORDER` | `0` or `1` | Metadata for LSB- or MSB-first consumers. It does not rewrite raw bytes. |
| `SIGNATURE` | non-empty UTF-8 string | Human-readable identity, limited to the PCP-I signature field. |
| `PADDING` | non-negative integer | Number of static zero bytes before the raw image. Defaults to `0`. |

The current compiler stores the metadata but does not reinterpret literal
bytes based on `ENDIANNESS` or `BITORDER`. If bytes must be reversed or
encoded, write the final byte order in the source or perform that operation in
the host producer.

## Raw bytes and static zeros

The raw region accepts two-digit hexadecimal byte tokens, with an optional
`0x` prefix:

```text
@RAW
7F 0x45 4C 46
ZERO 1024
00
@END
```

`ZERO n` emits exactly `n` fixed zero bytes. It does not create a future field,
an index record, or an alignment boundary. Use it for reserved space,
descriptor padding, and unused sectors.

## Pits

`[n]` creates one fillable pit of exactly `n` bytes:

```text
@RAW
01 02 03
[8]
FF
@END
```

Pits must have a positive size. PCP-I aligns each pit address to eight bytes by
inserting static zero bytes immediately before it when necessary. Those
alignment bytes are not part of the pit. In this example, the pit begins at
raw-image address `8`, has size `8`, and has `5` bytes of alignment padding.

The distinction is intentional:

```text
ZERO 2048   ; fixed zero bytes
[2048]      ; a 2048-byte field that must be filled later
```

Every pit is numbered in source order, starting at `0`. A later consumer must
replace each pit with exactly its declared size. PCP-I never truncates,
extends, or infers a replacement.

## What the compiled `.pcic` contains

The compiled container is validated before it is written. Its layout is:

```text
fixed PCP-I header (144 bytes)
PADDING bytes
raw template image
generated trailing alignment (RPAD)
pit table
```

Pit addresses are relative to the beginning of the raw template image, not to
the beginning of the `.pcic` file. The `.pcic` header and pit table are useful
to tools that inspect or render the template; they are not part of the payload
that `::RIF_PCPI SET` emits into MIR.

## Design rules

- Keep format metadata in `ENDIANNESS` and `BITORDER`; do not assume those
  fields transform bytes automatically.
- Use `ZERO` for static space and `[n]` only for a field owned by a later
  producer.
- Keep pits small and semantically clear. A large pit transfers ownership of
  every byte in that range to the later fill step.
- Do not put filesystem records, boot code, cursor data, or a complete ISO in
  a header-only PCP-I template unless the host format explicitly owns those
  bytes.
- Treat the compiled `.pcic` as an intermediate artifact, not as a bootable
  disk image.

For the complete binary header, pit-record structure, and address-space rules,
see [03. Compilation / PCP-I](../03-Compilation/06-pcp-i.md).
