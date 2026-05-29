# Importar plugins

Los plugins se declaran en `.pack`.

```rif
.pack
plugext ".py"
plugin "basics"
```

El loader busca:

```text
plugins/NOMBRE/plugins/*.py
```

Si el pack esta dentro de una carpeta de examples, tambien puede usar el directorio `plugins/` del workspace.

Los nombres de plugins no pueden ser rutas, absolutos ni contener `..`.
