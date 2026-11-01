# The RIF User Workflow

This page describes the complete workflow for a person building or consuming
a RIF target. It is the recommended starting point after installation.

## The five artifacts

RIF deliberately separates the target description from the program that uses
it:

| Artifact | Role | Usually written by |
| :--- | :--- | :--- |
| `.rif` | Declarative target definition: tables, Rules, output policy, and relocations. | Target author |
| `.riflib` | Reusable package of target-neutral RIF declarations. | Pattern/library author |
| `.pack` | Portable, validated compilation of a target definition. | Build or release process |
| `.mir` | External program whose lines select Rules in the target. | Program or frontend author |
| raw binary | Final bytes emitted by the target Rules and MIR input. | RIF output |

The normal release flow is:

```text
source .rif + referenced .riflib
              |
              v
       compiled .pack
              |
       .pack + .mir
              |
              v
       raw binary image
```

RIF is not a universal assembler. The `.rif` definition does not need to
know every possible MIR program, and RIF does not contain a built-in table of
AMD64, ARM, or any other processor's instructions. The target author teaches
RIF how to recognize a language through Rules and target-owned tables.

## Development workflow

During development, compile directly from the target source:

```powershell
vnma run main.py target/main.rif program.mir -o build/program.bin
```

The target's linker block defines the accepted MIR extension. A project may
call the file `.asm`, `.mir`, `.source`, or another extension; the contents
are still external MIR and are not automatically interpreted as a host
assembler language.

When the target is ready to reuse or distribute it, create a package:

```powershell
vnma run main.py --pack target/main.rif -o build/target.pack
vnma run main.py build/target.pack program.mir -o build/program.bin
```

The package contains the target definition, its source graph, referenced
libraries, hashes, and—when precompiled by the CLI—the compiled target cache.
It does not contain the external MIR program or the final binary.

## What happens in each phase

### Phase 1: teach RIF the target

RIF parses the `.rif` source, validates the configuration, indexes tables,
registers definitions, compiles Rules, and resolves references between Rules
and tables. The result is a resolved target definition. This phase does not
consume program instructions and does not emit the final program binary.

### Phase 2: run the target against MIR

RIF reads the external MIR stream. The first token of each ordinary line is a
Rule name; the remaining tokens are consumed by that Rule. Rules may select
table rows, validate operand widths, emit bits, reserve patch ranges, record
symbols, and schedule relocations.

The MIR preprocessor handles its own reserved directives before normal Rule
dispatch. For example, `::RIF_INSERT`, `::RIF_PATCH`, `::RIF_SECTION`,
`::RIF_STORE`, and bounded buffer directives are not silently passed to a
Rule.

### Finalization

After all MIR lines have run, RIF completes section layout and resolves the
fixups declared by the Rules. The output is committed atomically. A failed
Rule, layout check, or relocation cannot leave a partially valid binary as the
successful result.

## Choosing a backend

The default frontend backend is the in-memory Gram C/AOT parser. It parses
the RIF source into GIR and RIF then applies its normal target semantics. The
Python parser remains available for explicit comparison and troubleshooting:

```powershell
vnma run main.py --backend aot target/main.rif program.mir
vnma run main.py --backend python target/main.rif program.mir
```

The backend choice affects parsing of the target definition. It does not
change the target's declarative meaning or the external MIR contract.

## A useful project layout

```text
target/
├── main.rif             # target entry point
├── config.rif           # optional root-loaded config/linker blocks
├── tables.rif           # tables and reusable metadata
├── rules.rif            # Rules
├── patterns.riflib      # optional reusable library
└── program.mir          # external input, normally kept outside the pack
```

The target may split declarations with `@LOAD`. A reusable `.riflib` is
different from a local include: it is a portable source package with its own
manifest and content hash.

## What the target consumer owns

RIF produces the bits described by the target. The consumer of a bare-metal
raw image is responsible for decisions outside that contract, such as:

- physical placement of sections;
- the boot entry address and loader protocol;
- page tables, CPU mode, devices, and platform initialization;
- any object-file or operating-system ABI not declared by the target.

This boundary is intentional. A target can describe an instruction encoding
without becoming a linker, operating-system toolchain, or complete assembler.

## First troubleshooting checks

When a build fails, identify the phase first:

1. A syntax error means the `.rif` or MIR text is malformed.
2. A target validation error means configuration, tables, Rules, or the linker
   contract is incomplete.
3. A Rule error means the MIR line does not match the Rule's expected tokens
   or values.
4. A layout error means sections, alignments, reservations, or virtual ranges
   conflict.
5. A fixup error means a symbol is missing or its relocation value is outside
   the declared range.

Use the package inspector and an output map before changing Rules blindly:

```powershell
vnma run main.py --inspect-pack build/target.pack
vnma run main.py --inspect-pack build/target.pack --json > build/target.inspect.json
vnma run main.py build/target.pack program.mir -o build/program.bin --map build/program.map.json
```
