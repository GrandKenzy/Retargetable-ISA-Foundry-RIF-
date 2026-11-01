# AMD64 Friendly Syntax — QEMU

This target is a QEMU-specific wrapper around
[AMD64 Friendly Syntax](../../amd64-friendlysyntaxs/README.md). It keeps the
same readable Rules and register tables through a declaration-only `.riflib`,
then adds the QEMU std VGA/Bochs VBE contract through its own loaded sources.

The base Friendly target remains free of QEMU and framebuffer assumptions.
This directory is the bare-metal integration target for the MiniOS experiment.

## QEMU dependency

`main.rif` loads:

```rif
@LIBRARY "friendly.riflib"
@LOAD "qemu/framebuffer.rif"
@LOAD "qemu/rules.rif"
```

`friendly.riflib` is exported from the base Friendly `.pack` and contains only
the Friendly register tables and Rules. It cannot replace this target's
configuration, linker, or generic blocks. The QEMU-specific sources contain
the Bochs VBE register indexes, boot Rules, and the generic `framebuffer`
metadata block with this current test contract:

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

To refresh the reusable declaration package after changing the base Friendly
target:

```powershell
vnma run rif.py --pack examples/amd64-friendlysyntaxs/main.rif `
  -o examples/amd64-friendlysyntaxs/amd64-friendly.pack
vnma run rif.py --library examples/amd64-friendlysyntaxs/amd64-friendly.pack `
  -o examples/probe/probe_friendlysyntax_qemu/friendly.riflib
```

This explicit export is the supported composition boundary: a `.pack` is a
complete target, while `.riflib` is the reusable Rules/tables layer.

## Minimal boot entry and cursor checkpoint

`main.mir` imports the local PCP-I header in its first line, fills every pit,
marks `_start`, emits the 16-bit VBE/PS2-mouse boot stage, inserts the
converted cursor payload from storage, and pads the boot image to four
512-byte sectors:

```text
::RIF_PCPI SET "assets/mini_os_iso_header.pcic"
::RIF_PCPI FILL 0 "1900000000000019"
::RIF_PCPI FILL 1 "2200170000000000001700080000000000087E0B0100000000020000010000010100"
::RIF_PCPI FILL 2 "88000000000004001400000000000000"
_start
boot_stage_mouse
::RIF_STORE "assets/cursor_assets.storage.bin" cursor_arrow_bgrx8888 1 0
boot_tail
```

The boot stage uses the VBE banked window at `A000:0000`, sets mode `0x118`
(640×480×32), enables the PS/2 mouse, polls three-byte packets, clamps the
cursor to the screen and redraws it over black. It deliberately does not enter
protected or long mode. `qemu/boot_stage.s` is only a human-readable
verification reference; the target emits the fixed bytes from the
`boot_stage_mouse` Rule, so the `.pack + .mir` pipeline remains canonical.

The source cursor remains RGBA8888 in `probe_minios`; the `.store` compiler
also produces the target-ready `cursor_arrow_bgrx8888` payload, composited over
black for this first framebuffer checkpoint.

## Build

```powershell
vnma run rif.py --pack examples/probe/probe_friendlysyntax_qemu/main.rif `
  -o examples/probe/probe_friendlysyntax_qemu/friendly-qemu.pack
vnma run rif.py examples/probe/probe_friendlysyntax_qemu/friendly-qemu.pack `
  examples/probe/probe_friendlysyntax_qemu/main.mir `
  -o examples/probe/probe_friendlysyntax_qemu/main.bin
```

That command emits the RIF raw layout (20 descriptor blocks plus the one-block
boot image). To finish the QEMU artifact as a real ISO-9660 volume, run:

```powershell
vnma run examples/probe/probe_minios/build_qemu_iso.py
```

The script consumes the RIF output, fills the PCP-I layout fields, appends
path tables and a root directory, and writes
`examples/probe/probe_minios/build/mini_os.iso`. The ISO contains the boot image at
LBA 20 and is structurally checked before it is written.

Rebuild the local PCP-I asset from its canonical source when the header
changes:

```powershell
vnma run rif.py --comp-pcpi examples/probe/probe_minios/mini_os_iso_header.pci `
  -o examples/probe/probe_friendlysyntax_qemu/assets/mini_os_iso_header.pcic
```

The current boot image remains a real-mode VBE/mouse checkpoint: it selects
mode 0x118, draws and moves the cursor through the banked window, and keeps
polling safely. A future protected/long-mode transition is unnecessary for
this cursor-only goal and does not belong in the PCP-I descriptor template or
ISO producer.
