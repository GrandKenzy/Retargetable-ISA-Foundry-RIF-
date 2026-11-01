# Suite esencial

Pruebas fundamentales que deben ejecutarse en cada cambio. Cubren la gramática
base, el procesamiento semántico, MIR, runtime, buffers, variantes y el flujo
principal de empaquetado.

Ejecución:

```powershell
vnma test suite-essencial
```

El lanzador por defecto `vnma test` apunta a esta suite mediante
`tests/test_essential_suite.py`.
