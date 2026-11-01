# 03. Compilation

RIF exposes a command-line workflow and a direct Python API. Both compile the
same target definition and use the same MIR dispatcher.

| Guide | Summary |
| :--- | :--- |
| [01. External MIR](./01-external-mir.md) | CLI and direct API compilation of MIR files or token streams. |
| [02. RIF Packages](./02-rif-packages.md) | `.pack` contents, precompilation, and package advantages. |
| [03. Native Functions](./03-native-functions.md) | Closed native operations, `#:calc`, and bounded acquisition. |
| [04. Inspection, Output Maps, and Contracts](./04-inspection-output-maps-and-contracts.md) | Package inspection, maps, caches, and artifact compatibility. |
| [05. Verification, Oracles, and Property Testing](./05-verification-and-oracles.md) | Test tiers, optional assemblers, and deterministic fuzzing. |

## Two Compilation Stages

```text
Stage 1: main.rif + libraries -> CompiledRuleSet -> target.pack (optional)
Stage 2: target.pack + program.mir -> pure binary
```

Stage 1 resolves the target. The `.pack` stores Rules, tables, and context but
does not contain external MIR. Stage 2 loads the `.pack` (or the `.rif` during
development), validates the target contract, and runs its Rules against the
input MIR. A precompiled `.pack` combines most of Stage 1 into a portable
artifact.
