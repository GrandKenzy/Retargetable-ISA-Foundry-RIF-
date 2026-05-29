# Compilar

Compilar una instruccion:

```bash
python -m rif compile examples/minimal.pack byte 0xf
```

Compilar varias lineas con build:

```bash
python -m rif build examples/minimal.pack --source-text "byte 0x2a"
```

El resultado muestra bytes, hex y bloques.

Si hay placeholders, la salida los lista para que el linker o una fase posterior los resuelva.
