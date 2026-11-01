# Tablas de referencia binaria

Estas tablas son una referencia de trabajo para el backend x86-64 de RIF.
Describen la forma de los bytes, los puntos donde pueden aparecer símbolos y
el recorrido equivalente en LLVM MC. No sustituyen las especificaciones ni
son una copia de las tablas completas de Intel o NASM.

## Fuentes primarias

| Fuente | Uso en RIF |
| --- | --- |
| [Intel 64 and IA-32 Architectures Software Developer's Manuals](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html) | Formato de instrucciones, prefijos, opcodes, ModR/M, SIB, desplazamientos e inmediatos. El volumen 2 contiene la referencia completa de instrucciones. |
| [NASM documentation](https://www.nasm.us/doc/) | Sintaxis y codificación práctica x86; `-f bin` produce binarios raw y las pseudo-instrucciones `DB`/`DW`/`DD`/`DQ` muestran el orden little-endian de datos. |
| [NASM Chapter 3: The NASM Language](https://www.nasm.us/doc/nasm03.html) | Prefijos de instrucción, modos `BITS`, emisión de datos y expresiones relativas. |
| [LLVM MC layer](https://llvm.org/docs/CodeGenerator.html#the-mc-layer) | Modelo de secciones, símbolos, instrucciones y streamers que producen `.s` u objetos `.o`. |
| [LLVM `MCCodeEmitter`](https://llvm.org/doxygen/classllvm_1_1MCCodeEmitter.html) | Contrato que convierte un `MCInst` en bytes y produce `MCFixup` pendientes. |
| [LLVM `MCFixup`](https://llvm.org/docs/doxygen/classllvm_1_1MCFixup.html) | Modelo de parche simbólico: el encoder emite el campo provisional y el backend lo aplica o lo conserva como relocación. |

## Archivos

- [`x86-64-encoding-table.md`](x86-64-encoding-table.md): forma de una
  instrucción x86-64 y un conjunto pequeño de formas frecuentes para validar
  emisores de bytes.
- [`llvm-mc-binary-table.md`](llvm-mc-binary-table.md): correspondencia entre
  MIR/RIF y las etapas `MCInst` → bytes/fixups → sección/objeto.
- [`rif-relocations.csv`](rif-relocations.csv): tabla machine-readable de las
  relocaciones nativas actualmente soportadas por RIF y sus invariantes.

## Convenciones

- Los campos de datos multibyte de x86 se escriben little-endian.
- `rel8` y `rel32` son desplazamientos signed relativos al siguiente `RIP`/IP
  (la dirección después de la instrucción), no direcciones absolutas.
- En RIF, `pc8` y `pc32` usan el mismo punto de referencia: `next_virtual_bits`;
  `abs64` escribe la dirección virtual del símbolo.
- Estas tablas son deliberadamente pequeñas y normativas para RIF. Cuando una
  instrucción no esté aquí, la referencia de Intel/NASM es la autoridad y no se
  debe inferir su encoding por analogía.

