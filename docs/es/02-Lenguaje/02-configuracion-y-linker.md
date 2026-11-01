# Configuración y linker

`@block config` describe el formato de salida. `@block linker` describe la entrada MIR.

## Configuración

```rif
@block config:
    format section ".section"
    section text "rx"
    section data "rw"
    section bss "rw"
    format section_end ":"
    entry text "_start"
    format label_end ":"
    default text
    align text 4
    align data 4
    align bss 4
    word_size 32
    address_size 32
    byte_order little
    case_sensitive true
    symbol_prefix "_"
    local_prefix "."
    undefined_symbols "error"
    duplicate_symbols "error"
    strict true
    allow_empty_sections false
    bit_order msb
@end
```

Las entradas principales son:

| Entrada | Significado |
| :--- | :--- |
| `format section` | Prefijo al renderizar una sección. |
| `format section_end` | Termina la cabecera renderizada. |
| `format label_end` | Terminador de labels. |
| `section` | Declara una sección y sus flags de salida. |
| `entry` | Define la sección de entrada y su label. |
| `default` | Sección usada cuando no se especifica otra. |
| `align` | Alineación física y virtual de una sección, en bytes. |
| `vaddr` | Base virtual explícita de una sección. |
| `word_size` | Ancho de `eword`, en bits. |
| `address_size` | Ancho de direcciones, en bits. |
| `byte_order` | `little` o `big`. |
| `bit_order` | `msb` o `lsb`. |
| `case_sensitive` | Sensibilidad al resolver nombres de Rules MIR. |
| `symbol_prefix` | Prefijo de símbolos renderizados. |
| `local_prefix` | Prefijo de símbolos locales. |
| `undefined_symbols` | `error`, `warn` o `ignore`. |
| `duplicate_symbols` | `error`, `warn` o `ignore`. |
| `strict` | Política estricta del target. |
| `allow_empty_sections` | Permite renderizar secciones vacías. |

`format section`, `format section_end`, `format label_end`, `entry`,
`default`, `word_size`, `address_size` y `byte_order` tienen valores por
defecto razonables cuando se omiten. Debe declararse al menos una `section`.

## Linker

```rif
@block linker:
    extension ".asm"
    search_path "variants"
    search_path "fallback"
@end
```

`extension` es la extensión permitida para el MIR. `search_path` puede ser
repetido para declarar carpetas relativas en orden de prioridad. `""` busca
junto al archivo; la primera carpeta que contenga la variante gana. `false`
desactiva la búsqueda automática y no puede combinarse con carpetas. No se
conserva un nombre separado para el archivo principal porque no participa en
la resolución.

La API de compilación valida la extensión del MIR antes de procesarlo.
