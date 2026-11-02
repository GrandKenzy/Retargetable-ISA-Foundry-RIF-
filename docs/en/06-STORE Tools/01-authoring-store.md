# 06.01. Authoring STORE Sources

A `.store` file is a manifest for labeled byte payloads. Every label is unique
within that source, and every output entry can later be selected by that label.

## Source header

Every source begins with the exact magic and a supported version:

```text
MAGIC "store"
VERSION 1
```

Use `VERSION 1` for local/raw payloads. Use `VERSION 2` when the source
contains typed declarations or `@REQST`:

```text
MAGIC "store"
VERSION 2
```

Only versions `1` and `2` are currently supported. Version `3` is reserved for
future language features such as functions or macros.

## Media and opaque binary items

The block form has exactly four fields, in this order:

```text
@ITEM BINARY
: "config.bin"       ; source path, relative to the .store directory
: "bin"               ; source format
: "RAW"               ; output/data format
: config_blob         ; label
@end
```

The supported item kinds are `IMAGE`, `AUDIO`, and `BINARY`.

| Kind | Local source formats | Behavior |
| :--- | :--- | :--- |
| `IMAGE` | `png`, `jpg`, `jpeg`, `bmp`, `gif`, `tga`, `webp` | Sends the image through the image plugin using the declared output format. |
| `AUDIO` | `wav`, `flac`, `ogg` | Sends the audio through the audio plugin using the declared output format. MP3 is not a STORE audio input. |
| `BINARY` | `bin`, `dat`, `raw` | Copies the file byte-for-byte. Its data format must be `RAW` or `BYTES`; no media plugin runs. |

For `IMAGE` and `AUDIO`, the third field is the plugin output format, such as
the format supported by the selected image or audio converter. The source
extension must match the declared source format. For `BINARY`, `raw` means
opaque bytes, not a parser or an assembler.

## Typed exact-byte values

Typed values require `VERSION 2`:

```text
MAGIC "store"
VERSION 2

str greeting = "Hello, world"
uint8 age = 30
int32 count = -2
float32 decimal = 13.0000
```

The supported canonical types and aliases are:

| Canonical type | Alias | Width | Encoding |
| :--- | :--- | ---: | :--- |
| `str` | — | variable | UTF-8 bytes, without an implicit NUL terminator |
| `int8`, `int16`, `int32`, `int64` | `i8`, `i16`, `i32`, `i64` | 1, 2, 4, 8 bytes | Signed little-endian integer |
| `uint8`, `uint16`, `uint32`, `uint64` | `u8`, `u16`, `u32`, `u64` | 1, 2, 4, 8 bytes | Unsigned little-endian integer |
| `float32`, `float64` | `f32`, `f64` | 4, 8 bytes | IEEE-754 little-endian float |

Values are literals only. There are no expressions, assignments, runtime
updates, or type conversions in the STORE source language. Integer ranges are
checked against the selected width, and floats must be finite.

The declared type is retained in a version 2 storage index so a consumer can
apply a configured byte layout later. The payload itself is already encoded in
the canonical little-endian form above.

## Add a local file

`@FILE` copies an arbitrary local file as raw bytes:

```text
@FILE "myfile.bin"
@FILE "headers/boot.dat" AS boot_header
```

Without `AS`, the label is the filename stem (`myfile` in the first example).
The path is relative to the `.store` file and must stay inside that directory:
absolute paths and `..` traversal are rejected.

## Request a bounded GitHub binary

`@REQST` requires `VERSION 2` and a `.bin` file hosted on GitHub:

```text
@REQST algorithm "github.com/owner/repository/path/algorithm.bin/main"
```

`https://github.com/...` is also accepted. The path must end with a branch,
must contain a `.bin` file path, and cannot contain credentials, query strings,
fragments, or traversal segments. The request follows only HTTPS GitHub hosts,
rejects HTML responses, has a 15-second timeout, and is bounded by 16 MiB (or
the configured global limit).

`@REQST` is acquisition of raw bytes, not code execution. The downloaded file
is stored under the declared label without invoking an image or audio plugin.

## Import selected entries from another container

Use `@CONTAINER` to copy labeled entries from a validated storage file:

```text
@CONTAINER "variables/vars.storage.bin":
    get etiqueta1
    get etiqueta2
@end
```

The container path is local to the current `.store` directory and is subject
to the same path-safety rules as `@FILE`. The selected labels keep their
original names and bytes. An explicit `@end` is recommended; it may be omitted
only when the container block is the final block in the source.

If a selected entry carries version 2 type metadata, the importing source must
also be `VERSION 2`; version 1 can only contain raw entries.

## Source-level constraints

- Labels must be identifiers such as `config_blob` or `MODE_3` and must be
  unique.
- Paths are resolved from the source `.store` directory, not the process
  working directory.
- A `BINARY` item is not a typed integer; use a typed declaration when width
  and numeric representation matter.
- A typed declaration is not a runtime variable. It is one fixed payload in
  the final storage image.
- `IMAGE` and `AUDIO` conversion is explicit through the item kind and data
  format. Use `BINARY` or `@FILE` when the source must remain byte-for-byte.
