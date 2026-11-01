# Pendientes de RIF

Estado actualizado: 2026-11-01. La cola global de RIF y del perfil AMD64 está
cerrada.

Este backlog conserva la separación real del proyecto:

```text
.rif  = definición declarativa del target
.pack = definición .rif compilada y distribuible
.mir  = programa compatible con el .pack
.pack + .mir = binario final
```

RIF no debe convertirse en un ensamblador universal ni en un compilador que
conozca de antemano una arquitectura concreta.

Las tablas son datos extensibles del target: pueden existir muchas tablas y
cada una puede contener cualquier metadata que las Rules necesiten. No se debe
crear una estructura rígida paralela para registros, opcodes u otra categoría
que ya pueda expresarse mediante tablas.

## Pendientes globales de RIF

- [x] Formalizar y documentar el contrato de las dos fases: compilación del
  target (`.rif` → `CompiledRuleSet`/`.pack`) y compilación del programa
  (`.pack + .mir` → imagen/binario).
- [x] Reducir la lógica repetida que deben escribir los autores de `.rif` con
  helpers genéricos para matching de operandos, selección de tablas y emisión
  de campos.
- [x] Añadir y consolidar primitivas declarativas reutilizables para campos,
  registros, inmediatos signed/unsigned, memoria, reservas y relocaciones,
  sin introducir semántica de una ISA en el núcleo.
- [x] Mejorar el matching de operandos con selección tipada de tablas y
  validación de anchos, signo, rangos y restricciones mediante Rules
  declarativas; las clases siguen siendo metadata extensible de las tablas.
- [x] Validar el target completo antes de aceptar MIR: Rules, extensión,
  secciones, tablas, variantes y políticas de salida/símbolos. Los símbolos
  concretos siguen siendo datos del MIR y se validan durante su compilación.
- [x] Unificar los diagnósticos de frontend, Rules, MIR, layout y fixups con
  archivo, línea, tokens consumidos, regla activa y contexto de sección.
- [x] Garantizar que los errores de emisión sean transaccionales y nunca dejen
  una imagen o binario parcial utilizable por accidente.
- [x] Completar el modelo genérico de layout: dirección virtual, offset físico,
  reservas, alineación, secciones vacías, espacios de dirección y regiones no
  inicializadas.
- [x] Ampliar las relocaciones genéricas según las necesidades de los targets,
  manteniendo su declaración en `.rif` y su resolución en la fase MIR.
- [x] Añadir una herramienta de inspección de `.pack` que muestre Rules,
  tablas, configuración, linker, variantes, fingerprint, versión y extensiones
  MIR aceptadas.
- [x] Versionar explícitamente el contrato entre `.pack`, SQLite compilado,
  Gram, backend AOT y runtime.
- [x] Proteger la invalidación de caches cuando cambien fuentes, tablas, Gram,
  el compilador o el esquema de datos. El contrato incluye la huella de las
  fuentes de producción de RIF; AOT añade sus fuentes nativas, Gram/GIR y
  compilador C; `.pack` y SQLite validan contenido, contrato y esquema.
- [x] Añadir mapas de salida opcionales con símbolos, secciones, offsets,
  tamaños, reglas ejecutadas y relocaciones resueltas mediante la API
  `MIRCompilation.output_map()`, `map_output=` y la opción CLI `--map`.
- [x] Separar claramente en la API pública las operaciones de compilar un
  target (`compile_source`/`compile_pack`) y ejecutar MIR (`compile_mir_*`).
- [x] Mantener un preprocesador MIR extensible pero cerrado: nuevas directivas
  deben declararse, validarse y quedar fuera del despacho normal de Rules.
- [x] Mejorar la reutilización de targets preparados para compilar muchos MIR
  sin repetir carga, validación ni inicialización innecesaria mediante
  `PreparedTarget`.
- [x] Mantener paridad entre frontend Python y AOT/C en la superficie declarada:
  `Frontend.parity.compare_target()` compara AST, Rules y contexto completo;
  las suites cubren bloques, tablas, cargas, variantes y el fixture AMD64.
  Cada extensión futura debe añadir su fixture de paridad.
