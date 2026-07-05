# ADR-003: Text-to-Speech (Audio Feedback)

**Status:** Accepted  
**Date:** 2026-05-17  
**Revised:** 2026-07-05 — isolated letter names moved off runtime neural TTS to a curated `LetterAudioSource` chain (spike: [tts-letter-pronunciation](../research/tts-letter-pronunciation.md)).

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

**Character and key name pronunciation.** In *connected* speech (words, encouragement, instructions) neural TTS pronounces characters correctly in context (e.g. a German voice reads "ä" correctly inside a word); explicit overrides are added only when testing reveals specific mispronunciations — this list is expected to be very small. *Isolated* letter names are handled separately — see the revision note below.

> **Revised (2026-07-05):** the original claim that "neural TTS engines correctly pronounce letter names" is **false for isolated letters.** The [letter-pronunciation spike](../research/tts-letter-pronunciation.md) found neural TTS (Piper) is *structurally* bad at ultra-short 1–3 phoneme utterances at every quality tier: the phonemes espeak feeds it are correct, but the VITS acoustic model — trained on sentences — distorts them, and no text/SSML/tier trick fixes it. SAPI speaks letters cleanly but only for installed Windows voices (no Icelandic); espeak-ng is reliable and multilingual but robotic. Isolated letters are a **closed, fixed per-language set**, so they are resolved through the `LetterAudioSource` Protocol's three-layer priority chain (below), not by general synthesis. This applies to isolated letters only; Piper remains the default for all connected speech.

### Letter audio: the three-layer model

*(Canonical home for the letter-audio layering. Added with the revision note above, 2026-07-05.)*

Isolated-letter audio resolves through `LetterAudioSource` ([`src/takki/audio/letters.py`](../../src/takki/audio/letters.py)) as three named layers, highest priority first. Resolution **walks down** until it finds audio for the requested letter; a lower layer is consulted only when every layer above it is absent for that letter.

| Priority | Layer | Voice | Scope | Source | Progress-gated |
|---|---|---|---|---|---|
| 1 (wins) | **Personal** | the child's own | per **profile** | recorded in-app — the *reward* workflow ([ADR-030](0030-personal-letter-recordings.md)) | ✅ offered per learned letter |
| 2 | **Base** | a human's | per **language** | bundled curated clips (human-verified, best engine per language), or community-contributed | no |
| 3 (floor) | **Synthetic** | machine | universal | runtime TTS — SAPI where a Windows voice exists, espeak-ng otherwise | no |

**Invariant — Synthetic is the floor and can never be empty.** espeak-ng produces a full, correct (if robotic) letter alphabet for every target language, offline. So resolution always terminates in audio: Personal and Base are quality *upgrades* over the floor, never prerequisites. A missing, muted, or corrupt higher layer degrades exactly one step — never to silence.

**Naming is fixed and internally consistent:** the three *layers* are **Personal / Base / Synthetic**. `reward` names the workflow that populates Personal ([ADR-030](0030-personal-letter-recordings.md)) — it is not a layer. `floor` is informal shorthand for "Synthetic is guaranteed." User-facing copy may use warmer phrasing ("record it in your own voice"), but code, tables, and ADRs use the three layer names.

- **Base subsumes shipped *and* contributed clips** — same layer, same per-language scope. A parent/teacher-recorded alphabet is the community-contribution surface and is curatable into a later shipped bundle. The *contribution* recording workflow (a human supplies a language Base) is **deferred**: with the Synthetic floor there is no silent-language failure to rescue, so it is a post-Alpha feature and gets its own ADR when built.
- **Personal is per-profile** and lives in the profile database ([ADR-011](0011-persistence-and-state.md), [ADR-030](0030-personal-letter-recordings.md)); Base clips are read-only per-language assets, not per-profile.
- This model covers **isolated letters only**. Connected speech (words, encouragement, instructions) is unchanged — Piper per the main decision above.

**Per-student voice settings** are stored in the child profile (see ADR-011):

- `tts_rate` — Piper `length_scale` float. Default 1.0. Range 0.6–2.0 in 0.2 steps. Higher = slower. Adjusted via spoken "faster" / "slower" commands; each command moves one step. Speech rate is highly individual — a change of 0.2 is perceptible and meaningful. The range covers the full practical spectrum from fast-but-intelligible (0.6) to very deliberate (2.0).
- `tts_voice` — Piper voice model key, e.g. `en_US-amy-low`. Null means use the language default. Gender and accent are baked into the model; there is no separate gender field. The parent selects a voice from the curated `voice_catalog.yaml` (see ADR-015) before the model is downloaded — the chosen key is then stored here.
- `language` — BCP-47 language code override. Null means inherit the globally detected system language. Used when a child's instruction language differs from the OS locale (e.g. an English OS in a Welsh-medium school).

**SAPI fallback rate mapping:** SAPI rate runs −10 (slowest) to +10 (fastest), opposite direction to `length_scale`. Mapping: `sapi_rate = round((1.0 − length_scale) × 10)`, clamped to [−10, 10].

### Alternatives Considered

- **Pre-recorded audio for the *entire* corpus:** Rejected. Recording every letter, word, and phrase in every supported language eliminates multilingual flexibility and creates an enormous maintenance burden. *(Revised 2026-07-05: this rejection stands for the open-ended corpus only. Curated audio for the **closed isolated-letter set** — on the order of ~30 clips per language — is a distinct, accepted case, resolved behind the `LetterAudioSource` Protocol; see the revision note above and [ADR-009](0009-language-configuration.md). It keeps runtime TTS for open-ended speech while giving deterministic, human-verified letter audio.)*
- **Cloud TTS only:** Rejected. Breaks fully-offline principle.
- **SAPI only:** Rejected. Voice quality is insufficient for a primary audio interface, especially for children.
