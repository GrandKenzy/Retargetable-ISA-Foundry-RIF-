# Estructura de plugin

Forma minima:

```python
from rif import Expr, Line

def main():
    Line.Advance()
    return Expr(["op"])

def _start():
    return main()
```

APIs usuales:

- `Line`: tokens de la instruccion actual
- `RuleIndicator.current`: regla activa
- `Operators`: bindings declarados con `need`
- `PluginContext`: contexto de fase, programa y linea
- `Err`: error controlado
- `Expr`: IR para el compiler

El plugin debe evitar estado global propio salvo que pueda reiniciarse por contexto.
