# Diagnostics and Testing

RIF reports errors at the phase where they are detected. The API can collect
them with `DiagnosticBag`; every diagnostic keeps its phase (`frontend`,
`rules`, `mir`, `layout`, or `fixups`) and, when available, its file, line,
Rule, section, and token.

## Syntax Errors

Gram reports malformed RIF syntax, missing delimiters, invalid token forms,
and incomplete Rule lines. Newline-sensitive failures usually indicate a
missing newline, a missing final `|` in a table row, or a malformed multiline
`frame` block.

## Semantic Errors

The semantic phase reports unresolved token names, missing tables or columns,
unknown Rules, invalid reservation names, duplicate table keys, invalid widths,
and invalid configuration values. These errors occur while compiling the target
definition, before external MIR is executed.

## Runtime Errors

`RIFRuntimeError` reports failures such as:

- a consumer receiving the wrong token;
- an empty datastack pop;
- a missing table match;
- an immediate that cannot fit;
- an out-of-range bit read or patch;
- an unknown reservation or Rule;
- an invalid native operation result.

## Rule Traces

After execution, inspect:

```python
result.context.last_rule_trace
result.context.rule_traces
```

Traces show where a Rule started, how many physical and virtual bits it
produced, where it ended, and how much of that output was explicit padding.

The CLI uses the same structured rendering for frontend, Rule, MIR, layout,
and relocation failures instead of formatting each phase independently.

## Test Commands

Run the repository suite with VNMA:

```powershell
vnma test
```

That command runs the essential suite. Run the other layers explicitly:

```powershell
vnma test test/suite_aggressive
vnma test test/dedicated_suite
```

The essential suite covers parser integration, packages, direct and CLI MIR
compilation, native operations, physical and virtual memory, datastack behavior,
and failure paths. The aggressive suite covers benchmarks and stress cases; the
dedicated suite covers AOT, PCP-I, plugins, diagnostics, and API-specific
contracts that may need repair after an API change.
