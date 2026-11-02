# 06. STORE Tools

STORE is RIF's standalone indexed-payload tool. A `.store` source names binary
payloads and fixed-width values; the compiler produces a validated
`RIFSTOR` storage container with labels and byte ranges.

It is suitable for firmware constants, lookup data, images, audio, opaque
binary files, and small target-owned payloads. It does not create variables
with runtime behavior: a typed declaration is an exact byte payload.

## The complete workflow

```text
assets.store --comp-store--> build/assets.storage.bin --RIF_STORE--> MIR bytes
```

Compile a source:

```powershell
vnma run main.py --comp-store assets.store -o build/assets.storage.bin
```

Validate and inspect the compiled container:

```powershell
vnma run main.py --doctor-storage build/assets.storage.bin
```

Insert one labeled payload from external MIR:

```asm
::RIF_STORE "build/assets.storage.bin" title 1 0
```

For repeated use, declare an alias and configure it once:

```asm
::RIF_STORE AS assets "build/assets.storage.bin"
assets.ORDER 1
assets.ENDIANNESS 1

::RIF_STORE assets title
::RIF_STORE assets palette
```

## Guides

| Guide | Purpose |
| :--- | :--- |
| [01. Authoring STORE Sources](./01-authoring-store.md) | Raw items, typed literals, files, remote requests, containers, and version rules. |
| [02. Compiling and Consuming Storage](./02-cli-and-mir.md) | CLI operations, storage layout, aliases, byte order, and MIR insertion. |

## Version policy

| Storage version | Available features |
| :---: | :--- |
| `1` | Local media, opaque `BINARY`, `@FILE`, and container selection of raw entries. No typed declarations and no `@REQST`. |
| `2` | Everything in version 1 plus typed literals and bounded `@REQST`. Type metadata is retained in the index. |

RIF currently accepts only storage versions `1` and `2`. Version `3` is not a
current format; future functions or macros must not be assumed by current
tools.

## Format boundary

`RIF_STORE` inserts the selected payload bytes. It does not insert the storage
header, raw region, or index into the MIR output. Images and audio are converted
by their declared plugin format; `BINARY`, `@FILE`, typed values, and imported
raw entries are otherwise copied or encoded deterministically.
