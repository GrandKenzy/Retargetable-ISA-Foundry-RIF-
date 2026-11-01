![RIF Banner](./discentra_centra/badge/banner.jpeg)

# RIF — Retargetable ISA Foundry

**Define the rules. Control the bits. Build anything binary.**

> **Version:** `1.0.1` · **Runtime:** Python 3.10+ · **Parser dependency:** [Gram](https://github.com/GrandKenzy/Gram)

**RIF is an architecture-agnostic, bit-precise binary processing engine.** It lets you define rules for producing, reading, positioning, and modifying binary data without writing a new binary-processing engine for every format.

**RIF does not know what an instruction, opcode, register, processor, or file header means.** It knows how to work with bits. You define what those bits represent.

An assembler is one possible application of RIF—not its definition.

---

## The philosophy

**RIF doesn't decide what your bits mean. You do.**

You might define an instruction called `mov`, a field called `hamburguesa32`, a completely new virtual machine, or a binary format unrelated to CPUs. None of those names has intrinsic meaning to RIF. Its rules determine which input tokens are accepted and how values become binary fields.

For example, the following RIF operations manipulate bits without requiring any CPU knowledge:

```rif
. bits 5 3       ; append the three bits 101
. bits 10 13     ; append a 13-bit field containing 10
. read_bits 0 3       ; read three existing bits into the data stack
. patch_bits 0 3 2    ; overwrite the first three bits with 010
```

These are **bit operations**, not processor instructions. Whether the fields represent an opcode, a register, a color, a packet header, or something else is entirely up to your format.

RIF is designed to express the binary representation you want, not to force that representation into a predefined architecture.

## What can you build?

- **Custom assemblers:** encode instructions for existing, experimental, or entirely fictional instruction sets.
- **Binary formats:** describe custom headers, layouts, fields, offsets, and data structures.
- **Bytecode and virtual machines:** encode representations chosen by the language or VM author.
- **Compiler emission backends:** consume an external instruction representation and generate the binary format defined by a target.
- **Binary inspection and disassembly tooling:** build readers and decoders using RIF's low-level bit-reading capabilities and user-defined interpretation logic.

**Scope clarification:** RIF provides binary primitives and programmable rules. It does **not** automatically infer instruction semantics, invent a CPU, or generate a complete disassembler from an ISA definition. Those behaviors must be implemented by the tool author.

## Core capabilities

| Capability | What it provides |
|---|---|
| **Bit-precise storage** | `BitBuffer` and `BitEmitter` for fields that can start or end at arbitrary bit positions |
| **Binary reads and rewrites** | Read existing bit ranges, patch allocated fields, and work with byte-oriented values |
| **Configurable rules** | `.rif` definitions with tables, conditions, reusable rules, and target configuration |
| **Physical and virtual layouts** | Sections, positioning, padding, alignment, reservations, and location queries |
| **Assembler preprocessor** | `::RIF_INSERT` for binary preludes and `::RIF_PATCH` for final size/offset corrections |
| **Reusable `.pack` files** | Package rule definitions, included sources, assets, and optionally precompiled SQLite data |
| **External input processing** | Process a file or consume an existing token stream without repeating the external lexing step |
| **Native functions** | Closed, deterministic functions designed for Python/C parity |

A `.pack` defines how a particular input is interpreted. RIF's core does not ship with an intrinsic knowledge of AMD64, ARM, RISC-V, or any other processor.

## How RIF works

```text
Your binary format / encoding rules (.rif)
                  |
                  v
             Gram frontend
                  |
                  v
           CompiledRuleSet
                  |
           +------+------+
           |             |
      External input   Reusable .pack
      (file / tokens)  (optional)
           |             |
           +------+------+
                  |
                  v
              RIFMachine
                  |
                  v
     BitBuffer / AssemblyImage
                  |
                  v
           Exact binary output
```

The rule definition, its compiled representation (`CompiledRuleSet`), and the external input are separate concepts. The format author decides what the input means and how its fields are encoded.

RIF can produce raw binary data or construct a larger image with sections, inserted bytes, and final patches. The ELF64 example demonstrates that machinery; **ELF64 and AMD64 are examples, not built-in assumptions**.

## Quick start

### Requirements

- Python 3.10+
- [Gram](https://github.com/GrandKenzy/Gram) for parsing RIF definitions
- Pillow for local image conversion and `soundfile`/NumPy for local WAV, FLAC,
  and OGG conversion (optional until the media plugins are used)

This repository uses [VNMA](https://github.com/GrandKenzy/vnma) to manage project dependencies:

```powershell
vnma install
vnma sync-ide
```

To enable the local media plugins, install their optional dependencies:

```powershell
vnma install pillow
vnma install soundfile
```

To compile a standalone `.store` file into indexed raw storage:

```powershell
vnma run rif.py --comp-store datos.store -o storage.bin
```

For a clean clone, copy `vnma.toml.example` to `vnma.toml` before installing.
The example uses Gram from GitHub; a local checkout may instead use the ignored
editable `vnma.toml` and `vnma reload` after Gram changes.

### Command line

The repository includes an ELF64 demonstration that emits a small Linux x86-64 executable. It illustrates binary headers, instruction bytes, positions, and post-processing; it does not mean that RIF is limited to that architecture.

```powershell
# Process an existing RIF definition and its input
vnma run rif.py examples/probe/probe_elf64/main.rif examples/probe/probe_elf64/main.asm -o exit

# Package a user-defined target
vnma run rif.py --pack examples/probe/probe_elf64/main.rif -o target.pack

# Reuse the packaged rules
vnma run rif.py target.pack examples/probe/probe_elf64/main.asm -o exit-from-pack
```

Resource limits can be selected per invocation, in MiB, for example
`vnma run rif.py --plimit 16 ...`. The value is saved locally as
`RIF_PLIMIT_MIB` in `.env`; `.env` and the local VNMA workflow notes are not
published.

Packages keep absolute source origins only for diagnostics. Execution resolves
only relative paths inside the project or package, so those origins are never
used to read files. They can reveal paths from the machine that created the
package.

See the [examples](examples/README.md) for the expected binary results and how to inspect or run the ELF64 sample.

### Python API

```python
from pathlib import Path
from MIR import compile_mir_file, compile_mir_tokens, prepare_target

# Process an external file with user-defined rules.
compile_mir_file("target.pack", "program.asm", output="program.bin")

# Or reuse an already prepared target with tokens supplied by another tool.
target = prepare_target("target.pack")
result = compile_mir_tokens(target, tokens)
Path("program.bin").write_bytes(result.binary)
```

Here, `tokens` is an existing token stream compatible with the target's rules. Unlike `compile_mir_file`, `compile_mir_tokens` returns a compilation result and does not accept an `output` parameter.

For direct bit inspection and manipulation, see the [memory and bit-buffer documentation](docs/en/04-Execution/01-bit-memory.md) and the `BitBuffer` API.

> **Security:** RIF no ejecuta código Python proporcionado por un target. Las
> funciones nativas se registran explícitamente y no cargan módulos externos.

## Documentation

RIF's documentation is available in English and Spanish:

**English**
- [Overview](docs/en/index.md)
- [Introduction](docs/en/01-Introduction/index.md)
- [Language and rule definitions](docs/en/02-Language/index.md)
- [Compilation and packs](docs/en/03-Compilation/index.md)
- [Execution and binary memory](docs/en/04-Execution/index.md)

**Español**
- [Introducción](docs/es/index.md)
- [01. Introducción](docs/es/01-Introduccion/index.md)
- [02. Lenguaje y reglas](docs/es/02-Lenguaje/index.md)
- [03. Compilación y paquetes](docs/es/03-Compilacion/index.md)
- [04. Ejecución y memoria binaria](docs/es/04-Ejecucion/index.md)

Additional resources:
- [Architecture and terminology](docs/en/01-Introduction/03-architecture.md)
- [Functional examples](examples/README.md)
- [Changelog](changelog/README.md)

---

### RIF does not need to know what you are building.

**It only needs the rules that turn your intent into bits.**

![RIF Footer](./discentra_centra/badge/footer.jpeg)
