# ADR-025: Configuration System

**Status:** Accepted  
**Date:** 2026-05-23

> Part of the [Takki architecture](../architecture.md).

---

**Decision:** Three-tier configuration. Compiled-in defaults live in `config.py`; a user-editable `takki_config.yaml` in the app data directory lets a parent set app-wide defaults that apply to every profile; per-profile settings in SQLite override the app-level config for that child. Sound cues are named constants whose asset paths are overridable in `takki_config.yaml`. Alpha defaults are programmatically generated tones — no binary assets committed to source.

### Tier Hierarchy

```
config.py (compiled defaults)
    ↓ overridden by
takki_config.yaml  (app data dir — parent / power user)
    ↓ overridden by
profiles table in SQLite  (per-child — set via voice during onboarding)
```

A value is read from the highest tier that defines it. Missing keys at any tier fall through to the tier below. This lets a parent set preferences once for the whole installation — e.g. slightly slower speech, or press-and-hold PTT mode — without requiring each new profile to rediscover and re-apply them.

### App Data Directory

Located via the `platformdirs` library (`user_data_dir("Takki", "Takki")`):

| Platform | Path |
|---|---|
| Windows | `%APPDATA%\Takki\` |
| Linux (dev) | `~/.local/share/Takki\` |

All persistent files live here: `takki.sqlite`, `takki_config.yaml`, `language_override.yaml`, `custom_words.txt`, `voices/`, `sounds/`.

`platformdirs` is a small, widely-used library with no transitive dependencies; it is the standard solution for this problem and does not warrant a custom platform interface wrapper.

### `config.py` — Compiled Defaults

`config.py` is a plain Python module of constants. It is the authoritative source of defaults and is not user-editable (it ships inside the PyInstaller bundle).

```python
# Lesson progression thresholds
NEW_KEY_ACCURACY_THRESHOLD = 0.90
NEW_KEY_MIN_PRESSES        = 50
LAYER2_UNLOCK_KEY_COUNT    = 8
WORD_ADVANCE_ACCURACY      = 0.85
WORD_ADVANCE_WORD_COUNT    = 20

LAYER_PROPORTIONS = [        # (max_keys_known_exclusive, layer1_frac, layer2_frac)
    (8,    1.00, 0.00),
    (16,   0.60, 0.40),
    (26,   0.35, 0.65),
    (None, 0.20, 0.80),
]

# Key bindings (pynput key name strings)
TALK_KEY    = "ctrl_r"
REREAD_KEY  = "escape"
RESTART_KEY = "escape"       # hold or double-tap — see ADR-012

# Voice
TTS_RATE          = 1.0
PUSH_TO_TALK_MODE = "press_release"   # "press_release" or "hold"

# Technical cap — VAD failure safeguard; not surfaced in takki_config.yaml
MAX_RECORDING_SECONDS = 10

# Sound cue asset paths (relative to bundle assets/sounds/)
SOUND_CORRECT   = "correct.wav"
SOUND_ERROR     = "error.wav"
SOUND_BOUNDARY  = "boundary.wav"
SOUND_CHIRP_ON  = "chirp_on.wav"
SOUND_CHIRP_OFF = "chirp_off.wav"

# Alpha placeholder tone parameters (used when .wav path is empty or file is absent)
TONE_CORRECT   = dict(freq=880,  duration_ms=200, fade_ms=30)
TONE_ERROR     = dict(freq=220,  duration_ms=180, fade_ms=20)
TONE_BOUNDARY  = dict(freq=440,  duration_ms=100, fade_ms=10)
TONE_CHIRP_ON  = dict(freq_start=660,  freq_end=1100, duration_ms=150)
TONE_CHIRP_OFF = dict(freq_start=1100, freq_end=660,  duration_ms=150)
```

### `takki_config.yaml` — App-Level Overrides

Created in the app data directory on first run (empty file with inline comments). Any key present overrides the matching `config.py` constant. Unknown keys are ignored with a startup warning.

```yaml
# takki_config.yaml — all keys are optional; missing keys use the compiled default

sounds:
  correct:   ""           # absolute path to a .wav file, or "" to use built-in tone
  error:     ""
  boundary:  ""
  chirp_on:  ""
  chirp_off: ""

keys:
  talk:    "ctrl_r"       # pynput key name; also overridable per profile
  reread:  "escape"
  restart: "escape"

voice:
  tts_rate:          1.0             # speech rate multiplier; also overridable per profile
  push_to_talk_mode: "press_release" # "press_release" or "hold"; also overridable per profile

lesson:
  new_key_accuracy_threshold: 0.90
  new_key_min_presses:        50
  layer2_unlock_key_count:    8
  word_advance_accuracy:      0.85
  word_advance_word_count:    20
```

The file is the primary customisation surface for parents and power users. It is never written by the app after first-run creation — only the user edits it. This prevents the app from silently reverting a parent's changes.

### Per-Profile Overrides (SQLite `profiles` table)

Key bindings, `tts_rate`, `tts_voice`, and `push_to_talk_mode` may be overridden per child. These are set via the voice-driven onboarding flow and stored as nullable columns in the `profiles` table. A NULL value means "use the app-level config." See ADR-011 for the full schema.

### What Is Not Configurable via `takki_config.yaml`

- `MAX_RECORDING_SECONDS`: lives in `config.py` only — it is a VAD failure safeguard, not a user preference.
- Language config (`LANGUAGE_CONFIGS` dict in `config.py`): developer-maintained. The override path for unsupported languages is `language_override.yaml` (ADR-009), a separate file with its own format.
- Visual display settings: per-profile only (SQLite), not app-level.
- Asset and model paths (Piper voices, Whisper models): managed by installer conventions, not configurable.

### Alternatives Considered

- **Single `.ini` file.** Awkward for nested structures (layer proportions, sound cue map). YAML is already used elsewhere — consistency outweighs `.ini` familiarity.
- **All config in SQLite.** Eliminates a separate file but makes the config uninspectable and uneditable without tooling. A text file is the right surface for parent customisation.
- **Env-var overrides.** `TAKKI_DATA_DIR` overrides the `platformdirs` path for testing; no other env-var overrides are supported.
