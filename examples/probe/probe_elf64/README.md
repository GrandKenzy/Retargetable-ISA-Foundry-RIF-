# ELF64 example

This target produces a minimal executable ELF64 image for Linux x86-64. It
uses an inline ELF/program-header template, emits the code through normal RIF
Rules, and patches dynamic header fields with `::RIF_PATCH` after all MIR lines are
complete.

Compile it from the repository root:

```powershell
vnma run main.py examples/probe/probe_elf64/main.rif `
  examples/probe/probe_elf64/main.asm `
  -o examples/probe/probe_elf64/exit
```

The expected machine code at the end of the file is:

```text
48 C7 C0 3C 00 00 00 48 C7 C7 2A 00 00 00 0F 05
```

On Linux, make the output executable and run it:

```sh
chmod +x exit
./exit
echo $?
# 42
```

On Windows, the output can still be inspected with `Format-Hex`. It is a raw
ELF executable image, not a PE file.

The three final patches demonstrate the native queries:

- `#:qlsize` locates `_start` in the physical file.
- `#:qssize` obtains the physical end of `.text`.
- `#:qvssize` obtains the virtual end of `.text`.
- `#:calc` combines those values with the configured virtual base.
