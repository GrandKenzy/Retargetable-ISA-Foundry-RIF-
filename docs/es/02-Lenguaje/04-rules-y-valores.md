# Rules y valores

El cuerpo de una Rule es una secuencia de instrucciones, una por línea.

## Consumidores de tokens

```rif
. IDENT
. KW "ret"
. [NUMBER, STRING]
```

Los nombres canónicos como `IDENT` y `NUMBER` consumen el token esperado. `KW`
exige un keyword con valor exacto. La forma entre corchetes guarda el primer
token candidato que coincida.

## Control de Rules

```rif
. JUMP mov
. JUMPIF mov, true
. JUMPIF mov, #call[should_jump]
. BREAK
. ERROR, "instrucción inválida"
```

`JUMP` llama otra Rule y regresa al terminar. `JUMPIF` la llama solo si la
condición es verdadera. `BREAK` termina el flujo actual. Las referencias
`#call[...]` solo podrán resolver funciones nativas registradas.

El almacenamiento de tokens es distinto del datastack:

```rif
. save "current"
. load "current"
```

`save` guarda el token actual bajo un label. `load` exige que el token actual
coincida con el guardado y después lo consume.

## Emisión

```rif
. nibbles 0000 0001
. emit 1 0 1 0 1 0 1 0
. eword 4660
. frame 0000 0
00000000
0000
. frameend
```

`nibbles` emite dos campos de cuatro bits; `emit`, ocho campos de un bit; `eword`,
una palabra de `word_size`; y `frame`, un frame multilinea con cualquier
`VALUE`.

## Tablas, reservas y posiciones

```rif
. reserve "slot" 16
. write_res "slot" 0000000011111111
. emit_res "slot"
. drop_res "slot"
. eword &slot
. eword ::SIZE
. eword ::VSIZE
```

`&slot` lee una reserva. `reserve` crea bits en cero, `write_res` los parchea,
`emit_res` copia la reserva al cursor y `drop_res` quita su nombre sin limpiar los
bits ya emitidos.

## Símbolos nativos

`mark` registra el token actual como símbolo en la posición física y virtual
actual. No consume ese token; una Rule puede conservar el contrato habitual:

```rif
@rule mark:
. IDENT
. mark
. IDENT
```

La tabla queda disponible en `RIFMachine.symbols` con offsets relativos y en
`MIRCompilation.symbols` con direcciones virtuales absolutas después del
layout. Los nombres duplicados se rechazan.

Una relocación diferida usa la reserva física y el símbolo del token actual:

```rif
. reserve "fix32" 32
. fixup pc32 "fix32"
. drop_res "fix32"
```

`pc8` y `pc32` escriben desplazamientos signed relativos a la siguiente
instrucción; `abs64` escribe una dirección virtual absoluta. Se validan y
aplican juntas después del MIR, permitiendo símbolos definidos más adelante
sin dejar parches parciales.

La directiva MIR `::RIF_SECTION text` cambia el emisor activo de un MIR
sectionado. Solo está disponible cuando la ejecución tiene una
`AssemblyImage`; los símbolos y relocaciones conservan la sección donde fueron
definidos.

## Ajuste de inmediatos

```rif
. fit 8
. fit_exact 8
. fit_not 8
. fit $registers.name[rax].bits
```

Estas instrucciones usan el token MIR actual. `fit` conserva los bits bajos
si el valor es demasiado grande. `fit_exact` falla si no cabe. `fit_not` consume
solo cuando no cabe.

## Formas de `VALUE`

Se aceptan literales numéricos y string, booleanos, accesos a tablas, reservas,
llamadas y consultas de posición:

```rif
$registers.bits
$registers.name[rax].bits
&slot
#call[get_bits]
::SIZE
::VSIZE
::ALIGNMENT
dist "mov"
vdist "mov"
resdir "slot"
resvdir "slot"
resdist "slot"
resvdist "slot"
reswidth "slot"
vreswidth "slot"
```

Los consumidores aceptan nombres canónicos de `gram.lexer.Token` o el número
de su enum. El grupo `token_names` se rellena con todos los miembros del enum
al iniciar el frontend.

Los strings binarios conservan sus ceros iniciales. Por eso `0000`, `"0000"`
y un número pueden ser útiles en contextos distintos: la primera forma conserva
el ancho escrito para campos fijos y el string se valida como una secuencia
completa de bits en runtime.
