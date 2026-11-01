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

La definición raíz posee el contexto global. `RIFMachine` posee el estado de
ejecución: posición de tokens, storage, datastack, reservas y trazas.
