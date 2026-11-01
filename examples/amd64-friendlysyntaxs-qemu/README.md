# AMD64 Friendly Syntax — QEMU

This target is a QEMU-specific wrapper around
[AMD64 Friendly Syntax](../amd64-friendlysyntaxs/README.md). It keeps the
same readable Rules and register tables, then adds the QEMU std VGA/Bochs VBE
contract through an explicit `@LOAD` dependency.

The base Friendly target remains free of QEMU and framebuffer assumptions.
This directory is the bare-metal integration target for the MiniOS experiment.

## QEMU dependency

`main.rif` loads:

```rif
@LOAD "qemu/framebuffer.rif"
```

The loaded table describes the Bochs VBE register indexes. The root target
declares the generic `framebuffer` block with this current test contract:

```text
provider       qemu-std-vga
protocol       bochs-vbe
mode           linear
resolution     640x480
pixel format   BGRX8888
LFB source     PCI BAR0
    cursor         storage BGRX8888, 14x22
```

The block and table are metadata for future boot Rules. They do not initialize
the device by themselves and do not make the base Friendly target QEMU-aware.

## Minimal boot entry and cursor checkpoint

`main.mir` imports the local PCP-I header in its first line, fills every pit,
marks `_start`, emits the fixed 16-bit VBE boot stage, inserts the converted
cursor payload from storage, and pads the boot image to four 512-byte sectors:

```text
::RIF_PCPI SET "assets/mini_os_iso_header.pcic"
::RIF_PCPI FILL 0 "1900000000000019"
::RIF_PCPI FILL 1 "2200170000000000001700080000000000087E0B0100000000020000010000010100"
::RIF_PCPI FILL 2 "88000000000004001400000000000000"
_start
boot_stage
::RIF_STORE "assets/cursor_assets.storage.bin" cursor_arrow_bgrx8888 1 0
boot_tail
```

The boot stage uses the VBE banked window at `A000:0000`, sets mode `0x118`
(640×480×32), copies the centered 14×22 cursor, and halts. It deliberately
does not enter protected or long mode yet. `qemu/boot_stage.s` is only a
human-readable verification reference; the target emits the fixed bytes from
the `boot_stage` Rule, so the `.pack + .mir` pipeline remains canonical.

The source cursor remains RGBA8888 in `MiniOsExample`; the `.store` compiler
also produces the target-ready `cursor_arrow_bgrx8888` payload, composited over
black for this first framebuffer checkpoint.

## Build

```powershell
vnma run rif.py --pack examples/amd64-friendlysyntaxs-qemu/main.rif `
  -o examples/amd64-friendlysyntaxs-qemu/friendly-qemu.pack
vnma run rif.py examples/amd64-friendlysyntaxs-qemu/friendly-qemu.pack `
  examples/amd64-friendlysyntaxs-qemu/main.mir `
  -o examples/amd64-friendlysyntaxs-qemu/main.bin
```

That command emits the RIF raw layout (20 descriptor blocks plus the one-block
boot image). To finish the QEMU artifact as a real ISO-9660 volume, run:

```powershell
vnma run examples/MiniOsExample/build_qemu_iso.py
```

The script consumes the RIF output, fills the PCP-I layout fields, appends
path tables and a root directory, and writes
`examples/MiniOsExample/build/mini_os.iso`. The ISO contains the boot image at
LBA 20 and is structurally checked before it is written.

Rebuild the local PCP-I asset from its canonical source when the header
changes:

```powershell
vnma run rif.py --comp-pcpi examples/MiniOsExample/mini_os_iso_header.pci `
  -o examples/amd64-friendlysyntaxs-qemu/assets/mini_os_iso_header.pcic
```

The current boot image remains a real-mode VBE checkpoint: it selects mode
0x118, draws the cursor through the banked window, and halts safely. A future
protected/long-mode transition can replace only the RIF boot Rules; it does not
belong in the PCP-I descriptor template or ISO producer.
