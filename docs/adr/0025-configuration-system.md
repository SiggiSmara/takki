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

Located via the `platformdirs` library (`user_data_dir("Takki", appauthor=False)`):

| Platform | Path |
|---|---|
| Windows | `%LOCALAPPDATA%\Takki\` |
| Linux (dev) | `~/.local/share/Takki/` |
| macOS | `~/Library/Application Support/Takki/` |

All persistent files live here: `takki.sqlite`, `takki_config.yaml`, `language_override.yaml`, `custom_words.txt`, `voices/`, `sounds/`.

`platformdirs` is a small, widely-used library with no transitive dependencies; it is the standard solution for this problem and does not warrant a custom platform interface wrapper.

**Corrected 2026-09-20 (alpha session 12a-0 follow-up), on two counts — the call and the table had never agreed with each other.** The original call was `user_data_dir("Takki", "Takki")` and the original Windows row read `%APPDATA%\Takki\`; the call actually returns `%LOCALAPPDATA%\Takki\Takki` — Local rather than Roaming, and the app nested inside an identically-named *author* directory. Neither half was what the table promised, and nothing had implemented either, because `platformdirs` was not a project dependency until now (the code wrote `~/Documents/Takki/`, which is [ADR-015](0015-piper-voice-model-distribution.md)'s parent-facing *voices* folder, not a data directory).

`appauthor=False` removes the doubled directory: Takki has no separate vendor to name.

**Local, not Roaming, is a decision and not just the library default.** The database runs in WAL mode ([ADR-011](0011-persistence-and-state.md)), so it is three files — `takki.sqlite`, `-wal`, `-shm` — that are only meaningful together. A roaming profile syncs at logon and logoff and gives no guarantee of copying them consistently or in order, so on a managed school network — a deployment target [architecture.md](../architecture.md) names explicitly — roaming would risk corruption at every logoff and add the database's full size to every logon. Roaming also silently defeats the offline-and-local promise in [PRIVACY.md](../PRIVACY.md): a roamed profile copies the child's progress to a domain server. A database belongs in local app data.

The resolved paths are documented for parents in [README § Where your data lives](../../README.md#where-your-data-lives), which is the answer to this ADR's own "location is documented in the application" promise until an in-app help surface exists.

### Language and layout must agree

*(Added 2026-09-20, replacing the withdrawn `TAKKI_LANG` / `TAKKI_LAYOUT` env vars.)*

Two different things decide what a lesson looks like, and they come from two different places:

- **The language** is configuration. `config.LANGUAGE` (tier 1) names the curriculum — the wordfreq corpus, the letter audio, the milestone denominator. `None`, the default, means "ask the platform", which is [ADR-013](0013-onboarding-and-profile-selection.md)'s locale detection and the right answer on a machine with one language. The `takki_config.yaml` and per-profile tiers override it as they do any other key, once they exist.
- **The layout is not configuration.** [ADR-006](0006-language-and-keyboard-layout-scope.md) settles this: *"the app teaches on whatever layout Windows reports as active."* Takki never selects, substitutes or overrides a keyboard layout. Doing so would teach a child key positions their own keyboard does not have.

The two can therefore disagree, and on a machine with more than one layout installed they routinely will — the test laptop carries German, US and Icelandic, and a child's school computer is no different. **Takki verifies the pair at startup and refuses to run when they do not match** (`main.verify_layout`, before any component is constructed). With an `en` curriculum on an active German layout it would otherwise drill `y` and `z` at each other's positions and admit `ä ö ü ß` to a 30-grapheme milestone denominator, silently, with the child's accuracy record scored against a keyboard they are not typing on.

**The comparison is key positions, not layout identity.** Takki teaches letters only — no space, no Shift, no punctuation ([roadmap § What is deliberately never taught](../roadmap.md#what-done-looks-like-per-phase)) — and US and UK QWERTY differ only outside that set. Comparing KLIDs would reject a UK keyboard that types the English curriculum perfectly, so `layout.describe_mismatch()` compares each key's `(row, col)` and reports which letters are missing, unexpected or moved.

**Alpha reports and stops.** The message goes to stderr with the remedy (Win+Space switches layouts) and the process exits non-zero. Two known limits, both deliberate and both Beta's:

1. **Startup only.** A layout switched mid-session — one accidental Win+Space — is not detected, and the rest of that session is scored against the wrong keyboard. Filed in [roadmap § D](../roadmap.md#d-smaller-gaps-worth-a-line-in-the-relevant-adr).
2. **stderr is not an audio channel.** A blind parent never sees it. Alpha is developer-only so nothing is lost there, but this is the same gap as roadmap § D's "Error surfacing for blind parents", and the pilot is where it bites: the graceful resolution — say what is wrong, offer to switch layout or switch curriculum — belongs with onboarding ([ADR-013](0013-onboarding-and-profile-selection.md)).

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
REREAD_KEY  = "esc"
RESTART_KEY = "esc"          # held; tap on the same key re-reads — see ADR-012
RESTART_HOLD_MS = 800        # hold duration that separates restart from re-read;
                             # unused when reread_key and restart_key differ
RESUME_KEY  = "f1"           # held while PAUSED, to re-acquire foreground — see ADR-028 §C8
RESUME_HOLD_MS = 1000        # hold duration before the foreground request is made
RESUME_REQUEST_TIMEOUT_MS = 1500   # request_foreground() deadline; expiry speaks the Alt+Tab hint

# Key & accuracy state model (ADR-027)
ATTEMPT_WINDOW          = 200    # rolling key_attempts window per (profile, key)
KNOWN_MIN_ATTEMPTS      = 90     # graphomotor retention floor
KNOWN_MIN_ACCURACY      = 0.90   # first-attempt accuracy over the window
KNOWN_MIN_DISTINCT_DAYS = 2      # calendar days — one night of consolidation

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

**Amended 2026-08-22 (alpha session 6b), two corrections to the block above.**

**The resume binding was missing.** [ADR-028 §C8](0028-composite-input-and-keyboard-ownership.md)'s keypress taxonomy has a **Resume hold** row — "configured held-key, while PAUSED" — but this ADR's binding list never defined it, so implementing the focus model had no key and no threshold to read. `RESUME_KEY`, `RESUME_HOLD_MS`, and `RESUME_REQUEST_TIMEOUT_MS` close that.

The binding is chosen against a constraint the other three do not have: this key is held *while another application has focus*, so it must be one nobody holds for a second by accident. That rules out the bare modifiers — Ctrl (Ctrl+click, Ctrl+scroll, Ctrl+Shift+arrow) and Shift (Shift+arrow selection) are routinely held past a second, and Right Shift held 8 s additionally trips Windows FilterKeys, a trap for exactly this audience. `f1` is held by nobody, needs no chord, and is located by edge and by its neighbour Escape rather than by counting or by F-group gaps, which laptops and dense keyboards do not have. Its one side effect — opening the foreground app's help — costs a window Takki is about to raise past anyway. The Escape adjacency cuts the right way: Escape is live only while ACTIVE and `RESUME_KEY` only while PAUSED, so the two never contend, and a child groping for their reflex recovery key while paused lands on the key that brings them back.

`RESUME_HOLD_MS` is longer than `RESTART_HOLD_MS` for the same reason. `RESUME_REQUEST_TIMEOUT_MS` is not a preference but the deadline that stands in for a return value: `request_foreground()` cannot report success (ADR-028 § Re-acquire has no synchronous answer), so a `FocusGained` inside this window is the success signal and expiry is the failure signal that speaks the Alt+Tab hint.

**`"escape"` is not a pynput key name.** These values are `pynput.keyboard.Key` member names — what `Key.<member>.name` returns, which is what the keyboard stream puts in `KeyEvent.name`. pynput's member is `Key.esc`, so `"escape"` matched nothing: Escape would have fallen through to the taxonomy's **System** row and re-read would silently never have worked. Corrected to `"esc"` above.

**Amended 2026-08-22 (alpha session 7). ADR-027's four numbers were configurable only on paper.**

[ADR-027](0027-key-and-accuracy-state-model.md) says twice that its thresholds are "configurable (ADR-025)", but this ADR's listing never carried them, and the 200-attempt window existed only as a constructor default duplicated across `SqliteStore` and `FakeStore`. `ATTEMPT_WINDOW`, `KNOWN_MIN_ATTEMPTS`, `KNOWN_MIN_ACCURACY` and `KNOWN_MIN_DISTINCT_DAYS` close that; both stores now default their cap to `config.ATTEMPT_WINDOW`, and `KnownCriterion` (`takki.lesson.key_state`) takes the three floors as its field defaults, in the shape `KeyBindings` already uses for tier 1 — the yaml and per-profile tiers override by *constructing* `KnownCriterion(...)` and passing `window_cap`, never by mutating the `config` module after import.

These four are not preferences. They are research floors — see [motor-learning-repetitions.md](../research/motor-learning-repetitions.md) — and lowering any of them makes Known mean less than it says. They are exposed here because ADR-027 promised they would be and because a pilot may need to shorten them to demo progression, not because a parent should tune them; whether they surface in `takki_config.yaml` at all is a Beta question.

Note the distinction from the lesson-progression block above: `NEW_KEY_MIN_PRESSES = 50` / `NEW_KEY_ACCURACY_THRESHOLD = 0.90` gate *introducing the next key* ([ADR-010](0010-lesson-structure-and-progression.md)); the `KNOWN_*` floors gate *Known*, which is a much higher bar and the one milestones count. They are deliberately different numbers for different questions.

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
  reread:  "esc"
  restart: "esc"         # same key as reread → tap re-reads, hold restarts
  restart_hold_ms: 800   # ignored when reread and restart are bound to different keys
  resume:  "f1"          # held while paused, to bring Takki back to the foreground
  resume_hold_ms: 1000
  resume_request_timeout_ms: 1500

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
- **Env-var overrides.** Rejected. Nothing Takki does is configured by the environment: the data directory comes from `platformdirs`, the layout from Windows, and the language from the tiers above.

**Amended 2026-09-20, then re-amended the same day.** A first pass added `TAKKI_LANG` / `TAKKI_LAYOUT` alongside a proposed `TAKKI_DATA_DIR`, on the grounds that the Windows test laptop reports `en-150` on a German QWERTZ layout. That was the wrong instrument and all three were withdrawn: an env var is a *developer's* escape hatch, and the situation it was escaping — a machine with several keyboard layouts installed — is an ordinary one that a child's computer will meet too. A parent has no environment variables. `TAKKI_DATA_DIR` went with them: the resolved path is now correct on every platform, so there is nothing left for it to work around in Alpha. What replaces them is the section below.
