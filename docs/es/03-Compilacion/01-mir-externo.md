# MIR externo

El MIR externo es un programa lineal cuyo primer token selecciona una Rule:

```text
mov rax, 1
add rbx, 2
```

Los tokens restantes son consumidos por la Rule. Si una línea deja tokens sin
consumir, la compilación falla.

## Directivas de metaprogramación

El MIR externo puede contener marcadores reservados para integrar artefactos
binarios administrados por RIF:

```text
::RIF_PCPI SET "header.pcic"
::RIF_PCPI PIT 0
::RIF_PCPI PIT 0 SECTION text
::RIF_STORE "imagenes.bin" miImage 1 0
mov rax, 1
```

`::RIF_PCPI SET` debe ser la primera línea no vacía. Carga un `.pcic` y copia
el contenedor completo en la sección actual. `::RIF_PCPI PIT` no genera bytes:
consulta la dirección absoluta del payload reservado, contando desde el offset
`0` del archivo final. La forma `SECTION text` usa el offset real de esa
sección. Las consultas quedan en `MIRCompilation.pcpi_pit_addresses` y la CLI
las muestra.

`::RIF_STORE`
recibe `ENDIANNESS` (`1` little, `2` big) y `BITORDER` (`0` LSB, `1` MSB),
resuelve la ruta relativa al archivo MIR, abre el `storage.bin`, extrae el raw
por label y lo inserta en la sección actual. El payload debe comenzar en una
posición alineada a bytes y se copia sin reinterpretar sus bytes; los dos
argumentos describen el layout solicitado, pero el storage no tiene ancho de
palabra para permitir una conversión endianess genérica.

## Línea de comandos

```powershell
rif main.rif program.asm
rif main.pack program.asm
rif main.rif program.asm -o build/program.bin
```

La extensión debe coincidir con `extension` en `@block linker`. Sin `-o`, la salida usa la
misma ruta del MIR con extensión `.bin`.

## API directa

```python
from MIR import compile_mir_source

result = compile_mir_source("main.rif", "mov rax\n")
binary_data = result.binary
```

Para reutilizar el target:

```python
from MIR import compile_mir_source, prepare_target

target = prepare_target("main.pack")
first = compile_mir_source(target, "mov rax\n")
second = compile_mir_source(target, "add rbx\n")
```

Para archivo o tokens ya producidos por otro compilador:

```python
from MIR import compile_mir_file, compile_mir_tokens, tokenize_mir

result = compile_mir_file("main.rif", "program.asm")
tokens = tokenize_mir("mov rax\n", "generated.asm")
result = compile_mir_tokens("main.pack", tokens)
```

`compile_mir_tokens` evita volver a tokenizar y parsear el MIR.

## Secciones

La sección predeterminada es `default`. Una API directa puede elegir otra
sección configurada:

```python
result = compile_mir_source(target, source, section="text")
```

`MIRCompilation` expone `binary`, `image`, `executions`, `program`, `context`,
`section_binary`, `symbols` y el nombre de la sección seleccionada. `symbols`
contiene las direcciones virtuales absolutas de los símbolos definidos por
`mark` durante la compilación. `compile_mir` acepta texto o un iterable de
tokens.

Las Rules pueden registrar relocaciones con `fixup pc8`, `fixup pc16`,
`fixup pc32`, `fixup pc64`, `fixup abs8`, `fixup abs16`, `fixup abs32` o
`fixup abs64`. El target también puede declarar clases adicionales en
`@block relocations`; el runtime las resuelve después de todas las líneas MIR
y antes de aplicar `::RIF_PATCH`.

La directiva `::RIF_SECTION nombre` selecciona otra sección de la misma
`AssemblyImage` y conserva los emisores, símbolos y relocaciones de cada una.

También está disponible el pipeline de bajo nivel:

```python
from MIR import compile_definition, compile_project, execute_rule

program = compile_definition("main.rif")
project = compile_project("main.rif")
execution = execute_rule(project, "mov", tokens)
```

`parse_source` expone el parseo de Gram y `compile_source` devuelve el target
resuelto sin crear una imagen de salida.
