# RIF Foundry

Retargetable ISA Foundry es un generador para crear ensambladores, empaquetadores y linkers usando paquetes `.pack` y plugins.

El objetivo principal es que el core no este hardcodeado para una arquitectura. RIF debe saber leer, validar, ejecutar flujo comun, resolver placeholders, organizar secciones y dejar que las reglas especificas de cada ISA vivan en plugins.

Estado actual: **A 0.0 Beta**.

## Que incluye

- Lexer y parser para archivos `.pack`.
- AST declarativo para secciones, tablas, tipos, headers, memoria y reglas.
- Separacion entre parser puro, collector de IR y runtime de compilacion.
- Compiler runtime con `need`, `emit`, `call`, `ON/OFF`, `switch/case`, `end_instruction`, relocaciones y placeholders.
- Linker con secciones, headers, data, stacks, heaps, `nobits`, alineacion y referencias `link:*`.
- Plugin base `basics`.
- CLI local.
- Examples y tests limpios.
- Help local en HTML y Markdown.

## Instalacion

Desde el repo:

```bash
python -m pip install -e .
```

Con dependencias de test:

```bash
python -m pip install -e ".[test]"
```

Tambien puede ejecutarse sin instalar:

```bash
python -m rif help
```

## Uso rapido

Compilar una instruccion:

```bash
python -m rif compile examples/minimal.pack byte 0xf
```

Salida esperada:

```text
rule=byte
bits=00001111
hex=0f
```

Construir bytes desde texto:

```bash
python -m rif build examples/minimal.pack --source-text "byte 0x2a"
```

Leer ayuda local:

```bash
python -m rif help
python -m rif help version_actual
python -m rif help --open
```

## CLI

Comandos disponibles:

```bash
python -m rif lex archivo.pack
python -m rif parse archivo.pack
python -m rif pack archivo.pack
python -m rif link archivo.pack
python -m rif compile archivo.pack instruccion
python -m rif build archivo.pack
python -m rif help [tema]
```

Si se instala el paquete, tambien queda disponible:

```bash
rif help
```

## Estructura del repo

```text
rif/                 core del sistema
plugins/basics/      plugin base generico
examples/            paquetes y programas de ejemplo
tests/               tests unitarios
help/                documentacion local HTML/Markdown
```

El plugin de Atari no forma parte del core ni de los tests limpios.

## Ejemplo minimo

`examples/minimal.pack` define una ISA pequena para probar el core:

- `.pack`
- `.world`
- `.sections`
- `.regs`
- `.vars`
- `.types`
- `.DATA_DEFINITION`
- `.stacks`
- `.heaps`
- `.rules`

Incluye reglas para `VALUE`, registros, bit transforms, `ON/OFF`, `call call`, `end_instruction`, `reldis` y `reloc`.

## Modelo de fases

RIF separa las fases principales:

1. `Parser.parse_ast()` construye AST declarativo sin ejecutar plugins.
2. `collect_codegen(program)` ejecuta plugins para recolectar IR.
3. `Compiler` compila instrucciones y datos.
4. `Linker` organiza secciones, headers, memoria y placeholders.

`Parser.parse()` mantiene el flujo completo por compatibilidad.

## Plugins

Los plugins se declaran en `.pack`:

```rif
.pack
plugext ".py"
plugin "basics"
```

Estructura:

```text
plugins/NOMBRE/plugins/instruccion.py
```

Cada archivo expone una instruccion con el nombre del archivo.

Plugin minimo:

```python
from rif import Expr, Line

def main():
    Line.Advance()
    return Expr(["op"])

def _start():
    return main()
```

Los plugins deben devolver `Expr`, lista de `Expr`, `Err` o `None`.

## Basics

`basics` contiene piezas genericas:

- `need`
- `emit`
- `call`
- `exists`
- `fits`
- `eq`, `neq`
- `bitcat`
- `bitsize`
- `bitfit`
- `trunc`
- `zext`
- `sext`
- `lt`, `lte`, `gt`, `gte`
- `align`
- `pad`
- `reldis`
- `reloc`
- `emitadress`
- `error`, `raise`

No define una arquitectura.

## Tests

Ejecutar tests:

```bash
python -m unittest discover -s tests
```

Compilar modulos:

```bash
python -m compileall rif plugins tests
```

Con pytest instalado:

```bash
python -m pytest -q
```

## Documentacion

La documentacion local esta en:

```text
help/index.html
help/resources/
```

Temas principales:

- Home
- Instrucciones
- Plugins
- Empaquetadores
- CLI
- Futuros

## Roadmap

Trabajo futuro previsto:

- MIR.
- Optimizadores.
- Mas flujos e instrucciones internas.
- Mejoras del linker.
- Compiladores integrados con CLI autodefinida y manual.
- Soporte completo para extensiones VSIX semi automaticas.

## Licencia

MIT.
