# Datastack

The datastack is a LIFO value stack shared by Rules during one external MIR
compilation. It is independent from the token stack declared with `@stack`.

## Push and Pop

```rif
@rule prepare:
. dpush 64

@rule encode:
. fit dget
```

`dpush VALUE` evaluates a value and pushes it. `dget` used where a `VALUE` is
expected pops the top value. `dpeek` reads the top value without removing it.
`dpop` discards the top value. `::ddepth` returns the current stack depth.

The following flow is common:

```rif
. dpush 64
. fit dget
```

The first Rule line can push a width for a later emission. `fits dget` checks
the width and removes it only after a successful fit. A failed `fit_exact` leaves
the value available for recovery logic.

## Table-Driven Loads

The instruction form of `dget` queries a table using the current MIR token:

```rif
. dget ::registers.names : bits
```

It performs these operations atomically from the language point of view:

1. Read the current token value.
2. Find it in `registers.names`.
3. Push the matching row's `bits` value.
4. Consume the current token.

The selector column must contain unique keys. If the token is absent, the Rule
fails without consuming the token or pushing a value.

## State Lifetime

`RIFMachine.execute` starts an isolated run and clears the datastack.
`execute_line` processes one external MIR line while preserving the datastack,
reservations, and other cross-line state. This is what allows one MIR line to
prepare a value for a later line.

Native Rule operations receive explicit primitive values; no dynamic Python
context can inspect or manipulate the live list. See the [Rule Operation
ABI](./06-rule-operation-abi.md) for the closed C/AOT surface.

Target authors should keep stack ownership clear: use the datastack for
temporary values and the token storage instructions for token identity.
