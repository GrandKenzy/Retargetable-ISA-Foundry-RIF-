# What is RIF?

RIF is a retargetable compilation framework for describing instruction
languages and binary layouts. A RIF project defines a small declarative
language that recognizes lines from an external MIR program and emits fields
into a bit-addressable output buffer.

RIF generates target-defined binary output; it is not itself a universal
assembler, linker, object-file writer, or operating-system toolchain. A target
author chooses the syntax, tables, Rules, memory sections, and relocation
classes that a project supports.

RIF is designed around three separations:

- **Syntax:** Gram tokenizes and parses the RIF definition.
- **Compilation:** RIF resolves names, tables, Rules, and target settings.
- **Execution:** the MIR runtime consumes tokens and writes the binary.

## What a RIF Definition Contains

The root `main.rif` may contain:

- `@block config` for target sections, word size, byte order, labels, and symbol
  policy.
- `@block linker` for MIR file discovery.
- `@table` declarations for instruction metadata and other target data.
- `@define` declarations for named words.
- `@rule` declarations that describe how MIR lines are processed.
- `@stack` for the token-oriented stack used by `save` and `load`.
- `@LOAD` declarations for additional `.rif` sources.
- `@LIBRARY` declarations for portable `.riflib` pattern packages.
- `@SUPPORTS` and `@ASMVARIANT` declarations for target variants.

Only the root definition can declare configuration and linker policy. Included
files and libraries may provide definitions, tables, and Rules. Variant files
are deliberately limited to definitions and Rules so they share the root
context without changing the target layout.

## Processing Pipeline

```text
RIF source (.rif)
        |
        v
Gram lexer and parser
        |
        v
Frontend processor
  config, linker, tables, defines, Rules
        |
        v
CompiledRuleSet
        |
        +---- external MIR tokens
        v
RIFMachine
        |
        v
BitBuffer / AssemblyImage
        |
        v
Pure binary output
```

The same pipeline can load a `.pack`. A precompiled package may skip parsing
and semantic resolution by loading its validated SQLite compilation database.

## Target Neutrality

RIF does not assume one processor, assembler syntax, or instruction width.
The target author decides how tokens map to table rows, how fields are emitted,
how reservations are patched, and which generic relocation calculations are
needed. Tables are extensible and are not limited to registers or opcodes.
