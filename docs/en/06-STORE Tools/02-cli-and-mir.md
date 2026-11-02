# 06.02. Compiling and Consuming Storage

The STORE tool has a source stage and a consumption stage. The source stage
builds one validated indexed container. The external MIR stage selects a label
and emits only that entry's payload.

## Compile a `.store` source

```powershell
vnma run main.py --comp-store assets.store `
  -o build/assets.storage.bin
```

If `-o` is omitted, the compiler writes the source beside itself with the
`.storage.bin` suffix:

```powershell
vnma run main.py --comp-store assets.store
# writes assets.storage.bin
```

Compilation validates the source, keeps every label unique, resolves local
payloads relative to the source directory, runs only the declared media
converters, and writes the result atomically. The compiler never evaluates
typed values as program logic.

## Inspect a storage container

```powershell
vnma run main.py --doctor-storage build/assets.storage.bin
```

The doctor validates the `RIFSTOR` magic, version, header, raw region, index,
alignment, bounds, labels, and (for version 2) value-type metadata. It reports
the storage version, raw byte count, entry count, each entry's relative address,
payload size, alignment padding, label size, and label.

## Storage layout

The compiled file contains:

```text
fixed RIFSTOR header (48 bytes)
aligned raw payload region
fixed-width entry index
```

The current entry record is 24 bytes. Each entry points into the raw region and
may place its UTF-8 label immediately after its payload. The index is not part
of the payload returned by `RIF_STORE`.

Version 1 keeps the original raw entry format. Version 2 stores the declared
typed-value code in the existing entry metadata while preserving the same
header and entry sizes. Both versions are accepted by the loader; no version 3
format is emitted or accepted by current tools.

## Direct `RIF_STORE` use

The direct form selects a storage path, label, endianness, and order:

```asm
::RIF_STORE "build/assets.storage.bin" title 1 0
```

The numeric values are:

| Position | Values | Meaning |
| :--- | :--- | :--- |
| First number | `1` or `2` | `1` little-endian, `2` big-endian. |
| Second number | `0` or `1` | `0` LSB order, `1` MSB order. |

The insertion position must be byte-aligned. The selected label must exist, and
the path must have a `.bin` suffix. The storage header and index are never
emitted.

## Alias and per-storage layout

An alias avoids repeating the path:

```asm
::RIF_STORE AS GBA "build/gba.storage.bin"
GBA.ORDER 1
GBA.ENDIANNESS 1

::RIF_STORE GBA MODE_3
::RIF_STORE GBA DIR_VRAM
::RIF_STORE GBA DISPCNT
```

The path-first spelling remains accepted for existing MIR files:

```asm
::RIF_STORE "build/gba.storage.bin" AS GBA
```

Declare the alias before configuring or consuming it. `ORDER` accepts `0` or
`1`; `ENDIANNESS` accepts `1` or `2`. The alias and its configuration belong to
one MIR compilation and are not global project state.

For a version 2 typed scalar, `ENDIANNESS 2` reverses each complete scalar
element into big-endian byte order when it is inserted. Strings, images, audio,
`BINARY`, `@FILE`, `@REQST`, and other opaque raw entries remain byte-for-byte.
The current typed scalar set is byte-aligned, so `ORDER` is validated and
retained as layout metadata but does not change the emitted bytes by itself.

Explicit numeric arguments override the alias defaults for that one use:

```asm
::RIF_STORE GBA MODE_3 2 0
```

The alias form without numeric arguments is the recommended readable form when
several labels share one layout.

## Complete example

`assets.store`:

```text
MAGIC "store"
VERSION 2

uint32 MODE_3 = 0x04000000
uint32 DIR_VRAM = 0x06000000
uint16 DISPCNT = 0x0403
str title = "RIF GBA"
@FILE "assets/ball_palette.bin" AS palette
```

Build and consume it:

```powershell
vnma run main.py --comp-store assets.store -o build/gba.storage.bin
vnma run main.py --doctor-storage build/gba.storage.bin
```

```asm
::RIF_STORE AS GBA "build/gba.storage.bin"
GBA.ORDER 1
GBA.ENDIANNESS 1

; Actual STORE consumption: emit each selected payload at a byte-aligned
; position in the MIR output.
::RIF_STORE GBA MODE_3
::RIF_STORE GBA DIR_VRAM
::RIF_STORE GBA DISPCNT
```

The MIR output receives the bytes for each selected label at the point of use;
it does not receive the storage file's metadata. `RIF_STORE` does not currently
substitute `GBA.MODE_3` inside a normal instruction operand. If a target wants
named values such as `GBA.MODE_3` in an instruction, it needs a separate symbol
or operand-resolution feature.

## Errors and boundaries

| Error | Meaning |
| :--- | :--- |
| `VERSION de .store debe ser 1 o 2` | The source selected an unsupported storage version. |
| Typed values or `@REQST` in version 1 | Upgrade the source to `VERSION 2`. |
| Missing label | The requested entry is not present or is not unique. |
| Invalid `ORDER`/`ENDIANNESS` | Use `ORDER 0/1` and `ENDIANNESS 1/2`. |
| Unaligned insertion | `RIF_STORE` emits whole bytes and requires a byte-aligned MIR position. |
| QEMU or a boot format rejects the result | Storage is an indexed payload container, not an ISO, ROM, executable, or filesystem. |

For the broader external MIR contract, see [03. Compilation / External MIR](../03-Compilation/01-external-mir.md).
