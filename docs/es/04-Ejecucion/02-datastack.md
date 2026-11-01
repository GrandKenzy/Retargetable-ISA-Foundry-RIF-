# Datastack

El datastack es una pila LIFO de valores compartida por las Rules durante una
compilación MIR. Es independiente del stack de tokens de `@stack`.

## Push y pop

```rif
@rule prepare:
. dpush 64

@rule encode:
. fit dget
```

`dpush VALUE` evalúa y apila. `dget` usado como `VALUE` extrae el valor
superior. `dpeek` lo consulta sin extraerlo; `dpop` lo descarta y `::ddepth`
devuelve la profundidad.

`fits dget` valida el ancho y solo lo extrae después de un ajuste exitoso. Un
`fit_exact` fallido conserva el ancho para que una Rule pueda recuperarlo.

## Carga desde tablas

```rif
. dget ::registers.names : bits
```

La forma de instrucción de `dget`:

1. Lee el valor del token actual.
2. Lo busca en `registers.names`.
3. Apila el campo `bits` de la fila encontrada.
4. Consume el token actual.

La columna selectora necesita claves únicas. Si no encuentra el token, la Rule
falla sin consumirlo ni modificar la pila.

## Duración del estado

`RIFMachine.execute` inicia una ejecución aislada y limpia el datastack.
`execute_line` conserva datastack, reservas y demás estado entre líneas MIR.
Las funciones nativas futuras recibirán contratos explícitos; no existe un
contexto Python dinámico con acceso directo al datastack.
