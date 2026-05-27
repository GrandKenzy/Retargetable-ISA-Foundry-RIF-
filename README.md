# Retargetable ISA Foundry (RIF)

RIF is an experimental retargetable ISA description and packing/compiler toolkit. It reads `.pack` architecture descriptions and emits a compiled byte representation for rule-driven instruction encoding.

## Repository layout

```text
pack_compiler/              Python package for parsing and compiling `.pack` files
pack_compiler/ast_nodes/    AST, rule compilation, macro expansion and runtime evaluation
examples/amd64/             AMD64/x86_64 architecture description example
docs/                       Notes about the `.pack` format and project status
```

## Quick start

```bash
python -m pip install -e .
python -m pack_compiler examples/amd64/store.amd64.pack build/store.amd64.txt
```

Or use the console script after editable installation:

```bash
pack-compiler examples/amd64/store.amd64.pack build/store.amd64.txt
```

## Current example

The included AMD64 pack file defines:

- scalar types: `b8`, `b16`, `b32`, `b64`
- AMD64 general-purpose registers: `rax` through `r15`
- sub-register aliases for 64-bit, 32-bit, 16-bit and 8-bit register windows
- macros for REX prefixes, ModRM, SIB, literals, stack operations, jumps and stores
- rules for `copy`, `store`, `jump`, `move`, `reserve` and `stack`

## Development status

This is early-stage compiler infrastructure. The current package can parse and compile the included AMD64 `.pack` reference, but the DSL and binary format should still be treated as unstable.
