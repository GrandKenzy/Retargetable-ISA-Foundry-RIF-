# Diagnostics and Testing

RIF reports errors at the phase where they are detected.

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
- an invalid native function result.

## Rule Traces

After execution, inspect:

```python
result.context.last_rule_trace
result.context.rule_traces
```

Traces show where a Rule started, how many physical and virtual bits it
produced, where it ended, and how much of that output was explicit padding.

## Test Commands

Run the repository suite with VNMA:

```powershell
vnma test
```

The test suite covers parser integration, table stress, packages, direct and
CLI MIR compilation, native functions, physical and virtual memory, datastack
behavior, and failure paths.
