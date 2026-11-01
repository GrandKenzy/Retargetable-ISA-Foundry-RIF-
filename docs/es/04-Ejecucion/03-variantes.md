# Variantes

Las variantes permiten delegar sintaxis a otro archivo RIF, por ejemplo entre
los estados ARM y Thumb.

## Declaración

```rif
@SUPPORTS thumb

@ASMVARIANT thumb:
.MODE SWITCH
.ENTER "ENTER_thumb"
.EXIT "EXIT_thumb"
@END
```

El archivo se llama `thumb.rif` y se resuelve usando la búsqueda del linker.
Solo puede contener definiciones y Rules:

```rif
@define thumb_word

@rule ENTER_thumb:
. KW "thumb"

@rule EXIT_thumb:
. KW "endthumb"
```

Las tablas, configuración, linker y demás contexto global siguen siendo los
de la raíz.

## Modos

`SWITCH` representa un cambio de estado del ensamblador. `ENCAPSULATE`
representa una región sintáctica anidada. Ambos usan `.ENTER` y `.EXIT`.

RIF detecta cargas repetidas y ciclos, y valida que existan todas las Rules
referenciadas.

En un `.pack`, los archivos de variantes forman parte del grafo de fuentes y
se cargan desde el orden precalculado.
