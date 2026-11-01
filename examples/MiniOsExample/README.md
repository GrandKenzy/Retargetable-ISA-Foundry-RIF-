# MiniOS Example

This directory is the first asset checkpoint for a future AMD64 bare-metal
MiniOS. It deliberately keeps the two binary inputs separate:

- `mini_os_iso_header.pci` is the PCP-I source for the ISO-9660/El Torito
  header only. `build/mini_os_iso_header.pcic` is its validated PCP-I
  container.
- `cursor_assets.store` is the source media manifest.
  `build/cursor_assets.storage.bin` is the indexed RIF storage artifact, with
  source pixels under `cursor_arrow_rgba8888` and framebuffer-ready pixels
  under `cursor_arrow_bgrx8888`.

## QEMU contract

QEMU does not boot a PCP-I container directly. For BIOS boot, it needs a
real ISO-9660 image containing an El Torito boot catalog and a boot image. The
eventual launch command is:

```powershell
qemu-system-x86_64 `
  -cdrom build/mini_os.iso `
  -boot order=d `
  -m 128M `
  -no-reboot `
  -no-shutdown
```

The current `.pcic` contains the ISO system area plus four header sectors: the
primary descriptor, boot record, descriptor terminator, and catalog header.
It has four pits for values that depend on the final layout. It contains no
boot image, boot code, filesystem, cursor data, or other payload. A later RIF
MIR/preprocessor step can fill these pits and append the separately emitted
boot image and filesystem data. `qemu-system-x86_64.exe` 11.x is available in
the development machine; an ISO authoring tool or a small deterministic
ISO builder is still required to assemble the final ISO-9660 filesystem.

## Rebuild the artifacts

From the RIF root:

```powershell
vnma run rif.py --comp-pcpi examples/MiniOsExample/mini_os_iso_header.pci `
  -o examples/MiniOsExample/build/mini_os_iso_header.pcic

vnma run rif.py --comp-store examples/MiniOsExample/cursor_assets.store `
  -o examples/MiniOsExample/build/cursor_assets.storage.bin

vnma run rif.py --doctor-pcpi `
  examples/MiniOsExample/build/mini_os_iso_header.pcic

vnma run rif.py --doctor-storage `
  examples/MiniOsExample/build/cursor_assets.storage.bin
```

The storage payloads can later be inserted into MIR with:

```text
::RIF_STORE "cursor_assets.storage.bin" cursor_arrow_rgba8888 1 0
```

The QEMU Friendly target uses the parallel `cursor_arrow_bgrx8888` label so
the 16-bit boot checkpoint can copy pixels directly into the BGRX framebuffer.

The insertion remains an external-MIR/preprocessor operation. It does not
make RIF core know anything about cursors or operating systems.