- [x] Generar scaffolding de tests para cada target: casos válidos, rangos,
  símbolos, errores y bytes esperados mediante
  `rif_tools.target_scaffold`.
- [x] Incorporar oráculos externos opcionales, fuzzing de operandos y pruebas
  de propiedades sin hacer que NASM, LLVM u otra herramienta sean dependencia
  obligatoria de RIF. `rif_tools.oracles` limita procesos, tiempo y salida;
  `rif_tools.properties` ofrece casos reproducibles por seed y las suites ya
  cubren sus casos base/agresivos.
- [x] Añadir una capa de paquetes/librerías de patrones RIF reutilizables entre
  targets sin hardcodear arquitecturas en el núcleo. `.riflib` es un ZIP fuente
  reproducible, `@LIBRARY` lo carga por filesystem o desde `.pack`, la CLI lo
  crea con `--library` y el inspector reporta sus dependencias.
- [x] Documentar y estabilizar la API C/AOT de las operaciones que pueden
  aparecer dentro de Rules. `MIR.operations` define la tabla cerrada, versión,
  descriptores, JSON, header e implementación C; `fit` y relocaciones consumen
  la misma tabla desde el runtime Python. El cambio actual usa runtime ABI 1.1.
- [x] Mantener límites de recursos, determinismo y reproducibilidad en `.pack`,
  layout, binarios y caches. La caché AOT, los paquetes reproducibles y las
  emisiones transaccionales ya tienen cobertura; quedan auditorías futuras.

## Pendientes específicos de AMD64

- [x] Completar operandos de 8, 16, 32 y 64 bits donde el target los declare.
- [x] Añadir direccionamiento sin desplazamiento, `disp8` y `disp32`.
- [x] Cubrir los casos especiales de `RSP`, `R12`, `RBP` y `R13` en ModR/M y
  SIB dentro del perfil actual de desplazamiento explícito `disp32`.
- [x] Completar ramas cortas y largas, incluyendo las 16 condiciones.
- [x] Añadir branches indirectos por registro y memoria.
- [x] Completar formas de inmediatos `imm8`, `imm32` e `imm64`.
- [x] Añadir instrucciones enteras que entren en el perfil base: operaciones
  unarias, shifts variables, multiplicación/división y operaciones de bits;
  las extensiones no declaradas siguen fuera del perfil.
- [x] Declarar y probar prefijos `0x66`, `0x67`, `LOCK`, `REP` y segmentos
  `FS`/`GS` dentro del perfil elegido.
- [x] Decidir explícitamente el alcance ISA: MMX, SSE, AVX, AVX-512, x87 y
  system instructions quedan excluidos del perfil base.
- [x] Completar las relocaciones AMD64 requeridas por el perfil actual (`pc8`,
  `pc32`, `abs64` y RIP-relative), sin introducir ELF, Linux, PLT, GOT o una
  ABI de host en el target bare metal.
- [x] Complementar el oráculo manual de `test_encoding.py` con comparaciones
  externas: 60 formas representativas contra el ensamblador integrado LLVM;
  NASM y LLVM MC quedan soportados de forma opcional por
  `rif_tools.oracles`. El cross-check además detectó y corrigió la separación
  `/2` de `callmem64_*` frente al `/4` de `jmpmem64_*`.
- [x] Definir el límite del contrato de carga bare metal: el target entrega
  bytes raw, secciones, direcciones virtuales y metadatos; dirección física,
  entrada, stack, paginación y dispositivos quedan explícitamente a cargo del
  loader consumidor.

## Referencias y foot

`foot/` es material de trabajo temporal para alimentar y verificar los ejemplos
de `examples/`. No es una dependencia del núcleo RIF ni un entregable final;
se eliminará cuando los ejemplos ya no necesiten estas referencias. Por ello
no genera pendientes de producto.

## Criterio de cierre

Un target se considera terminado cuando su `.rif` declara el alcance, su `.pack`
se valida y se reutiliza, sus `.mir` producen bytes reproducibles, sus símbolos
y fixups tienen pruebas de límites, y el perfil documenta explícitamente lo que
queda fuera.
