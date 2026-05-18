# ADR-003: Text-to-Speech (Audio Feedback)

**Status:** Accepted  
**Date:** 2026-05-17

> Part of the [Takki architecture](../architecture.md).

---

**Decision:** Piper TTS as default, with pyttsx3/Windows SAPI as automatic fallback.

### Rationale

Audio feedback is the primary output modality. Quality matters — a robotic or mispronouncing voice is demotivating for children.

**Piper TTS** is chosen as the default because:
- High-quality neural voices, substantially better than SAPI
- Runs fully locally, no internet
- Pre-built voice models available for many languages
- Lightweight enough to bundle or download at first run
- Confirmed working natively on Windows (Python 3.11 MSVC): model load ~2.3s once per session, synthesis ~0.19s per phrase (real-time factor ~0.06×)

**pyttsx3/SAPI** is retained as fallback because:
- Zero additional installation — uses built-in Windows voices
- Guarantees the app works even if Piper model download fails
- Some users may prefer it for familiarity

**Character and key name pronunciation** is handled directly by TTS rather than through lookup tables. Neural TTS engines correctly pronounce letter names and common special characters in their target language (e.g., a German TTS voice pronounces "ä" as "A-Umlaut" correctly). Explicit overrides are added only when testing reveals specific mispronunciations — this list is expected to be very small.

**Per-student voice settings** are stored in the child profile (see ADR-011):

- `tts_rate` — Piper `length_scale` float. Default 1.0. Range 0.6–2.0 in 0.2 steps. Higher = slower. Adjusted via spoken "faster" / "slower" commands; each command moves one step. Speech rate is highly individual — a change of 0.2 is perceptible and meaningful. The range covers the full practical spectrum from fast-but-intelligible (0.6) to very deliberate (2.0).
- `tts_voice` — Piper voice model key, e.g. `en_US-amy-low`. Null means use the language default. Gender and accent are baked into the model; there is no separate gender field. The parent selects a voice from the curated `voice_catalog.yaml` (see ADR-015) before the model is downloaded — the chosen key is then stored here.
- `language` — BCP-47 language code override. Null means inherit the globally detected system language. Used when a child's instruction language differs from the OS locale (e.g. an English OS in a Welsh-medium school).

**SAPI fallback rate mapping:** SAPI rate runs −10 (slowest) to +10 (fastest), opposite direction to `length_scale`. Mapping: `sapi_rate = round((1.0 − length_scale) × 10)`, clamped to [−10, 10].

### Alternatives Considered

- **Pre-recorded audio files:** Rejected. Would require recording every letter, word, and phrase in every supported language. Eliminates multilingual flexibility and creates an enormous maintenance burden.
- **Cloud TTS only:** Rejected. Breaks fully-offline principle.
- **SAPI only:** Rejected. Voice quality is insufficient for a primary audio interface, especially for children.
