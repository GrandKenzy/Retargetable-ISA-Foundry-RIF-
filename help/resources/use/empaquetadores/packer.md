# Packer

El packer une archivos y valida estructura declarada en `.pack`.

Opciones principales:

```rif
packer:
    fsystem 0
    ext ".bin"
    definesec ".pack"
    setpre world ".world"
    needsect world
```

Campos:

- `fsystem`: modo de sistema de archivos
- `ext`: extension de salida
- `definesec`: seccion conocida
- `setpre`: mapeo de prefijo a seccion
- `needsect`: prefijo requerido
- `subpre`: prefijo para subarchivos

El packer prepara entrada para parseo y linking.
