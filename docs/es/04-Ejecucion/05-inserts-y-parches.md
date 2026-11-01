# Directivas binarias del MIR externo

Los preámbulos binarios y los parches finales pertenecen al programa MIR
externo, no a la definición `.rif`. El preprocesador consume estas líneas
antes de despachar Rules y nunca las entrega a una Rule.

## `::RIF_INSERT`

Inserta bytes, cadenas binarias o un archivo local en una sección configurada:

```asm
::RIF_INSERT BYTES "7f454c46" SECTION text
::RIF_INSERT BINARY "00000001" SECTION text
::RIF_INSERT FILE "header.bin" SECTION text
```

`BYTES` exige bytes hexadecimales completos. `BINARY` solo acepta `0` y `1`.
`FILE` acepta una ruta relativa que permanezca dentro del proyecto del MIR.
La directiva se aplica antes de la primera línea externa de una Rule.

## `::RIF_PATCH`

Los parches se evalúan después de todas las Rules y cuando ya existe el layout
final de las secciones:

```asm
::RIF_PATCH 24, 8, #:calc(4194304 + #:qlsize(0, "_start"))
::RIF_PATCH 96, 8, #:qssize(0, "text")
::RIF_PATCH 104, 8, #:calc(#:qvssize(0, "text") - 4194304)
```

El ancho opcional se expresa en bytes. Las expresiones nativas se limitan a
literales, `+`, `-`, `#:calc`, `#:query`, `#:qssize`, `#:qlsize`, `#:qvsize` y
`#:qvssize`. Las llamadas arbitrarias `#call[...]` se rechazan. Todos los
parches se validan antes de confirmar los bytes finales.

## Storage y adquisición

El preprocesador externo también reconoce `::RIF_BUFFER`, `::RIF_REQSTS` y
`::RIF_STORE`. Estas directivas adquieren bytes con capacidad limitada, cargan
un payload etiquetado desde un contenedor `.bin` validado o extraen un rango
del buffer. Sus reglas se documentan junto al MIR externo.

Los bloques antiguos `@insert`, `@before`, `.bytes`, `.binary`, `.file` y
`.patch` no son sintaxis válida de `.rif` ni aliases de compatibilidad.
