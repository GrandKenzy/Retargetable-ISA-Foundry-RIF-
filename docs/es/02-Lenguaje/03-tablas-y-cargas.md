# Tablas y cargas

Una tabla tiene una fila de encabezado, una fila separadora y una o más filas
de datos:

```rif
@table registers
| name | opcode | bits |
________________________
| mov  | 1      | 32   |
________________________
| add  | 2      | 32   |
@end
```

La separación debe tener dos o más `_` consecutivos. Se requiere una
separación entre filas y cada fila debe terminar en `|` antes del salto de
línea; con `ident_underscores = -2`, Gram la entrega como
`Token.UNDERSCORES`.

## Acceso a tablas

```rif
. $registers.name, IDENT
. nibbles $registers.opcode 0000
```

La primera instrucción compara el token actual con `name` y selecciona la fila.
Los accesos posteriores leen datos de esa fila.

El acceso indexado estático no consume un token MIR:

```rif
. fit $registers.name[rax].bits
```

RIF materializa la tabla como una matriz inmutable y construye índices
constantes para todas sus columnas. Las columnas auxiliares pueden repetir
valores; una columna solo debe ser única cuando se usa para seleccionar una
fila.

## Cargar fuentes

```rif
@LOAD "tables.rif"
@LOAD "rules.rif"
```

`@LOAD` resuelve rutas relativas, exige la extensión `.rif`, detecta ciclos y
conserva el alcance de la declaración. Un archivo cargado puede aportar tablas
y Rules, pero no configuración raíz.

## Tablas en paquetes

Al crear un `.pack`, las fuentes cargadas quedan en el manifiesto junto con su
orden de dependencias. Un paquete precompilado guarda las filas en SQLite. Al
abrirse, RIF reconstruye la matriz inmutable y sus índices.
