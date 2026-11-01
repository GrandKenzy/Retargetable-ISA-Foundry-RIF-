# RIF AMD64 Linux v3 — símbolos, relocaciones y memoria virtual

**Objetivo:** Linux x86-64, System V AMD64, ELF64 ejecutables estáticos `ET_EXEC`.
**Motor utilizado:** RIF con Gram AOT por defecto y semántica Python, sin
modificar las fuentes de Gram.
**Advertencia:** Prototipo de codificación AMD64 y enlace de ejecutables pequeños; **NO** es un linker ELF completo, un ensamblador completo ni un reemplazo de LLVM.

## Archivos

- `main.rif`: definición de arquitectura, secciones y ELF64 RX con un PT_LOAD.
- `main_rw.rif`: variante ELF64 con **dos PT_LOAD**, `.text` RX (base `0x400000`) y `.data` RW (base `0x401000`, offset en fichero `0x1000`).
- `registers.rif`, `encoding.rif`, `arithmetic.rif`, `width32.rif`, `memory.rif`, `control.rif`, `conditions.rif`, `instructions.rif`: familias AMD64 anteriores (REX, ModRM, SIB, MOV, aritmética, memoria, stack, condiciones).
- **`relocations.rif`**: nuevas Rules para símbolos, relocaciones PC-relative (`rel8` y `rel32`), `abs64`, acceso RIP-relative, reservas y posiciones virtuales.
- **`funcs.py`**: puente de *link* explícito (escape Python documentado de RIF); la Rule MIR `link_image` aplica los fixups y el módulo habilita cambios de sección entre líneas MIR.
- Los paquetes se generan localmente; no se incluyen `.pack`, ELF ni binarios
  generados en el ejemplo.
- `symbols_runtime.asm`: saltos y CALL a etiquetas, lectura de texto RIP-relative e impresión `Hi` con syscall `write`.
- `symbols_rw.asm`: escritura a `.data`, lectura de `.data`, referencias RIP-relative, reserva virtual de 32 B, syscall `write` y `exit(42)`.
- `tests/test_encoding.py`: verificador anterior de 13.073 combinaciones de instrucciones AMD64.
- `tests/test_relocations.py`: nuevos test de resoluciones, memoria virtual, errores y ejecución de ELF.

## Compilación

Desde la raíz del proyecto RIF:

```bash
vnma run rif.py --pack examples/AMD64-Linux-v3/main.rif \
  -o examples/AMD64-Linux-v3/amd64.pack
vnma run rif.py --pack examples/AMD64-Linux-v3/main_rw.rif \
  -o examples/AMD64-Linux-v3/amd64-rw.pack

vnma run rif.py examples/AMD64-Linux-v3/amd64.pack \
  examples/AMD64-Linux-v3/symbols_runtime.asm \
  -o examples/AMD64-Linux-v3/symbols_runtime.elf
vnma run rif.py examples/AMD64-Linux-v3/amd64-rw.pack \
  examples/AMD64-Linux-v3/symbols_rw.asm \
  -o examples/AMD64-Linux-v3/symbols_rw.elf
chmod +x examples/AMD64-Linux-v3/symbols_runtime.elf \
  examples/AMD64-Linux-v3/symbols_rw.elf
examples/AMD64-Linux-v3/symbols_runtime.elf
# Hi
# exit(42)
```

En Windows puedes generar los `.pack` y revisar el GIR/binario resultante,
pero la ejecución de los ELF requiere Linux AMD64 o WSL.

Para las pruebas de codificación y relocaciones:

```bash
vnma run examples/AMD64-Linux-v3/tests/test_encoding.py \
  --rif-root .
vnma run examples/AMD64-Linux-v3/tests/test_relocations.py \
  --rif-root .
```

Si Gram no está en el entorno de Python de VNMA, añade
`--gram-root /ruta/Gram-main` al segundo script.

## Nuevas instrucciones MIR

```asm
mark label                 ; define símbolo en la VA actual
jmp_label label            ; E9 + rel32 (adelante o atrás)
jmp8_label label           ; EB + rel8
call_label label           ; E8 + rel32
jcc_label ne, label        ; 0F 85 + rel32
learip64 rsi, label       ; LEA rsi, [rip + rel32]
loadrip64 r10, label      ; MOV r10, [rip + rel32]
storerip64 rax, label     ; MOV [rip + rel32], rax
movaddr64 r9, label       ; MOVABS r9, dir.virtual.64
dqaddr label              ; emite dirección virtual de 64 bits
use_data                  ; seleccionar .data vía CALLBACK
use_text                  ; seleccionar .text vía CALLBACK
db 72                     ; emitir un byte
dq 42                     ; emitir uint64 en little-endian
virtual_scratch           ; vreserve 256 bits, no bytes físicos
reserve_and_fill_demo    ; reserve/write_res/drop_res demostrados sin Python
reserve_position_demo    ; reserva + resvdir (bit offset virtual)
```

