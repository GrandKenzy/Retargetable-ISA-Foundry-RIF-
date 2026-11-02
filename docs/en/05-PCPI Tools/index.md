# 05. PCP-I Tools

PCP-I is RIF's standalone binary-template tool. It describes a deterministic
byte image with fixed bytes, zero-filled static regions, and explicitly named
fillable regions called pits.

PCP-I is useful when a later producer knows the final value of a field but the
surrounding binary envelope is already stable. It is not an assembler, linker,
filesystem builder, ISO generator, or bootloader.

## The complete workflow

```text
header.pci --comp-pcpi--> header.pcic --SET/FILL--> bytes in an MIR output
```

Compile a source template:

```powershell
vnma run main.py --comp-pcpi header.pci -o build/header.pcic
```

Validate an existing compiled template:

```powershell
vnma run main.py --doctor-pcpi build/header.pcic
```

Use it from an external MIR program:

```asm
::RIF_PCPI SET "build/header.pcic"
::RIF_PCPI FILL 0 "0102030405060708"
```

`SET` materializes the PCP-I payload in the current MIR section. `FILL`
replaces a pit with exactly the number of bytes declared by that pit. The
144-byte PCP-I container header and the pit table are metadata; they are not
inserted into the MIR output.

## Guides

| Guide | Purpose |
| :--- | :--- |
| [01. Authoring PCP-I Templates](./01-authoring-templates.md) | Source syntax, fixed bytes, `ZERO`, pits, alignment, and the compiled container. |
| [02. Compiling, Inspecting, and Filling](./02-cli-and-mir.md) | CLI commands, Python API, external MIR directives, ordering, and final-image boundaries. |

## Format boundary

PCP-I version 1 is independent from RIF target definitions and from STORE
versioning. A `.pcic` file is an intermediate validated template. A real ISO,
ROM, executable, or firmware image still needs a producer that assembles the
template with its payloads and format-specific metadata.

The full PCP-I contract, including binary field sizes and address spaces, is
also documented in [03. Compilation / PCP-I](../03-Compilation/06-pcp-i.md).
