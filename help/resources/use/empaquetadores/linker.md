# Linker

El linker construye bloques de salida desde `.sections`, resultados compilados, datos, memoria y headers.

Soporta:

- secciones con orden, permisos, alineacion y relleno
- secciones `nobits`
- headers declarativos
- placeholders
- relocaciones
- regiones `stack` y `heap`
- expresiones `link:*`

El linker no debe saber reglas de una arquitectura. Solo organiza bytes, offsets y referencias.
