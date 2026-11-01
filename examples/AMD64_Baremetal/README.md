# RIF AMD64 Baremetal

Este ejemplo describe un emisor de bytes AMD64 para imágenes raw. No depende
de un sistema operativo, ABI, linker externo ni formato de objeto.
RIF no intenta ser un ensamblador completo: las tablas y Rules cubren las
familias de encoding que este target declara.

## Qué contiene

- `main.rif`: target AMD64 raw con una sección `text`.
- `main_rw.rif`: target AMD64 raw con `text` y `data` alineada a 4096 bytes.
- `registers.rif`, `encoding.rif`, `arithmetic.rif`, `width8.rif`,
  `width16.rif`, `width32.rif`, `memory.rif`, `addressing.rif`, `control.rif`,
  `branches.rif`, `integer.rif`, `prefixes.rif`, `conditions.rif`,
  `instructions.rif`: tablas y Rules de registros, REX, ModR/M, SIB, memoria,
  aritmética, control, enteros y prefijos.
- `relocations.rif`: símbolos, `pc8`, `pc32`, `abs64`, referencias RIP-relative,
  reservas y posiciones virtuales.
- Los programas MIR y fixtures raw viven fuera del target, en
  `examples/probe/probe_amd64/`; este directorio conserva solo la definición
  AMD64, sus pruebas y los paquetes compilados.

## Perfil cubierto por este ejemplo

El perfil declara explícitamente estas familias, siempre como Rules y tablas
del target, no como conocimiento AMD64 dentro del núcleo RIF:

- registros GPR de 8, 16, 32 y 64 bits, incluidos bytes altos legacy y las
  formas base de operaciones lógicas/aritméticas declaradas;
- inmediatos `imm8`, `imm32` e `imm64`, con validación signed/unsigned según la
  codificación (`movabs` cubre el inmediato completo de 64 bits);
- memoria base e indexada sin desplazamiento, con `disp8` signed y `disp32`,
  incluidos `RSP`, `R12`, `RBP` y `R13` mediante SIB o desplazamiento cero;
- ramas directas cortas y largas para las 16 condiciones, más branches
  indirectos por registro y por memoria.

La extensión entera base incluye unarias (`not`, `neg`, `inc`, `dec`),
`mul`/`imul`/`div`/`idiv`, shifts variables por `CL`, shifts inmediatos de
32 bits, bit-test/bit-modify, `bsf`/`bsr`, `popcnt` y `bswap`. La extensión de
prefijos incluye `0x66` en las formas de 16 bits, `0x67` para direcciones de
32 bits, `LOCK` en memoria read-modify-write, `REP` para formas string y
segmentos `FS`/`GS`.

El alcance ISA es deliberadamente `amd64-base-integer`: MMX, SSE, AVX,
AVX-512, x87 y system instructions están declarados como excluidos. Su
ausencia produce rechazo normal por falta de Rule; no se agrega una tabla
universal de la ISA.

Las formas se mantienen separadas por nombre MIR (`load64_0`, `load64_8`,
`load64`, `jcc8`, `jcc32`, etc.) para que el matching sea explícito y el
preprocesador pueda seleccionar el MIR compatible. El ejemplo no afirma ser un
ensamblador AMD64 completo.

## Empaquetar y emitir

Desde la raíz de RIF:

```bash
vnma run rif.py --pack examples/AMD64_Baremetal/main.rif \
  -o examples/AMD64_Baremetal/amd64.pack
vnma run rif.py --pack examples/AMD64_Baremetal/main_rw.rif \
  -o examples/AMD64_Baremetal/amd64-rw.pack

vnma run rif.py examples/AMD64_Baremetal/amd64.pack \
  examples/probe/probe_amd64/symbols.mir \
  -o examples/AMD64_Baremetal/symbols.bin
vnma run rif.py examples/AMD64_Baremetal/amd64-rw.pack \
  examples/probe/probe_amd64/sections.mir \
  -o examples/AMD64_Baremetal/sections.bin
```

Las salidas son bytes raw. El consumidor bare metal decide cómo ubicarlas en
memoria, qué dirección de entrada usar y cómo configurar segmentos, paginación
o dispositivos. RIF solo genera los bits y resuelve los fixups declarados.

## Pruebas

```bash
vnma run examples/AMD64_Baremetal/tests/test_encoding.py \
  --rif-root .
vnma run examples/AMD64_Baremetal/tests/test_relocations.py \
  --rif-root .
vnma run examples/AMD64_Baremetal/tests/test_profile_points.py \
  --rif-root .
vnma run examples/AMD64_Baremetal/tests/test_integer_prefixes.py \
  --rif-root .
vnma run examples/AMD64_Baremetal/tests/test_external_oracle.py \
  --rif-root .
```

`test_encoding.py` compara directamente los bytes raw con un oráculo
independiente y cubre 13.072 combinaciones. `test_relocations.py` valida
símbolos, rangos, fixups, secciones, layout virtual, reservas y errores sin
intentar ejecutar el resultado en el sistema operativo anfitrión.
`test_profile_points.py` añade el oráculo independiente de los puntos de
anchos, direccionamiento, branches e inmediatos y verifica las 16 condiciones
en sus formas corta y larga.
`test_integer_prefixes.py` valida las extensiones enteras, prefijos y el
alcance declarado. `test_external_oracle.py` compara 60 formas representativas
de todas las familias activas contra el ensamblador integrado de LLVM mediante
Clang/`llvm-objcopy`; NASM y LLVM MC permanecen disponibles como oráculos
opcionales cuando el entorno los instala. El cross-check evita formas con
codificaciones equivalentes pero no únicas, como ciertos `mov`/`test`, y fuerza
SIB o `disp32` cuando LLVM puede escoger una forma más corta.

## Contrato de relocaciones

```rif
@rule jmp_label:
. IDENT
. bits 233 8
. reserve "fix32" 32
. fixup pc32 "fix32"
. drop_res "fix32"
. IDENT
```

`pc8` y `pc32` escriben `target - next_ip` en complemento a dos y validan el
rango signed. `abs64` escribe la dirección virtual del símbolo en 64 bits
little-endian. `::RIF_SECTION` cambia la sección de la entrada MIR; no es una
instrucción de la definición `.rif`.

## Límites intencionales

- No hay ensamblado completo de AMD64.
- No se genera formato de objeto, tabla de relocaciones externa, PLT/GOT, PIE
  ni enlace dinámico.
- No se ejecutan bytes generados en la máquina host.
- El layout de `main_rw.rif` es una imagen ilustrativa con `data` alineada a
  4096; no es un gestor universal de memoria bare metal.

