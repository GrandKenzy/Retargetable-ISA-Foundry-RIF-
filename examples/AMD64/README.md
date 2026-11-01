# AMD64 bare-metal example

Este ejemplo mínimo usa RIF para emitir bytes raw AMD64 sin asumir sistema
operativo, ABI ni formato de objeto. El MIR solo contiene instrucciones; el
consumidor bare metal decide dónde ubicarlas y cómo ejecutarlas.

## Fuente y resultado

```text
mov rax, 42
mov rdi, 7
nop
```

Resultado esperado:

```text
48 C7 C0 2A 00 00 00 48 C7 C7 07 00 00 00 90
```

## Compilar

```powershell
vnma run rif.py examples/AMD64/main.rif examples/probe/probe_amd64/main.mir `
  -o examples/AMD64/output.bin
Format-Hex examples/AMD64/output.bin
```

También puede precompilarse como paquete:

```powershell
vnma run rif.py --pack examples/AMD64/main.rif `
  -o examples/AMD64/amd64.pack
vnma run rif.py examples/AMD64/amd64.pack examples/probe/probe_amd64/main.mir `
  -o examples/AMD64/output-from-pack.bin
```

Los dos binarios deben ser idénticos. El target usa la tabla `registers` para
seleccionar el ModR/M de `MOV r64, imm32`; el `fit 32` emite el inmediato en
little-endian.

## Comparación de sintaxis

El programa `examples/probe/probe_amd64/main.mir` es la versión convencional
del programa usado por `examples/probe/probe_friendlysyntax/equivalent.mir`. La prueba diferencial compila
ambos targets desde `.rif` y desde `.pack` y verifica que las cuatro salidas
sean los mismos 15 bytes:

```powershell
vnma run examples/amd64-friendlysyntaxs/tests/test_syntax_equivalence.py `
  --rif-root .
```

Esto demuestra que la sintaxis amigable se declara en tablas y Rules del
target; no es un alias incorporado en RIF.
