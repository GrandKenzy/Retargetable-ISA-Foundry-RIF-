# RIF local media plugins

These converters accept existing local filesystem paths only. They do not
fetch URLs and they do not accept in-memory `bytes`.

```python
from plugins import convert_audio, convert_image

image = convert_image("sprite.png")
audio = convert_audio("sound.wav")
```

From a standalone `.store` source, the raw bytes can be indexed without coupling the media conversion to RIF:

```rif
MAGIC "store"
VERSION 1

@ITEM IMAGE
: "assets/sprite.png"
: "png"
: "RGB888"
: sprite
@end
```

An audio item uses the same four-field shape:

```rif
@ITEM AUDIO
: "assets/music.wav"
: "wav"
: "PCM_S16LE"
: music
@end
```

Paths are resolved relative to the `.store` file.

The compiler writes an indexed `storage.bin`: each entry contains `u64`
relative address, `u64` payload size, `u32` alignment padding, and `u32`
label size. The UTF-8 label bytes live directly after that entry's payload in
the raw region.

`convert_image` returns only immutable row-major `RGBA8888` bytes. It requires
Pillow; dimensions are intentionally not part of the plugin result.

`convert_audio` returns only immutable interleaved signed little-endian
`PCM_S16LE` bytes from WAV, FLAC, or OGG containers. It requires `soundfile`
and NumPy; stream metadata is intentionally not part of the plugin result.

Video conversion is intentionally outside the RIF plugin scope.

Both converters enforce the RIF resource limit before decoding and before
materializing their output.
