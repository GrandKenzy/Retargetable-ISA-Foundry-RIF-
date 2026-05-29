# Instrucciones

Las instrucciones viven en `.rules`.

Una regla usa `need` para capturar operandos y plugins para producir IR o bytes.

```rif
byte:
    need VALUE, imm
    emit imm.binary
```

Elementos comunes:

- `need`: captura operandos o literales
- `emit`: emite bits
- `call`: ejecuta otra regla
- `end_instruction`: termina la regla actual
- `ON/OFF`: flujo condicional
- `switch/case`: seleccion por valor

Las reglas deben mantenerse genericas. La semantica propia de una arquitectura debe estar en plugins.
