# External MIR

External MIR is a line-oriented program whose first token selects a RIF Rule.
For example, if the target defines `mov`:

```text
mov rax, 1
add rbx, 2
```

The remaining tokens on each line are consumed by the selected Rule. A line
that leaves unconsumed tokens is rejected.

## Metaprogramming directives

External MIR may contain reserved markers for binary artifacts managed by RIF:

```text
::RIF_PCPI SET "header.pcic"
::RIF_PCPI PIT 0
::RIF_PCPI PIT 0 SECTION text
::RIF_STORE "images.bin" myImage 1 0
mov rax, 1
```

`::RIF_PCPI SET` must be the first non-empty line. It loads a `.pcic` file and
copies the complete container into the current section. `::RIF_PCPI PIT` emits
no bytes; it queries the absolute address of the reserved payload, measured
from offset `0` of the final file. The `SECTION text` form uses that section's
actual file offset. Queries are returned through
`MIRCompilation.pcpi_pit_addresses` and printed by the CLI.

`::RIF_STORE`
receives `ENDIANNESS` (`1` little, `2` big) and `BITORDER` (`0` LSB, `1` MSB),
resolves its path relative to the MIR file, opens `storage.bin`, extracts the
raw payload by label, and inserts it into the current section. The payload must
start at a byte-aligned position and is copied without reinterpretation; the
storage has no word size with which to perform a generic endian conversion.

## Command Line

The command-line entrypoint is `rif.py`:

```powershell
rif main.rif program.mir
rif target.pack program.mir
rif main.rif program.mir -o build/program.bin
```

The MIR extension must match `extension` in the target's linker block. When `-o` is
omitted, the output path is the MIR path with a `.bin` suffix.

## Direct Python API

Use the direct source API when RIF should tokenize a string:

```python
from MIR import compile_mir_source

result = compile_mir_source("main.rif", "mov rax\n")
binary = result.binary
```

Prepare a target once when compiling multiple inputs:

```python
from MIR import compile_mir_source, prepare_target

target = prepare_target("target.pack")
first = compile_mir_source(target, "mov rax\n")
second = compile_mir_source(target, "add rbx\n")
```

Use `compile_mir_file` for a file and `compile_mir_tokens` when another
compiler already has a token stream:

```python
from MIR import compile_mir_file, compile_mir_tokens, tokenize_mir

result = compile_mir_file("main.rif", "program.mir")
tokens = tokenize_mir("mov rax\n", "generated.mir")
result = compile_mir_tokens("target.pack", tokens)
```

`compile_mir_tokens` avoids lexing and parsing the MIR a second time. It is the
preferred entry when a host compiler already owns tokenization.

## Sections

The default output section is `default` from `@block config`. A direct caller
can select another configured section:

```python
result = compile_mir_source(target, source, section="text")
```

The returned `MIRCompilation` exposes `binary`, `image`, `executions`,
`program`, `context`, `section_binary`, and the selected section name.

The lower-level pipeline is also public:

```python
from MIR import compile_definition, compile_project, execute_rule

program = compile_definition("main.rif")
project = compile_project("main.rif")
execution = execute_rule(project, "mov", tokens)
```

`parse_source` exposes the Gram parse phase, while `compile_source` returns a
resolved target definition without creating an output image. These helpers are
useful when a host compiler needs to inspect or execute individual Rules.
