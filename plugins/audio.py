"""Deterministic local audio-to-PCM conversion."""

from __future__ import annotations

from pathlib import Path

from .paths import PluginError, local_file, output_limit


SUPPORTED_AUDIO_FORMATS = frozenset({"WAV", "FLAC", "OGG"})


def convert_audio(source: str | Path, sample_format: str = "PCM_S16LE") -> bytes:
    """Decode one local audio file to interleaved signed little-endian PCM16."""

    path = local_file(source, "convert_audio")
    if str(sample_format).upper() != "PCM_S16LE":
        raise PluginError("convert_audio solo admite el tipo de dato PCM_S16LE.")
    try:
        import numpy as np
        import soundfile as sf
    except ImportError as exc:
        raise PluginError(
            "convert_audio requiere soundfile y numpy; instala el plugin con "
            "`vnma install soundfile`."
        ) from exc

    try:
        info = sf.info(path)
        container = str(getattr(info, "format", "")).upper()
        if container not in SUPPORTED_AUDIO_FORMATS:
            raise PluginError("convert_audio solo admite contenedores WAV, FLAC u OGG.")
        frames = int(info.frames)
        channels = int(info.channels)
        sample_rate = int(info.samplerate)
        if frames <= 0 or channels <= 0 or sample_rate <= 0:
            raise PluginError("convert_audio recibió un stream sin datos válidos.")
        expected = frames * channels * 2
        if expected > output_limit():
            raise PluginError("convert_audio excede el límite de salida permitido.")
        samples, actual_rate = sf.read(
            path,
            dtype="int16",
            always_2d=True,
        )
        if int(actual_rate) != sample_rate:
            raise PluginError("convert_audio detectó una frecuencia inconsistente.")
        data = np.asarray(samples, dtype="<i2").tobytes(order="C")
    except PluginError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise PluginError(f"convert_audio no pudo decodificar {path.name}.") from exc

    if len(data) != expected:
        raise PluginError("convert_audio produjo una cantidad de bytes inesperada.")
    return data


__all__ = ["SUPPORTED_AUDIO_FORMATS", "convert_audio"]
