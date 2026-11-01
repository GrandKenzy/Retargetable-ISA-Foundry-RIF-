# Funciones nativas

RIF no carga ni ejecuta `funcs.py`. Las funciones del lenguaje deben ser
deterministas, estar registradas dentro de RIF y usar contratos con valores
primitivos para poder tener una implementación equivalente en C.

## `calc`

La primera función nativa es `#:calc`, disponible en expresiones de
`::RIF_PATCH`:

```rif
::RIF_PATCH 0, 4, #:calc(4096 + 128)
::RIF_PATCH 4, 4, #:calc(8192 - 4096)
```

Solo se admiten `+` y `-`. El ancho resultante es el mayor ancho de sus dos
operandos. Los resultados fuera del rango signed `int64` se rechazan antes de
aplicar el parche.

La implementación canónica vive en `MIR/functions/calc.py`; no depende del
runtime, del estado de una Rule ni de módulos del proyecto.

## `reqsts`

`reqsts` descarga bytes crudos desde GitHub dentro de la fase externa del
buffer. El branch es obligatorio y debe ser el último segmento:

```rif
::RIF_BUFFER SET 512
::RIF_BUFFER CLEAN
::RIF_REQSTS "github.com/GrandKenzy/RIFIMG/images/img.bin/main"
::RIF_BUFFER EXTRACT 0 8
```

Solo se aceptan archivos `.bin`, HTTPS y hosts oficiales de GitHub. El tamaño,
el timeout, las redirecciones y las respuestas HTTP se validan antes de
devolver los bytes. Los fallos se muestran mediante `Diagnostics` de Gram en
la consola y después se propagan como error de compilación; `DiagnosticsLite`
queda reservado para el lexer/parser AOT en C.

## `#call[...]`

La forma `#call[nombre]` queda reservada para futuras funciones nativas
cerradas. No es un mecanismo para cargar Python externo y un nombre no
registrado produce un error determinista.
