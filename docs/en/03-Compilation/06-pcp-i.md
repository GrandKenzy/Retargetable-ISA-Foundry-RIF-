# PCP-I: Declarative Binary Templates and Fillable Regions

PCP-I is RIF's small, standalone format for describing a binary image that
contains fixed bytes and explicitly fillable regions. It is useful when a
binary format has a stable envelope but some fields depend on a later layout
pass. ISO/El Torito headers are one example.

PCP-I is intentionally not part of the `.rif` target language. It does not
define Rules, tables, operands, instruction encodings, an assembler, a linker,
an ISO filesystem, or a bootloader. It is a declarative binary-template tool
that can be consumed by the external MIR preprocessor.

The core pipeline is:

```text
header.pci --comp-pcpi--> header.pcic --fill/render--> bytes for a later producer
                                      \
                                       `::RIF_PCPI SET` in external MIR
```

The `.pcic` file is a validated PCP-I container. It is not automatically the
final image that an operating system, firmware, or QEMU can boot.

## The names and their responsibilities

| Artifact or operation | Responsibility | Does not do |
| --- | --- | --- |
| `.pci` | Human-readable PCP-I template source | Execute RIF Rules or emit a final application image |
| `.pcic` | Validated binary PCP-I container with a template image and pit table | Become an ISO, executable, or boot image by itself |
| `ZERO n` | Emit `n` static zero bytes in the template image | Declare a fillable region |
| `[n]` | Declare an `n`-byte pit, aligned by the compiler | Define what value will be written later |
| `PADDING n` | Add zero bytes before the raw template image | Add bytes to the raw image or create a pit |
| `::RIF_PCPI SET` | Load a `.pcic` template and materialize its rendered payload in an MIR section | Insert PCP-I metadata or resolve pits by itself |
| `::RIF_PCPI FILL` | Replace one declared pit from MIR with exact hexadecimal bytes | Infer values, resize a pit, or render an ISO filesystem |
| `::RIF_PCPI PIT` | Report the address of one filled field in the rendered payload | Emit bytes or perform the fill |
| `compile_pcpi_source` | Compile and validate a source template in Python | Infer missing fields or resolve external symbols |

Keeping these responsibilities separate is important. A PCP-I header template
can be used by a later ISO builder, but PCP-I does not know the boot image,
filesystem files, cursor payload, or the final placement of those objects.

## Source format

A `.pci` source has a small header followed by one `@RAW` region:

```text
MAGIC "pcpi"
VERSION 1
ENDIANNESS 1
BITORDER 1
SIGNATURE "Example header template"
PADDING 32768

@RAW
01 43 44 30 30 31 01 00
ZERO 72
[8]
ZERO 40
[32]
ZERO 1888
@END
```

The header fields are:

| Field | Required | Meaning |
| --- | --- | --- |
| `MAGIC "pcpi"` | Yes | Selects the PCP-I format. The value is exact. |
| `VERSION 1` | Yes | Selects PCP-I version 1. |
| `ENDIANNESS 1` | Yes | Little-endian metadata. `2` selects big-endian metadata. It does not transform raw bytes. |
| `BITORDER 1` | Yes | MSB-first metadata. `0` selects LSB-first metadata. It does not reverse raw bytes. |
| `SIGNATURE "..."` | Yes | UTF-8 human-readable identity, from 1 to 100 bytes. |
| `PADDING n` | No | Zero-filled bytes placed before the raw image. Defaults to zero. |

The source compiler ignores blank lines and semicolon comments. Byte tokens are
exactly two hexadecimal digits, with an optional `0x` prefix, for example
`7F`, `00`, or `0xAA`.

`@RAW` and `@END` are required. No source content may appear after `@END`.
The raw region is processed in order, so its byte size and pit addresses are
deterministic.

### Static bytes and `ZERO`

Literal byte tokens write fixed bytes to the template. `ZERO n` writes exactly
`n` zero bytes and creates no pit:

```text
AA BB
ZERO 1024
CC
```

This produces 1027 static bytes. `ZERO` is useful for reserved fields,
descriptor padding, unused sectors, and large zero-filled areas. It does not
align the following item and it does not add a record to the pit table.

`ZERO 0` is a no-op. A negative or non-numeric size is invalid. `ZERO` is a
source directive only; the resulting `.pcic` contains the actual zero bytes.

