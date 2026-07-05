# ADR-009: Language Configuration

**Status:** Accepted  
**Date:** 2026-05-17  
**Revised:** 2026-07-05 — isolated-letter spoken names are resolved via the `LetterAudioSource` chain ([ADR-003](0003-text-to-speech.md), revised), not runtime TTS; no letter-name map lives in language config. See [tts-letter-pronunciation](../research/tts-letter-pronunciation.md).

> Part of the [Takki architecture](../architecture.md).

---

**Decision:** Hardcode internal configuration for all ~40 languages supported by `wordfreq`. Configuration per language is minimal (language code + optional exclude list). Support an override YAML file for unsupported languages and edge cases.

### Rationale

Eliminating setup complexity is a core design principle. The entire language configuration for all supported languages fits in a single small Python dictionary shipped with the app:

```python
LANGUAGE_CONFIGS = {
    "de": {"exclude": ["ß"]},
    "fr": {"exclude": []},
    "en": {"exclude": []},
    "nl": {"exclude": []},
    "pl": {"exclude": ["ą", "ź", "ż"]},  # introduce in later lessons
    # ... ~40 entries total
}
```

**What was removed from config through derivation:**
- **Home row definition** — derived from Windows keyboard layout API at runtime by querying characters at the 10 home row scan code positions, then applying the exclude list
- **Character spoken names** — no per-language letter-name map lives in language config. *Isolated* letter names are resolved by the audio layer through the `LetterAudioSource` priority chain ([ADR-003](0003-text-to-speech.md), revised 2026-07-05), not by runtime TTS; in-word/connected pronunciation is still handled by TTS directly. The derivation-removal decision stands — the mechanism moved from "TTS says letters" to "the audio layer owns letter clips," so language config still carries no name table. If a runtime-TTS fallback tier ever needs a name map, it is owned by the audio layer, not here.
- **Special key spoken names** — handled by TTS engine directly (Spacebar, Enter are ordinary words in each language; Backspace is disabled in the lesson engine and never instructed)

**The override file** (`language_override.yaml` in the app data folder) is checked before the hardcoded config at startup. It exists for:
- Languages not in `wordfreq` (parent provides a custom word list)
- Unusual regional variants
- Edge cases discovered after release

**Setup flow for a supported language:**
1. App starts
2. Detects Windows locale (e.g., `de-DE`)
3. Looks up `"de"` in hardcoded config
4. Derives word list and frequency data from `wordfreq`
5. Announces in the target language: language detected, ready to begin
6. No questions asked, no files to find
