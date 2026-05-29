# Tablas y secciones

Una seccion empieza con `.nombre`.

Las tablas usan el separador configurado:

```rif
.regs
| NAME | binary | bits |
| a    | 000    | 8    |
```

Convenciones principales:

- `.pack`: plugins, packer y mapeos de tipos
- `.world`: datos globales del target
- `.sections`: secciones de salida
- `.regs`: registros
- `.vars`: variables de bits
- `.types`: tipos declarados
- `.DATA_DEFINITION`: patron de definicion de datos
- `.rules`: reglas de instrucciones
- `.stacks` y `.heaps`: regiones de memoria

Las tablas se convierten en objetos consultables por el compiler, linker y plugins.
