import math
import struct

from takki import config

# Chirp (ptt) and keypress cues live on separate reserved channels (ADR-012)
# and can sound at the same instant, so the mixer sums them. Half of int16
# full-scale is the largest per-cue peak whose sum still cannot clip.
PEAK_AMPLITUDE = 16383

_PACKER = struct.Struct("<h")


def fade_multiplier(index: int, total: int, fade_samples: int) -> float:
    if fade_samples <= 0:
        return 1.0
    if index < fade_samples:
        return index / fade_samples
    if index >= total - fade_samples:
        return (total - 1 - index) / fade_samples
    return 1.0


def sweep_frequency(index: int, total: int, freq_start: float, freq_end: float) -> float:
    return freq_start + (freq_end - freq_start) * index / total


def _pack_frame(sample: float) -> bytes:
    frame = _PACKER.pack(int(sample * PEAK_AMPLITUDE))
    return frame * config.MIXER_CHANNELS


def generate_tone(freq: float, duration_ms: int, fade_ms: int) -> bytes:
    sample_rate = config.MIXER_FREQUENCY
    total = int(sample_rate * duration_ms / 1000)
    fade_samples = int(sample_rate * fade_ms / 1000)
    out = bytearray()
    for i in range(total):
        value = math.sin(2 * math.pi * freq * i / sample_rate)
        value *= fade_multiplier(i, total, fade_samples)
        out += _pack_frame(value)
    return bytes(out)


def generate_sweep(freq_start: float, freq_end: float, duration_ms: int) -> bytes:
    sample_rate = config.MIXER_FREQUENCY
    total = int(sample_rate * duration_ms / 1000)
    # Fixed short fade -- not in ADR-012's cue table, just click prevention at
    # the sweep's start/end sample.
    fade_samples = int(sample_rate * 5 / 1000)
    out = bytearray()
    phase = 0.0
    for i in range(total):
        freq = sweep_frequency(i, total, freq_start, freq_end)
        phase += 2 * math.pi * freq / sample_rate
        value = math.sin(phase)
        value *= fade_multiplier(i, total, fade_samples)
        out += _pack_frame(value)
    return bytes(out)
