# Architecture

RIF has two compilation phases and one output phase. The first phase teaches
the target to RIF; the second applies that compiled target to external MIR.

## Target Definition

`main.rif` and any referenced `.riflib` sources describe the target:

```text
main.rif -> CompiledRuleSet
```

The compiled Rule Set contains resolved instruction operands and references to
tokens, tables, and other Rules. It is reused for every external MIR program
compiled against the target.

## External MIR

The external MIR is the program that the target consumes:

```text
CompiledRuleSet + program.mir -> program.bin
```

Its first token on each ordinary line selects a Rule. The remaining tokens are
passed to that Rule. Preprocessor directives beginning with `::RIF_` are
handled before Rule dispatch. RIF can tokenize the file itself or receive
tokens from another compiler through the direct Python API.

## Internal Components

| Component | Responsibility |
| :--- | :--- |
| `Frontend.syntax` | Declares the Gram grammar for RIF definitions. |
| `Frontend.processor` | Materializes configuration, tables, defines, Rules, and loads. |
| `MIR.compiler` | Converts parsed instruction nodes into flat internal instructions. |
| `MIR.semantic` | Resolves token, table, Rule, and reservation references. |
| `MIR.runtime.RIFMachine` | Executes instructions against MIR tokens. |
| `MIR.bitbuffer.BitBuffer` | Stores and rewrites arbitrary bit ranges. |
| `MIR.output.AssemblyImage` | Owns one output buffer per configured section. |
| `rif_core/pack.py` | Creates and validates reproducible `.pack` archives. |
| `rif_core/library.py` | Creates and validates reusable `.riflib` source packages. |

## State Ownership

The root target owns global definitions, tables, configuration, and Rules.
`RIFMachine` owns execution state such as token position, saved tokens,
selected rows, datastack values, reservations, and traces. A machine can be
created for a section of an `AssemblyImage` without changing the target
definition.
