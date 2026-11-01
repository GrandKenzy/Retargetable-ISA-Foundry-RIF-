# Memoria de bits

RIF escribe directamente en `BitBuffer`. Un campo puede comenzar o terminar en
cualquier bit, sin limitarse a bytes completos.

## Cursor físico

```rif
. nibbles 0000 0001
. emit 1 0 1 0 1 0 1 0
. eword 4660
. bits 5 3
```

La emisión normal avanza el cursor físico, consultable con `::SIZE`. `eword`
usa `word_size`; `nibbles` y `emit` tienen anchos fijos; `bits` recibe valor y
ancho explícitos.

## Reescribir bits

```rif
. read_bits 0 8
. patch_bits 0 8 255
```

`read_bits OFFSET WIDTH` lee un rango físico y apila su entero en el datastack.
`patch_bits OFFSET WIDTH VALUE` reescribe el rango sin avanzar los cursores.
Fuera de rango falla antes de modificar el buffer.

Los anchos múltiplos de ocho respetan `byte_order`; los demás respetan
`bit_order`.

## Padding y alineamiento

```rif
. pad 3
. align 16
```

Ambos emiten ceros y avanzan los dos cursores. `pad` agrega el ancho
exacto. `align N` alcanza el siguiente múltiplo de `N`. Ambos se registran
como padding en `RuleTrace`.

Las versiones virtuales avanzan solamente `::VSIZE`:

```rif
. vpad 8
. valign 32
```

## Reservas

```rif
. reserve "header" 16
. write_res "header" 0000000011111111
. emit_res "header"
. drop_res "header"
```

Una reserva física agrega bits en cero y conserva un rango con nombre. `write_res`
lo parchea, `emit_res` lo copia al cursor y `drop_res` quita el nombre sin limpiar
los bits ya emitidos.

```rif
. vreserve "scratch" 64
```

Una reserva virtual no crea bits físicos. `resdir`, `resvdir`, `reswidth`,
`vreswidth`, `resdist` y `resvdist` consultan su metadata.

## Trazas

Cada invocación crea un `RuleTrace` con inicio, ancho y final físicos y
virtuales, además del padding de cada espacio. Una Rule padre incluye el output
de sus Rules hijas.

## API de bajo nivel

Los callers Python pueden usar directamente `BitBuffer`:

```python
query = buffer.query("header")
bits = buffer.read_bit_sequence(0, 12)
checkpoint = buffer.checkpoint()

with buffer.transaction():
    buffer.write_bits(0, 3, 2)
```

`rollback(checkpoint)` restaura almacenamiento, tamaño y regiones.
`transaction()` revierte automáticamente si su cuerpo falla. `to_bytes()`
devuelve una copia serializada y `view()` una vista viva. `BitQuery` expone el
valor entero, bits, rango y bytes cuando el rango está alineado.

Una ejecución de Rule usa la misma idea para el emisor físico y virtual:
si una instrucción falla, se restauran bits, reservas, posiciones virtuales,
símbolos, fixups, datastack y selección de sección. `AssemblySection` expone
`file_size`/`initialized_size`, `virtual_size` y `uninitialized_size`; las
reservas `vreserve` ocupan solamente el último espacio.

`AssemblyImage.render()` genera una representación de las secciones usando la
configuración de `format section`, `format section_end`, labels, comentarios y alineación.
