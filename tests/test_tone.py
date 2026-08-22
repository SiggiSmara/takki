import struct

from takki import config
from takki.audio.tone import fade_multiplier, generate_sweep, generate_tone, sweep_frequency

_PACKER = struct.Struct("<h")


def _unpack_left_channel(pcm: bytes) -> list[int]:
    frame_size = 2 * config.MIXER_CHANNELS  # int16 per channel
    return [_PACKER.unpack(pcm[i : i + 2])[0] for i in range(0, len(pcm), frame_size)]


class TestGenerateTone:
    def test_sample_count_matches_duration(self) -> None:
        pcm = generate_tone(freq=440, duration_ms=100, fade_ms=0)
        expected_frames = config.MIXER_FREQUENCY * 100 // 1000
        assert len(pcm) == expected_frames * 2 * config.MIXER_CHANNELS

    def test_amplitude_within_int16_bounds(self) -> None:
        pcm = generate_tone(freq=880, duration_ms=200, fade_ms=30)
        samples = _unpack_left_channel(pcm)
        assert all(-32768 <= s <= 32767 for s in samples)

    def test_fade_in_ramps_up_from_silence(self) -> None:
        # Compare energy over small windows, not single samples -- a lone
        # sample can coincide with the sine's own zero crossing.
        pcm = generate_tone(freq=880, duration_ms=200, fade_ms=30)
        samples = _unpack_left_channel(pcm)
        start_energy = sum(abs(s) for s in samples[:5])
        mid_energy = sum(abs(s) for s in samples[2000:2005])
        assert start_energy < mid_energy

    def test_zero_fade_reaches_full_amplitude(self) -> None:
        pcm = generate_tone(freq=440, duration_ms=50, fade_ms=0)
        samples = _unpack_left_channel(pcm)
        assert max(abs(s) for s in samples) > 19000

    def test_stereo_channels_are_identical(self) -> None:
        pcm = generate_tone(freq=440, duration_ms=20, fade_ms=0)
        frame_size = 2 * config.MIXER_CHANNELS
        for i in range(0, len(pcm), frame_size):
            left = _PACKER.unpack(pcm[i : i + 2])[0]
            right = _PACKER.unpack(pcm[i + 2 : i + 4])[0]
            assert left == right


class TestGenerateSweep:
    def test_sample_count_matches_duration(self) -> None:
        pcm = generate_sweep(freq_start=660, freq_end=1100, duration_ms=150)
        expected_frames = config.MIXER_FREQUENCY * 150 // 1000
        assert len(pcm) == expected_frames * 2 * config.MIXER_CHANNELS

    def test_amplitude_within_int16_bounds(self) -> None:
        pcm = generate_sweep(freq_start=660, freq_end=1100, duration_ms=150)
        samples = _unpack_left_channel(pcm)
        assert all(-32768 <= s <= 32767 for s in samples)


class TestSweepFrequency:
    def test_starts_at_freq_start(self) -> None:
        assert sweep_frequency(0, 1000, 660, 1100) == 660

    def test_ends_near_freq_end(self) -> None:
        assert sweep_frequency(999, 1000, 660, 1100) == 660 + (1100 - 660) * 999 / 1000

    def test_midpoint_is_average(self) -> None:
        assert sweep_frequency(500, 1000, 660, 1100) == 660 + (1100 - 660) * 0.5

    def test_descending_sweep(self) -> None:
        assert sweep_frequency(0, 1000, 1100, 660) == 1100
        assert sweep_frequency(999, 1000, 1100, 660) < 1100


class TestFadeMultiplier:
    def test_zero_fade_samples_is_always_full(self) -> None:
        assert fade_multiplier(0, 100, 0) == 1.0
        assert fade_multiplier(50, 100, 0) == 1.0

    def test_first_sample_is_silent(self) -> None:
        assert fade_multiplier(0, 100, 10) == 0.0

    def test_last_sample_is_silent(self) -> None:
        assert fade_multiplier(99, 100, 10) == 0.0

    def test_middle_is_full_amplitude(self) -> None:
        assert fade_multiplier(50, 100, 10) == 1.0