### Pits

`[n]` declares a fillable byte range:

```text
01 02 03
[8]
FF
```

The compiler reserves `n` zero bytes and records a pit. Before the pit, it may
insert zero alignment bytes so that the pit address is a multiple of eight.
Those alignment bytes are static image bytes, not part of the pit. A pit must
have a positive size.

For the example above, the three literal bytes are followed by five static
alignment bytes, then an eight-byte pit. The pit has:

```text
address = 8
size    = 8
padding = 5
```

The `padding` value is metadata describing the alignment inserted immediately
before that pit. It is not a second fill region.

Pits are zero-filled in the template image. A zero-filled pit is a placeholder,
not a promise that zero is the final value. The consumer must replace it with
exactly the declared number of bytes.

### What is and is not a pit

This distinction is the most important PCP-I rule:

```text
ZERO 2040       ; 2040 fixed zero bytes, no pit
[16]            ; one fillable 16-byte region
```

Do not write `[2040]` when the bytes are meant to be static. That would create
a 2040-byte pit and force a later consumer to provide a replacement for all of
it. Conversely, do not use `ZERO n` for a field whose final value depends on a
later layout pass.

## Compiled `.pcic` container

`rif.py --comp-pcpi` validates the source and writes a binary `.pcic` file. A
version 1 container has this order:

```text
fixed PCP-I header (144 bytes)
explicit PADDING bytes
raw template image
generated RPAD bytes
pit table
```

The `PADDING`, image, and `RPAD` areas are zero-filled. The pit table describes
regions relative to the beginning of the raw template image, not relative to
the beginning of the `.pcic` file.

### Fixed header

The fixed header is little-endian metadata and has a total size of 144 bytes.
Its fields are:

| Field | Size | Meaning |
| --- | ---: | --- |
| magic | 4 | ASCII `pcpi` |
| version | 1 | PCP-I version, currently `1` |
| endianness | 1 | Source metadata value `1` or `2` |
| bitorder | 1 | Source metadata value `0` or `1` |
| flags | 1 | Reserved; must be zero |
| signature | 100 | UTF-8 signature, NUL padded |
| padding size | 4 | Number of bytes before the image |
| RPAD size | 4 | Number of generated trailing alignment bytes |
| image size | 8 | Raw template image size |
| pit count | 4 | Number of pit records |
| header size | 4 | Fixed value `144` for version 1 |
| reserved fields | 12 | Must be zero |

`image size` excludes both `PADDING` and `RPAD`. It is therefore the size of
the source `@RAW` result after pit alignment bytes have been inserted.

### Pit records

Each pit record is 20 bytes:

```text
uint64 address
uint64 size
uint32 padding
```

The records use the order in which pits appear in the source. Pit indexes are
zero-based. `address` and `size` are relative to the raw image. Records are
validated for positive size, eight-byte alignment, bounds, and non-overlap.

The compiled container is rejected if its header, lengths, reserved fields,
signature, padding, RPAD, image, or pit table is inconsistent. This validation
is performed both while compiling the source and when loading an existing
`.pcic`.

## Compiling and inspecting PCP-I

Compile a source template:

```powershell
vnma run rif.py --comp-pcpi examples/MiniOsExample/mini_os_iso_header.pci `
  -o examples/MiniOsExample/build/mini_os_iso_header.pcic
```

The output path must not overwrite the source `.pci`. If `-o` is omitted, RIF
uses the source path with a `.pcic` suffix.

Validate and inspect a compiled container without modifying it:

```powershell
vnma run rif.py --doctor-pcpi `
  examples/MiniOsExample/build/mini_os_iso_header.pcic
```

The doctor reports the version, signature, byte-order metadata, raw image size,
padding, RPAD, and every pit's relative address, size, and alignment padding.
It returns a non-zero status for a missing or malformed artifact.

The PCP-I compiler is independent of target compilation. These commands do
not load a `.rif`, `.pack`, or MIR program:

```powershell
rif --comp-pcpi header.pci -o build/header.pcic
rif --doctor-pcpi build/header.pcic
```

## Filling and rendering from Python

The Python API exposes a validated `CompiledPCPI` object:

