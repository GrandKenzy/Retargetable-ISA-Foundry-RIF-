# Diagnóstico y pruebas

RIF informa los errores en la fase donde se detectan. La API puede recogerlos
con `DiagnosticBag`; cada diagnóstico conserva fase (`frontend`, `rules`,
`mir`, `layout` o `fixups`), archivo, línea, Rule, sección y token cuando
están disponibles.

## Errores sintácticos

Gram reporta delimitadores faltantes, tokens inválidos, filas incompletas y
bloques `frame` mal formados. En tablas, revisa el `|` final y la fila de
separación.

## Errores semánticos

Incluyen tokens, tablas, columnas o Rules desconocidas, reservas inválidas,
claves duplicadas, anchos incorrectos y configuración inválida. Ocurren antes
de ejecutar el MIR.

## Errores de runtime

`RIFRuntimeError` cubre consumidores con token incorrecto, pop de datastack
vacío, ausencia de una fila, inmediatos que no caben, rangos fuera de memoria,
reservas o Rules desconocidas y retornos inválidos de funciones nativas.

## Trazas

```python
result.context.last_rule_trace
result.context.rule_traces
```

Las trazas muestran inicio, bits físicos y virtuales, final y padding de cada
Rule.

La CLI usa el mismo formato estructurado para errores de frontend, Rules, MIR,
layout y relocaciones, en vez de convertir cada fase a un mensaje distinto.

## Ejecutar pruebas

```powershell
vnma test
```

Ese comando ejecuta la suite esencial. Las otras capas son explícitas:

```powershell
vnma test test/suite_aggressive
vnma test test/dedicated_suite
```

La suite esencial cubre Gram, tablas, paquetes, compilación CLI y directa de
MIR, memoria física y virtual, datastack y rutas de error. La agresiva cubre
benchmarks y estrés; la dedicada cubre AOT, PCP-I, plugins, doctores y
contratos específicos que pueden cambiar junto con una API.
