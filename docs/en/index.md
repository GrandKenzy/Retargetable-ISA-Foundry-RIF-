# RIF Documentation

> **Version:** `1.0.0`
> **Runtime:** Python 3.10+ with Gram

RIF is a retargetable instruction format and compilation framework. A RIF
definition describes how an external MIR program is recognized, how values are
looked up, and how the final pure binary is emitted. RIF is a target-definition
language and binary generator, not a universal assembler or host linker.

RIF uses [Gram](https://github.com/GrandKenzy/Gram) for lexical analysis and
syntax parsing. The RIF frontend turns a `.rif` definition into compiled Rules;
the MIR runtime then executes those Rules against an external source program.

See the [RIF changelog](../../changelog/README.md) for versioned release notes.

## Documentation Index

### [01. Introduction](./01-Introduction/index.md)

Concepts, installation, project layout, and the complete RIF pipeline.

- [01. What is RIF?](./01-Introduction/01-what-is-rif.md)
- [02. Installation](./01-Introduction/02-installation.md)
- [03. Architecture](./01-Introduction/03-architecture.md)
- [04. The RIF User Workflow](./01-Introduction/04-user-workflow.md)

### [02. Language](./02-Language/index.md)

The `.rif` language: declarations, configuration, tables, Rules, values,
external loads, and reusable libraries.

- [01. Source Structure](./02-Language/01-source-structure.md)
- [02. Configuration and Linker](./02-Language/02-configuration-and-linker.md)
- [03. Tables and Loads](./02-Language/03-tables-and-loads.md)
- [04. Rules and Values](./02-Language/04-rules-and-values.md)
- [05. Reusable Pattern Libraries](./02-Language/05-reusable-pattern-libraries.md)

### [03. Compilation](./03-Compilation/index.md)

How RIF compiles target definitions, processes external MIR, creates `.pack`
files, inspects artifacts, and verifies output.

- [01. External MIR](./03-Compilation/01-external-mir.md)
- [02. RIF Packages](./03-Compilation/02-rif-packages.md)
- [03. Native Functions](./03-Compilation/03-native-functions.md)
- [04. Inspection, Output Maps, and Contracts](./03-Compilation/04-inspection-output-maps-and-contracts.md)
- [05. Verification, Oracles, and Property Testing](./03-Compilation/05-verification-and-oracles.md)

### [04. Execution](./04-Execution/index.md)

Runtime state, bit emission, physical and virtual memory, datastack usage,
variants, and diagnostics.

- [01. Bit Memory](./04-Execution/01-bit-memory.md)
- [02. Datastack](./04-Execution/02-datastack.md)
- [03. Variants](./04-Execution/03-variants.md)
- [04. Diagnostics and Testing](./04-Execution/04-diagnostics-and-testing.md)
- [05. Binary Artifacts](./04-Execution/05-binary-artifacts.md)
- [06. Rule Operation ABI](./04-Execution/06-rule-operation-abi.md)

## Quick Start

```text
target.rif + program.mir -> program.bin
```

Compile directly from a RIF definition:

```powershell
rif main.rif program.mir
```

Create a precompiled package and use it as the target definition:

```powershell
rif --pack main.rif -o target.pack
rif target.pack program.mir -o program.bin
```

The output is a pure binary file. Its default name is derived from the MIR
input, so `program.mir` produces `program.bin` unless `-o` is supplied.
