# Crear y usar plugins

Un plugin vive en:

```text
plugins/NOMBRE/plugins/
```

Cada archivo `.py` dentro de esa carpeta registra una instruccion con el nombre del archivo.

Ejemplo:

```text
plugins/demo/plugins/op.py
```

En el pack:

```rif
.pack
plugin "demo"
```

Uso:

```rif
.rules
rule:
    op arg1, arg2
```

El plugin puede devolver `Expr`, una lista de `Expr`, `Err` o `None`.