### Cómo se reserva un desplazamiento de salto

```rif
@rule jmp_label:
. IDENT
. bits 233 8
. reserve "fix32" 32
. fixup pc32 "fix32"
. drop_res "fix32"
. IDENT
```

- `reserve` añade **cuatro bytes cero** al código máquina y crea un rango nombrado.
- `fixup pc32 "fix32"` recibe el nombre del símbolo aún sin consumir y registra
  el rango junto con la dirección virtual de la instrucción **siguiente**. La
  resolución nativa ocurre después de todas las líneas MIR.
- `drop_res` libera el *nombre* para reutilizarlo en la siguiente instrucción sin eliminar los cuatro bytes reservados.
- La línea MIR `link_image` sigue llamando al hook Python para las familias del
  ejemplo que todavía no fueron migradas; `pc32` ya no depende de ese hook.
- La fase final del preprocesador MIR aplica únicamente los parches **nativos** de cabecera ELF con `::RIF_PATCH`, usando `#:qvsize`, `#:qssize` y `#:qvssize`.

Para `PC32`, se calcula `target_va - next_instruction_va`, se verifica el rango signed 32-bit y se emite el complemento a dos en little-endian; `PC8` usa signed 8-bit. Para `ABS64`, se emite la VA absoluta de 64 bits.

## Resultados **verificados en Linux x86_64**

- Pack RX: **25.365 bytes**; pack RX/RW: **25.366 bytes** (incluyen el Python externo de enlace).
- **13.073** codificaciones AMD64 existentes conservadas, **68.361 bytes** comparados con un codificador de referencia independiente.
- **27** verificaciones nuevas de relocaciones, direcciones virtuales, reservas y errores intencionales.
- **Dos ELF adicionales** ejecutados en Linux: ambos imprimen `Hi` y terminan con `exit(42)`.
- ELF RW: `PT_LOAD` RX de 239 bytes; `PT_LOAD` RW con `p_filesz=11` y `p_memsz=43`. Los 32 bytes extra provienen de **`vreserve`**, no de datos grabados en el archivo.
- Errores rechazados: símbolo no definido, símbolo duplicado, identificador inválido, desbordamiento de `rel8`; el linker no deja parches parcialmente aplicados en el resultado.

## Detalles y límites encontrados

1. **El ejemplo todavía conserva un escape Python (`funcs.py`) para la orquestación restante.** RIF ya ofrece `mark` y `fixup pc8|pc32|abs64` nativos; la Rule MIR `link_image` y la selección dinámica de secciones del ejemplo siguen siendo parte del experimento Python y no deben atribuirse al núcleo nativo.
2. **`write_res` escribe bits en el orden de bitstream, no serializa un entero little-endian.** `reserve_position_demo` captura `resvdir` (medido **en bits**, sección-local) y demuestra esta diferencia. Para relocaciones Intel usamos `int.to_bytes(..., 'little')` en el enlace.
3. **Cambiar entre `.text` y `.data` dentro de un único MIR requiere un callback** que selecciona el `BitEmitter` correspondiente. La API estándar `compile_mir_source` inicializa un único `section`. Esta técnica sirve como experimento y puede alterar la interpretación de `RuleTrace` alrededor de los cambios de sección; no es una directiva nativa de MIR.
4. `main_rw.rif` fija `.data` en `0x401000` y offset de fichero `0x1000`; los textos mayores de una página se rechazan para evitar solapamientos. Es un layout ilustrativo, no un asignador flexible de segmentos. El programa MIR debe volver a `.text` al terminar si usa la consulta nativa de `_start` en la cabecera.
5. **ELF ejecutable != objeto relocatable.** No generamos ELF `ET_REL`, registros `.rela.text`, símbolos ELF externos, resolución entre objetos, PLT/GOT, PIE, ASLR o enlazado dinámico. Los fixups se resuelven antes de producir el ejecutable final.
6. No hay ensamblado completo de AMD64, ni verificación de todas las reglas ejecutadas por CPU. La regresión verifica bytes y hay programas de ejemplo controlados.
7. Una reserva virtual de 32 B al final de `.data` aumenta `p_memsz` sin incrementar `p_filesz`, pero **`vreserve` por sí misma no gestiona permisos, segmentación o BSS ELF**: eso lo hace el layout definido en `main_rw.rif`.

## Recomendaciones al núcleo RIF

- Orquestación nativa para seleccionar secciones durante un mismo MIR y
  publicar relocaciones entre ellas sin un callback externo.
- Selección nativa de sección por instrucción MIR sin alterar internamente `RIFMachine.emitter` desde Python.
- API con offsets dinámicos para `::RIF_PATCH`, o fixups basados en regiones.
- Especificar en la documentación las diferencias de orden de bits entre `write_res` y emisión de enteros little-endian.

**Ningún archivo de Gram, VNMA ni el núcleo RIF se ha cambiado.**
