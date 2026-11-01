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
Fase 1: main.rif -> CompiledRuleSet -> main.pack (opcional)
Fase 2: main.pack + programa.mir -> binario puro
```

La fase 1 resuelve el target. El `.pack` guarda Rules, tablas y contexto, pero
no contiene el MIR externo. La fase 2 carga el `.pack` (o el `.rif` durante
desarrollo), valida el contrato del target y ejecuta sus Rules contra el MIR.
