# Instalación

RIF es un proyecto Python local que usa Gram desde el proyecto hermano
`Gram`. El `vnma.toml` declara la dependencia como una ruta editable local:

```toml
[project]
name = "RIF"
version = "1.0.0"

[dependencies]
gram = { path = "~/Desktop/Gram", editable = true }
```

Instala y sincroniza el entorno con VNMA:

```powershell
vnma install
vnma sync-ide
```

Ejecuta el entrypoint:

```powershell
vnma run main.py
```

La estructura normal es:

```text
RIF/
├── Frontend/
│   ├── globals.py
│   ├── syntax/
│   └── processor/
├── MIR/
├── tests/
├── examples/
│   └── probe/
├── main.py
├── pack.py
└── vnma.toml
```

RIF importa Gram así:

```python
from gram import config
from gram import lexer
```

La sintaxis usa `;` como comentario, conserva los tokens `NEWLINE` y desactiva
la indentación porque las Rules delimitan sus instrucciones por líneas.
