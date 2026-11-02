# Arquitectura

RIF tiene dos fases de entrada y una fase de salida.

## Definición del target

`main.rif` describe el target:

```text
main.rif -> CompiledRuleSet
```

El Compiled Rule Set contiene instrucciones internas y referencias resueltas a
tokens, tablas y Rules. Se puede reutilizar para cada MIR externo que use el
target.

## MIR externo

El MIR externo es el programa que consume el target:

```text
CompiledRuleSet + program.asm -> program.bin
```

El primer token de cada línea selecciona una Rule. Los demás tokens se entregan
a esa Rule. RIF puede tokenizar el archivo o recibir tokens de otro compilador
mediante la API directa.

## Componentes

| Componente | Responsabilidad |
| :--- | :--- |
| `Frontend.syntax` | Gramática Gram de la definición RIF. |
| `Frontend.processor` | Materializa configuración, tablas, definiciones, Rules y cargas. |
| `MIR.compiler` | Convierte nodos en instrucciones internas planas. |
| `MIR.semantic` | Resuelve tokens, tablas, Rules y reservas. |
| `MIR.runtime.RIFMachine` | Ejecuta instrucciones contra tokens MIR. |
| `MIR.bitbuffer.BitBuffer` | Guarda y reescribe rangos arbitrarios de bits. |
| `MIR.output.AssemblyImage` | Mantiene un buffer por sección. |
| `rif_core/pack.py` | Crea y valida paquetes `.pack` reproducibles. |

`CompilationSession` posee el estado mutable de una compilación: fuentes
cargadas, tablas pendientes, Rules, configuración, linker, bloques, variantes
y los textos necesarios para conservar lexemas. Los loaders y visitors reciben
esa sesión explícitamente, por lo que dos targets consecutivos o concurrentes
no comparten declaraciones.

La sesión se resuelve y se congela en un `TargetContext` inmutable. MIR recibe
las Rules y el contexto de forma explícita y no depende del estado frontend
global. `activate_target_context()` queda solo como adaptador transitorio para
introspección y pruebas antiguas.

La CLI pública usa siempre la FFI C/AOT en memoria. GCC o Clang solo construye
la biblioteca compartida cuando la caché se invalida; Python queda como oráculo
interno de paridad y diagnóstico. `RIFMachine` posee el estado de ejecución:
posición de tokens, storage, datastack, reservas y trazas.
