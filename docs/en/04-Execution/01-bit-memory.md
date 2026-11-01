# Bit Memory

RIF writes bits directly into `BitBuffer`. The buffer is not restricted to
whole bytes, so a field can begin or end at any bit offset.

## Physical Cursor

Normal emission advances the physical cursor, exposed as `::SIZE`:

```rif
. nibbles 0000 0001
. emit 1 0 1 0 1 0 1 0
. eword 4660
. bits 5 3
```

`eword` uses `word_size`. `nibbles` and `emit` have fixed widths. `bits` takes
an explicit value and width and is useful for arbitrary fields.

## Rewriting Existing Bits

```rif
. read_bits 0 8
. patch_bits 0 8 255
```

`read_bits OFFSET WIDTH` reads a physical range and pushes its integer value to
the datastack. `patch_bits OFFSET WIDTH VALUE` rewrites an allocated range and
does not advance either cursor. An out-of-range operation fails before changing
the buffer.

For widths divisible by eight, the configured `byte_order` is used. Other
widths are read and written according to `bit_order`.

## Padding and Alignment

```rif
. pad 3
. align 16
```

Both emit zero bits and advance physical and virtual positions. `pad` adds
the exact width. `align N` adds the number of bits required to reach the
next multiple of `N`. These bits are recorded as padding in the active
`RuleTrace`.

Virtual-only operations are useful when the target has a separate address
layout:

```rif
. vpad 8
. valign 32
```

They advance only the virtual cursor, exposed as `::VSIZE`. Their widths are
recorded as virtual padding.

## Reservations

```rif
. reserve "header" 16
. write_res "header" 0000000011111111
. emit_res "header"
. drop_res "header"
```

Physical reservations append zero-filled bits and keep a named span. `write_res`
rewrites that span, `emit_res` copies its current value to the output cursor, and
`drop_res` removes the name while leaving already emitted bits untouched.

Virtual reservations do not write physical bits:

```rif
. vreserve "scratch" 64
```

`resdir`, `resvdir`, `reswidth`, and `vreswidth` query reservation metadata.
`resdist` and `resvdist` calculate the distance from the current cursor.

## Rule Traces

Every Rule invocation produces a `RuleTrace` containing physical and virtual
start, width, end, and padding fields. Nested Rules receive independent traces;
the parent span includes the output produced by its children.

## Low-Level Buffer API

Python callers that need direct memory control can use `BitBuffer`:

```python
query = buffer.query("header")
bits = buffer.read_bit_sequence(0, 12)
checkpoint = buffer.checkpoint()

with buffer.transaction():
    buffer.write_bits(0, 3, 2)
```

`rollback(checkpoint)` restores storage, bit length, and named regions.
`transaction()` rolls back automatically when its body raises. `to_bytes()`
returns a masked serialized copy; `view()` returns a live byte-level view.
`BitQuery` exposes the integer value, individual bits, span, and aligned raw
bytes when the queried range covers complete bytes.

`AssemblyImage.render()` can render configured sections using `format section`,
`format section_end`, `entry`, `format label_end`, `comment`, and section alignment.