```python
from pcpi_compiler import compile_pcpi_source

compiled = compile_pcpi_source("header.pci").image

# Replace pit 0 with exactly its declared size.
raw_image = compiled.fill(0, b"ABCDEFGH")

# Render the complete payload layout: PADDING + image + RPAD.
rendered = compiled.render({0: b"ABCDEFGH"})
```

`fill(index, value)` returns only the raw image and does not mutate the
`CompiledPCPI` object. `render(values)` returns the explicit leading padding,
the filled raw image, and the generated trailing padding. Every replacement
must have exactly the pit's declared size; PCP-I never silently truncates or
extends a replacement.

`to_bytes()` serializes the validated `.pcic` container. It serializes the
template image and its pit table; it does not apply a `render()` replacement.
A host image producer that wants a final binary should render or fill the
template, then assemble that result with its own payloads and format rules.

### Address spaces

There are three relevant address spaces:

1. **Raw-image address**: the `address` in a pit record. Offset zero is the
   first byte of `@RAW`.
2. **Rendered payload address**: raw-image address plus `PADDING` and any
   preceding image placement chosen by the host producer. `RPAD` follows the
   raw image.
3. **Container-file address**: raw-image address plus the fixed 144-byte PCP-I
   header and `PADDING`. The pit table is after the image and is not part of
   the rendered payload.

Confusing these spaces is a common source of incorrect patches. Always state
which representation a consumer expects before applying a pit address.

## External MIR integration

The external MIR preprocessor has three closed PCP-I directives:

```text
::RIF_PCPI SET "header.pcic"
::RIF_PCPI FILL 0 "0102030405060708"
::RIF_PCPI PIT 0
::RIF_PCPI PIT 1 SECTION text
```

### `SET`

`SET` must be the first non-empty MIR line. It loads and validates a `.pcic`
path relative to the MIR source. The current section must be byte-aligned and
only one `SET` is allowed. During final image construction, RIF materializes
the rendered PCP-I payload at that position:

```text
PADDING + resolved RAW image + RPAD
```

The fixed 144-byte PCP-I header and the pit table are never emitted by
`::RIF_PCPI SET`. The raw image is materialized with zero placeholders first
so later MIR lines keep stable offsets; before compilation succeeds, every pit
must be replaced by a matching `FILL` value. The committed output therefore
contains no unresolved PCP-I pits.

`SET` does not:

- fill pits by itself;
- insert the PCP-I header;
- insert the PCP-I pit table;
- append a boot image or filesystem;
- convert the container into an ISO;
- dispatch a RIF Rule.

`SET` plus `FILL` is the MIR path for producing the rendered raw payload. The
Python `render()` API remains available when a host producer needs to
materialize the template outside MIR.

### `FILL`

`FILL` replaces one pit in the rendered payload produced by `SET`:

```text
::RIF_PCPI SET "header.pcic"
::RIF_PCPI FILL 0 "0102030405060708"
```

The index is zero-based and the string is hexadecimal bytes. Spaces and
underscores may be used for readability, and an optional leading `0x` is
accepted. The decoded replacement must have exactly the pit's declared size;
short values, long values, malformed hex, nonexistent indexes, and duplicate
fills are rejected. `FILL` emits no additional bytes and does not change the
pit table or the PCP-I header.

Fills are collected while MIR is read and committed after Rules and final
fixups, together with the other final binary operations. The update is
transactional: if any fill is invalid, the output is not partially committed.
The replacement is written at the pit's rendered-payload position, so its
address includes `PADDING` but not the 144-byte PCP-I header or pit table.
`FILL` currently accepts literal hexadecimal bytes; layout-derived arithmetic
belongs in a separate `::RIF_PATCH` expression or host-side producer.

### `PIT`

`PIT index` emits no bytes. It records the absolute address of a filled pit in
the rendered payload emitted by `SET`. The optional `SECTION name` form queries
the final file offset of the named section. The address includes:

```text
section file offset
+ SET insertion offset
+ PADDING length
+ pit address inside the raw image
```

The result is exposed through `MIRCompilation.pcpi_pit_addresses` and can also
be printed by the CLI. It points into the rendered bytes in the MIR output;
there is no PCP-I header or pit table before that address.

`PIT` indexes are zero-based and must refer to an existing record. `PIT` must
follow `SET`. `FILL` also requires a preceding `SET`; it may appear before or
after ordinary Rule lines, but its replacement is committed only at final
image construction.

