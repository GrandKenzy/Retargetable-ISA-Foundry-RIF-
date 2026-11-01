# Rules and Values

Rule bodies are line-oriented instruction sequences. The current instruction
families are grouped below.

## Token Consumers

```rif
. IDENT
. KW "ret"
. [NUMBER, STRING]
```

`IDENT`, `NUMBER`, and other canonical `Token` names consume a matching token.
`KW` consumes a keyword with an exact string value. The bracket form stores the
first matching token from its candidates.

## Rule Control

```rif
. JUMP mov
. JUMPIF mov, true
. JUMPIF mov, #call[should_jump]
. BREAK
. ERROR, "invalid instruction"
```

`JUMP` invokes another Rule and returns when it finishes. `JUMPIF` invokes it only
when its boolean condition is true. `BREAK` stops the current Rule flow.
`#call[...]` references can only resolve registered native functions.

Token storage is separate from the datastack:

```rif
. save "current"
. load "current"
```

`save` records the current token under a label. `load` requires the current
token to match that saved token and then consumes it.

## Emission

```rif
. nibbles 0000 0000
. emit 0 1 0 1 0 1 0 1
. eword 83847483
. frame 0000 0
00000000
0000
. frameend
```

`nibbles` emits two four-bit fields. `emit` emits eight one-bit fields. `eword`
uses `word_size`. `frame` emits a multiline frame and accepts any `VALUE` in
its rows.

## Tables, Reservations, and Positions

```rif
. reserve "slot" 16
. write_res "slot" 0000000000000000
. emit_res "slot"
. drop_res "slot"
. eword &slot
. eword ::SIZE
. eword ::VSIZE
```

`&slot` reads a reservation as a value. `reserve` creates a zero-filled named
region, `write_res` patches it, `emit_res` copies it into the current output, and
`drop_res` removes its name without clearing its previous bits.

## Immediate Fitting

```rif
. fit 8
. fit_exact 8
. fit_not 8
. fit $registers.name[rax].bits
```

These instructions operate on the current MIR token. `fit` emits the low bits
when the value is too wide. `fit_exact` emits only when the value fits exactly.
`fit_not` consumes a value only when it does not fit.

Widths can be values obtained from a table, a native function, a reservation,
or the datastack.

## Value Forms

RIF values include numeric and string literals, booleans, table accesses,
reservation accesses, calls, and position queries:

```rif
$registers.bits
$registers.name[rax].bits
&slot
#call[get_bits]
::SIZE
::VSIZE
::ALIGNMENT
dist "mov"
vdist "mov"
resdir "slot"
resvdir "slot"
resdist "slot"
resvdist "slot"
reswidth "slot"
vreswidth "slot"
```

Token references inside consumers use canonical names from `gram.lexer.Token`
or their numeric enum value. The `token_names` keyword group is populated from
the complete enum at frontend initialization.

Binary strings preserve their written width, including leading zeroes. This is
why `0000`, `"0000"`, and a numeric value are useful in different contexts:
the first form retains a source width for fixed fields, while a quoted binary
string is validated as a complete bit sequence at runtime.
