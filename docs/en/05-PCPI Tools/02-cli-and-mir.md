# 05.02. Compiling, Inspecting, and Filling PCP-I

PCP-I has two separate operations: compile a textual template into a validated
`.pcic`, then render selected pits into a later binary-producing step.

## Compile a source template

```powershell
vnma run main.py --comp-pcpi examples/headers/header.pci `
  -o build/header.pcic
```

If `-o` is omitted, RIF changes the source suffix to `.pcic`:

```powershell
vnma run main.py --comp-pcpi header.pci
# writes header.pcic beside header.pci
```

The output cannot overwrite its source. Compilation validates the source
header, raw image, pit alignment, bounds, reserved fields, and final container
lengths before writing the file atomically.

## Inspect a compiled container

```powershell
vnma run main.py --doctor-pcpi build/header.pcic
```

The doctor validates the artifact without changing it and reports its version,
signature, byte-order metadata, raw image size, padding, RPAD, and pit records.
Each pit report includes its zero-based index, raw-image address, exact size,
and alignment padding.

## Use PCP-I from external MIR

The external MIR preprocessor recognizes three closed directives:

```asm
::RIF_PCPI SET "build/header.pcic"
::RIF_PCPI FILL 0 "0102030405060708"
::RIF_PCPI PIT 0
```

### `SET`

`SET` must be the first non-empty MIR line. It loads one `.pcic` relative to the
MIR source, validates it, and reserves its rendered payload in the current
section. Only one `SET` is allowed, and the section must be byte-aligned.

`SET` emits:

```text
PADDING + resolved raw image + RPAD
```

It does not emit the 144-byte PCP-I container header or the pit table. The
placeholder bytes are initially zero so later offsets remain stable.

### `FILL`

```asm
::RIF_PCPI FILL 0 "0102030405060708"
```

The index is zero-based. The value is hexadecimal bytes; spaces, underscores,
and an optional leading `0x` are accepted. The decoded value must have exactly
the pit's declared size. Missing, duplicate, malformed, short, long, or
out-of-range fills are errors. Every pit must be filled before compilation can
commit the final output.

`FILL` emits no additional bytes and does not modify the `.pcic` file.

### `PIT`

```asm
::RIF_PCPI PIT 0
::RIF_PCPI PIT 0 SECTION text
```

`PIT` emits no bytes. It reports the final output address of the selected pit
through the MIR compilation result and CLI diagnostics. The address is based on
the MIR section offset, PCP-I insertion offset, `PADDING`, and the pit's
raw-image address. It does not include the `.pcic` header or pit table.

The optional `SECTION name` form queries the final file offset of a named
section. Use it when a later calculation needs the position of a filled field,
not when the field itself needs a replacement.

## Python API

For a host producer that does not use MIR:

```python
from rif_tools.pcpi_compiler import compile_pcpi_source

compiled = compile_pcpi_source("header.pci").image
raw_image = compiled.fill(0, bytes.fromhex("0102030405060708"))
rendered = compiled.render({0: bytes.fromhex("0102030405060708")})
```

`fill()` returns the raw image. `render()` returns the full rendered payload:
leading `PADDING`, the resolved raw image, and trailing `RPAD`. Both operations
validate exact pit sizes and leave the compiled object unchanged.

## Final-image boundary

PCP-I does not create an ISO-9660 filesystem, El Torito catalog, executable,
ROM, or QEMU disk. A later producer must assemble the rendered payload with
the format-specific records and data. For example, a GBA header template still
needs the ROM producer to place the boot code and asset payloads at their final
offsets.

The external MIR stage is therefore:

```text
load .pcic -> reserve payload -> fill every pit -> emit payload bytes
```

It is not:

```text
.pcic -> automatically bootable image
```

## Common failures

| Failure | Cause | Fix |
| :--- | :--- | :--- |
| `SET` is rejected | It is not the first non-empty MIR line, or more than one was used | Move one `SET` to the top of the MIR file. |
| A fill has the wrong size | PCP-I fields are exact-size | Encode exactly `pit.size` bytes. |
| A pit remains unresolved | No `FILL` was supplied | Fill every pit exactly once. |
| A pit address seems too small or too large | Raw-image and final-file addresses were mixed | Account for section offset, insertion offset, and PCP-I `PADDING`; never add the container header. |
| QEMU cannot boot the result | `.pcic` is a template container, not an ISO | Assemble a real image after rendering PCP-I. |
