# Diagnóstico y pruebas

RIF informa los errores en la fase donde se detectan.

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

## Ejecutar pruebas

```powershell
vnma test
```

La suite cubre integración con Gram, tablas, paquetes, compilación CLI y
directa de MIR, funciones nativas, memoria física y virtual, datastack y rutas
de error.
