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

`CompilationSession` owns the mutable state of one frontend compilation:
loaded sources, pending tables, Rules, configuration, linker data, blocks,
variants, and source text needed to preserve lexemes. Loaders and visitors
receive that session explicitly, so consecutive or concurrent targets do not
share declarations.

The session is resolved and frozen into an immutable `TargetContext`. MIR
compilation receives the Rules and context explicitly; it does not need the
frontend globals. `activate_target_context()` remains only as a transitional
introspection adapter for older tests.

The public CLI uses the in-memory C/AOT FFI. GCC or Clang runs only when the
cached shared library must be built or invalidated. Python remains an internal
parity oracle and diagnostic backend. `RIFMachine` owns execution state such
as token position, saved tokens, selected rows, datastack values, reservations,
and traces.
