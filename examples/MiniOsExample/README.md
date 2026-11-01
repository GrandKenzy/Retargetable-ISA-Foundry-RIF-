# MiniOS Example

This directory contains the reproducible AMD64 BIOS image build for MiniOS.
It deliberately keeps the binary inputs separate:

- `mini_os_iso_header.pci` is the PCP-I source for the ISO-9660/El Torito
  descriptor sectors. `build/mini_os_iso_header.pcic` is its validated PCP-I
  container.
- `cursor_assets.store` is the source media manifest.
  `build/cursor_assets.storage.bin` is the indexed RIF storage artifact, with
  source pixels under `cursor_arrow_rgba8888` and framebuffer-ready pixels
  under `cursor_arrow_bgrx8888`.

## QEMU contract

QEMU does not boot a PCP-I container directly. The build script uses the QEMU
Friendly RIF target to emit the El Torito boot image, then assembles a real
ISO-9660 image containing descriptors, an El Torito catalog, a root directory
and `README.TXT;1`. Launch it with:

```powershell
qemu-system-x86_64 `
  -cdrom examples/MiniOsExample/build/mini_os.iso `
  -boot order=d `
  -m 128M `
  -no-reboot `
  -no-shutdown
```

The `.pcic` contains the ISO system area plus four descriptor sectors. Its
three pits are filled by the RIF MIR program and the final ISO producer. The
resulting ISO has the RIF boot image at LBA 20 and a valid root directory.
No external `xorriso` or `mkisofs` dependency is required.

## Rebuild the artifacts

From the RIF root:

```powershell
vnma run examples/MiniOsExample/build_qemu_iso.py

vnma run rif.py --doctor-pcpi `
  examples/MiniOsExample/build/mini_os_iso_header.pcic

vnma run rif.py --doctor-storage `
  examples/MiniOsExample/build/cursor_assets.storage.bin
```

The script performs the complete chain: PCP-I and storage compilation, RIF
packaging, `.pack + .mir` boot-image emission, ISO-9660 assembly and
structural validation. It writes `build/mini_os.iso`.

The storage payloads can later be inserted into MIR with:

```text
::RIF_STORE "cursor_assets.storage.bin" cursor_arrow_rgba8888 1 0
```

The QEMU Friendly target uses the parallel `cursor_arrow_bgrx8888` label so
the 16-bit boot checkpoint can copy pixels directly into the BGRX framebuffer.

The insertion remains an external-MIR/preprocessor operation. It does not
make RIF core know anything about cursors or operating systems. The ISO
assembler is deliberately a separate producer for the final container.
