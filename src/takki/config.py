"""Compiled configuration defaults (ADR-025). Overridable by takki_config.yaml
and per-profile SQLite settings once those tiers land -- Alpha reads these
values directly."""

# Sound cue asset paths (relative to bundle assets/sounds/). Alpha has no
# bundled assets and no takki_config.yaml override chain -- these paths are
# inert until the Beta config loader resolves them (ADR-012).
SOUND_CORRECT = "correct.wav"
SOUND_ERROR = "error.wav"
SOUND_BOUNDARY = "boundary.wav"
SOUND_CHIRP_ON = "chirp_on.wav"
SOUND_CHIRP_OFF = "chirp_off.wav"

# Alpha placeholder tone parameters -- generated in-process (takki.audio.tone),
# no binary assets committed to source.
TONE_CORRECT = dict(freq=880, duration_ms=200, fade_ms=30)
TONE_ERROR = dict(freq=220, duration_ms=180, fade_ms=20)
TONE_BOUNDARY = dict(freq=440, duration_ms=100, fade_ms=10)
TONE_CHIRP_ON = dict(freq_start=660, freq_end=1100, duration_ms=150)
TONE_CHIRP_OFF = dict(freq_start=1100, freq_end=660, duration_ms=150)

# pygame.mixer init, pinned rather than left to the pygame default (ADR-012):
# MIXER_BUFFER is the floor on cue latency -- 512 samples is ~23ms at 22050 Hz.
# Must not drift silently with a pygame version bump.
MIXER_FREQUENCY = 22050
MIXER_SIZE = -16  # signed 16-bit
MIXER_CHANNELS = 2  # stereo
MIXER_BUFFER = 512