## ISO-9660 and El Torito use case

PCP-I can describe an ISO header template, but it does not implement ISO-9660.
For a BIOS-bootable image, a later producer still needs to create or append,
according to the chosen layout:

- the ISO system area and volume descriptors;
- the El Torito boot record and validation/default catalog entries;
- the boot image containing boot code;
- directory records and file data;
- any cursor or other assets;
- the final sector count and all fields that refer to final locations.

QEMU consumes a real ISO image through `-cdrom`; it does not consume a `.pcic`
container as an ISO. A PCP-I file named `iso_header.pcic` is therefore an
intermediate template artifact, not a bootable disk image.

The MiniOS example follows this separation:

```text
mini_os_iso_header.pci       declarative header template
mini_os_iso_header.pcic      validated PCP-I container
cursor_assets.store          source asset manifest
cursor_assets.storage.bin    indexed cursor payload
future mini_os.iso           final ISO assembled by a later producer
```

The header template contains no boot code, cursor bytes, filesystem, or final
ISO payload. Its pits identify fields whose values depend on the final layout;
its `ZERO` directives keep unused header bytes static without making them
fillable.

## Security and correctness rules

PCP-I applies strict bounded behavior:

- source and compiled artifacts are checked against the configured resource
  limit;
- signatures must be non-empty valid UTF-8 and cannot contain NUL bytes;
- versions, magic, metadata values, flags, reserved fields, and fixed header
  size are checked;
- padding and RPAD must contain only zero bytes;
- pit sizes must be positive and replacements must match exactly;
- pits must be aligned, within the raw image, and non-overlapping;
- source output is written atomically and cannot overwrite its own `.pci`
  source;
- MIR paths are resolved through the external preprocessor's path policy;
- malformed or out-of-range pit indexes are rejected.

PCP-I does not evaluate arbitrary Python callbacks, symbols, relocations, or
expressions. If a field needs arithmetic, symbol resolution, a relocation, or
knowledge of a later section, that calculation belongs to the host producer,
MIR preprocessor, or another explicitly defined RIF operation—not to the PCP-I
source parser.

## Common mistakes

| Mistake | Why it is wrong | Correct approach |
| --- | --- | --- |
| Treating `.pcic` as an ISO | `.pcic` has a 144-byte PCP-I header and pit table | Render/fill it, then assemble a real ISO |
| Using `[2048]` for a static sector | This creates a 2048-byte pit | Use literal bytes or `ZERO 2048` |
| Assuming `ZERO n` creates a future field | `ZERO` is fixed output | Use `[n]` for a field filled later |
| Using `FILL` with the wrong byte count | Pit replacements are exact-size | Match the declared pit size exactly |
| Filling a pit with a shorter or longer value | PCP-I is exact-size by design | Encode exactly the declared number of bytes |
| Treating pit addresses as file offsets | Pit addresses are raw-image-relative | Add the representation's header/padding/section base explicitly |
| Expecting `SET` to fill pits | `SET` only loads/materializes the template | Add one exact-size `FILL` for every pit |
| Adding boot code to a header-only template | It mixes format layers and hides ownership | Keep boot image and payloads as separate outputs |
| Sending PCP-I fields through a RIF Rule | PCP-I is not target syntax | Use `--comp-pcpi` or the external MIR directives |

## Source of truth in the implementation

The format is implemented by:

- `pcpi_compiler.py`: `.pci` parsing and source compilation;
- `pcpi.py`: `.pcic` serialization, loading, and validation;
- `rif.py`: `--comp-pcpi` and `--doctor-pcpi` CLI operations;
- `MIR/preprocessor.py`: syntax and ordering of `::RIF_PCPI` directives;
- `MIR/external.py`: container insertion and pit address reporting;
- `dedicated-suite/test_pcpi.py`: format, alignment, filling, and rejection
  tests;
- `examples/MiniOsExample/`: a header-only ISO/El Torito template and an
  independent external cursor payload.

When changing PCP-I, update the source compiler, binary validator, MIR
integration tests, and this guide together. In particular, never change the
meaning of `[n]`, `ZERO n`, container-relative addresses, or `SET` silently:
those meanings are the contract between the template producer and its consumer.
