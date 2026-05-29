# Como se usa

Define un `.pack`, carga plugins y compila instrucciones.

Ejemplo:

```bash
python -m rif compile examples/minimal.pack byte 0xf
```

Salida esperada:

```text
rule=byte
bits=00001111
hex=0f
```

Para compilar varias lineas y construir secciones:

```bash
python -m rif build examples/minimal.pack --source-text "byte 0x2a"
```

Para leer la ayuda:

```bash
python -m rif help
python -m rif help instrucciones
```
