# Flujos ON y switch

`ON/OFF` ejecuta una rama segun una condicion.

```rif
rule:
    ON imm.size == 8:
        emit imm.binary
    OFF:
        zext OUT, imm.binary, 8
        emit OUT
```

Condiciones soportadas:

- literales booleanos como `true`, `false`, `on`, `off`
- comparaciones `==`, `!=`, `<`, `<=`, `>`, `>=`
- campos de operandos como `op.bits` o `imm.size`

`switch/case` compara un valor contra casos concretos.

```rif
rule:
    switch op.PRIVTYPE:
        case "symbol":
            emit 00000000
        case "register":
            emit 11111111
```

Si una condicion no puede resolverse, queda como placeholder.
