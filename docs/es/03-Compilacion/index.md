# 03. Compilación

RIF ofrece un flujo por CLI y una API Python directa. Ambos compilan la misma
definición y usan el mismo dispatcher de MIR.

| Guía | Resumen |
| :--- | :--- |
| [01. MIR externo](./01-mir-externo.md) | Compilación por CLI y API de archivos, texto o tokens. |
| [02. Paquetes RIF](./02-paquetes-rif.md) | Contenido, precompilación y ventajas de `.pack`. |
| [03. Funciones nativas](./03-funciones-nativas.md) | Contratos estáticos y función `#:calc`. |

## Dos fases

```text
Fase 1: main.rif o main.pack -> CompiledRuleSet
Fase 2: CompiledRuleSet + MIR externo -> binario puro
```

La fase 1 resuelve el target. La fase 2 ejecuta sus Rules contra el MIR.
