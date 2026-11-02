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

## Operaciones de tablas

Las declaraciones pueden derivar columnas desde otra tabla. El selector entre
corchetes se toma de la fila actual y la columna de origen se convierte en el
nombre de la columna derivada:

```rif
@table membase
| name | %[name]=registers.lo% | %[name]=registers.hi% | sib |
__
| rax | %othertable.name[r12].sib% |
@end
```

`%[name]=registers.lo%` busca en `registers.name` usando el `name` de la fila
actual y copia `registers.lo`. Las columnas derivadas se omiten de las filas;
las celdas restantes llenan las columnas literales en el orden de la cabecera.
Una consulta como `%othertable.name[r12].sib%` selecciona la fila única cuyo
`name` es `r12` y copia su valor `sib`.

Las operaciones se resuelven al materializar las tablas. Se permiten
referencias hacia adelante, pero son errores las tablas o columnas inexistentes,
las claves ausentes, las claves selectoras duplicadas y los ciclos de
dependencias. El `.pack` guarda solamente la matriz inmutable ya resuelta, por
lo que el runtime y el backend AOT no necesitan otro evaluador de expresiones
de tablas.

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
