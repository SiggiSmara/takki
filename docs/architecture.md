# Takki
## Typing Tutor for Visually Impaired Children
### Pre-Implementation Architecture Document

> **Status:** Pre-ADR — decisions agreed, implementation not yet started  
> **Scope:** Open source hobby project, Windows desktop only  
> **Target users:** Visually impaired children, their parents, and teachers  
> **Repository:** github.com/SiggiSmara/takki  
>
> *Takki (Icelandic): a key or mechanical button.  Implies the sound of a button being pressed.*

---

## Table of Contents

1. [Project Context](#1-project-context)
   - [Design Principles](#design-principles)
   - [Cross-Platform Readiness](#cross-platform-readiness)
2. [ADR-001: Runtime and Distribution](#adr-001-runtime-and-distribution)
3. [ADR-002: Speech Recognition](#adr-002-speech-recognition)
4. [ADR-003: Text-to-Speech](#adr-003-text-to-speech)
5. [ADR-004: LLM Integration](#adr-004-llm-integration)
6. [ADR-005: Keyboard Handling](#adr-005-keyboard-handling)
7. [ADR-006: Language and Keyboard Layout Scope](#adr-006-language-and-keyboard-layout-scope)
8. [ADR-007: Language Data — Word Frequency and Letter Frequency](#adr-007-language-data--word-frequency-and-letter-frequency)
9. [ADR-008: Word List Strategy](#adr-008-word-list-strategy)
10. [ADR-009: Language Configuration](#adr-009-language-configuration)
11. [ADR-010: Lesson Structure and Progression](#adr-010-lesson-structure-and-progression)
12. [ADR-011: Persistence and State](#adr-011-persistence-and-state)
13. [ADR-012: Audio Feedback Design](#adr-012-audio-feedback-design)
14. [ADR-013: Onboarding and Profile Selection](#adr-013-onboarding-and-profile-selection)
15. [ADR-014: Progress Reporting](#adr-014-progress-reporting)
16. [ADR-015: Piper Voice Model Distribution](#adr-015-piper-voice-model-distribution)
17. [ADR-016: Visual Display Design](#adr-016-visual-display-design)
18. [ADR-017: Voice Command and Intent Recognition](#adr-017-voice-command-and-intent-recognition)
19. [ADR-018: Hardware-Adaptive LLM Tiering](#adr-018-hardware-adaptive-llm-tiering)
20. [ADR-019: Testing Strategy and I/O Isolation](#adr-019-testing-strategy-and-io-isolation)
21. [ADR-020: Voice Input Trigger — Push-to-Talk](#adr-020-voice-input-trigger--push-to-talk)
22. [ADR-021: Voice Activity Detection](#adr-021-voice-activity-detection)
23. [ADR-022: Localisation Strategy](#adr-022-localisation-strategy)
24. [Component Overview](#component-overview)
25. [Out of Scope](#out-of-scope)
26. [Open Questions](#open-questions)
27. [Next Steps Before Implementation](#next-steps-before-implementation)
---

## 1. Project Context

This project aims to fill a gap in the accessibility software landscape: a free, open source, multilingual touch typing tutor designed specifically for visually impaired children. 

### Design Principles

- **Fully offline.** The app works completely without internet access after installation. Nothing about a child's voice, typing, or progress is ever sent anywhere. Some optional components (Piper voice models, optional local LLM models) are downloaded once at setup; after that, the app never needs network access.
- **Zero elevated privileges.** Installation and operation must not require administrator rights. This is a hard constraint for school deployment.
- **Minimal setup friction.** The fewer decisions required of a parent or teacher at setup, the better. The ideal is: install, hand to child, done.
- **Audio is the primary interface.** All interaction — instructions, feedback, navigation — must work without any visual reference.
- **Open source contribution friendly.** Architecture should make it easy for teachers, linguists, and developers to contribute word lists, and lesson content without deep Python knowledge.
- **Start focused, don't block the future.** Build for Windows first, but architect for everywhere. Avoid Windows-specific patterns where a cross-platform alternative costs nothing extra. Platform-specific code lives behind clean interfaces so future contributors can add macOS or Linux support without unpicking assumptions throughout the codebase.

### Platform Constraints (Fixed)

- Windows only (no macOS, no Linux, no tablets, no phones) — **for v1**
- Physical keyboard required (no touchscreen input)
- No IME-based languages (see ADR-006)

### Cross-Platform Readiness

The v1 target is Windows, but the architecture is intentionally portable. Almost the entire chosen stack — `faster-whisper`, Piper TTS, `pynput`, `wordfreq`, SQLite, `pygame`, PyInstaller — runs on Windows, macOS, and Linux without modification.

The three areas that are genuinely Windows-specific are isolated behind clean interfaces from the start:

| Interface | Windows implementation | Future platform hook |
|---|---|---|
| `get_system_language()` | Windows locale API | `locale` module / `NSLocale` / `$LANG` |
| `get_home_row_keys()` | Windows keyboard layout scan codes | Carbon (macOS) / xkb (Linux) |
| `get_fallback_tts()` | pyttsx3 → SAPI | pyttsx3 → nsss (macOS) / espeak (Linux) |

By calling these functions rather than the platform APIs directly, adding macOS or Linux support becomes an exercise in implementing three functions — not refactoring the codebase. The practical effort to port to either platform, once Windows is stable, should be a minimal ammount of focused work plus platform-specific packaging and testing.

---

## ADR-001: Runtime and Distribution

**Decision:** Python 3.11+, distributed as a PyInstaller standalone executable bundle.

### Rationale

Python provides the best combination of:
- No administrator rights required for keyboard/microphone/speaker access
- Rich ecosystem for speech, ML, and audio libraries
- Broad familiarity among open source contributors
- Cross-version stability for long-term maintenance

PyInstaller bundles the Python runtime into the executable, meaning users do not need to install Python separately. This is critical for accessibility — a visually impaired parent should not need to navigate a Python installation process.

### Alternatives Considered

- **Electron/web stack:** Rejected. Heavy, adds complexity with no benefit for this use case. Audio latency concerns.
- **C# / .NET:** Good Windows integration but narrows the contributor pool significantly and is less suited to ML/speech libraries.
- **Requiring Python install:** Rejected. Too much friction for non-technical users.

---

## ADR-002: Speech Recognition (Voice Control)

**Decision:** `faster-whisper` (local OpenAI Whisper implementation) as the sole speech recognition engine.

### Rationale

Voice control is a core feature — the app must be navigable without vision. The multilingual requirement makes this non-trivial. `faster-whisper` solves multiple constraints simultaneously:

- **Fully local** — no internet, no API keys, no privacy concerns (critical for children's data)
- **99+ languages** out of the box with no pre-training or language-specific setup
- **No ongoing cost** — important for a free open source project
- **Practical hardware requirements** — `tiny` and `base` are both bundled in the installer and auto-selected at startup by the CPU microbenchmark (see ADR-018). `small` is not bundled: even on a modern Intel Core Ultra 7 it takes ~1.4s per utterance and is impractical without a CUDA-capable GPU. Measured latency on target hardware (AVX2, warm cache, mains power):

  | model | Ryzen 7 5700U | Intel Core Ultra 7 256V |
  |-------|--------------|------------------------|
  | tiny  | ~400ms       | ~230ms                 |
  | base  | ~730ms       | ~415ms                 |
  | small | ~2,300ms     | ~1,390ms               |

  On battery the Ryzen 5700U is ~2× slower (tiny ~800ms, base ~1.5s). Hardware below AVX2 (e.g. Celeron G555, SSE4.2 only) is below minimum spec — even `tiny` takes ~2.6s.

The model load time after the first run is under 1s (OS filesystem cache). Model load on first ever run is 16–19s due to Windows Defender scanning new files; subsequent runs are fast.

Whisper produces text transcriptions. Mapping transcriptions to actionable intents (e.g. "faster", "next", "stop") is handled by a separate intent recognition layer — see ADR-017. The microphone is closed by default and opens only via push-to-talk — see ADR-020 for the activation model and ADR-021 for end-of-utterance detection.

### Alternatives Considered

- **Windows Speech Recognition API:** Rejected. Requires per-language configuration, poor multilingual support, inconsistent accuracy.
- **Cloud APIs (Google, Azure):** Rejected. Require internet, API keys, ongoing cost, and raise data privacy concerns for children.
- **Pre-recorded command matching:** Rejected. Would require pre-recording commands in every supported language, which defeats the multilingual goal.

---

## ADR-003: Text-to-Speech (Audio Feedback)

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

---

## ADR-004: LLM Integration

**Decision:** Local LLM only, optional, hardware-adaptive (see ADR-018). Never used for real-time encouragement. Used only as a tertiary fallback for intent recognition (see ADR-017) when the rule-based pipeline returns no confident match, primarily during setup. Online/cloud LLMs are explicitly out of scope.

### Rationale

LLMs add genuine value in specific places but introduce risk if overused. After detailed evaluation:

**Where LLMs help (and are used):**
- Fallback intent recognition during setup, when the child uses phrasing not anticipated by the rule-based pipeline
- Tertiary fallback during steady-state voice navigation, for unusual phrasings

**Where LLMs are explicitly NOT used:**

*Real-time encouragement generation.* Latency budget is essentially zero — the child completes a word and expects positive feedback immediately. Even on capable hardware, local LLM generation of a short encouragement phrase takes seconds; on the target older hardware it takes 4–10 seconds. This breaks the encouragement loop entirely. Encouragement uses a rule-based phrase bank per language with light randomization (see ADR-012). The "variety problem" is solved by authoring enough phrases — 30–50 per language is sufficient for any practical session length.

*Word list filtering for age-appropriateness.* LLMs have baked-in cultural bias, inconsistent results between runs, and impose value judgements that belong to parents and teachers, not the software. See ADR-008.

*Online/cloud LLM integration.* Rejected entirely. The benefits are concentrated in setup (a one-time event), but cloud integration requires the user to configure API keys, accept network dependency, and accept that their child's voice transcriptions leave the device. The trade is wrong: the users who would most benefit from a smoother setup are the least likely to do additional configuration to get there. Cloud LLM support would also contradict the fully-offline principle, add testing and maintenance burden, and create privacy concerns disproportionate to its benefit. Users who want this can fork the project.

### LLM Tier Model

Three optional tiers, with the offered tier determined automatically by hardware detection at setup (see ADR-018):

**Tier 0 — No LLM (default for all users)**
- Rule-based intent recognition (ADR-017) and rule-based encouragement
- Works on any 8 GB RAM machine of any reasonable age
- No download, no runtime cost beyond the base app

**Tier 1 — Small LLM (1–1.5B parameters)**
- For machines with ~3 GB+ free RAM after Takki loads, CPU roughly 7+ years old or newer
- Model: Llama 3.2 1B Q4 or Qwen 2.5 1.5B Q4 in GGUF format
- Download: ~700 MB – 1.2 GB on demand
- Intent recognition latency: 1–3 seconds on target hardware

**Tier 2 — Medium LLM (3–4B parameters)**
- For machines with ~5 GB+ free RAM after Takki loads, CPU roughly 5+ years old or newer
- Model: Llama 3.2 3B Q4 or Gemma 3 4B Q4
- Download: ~2–2.5 GB on demand
- Intent recognition latency: under 1.5 seconds; quality noticeably better than Tier 1

**Tier 3 — Larger LLM (7–8B parameters)**
- For modern machines or machines with a capable discrete GPU
- Model: Qwen 2.5 7B Q4 or Llama 3.1 8B Q4
- Download: ~4–5 GB on demand
- Intent recognition latency: under 1 second; approaches frontier-model quality on narrow tasks

The runtime is `llama-cpp-python` — pure Python bindings to `llama.cpp`, fully offline, cross-platform.

### Why Not Fine-Tune a Takki-Specific Model

Considered and deferred. A fine-tuned 1B model can achieve 99%+ intent accuracy on narrow domains (e-commerce benchmarks confirm this), but requires synthetic dataset generation per language, single-GPU training infrastructure, and ongoing maintenance as intents evolve. For a hobby project at this stage, generic instruction-tuned models are good enough as a fallback layer behind the rule-based pipeline. Fine-tuning remains a viable future direction if usage grows and the rule-based pipeline shows systematic gaps.

### Alternatives Considered

- **LLM as core dependency:** Rejected. Breaks fully-offline principle, adds hardware requirements, excludes families with older equipment.
- **No LLM at all:** Viable; would work but loses the fallback option for unusual phrasings during setup. The hardware-adaptive opt-in pattern means no user is forced to use an LLM, so this provides upside without imposing cost on constrained machines.
- **Cloud/online LLM:** Rejected. See above.
---

## ADR-005: Keyboard Handling

**Decision:** Use `pynput` for key capture. Rely entirely on Windows to report the correct character for the active keyboard layout. No custom layout definitions maintained by the app.

### Rationale

Windows handles keyboard layout translation transparently. When a user presses a key, `pynput` reports the already-translated character — so on a German QWERTZ keyboard, the key in the Z position reports `y`, and the `ü` key reports `ü`. The app never needs to know which physical key was pressed, only which character was produced.

This means:
- No layout definition files to maintain
- No layout detection logic beyond reading the Windows locale
- Automatic correct behaviour for all QWERTY, QWERTZ, AZERTY, and national variant layouts
- Dead keys and AltGr combinations are handled by Windows before the app sees them

`pynput` is chosen over the `keyboard` library because it does not require elevated privileges on Windows for standard key capture.

The push-to-talk key (ADR-020) is captured via the same `pynput` pipeline as any other key; the lesson engine consumes character events and ignores the talk key, while the voice subsystem subscribes to talk-key events and ignores character keys.

### Alternatives Considered

- **Custom layout definition files (JSON):** Rejected. Unnecessary duplication of information Windows already has. Maintenance burden. Risk of mismatch between app definition and actual system layout.
- **`keyboard` library:** Viable alternative but requires more careful privilege handling. `pynput` is cleaner for this use case.

---

## ADR-006: Language and Keyboard Layout Scope

**Decision:** Support Latin-script languages with direct-input keyboard layouts only. Explicitly exclude IME-based languages (Chinese, Japanese, Vietnamese) from scope.

### Rationale

**On keyboard layout families:**

Research confirmed three categories of Latin-script keyboard layouts:
1. **Structurally different base layouts** (QWERTZ, AZERTY) — letter positions differ from QWERTY
2. **QWERTY with dedicated special-character keys** (Nordic languages, Polish, Romanian, etc.) — base positions unchanged, some keys repurposed for native characters
3. **QWERTY with dead keys / AltGr only** (Dutch, Spanish, Italian, etc.) — base QWERTY essentially intact

All three categories are handled transparently by the Windows + pynput approach in ADR-005. No special handling is needed per category.

**On native vs. English layout for learning:**

Pedagogical consensus is clear: children should learn on their native language keyboard layout, not on US QWERTY first. Native layouts exist for linguistic reasons (letter frequency optimisation) and switching later means learning twice. The app teaches on whatever layout Windows reports as active.

**On IME languages:**

Chinese, Japanese, and Vietnamese use Input Method Editors — the user types Latin keystrokes that are converted by IME software into native characters. This is architecturally a different problem: the "typing" is a two-stage process, and the child is effectively learning QWERTY regardless of their native language. This is out of scope for v1. The Windows + pynput approach would receive IME-converted characters in some configurations, creating unpredictable behaviour.

**Direct-script non-Latin languages** (Arabic, Russian/Cyrillic, Greek, Korean, Thai) are architecturally compatible — the input model is the same as European languages — but are not targeted in v1 due to TTS voice availability and lesson content requirements. The architecture does not preclude adding them later.

---

## ADR-007: Language Data — Word Frequency and Letter Frequency

**Decision:** Use the `wordfreq` Python library as the sole source for word frequency, letter frequency, and bigram/trigram patterns. Derive all three at application startup from the bundled `wordfreq` data. No external download required at runtime.

### Rationale

`wordfreq` provides:
- Word frequency data for 40+ languages
- Data bundled within the package — no internet needed after installation
- Multiple sources combined per language (Wikipedia, subtitles, news, books, web, Twitter) for accuracy
- `pip install wordfreq` — integrates naturally into the Python stack

From the word frequency data, the app derives:
- **Letter frequency ranking** — computed by iterating over frequency-weighted words, restricted to characters present on the keyboard layout, determines the order in which new keys are introduced in lessons
- **Bigram and trigram frequencies** — computed from the same source, drives character pair and sequence generation in Layer 1 drills
- **Filtered word list** — top N words by frequency meeting length and character criteria; words containing characters absent from the keyboard layout are excluded (see Layer 2 below)

**Native alphabet definition** — The authoritative set of characters in the language's alphabet comes from the keyboard layout, not from wordfreq. The platform interface (scan code enumeration via `get_home_row_keys()` extended to all alphabetic positions) returns exactly the characters the physical keyboard can produce; this is the native key set. Characters present in wordfreq only through loanwords — e.g. é in English, from café and résumé — are absent from the keyboard layout and excluded from the native set.

Two consequences:
- The letter frequency ranking (which key to introduce next) uses wordfreq `char_weight`, restricted to characters in the native key set. Loanword-only characters are never in the ordering.
- The Layer 2 word list excludes any word containing a character not in the native key set. Loanwords are dropped entirely — from the lesson and from the coverage denominator.

In the spike script (`spikes/wordfreq_coverage_spike.py`), native alphabet membership is approximated statistically: a character is native if it appears in words totalling ≥0.1% of 3+ character alphabetic text (`MIN_NATIVE_COVERAGE = 0.001`). This correctly separates genuine alphabet members (Icelandic ð, þ; German ü, ä, ö) from loanword-only characters. The real implementation uses the keyboard layout, which is authoritative.

**Startup cost (measured across 20 Latin-script languages):**
- `get_frequency_dict()` load: 25–400ms for most languages. Polish (1.2s) and Finnish (0.8s) are outliers due to large word counts (450k and 725k words respectively). On Windows, file I/O is slower — lazy loading on first language access is preferred over loading all at startup.
- Letter frequency ranking: sub-100ms for any language — just a weighted sum over the frequency dict.
- Full coverage curve (all 26 steps): 200ms–14s depending on word count. **Never compute the full curve at startup.** The app only needs the letter ordering (cheap) at startup; coverage for the child's current key set is computed incrementally as keys are mastered.

This approach avoids cache invalidation complexity. If lazy loading is insufficient for the Polish/Finnish case, a pre-computed letter ordering can be bundled as a small static file alongside the language config.

**Limitation:** `wordfreq` data is a snapshot through approximately 2021 and is no longer actively updated. For a children's typing tutor using common vocabulary, this is entirely acceptable — high-frequency common words do not change significantly over time.

### Alternatives Considered

- **FineFreq (HuggingFace):** Covers 1900+ languages from 96 trillion characters — impressive but requires download and is overkill for this use case. Retained as a fallback reference for languages not in `wordfreq`.
- **Per-language static CSV files:** Rejected. Creates a maintenance burden and requires manual updates when language data improves.
- **Deriving from Wikipedia dumps:** Rejected. Single source, biased toward encyclopedic vocabulary, significant processing overhead.

---

## ADR-008: Word List Strategy

**Decision:** Algorithmic default derived from `wordfreq` (top N words, 3-6 letters, no proper nouns). Parent/teacher override via a plain text file with addition and exclusion syntax. No LLM filtering. No bundled curriculum word lists.

### Rationale

**On age-appropriateness filtering:**

Age-appropriateness is not a linguistic property — it is a cultural and values judgement that varies by family, community, and country. LLM filtering was explicitly evaluated and rejected because:
- LLMs have baked-in Anglo-American cultural bias
- Results are inconsistent between runs (not reproducible)
- Over-filtering removes common useful words; under-filtering causes parent complaints
- The app should not be making values decisions on behalf of families

The algorithmic filter (frequency + length) produces a vocabulary that is overwhelmingly uncontroversial in practice — the genuinely contested words tend to be longer and lower-frequency.

**On bundled curriculum word lists:**

National curriculum vocabulary lists (e.g., German Grundwortschatz, UK National Curriculum word lists) were considered but rejected as the primary approach because:
- Licensing varies by country and requires per-language legal research
- Maintenance burden when lists are updated by education ministries
- Inconsistency between countries in what constitutes a "curriculum list"

They remain a valid contribution path — a contributor can supply a curated word list for their language — but are not required.

**On parent override:**

The plain text override file supports two operations:

```
# Words to add (personally meaningful words for this child)
oma
opa
luna

# Words to exclude
- krieg
- tod
```

The file is processed at every startup. The result is confirmed audibly so visually impaired parents using screen readers know it was applied. This puts values decisions where they belong — with the family — without requiring any code changes.

---

## ADR-009: Language Configuration

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
- **Character spoken names** — handled by TTS engine directly (neural TTS pronounces letter names correctly in the target language)
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

---

## ADR-010: Lesson Structure and Progression

**Decision:** Two-layer concurrent lesson engine with named milestone levels. Lesson content is generated algorithmically from frequency data. Progression rules are language-agnostic. Per-language YAML files contain only the minimal config from ADR-009.

### The Two Practice Layers

**Layer 1 — Character drills** (always active; never replaced)  
Motor learning through character pairs and short sequences weighted by letter and bigram frequency. Home row keys only initially, introduced one hand at a time. Goal: accurate finger placement through repetition, building towards muscle memory.

**Layer 2 — Real words** (unlocks when ≥ 8 keys known)  
Words from the filtered word list constrained to keys the child has already mastered. Words containing characters absent from the keyboard layout (loanwords such as café, résumé) are excluded from both the word list and the coverage denominator — the child is never asked to type them and they do not inflate coverage. Runs alongside Layer 1 — does not replace it. Word length progresses (3 → 4 → 5 → 6 letters) as accuracy on the current length exceeds 85% over 20 words. Hearing a real word spoken then typing it reinforces correct phoneme-grapheme associations alongside motor skill — a documented benefit for visually impaired children.

**Why two layers, not three:** The original design included a pseudo-word layer between drills and real words, following the Keybr approach. Pseudo-words work for sighted typists because the exercise is purely visual — copy this symbol sequence, no phonics involved. For a blind child hearing a spoken pseudo-word, the exercise unavoidably teaches sound-to-spelling associations, and those associations may be wrong or misleading in languages with irregular spelling (English and French especially). The real-words layer with a constrained key set fills the same bridge role from drills to fluent typing without the linguistic risk. Interleaving Layer 1 and Layer 2 concurrently also produces better long-term retention than completing each phase in strict sequence.

### Progression Rules

Progression is adaptive and continuous, not fixed-step:
- A new key is introduced in Layer 1 when first-attempt accuracy on current keys exceeds 90% over a minimum of 50 presses (auto-rejections count as failed attempts — see ADR-012)
- A key is considered "known" when first-attempt accuracy has been sustained above 90% across multiple sessions
- Layer 2 unlocks when ≥ 8 keys are known
- Word length in Layer 2 advances when clean word rate exceeds 85% over 20 words
- Clean word rate (no auto-rejections, no restarts — see ADR-012) is the sole progression gate until the child reaches sustained real-word fluency (see milestones below)
- All thresholds are configurable in a single global config file (not per-language)

**Session composition:** Each session is a weighted mix across unlocked layers. Proportions shift automatically as key knowledge grows:

| Keys known | Layer 1 (drills) | Layer 2 (real words) |
|---|---|---|
| < 8        | 100%             | —                    |
| 8–15       | 60%              | 40%                  |
| 16–25      | 35%              | 65%                  |
| 26+ (full) | 20%              | 80%                  |

Proportions are configurable in the global lesson progression rules config (not per-language).

### Milestone Levels

Named milestones wrap the adaptive engine to give parents, teachers, and children concrete progress markers:

| Level | Criterion |
|---|---|
| **Bronze** | Home row keys known (≥ 90% accuracy sustained) — drills only |
| **Silver** | ≥ 1/3 of the language's full key set mastered |
| **Gold** | ≥ 2/3 of the language's full key set mastered |
| **Platinum** | Full alphabet known (≥ 90% accuracy sustained) — any word attemptable |
| **Diamond** | Fluent dictation — ≥ 95% accuracy on real words without spelling prompt |
| **Speed** | Dictation at ≥ 30 WPM with ≥ 95% accuracy (optional; for motivated older learners) |

**Milestone gates are key-count based, not coverage based.** Silver triggers when the child has mastered ≥ 1/3 of the language's full key set; Gold at ≥ 2/3. "Full key set" is the count of distinct alphabetic characters on the language's physical keyboard layout, enumerated via the platform scan code interface. This is the authoritative source — it includes diacritics and native special characters (e.g. Icelandic has 34 keys including ð, þ, á, é, í; Czech 40 keys) and excludes loanword-only characters that happen to appear in wordfreq data. Using the language's own alphabet size as the denominator means Silver and Gold are always "a third of your alphabet" and "two thirds of your alphabet" regardless of language complexity.

Measured across 20 Latin-script languages: Silver gate (⌊alpha/3⌋) ranges from 8 keys (Finnish, Indonesian) to 13 keys (Czech, Slovak), average 10 keys. Gold gate (⌊alpha×2/3⌋) ranges from 16 keys (Indonesian) to 27 keys (Czech, Slovak), average 21 keys. Coverage at the Silver gate varies from 5% (Slovenian) to 35% (French); at Gold from 61% (Turkish) to 96% (Italian). This wide variation confirms that coverage percentage is unsuitable as a milestone criterion: the same key-count fraction produces very different coverage depending on language frequency distribution.

**Vocabulary coverage is displayed as motivating information, not as a milestone gate.** Coverage = frequency-weighted fraction of 3-or-more-letter words typeable with the child's current key set. It is reported live ("you can now type 1 in 3 everyday words") and announced at each key milestone, but it does not trigger level-ups.

The ≥ 3 character floor serves two purposes: it aligns the metric with the lesson engine (Layer 2 starts with 3-letter words, so coverage reflects what the child actually practises), and it prevents single-character function words from distorting the number. Without the floor, Hungarian coverage jumps ~8% the moment 'a' (the definite article, a 1-letter word) is added to the key set — a spike that has nothing to do with typing skill. With the floor, the early coverage curve is honestly flat (you cannot form meaningful words from just two or three letters), then rises sharply when enough letters combine to unlock real words.

Speed is not reported or targeted until Diamond and above because before that point the bottleneck is key-finding, not finger movement. The natural transition signal from Platinum to Diamond is the child succeeding in dictation mode — hearing just the whole word and typing it correctly from memory without the spelling prompt.

Each milestone triggers a distinct audio celebration — an important engagement mechanism for visually impaired children who cannot see progress bars or badges.

### Why Lessons Are Not Authored Per Language

The lesson engine is entirely language-agnostic. The same code drives German, French, English, and Polish lessons because all content is derived from frequency data at runtime. The only language-specific inputs are:
- The filtered word list (from `wordfreq` + parent override)
- The letter frequency ranking (computed from `wordfreq`)
- The bigram/trigram model (computed from `wordfreq`, used for drill sequence generation)

This means adding a new language requires no lesson authoring — only the minimal config entry from ADR-009.

---

## ADR-011: Persistence and State

**Decision:** SQLite via Python's built-in `sqlite3` module. Local only, no server, no sync.

### Rationale

Child profiles and progress data need to persist across sessions. SQLite is the right choice because:
- Built into Python's standard library — no additional dependency
- Single file on disk, trivially backed up by parents
- No server, no network, no account required
- Sufficient for the data volumes involved (per-key accuracy history, session logs, milestone records)

Each child has a named profile selected at startup (spoken menu). Multiple children can share one installation. Each profile stores:
- Visual display settings (on/off, text size, background color, foreground color, cursor style) — see ADR-016
- Voice settings (`tts_rate`, `tts_voice`, `language` override) — see ADR-003

**Profile portability:** the SQLite file *is* the profile data. It lives at `%APPDATA%\Takki\takki.sqlite` on Windows (the cross-platform location is the standard per-user application data folder reported by the platform interface). To move a child's progress to another computer, copy that file to the same location on the destination machine and rename if necessary to avoid colliding with an existing profile. No export/import flow is provided in v1 — the file is the export format. Parents are reminded of this in the parent/teacher summary (ADR-014).

---

## ADR-012: Audio Feedback Design

**Decision:** Two-tier audio feedback — TTS for spoken content, bundled sound cues for immediate correctness feedback.

### Rationale

For a visually impaired child, the timing and nature of feedback is critical:

**Immediate sound cues** (not TTS): A short pleasant chime for a correct keypress, a gentle low tone for incorrect. These play within milliseconds of the keypress — fast enough to feel like direct cause and effect. Implemented via `pygame.mixer` with small bundled `.wav` files. TTS latency (even with fast local models) is too slow for this feedback loop. Confirmed on Windows: `pygame.mixer` initialises and plays audio without `pygame.display` — no window is opened (pygame 2.6.1, SDL 2.28.4, 22050 Hz stereo).

The talk-key chirp tones (chirp-on / chirp-off, see ADR-020) use the same `pygame.mixer` pipeline. They are tonally distinct from the correct/error cues so the child never confuses "mic is open" with "you typed correctly."

**TTS for spoken content:** Everything else — what to type next, encouragement, instructions, milestone announcements, menu navigation — uses Piper TTS (or SAPI fallback). This content is not latency-sensitive.

**Encouragement variety:** The default rule-based feedback generator cycles through a set of varied encouragement phrases per language. The optional LLM plugin can replace this with dynamically generated responses for more natural variety.

**Progress encouragement — two-phase design:** Between key milestones, the app motivates continued practice by describing what unlocking the next key would gain. This uses two phases:

*Phase 1 — coverage gain framing* (most of the journey, while the coverage curve is steep):
> "Learn your next letter and you'll be able to type X% more everyday words."

X is the marginal coverage gain from the next letter in frequency order. The letter itself is not named — the lesson engine controls introduction order, and revealing the next letter encourages the child to skip ahead rather than consolidate current keys. This framing is most effective while marginal gains are large (the steep middle of the coverage curve).

*Phase 2 — countdown framing* (when ≤ 6 letters remain in the native alphabet):
> "Only 5 letters of the alphabet left!"

Triggered when `remaining = alpha_size − keys_mastered ≤ 6`. The coverage framing is dropped at this point because marginal gains are tiny in the tail and the countdown is more motivating. Knowing you are nearly done is a stronger motivator than being told the next letter unlocks 0.3% more words.

**Word presentation protocol:**

- *Character drills (Layer 1):* Each character is announced individually by TTS, then the child types it. The next character follows after a correct keypress or a configurable timeout.

- *Real words, early (Layer 2, pre-Diamond):* The whole word is spoken first, then spelled letter by letter: *"house — h, o, u, s, e"*. The child then types. The whole-word reading reinforces correct pronunciation; the spelling reinforces phoneme-grapheme mapping. Both are intentional — this is the design that distinguishes real words from the pseudo-word approach that was considered and rejected (see ADR-010).

- *Real words, dictation mode (Layer 2, Diamond+):* The spelling step is withheld. Only the whole word is spoken. The child must recall the spelling from memory. Successful typing without the spelling prompt is the readiness signal for the Diamond milestone.

**TTS interrupt on keypress:**

When the child types while TTS is still speaking the prompt, the TTS is cancelled immediately and the keypress is processed normally. Confident typers — especially older or more fluent children — should not be slowed by the prompt audio they already know. The sound cue and any re-prompt that follow play against silence, not over a tail of unfinished speech. The cancellation is per-utterance: only the current spoken prompt is interrupted, not the application's audio pipeline.

This applies in both layers and to any non-essential TTS (encouragement, between-word remarks). Universal voice commands and milestone announcements complete their utterance and are not interrupted by keypresses, since they are not part of the current type-this-character loop.

**Wrong character handling — auto-reject:**

When the child types an incorrect character, the keypress is auto-rejected: it is never committed to the typed sequence. The error tone fires immediately (low-latency sound cue, not TTS). TTS then re-prompts the current character. The child simply tries again. This means every character that has been accepted is correct by definition — the child is always at a known position with a clean sequence behind them.

Auto-reject applies in both layers. In Layer 1 the drill repeats the same character prompt. In Layer 2 the same character position in the word is re-prompted.

**Backspace — considered and rejected:**

With auto-reject in place, backspace has no meaningful use case. The only situations where backspace seems useful — "I typed the wrong character," "I want to rethink from an earlier position" — are either already handled (wrong characters are discarded automatically) or better served by other controls. Going back one character does not help a child who is disoriented; re-reading the full prompt does. Backspace is therefore disabled entirely. Pressing it plays the boundary tone so the child knows the key registered but had no effect.

This was a deliberate decision. Future contributors should not reintroduce backspace without revisiting the auto-reject model — the two are in tension, and the combination creates more complexity than it resolves.

**Recovery — re-read key:**

A dedicated re-read key (configurable, default Escape) re-speaks the full current prompt and position at any time: *"house — typed: h, o — next: u"*. This is the recovery path for a child who has lost track, mis-heard a character, or simply wants to reorient. It does not reset progress on the current word.

A separate restart key (configurable, default Escape held or double-tap) abandons the current word and re-presents it from the beginning. The word is not counted toward session totals.

**WPM measurement:** Execution time is measured from the child's first keystroke to their last accepted keystroke on a given word. Prompt delivery time is excluded entirely. WPM is only computed and surfaced in progress reporting once the child is in dictation mode (Diamond milestone reached).

**Clean word definition:** A word is "clean" if it was completed with no auto-rejections and no restarts — every character accepted on the first attempt. This is the metric used for progression thresholds and the child summary, not raw completion rate.

---

## ADR-013: Onboarding and Profile Selection

**Decision:** Detect language automatically from Windows locale on first run and begin communicating immediately in that language. If detection fails or the detected language is not supported, rotate spoken welcomes through the top 5 languages by global speaker population until the user responds or selects a language.

### Rationale

The first-run experience must itself be fully accessible — a visually impaired parent or child should not face a silent or text-only setup screen. The Windows locale is the most reliable available signal and is almost always correct. Acting on it immediately, without asking, satisfies the minimal setup friction principle.

The fallback rotation handles the edge cases: unsupported locale, locale not set, or a system configured by a school IT department in a different language than the child's home language. Rotating through the top 5 languages (by speaker population among supported languages — likely English, Spanish, French, German, Arabic or similar) with a short spoken greeting in each gives the user a natural moment to respond in their language, which `faster-whisper` then detects.

### Behaviour

1. App starts → query Windows locale → look up in hardcoded config
2. If found: immediately speak welcome in that language, proceed to profile setup
3. If not found: speak a short greeting in each of the top 5 supported languages in rotation, pausing 3 seconds between each for a voice response
4. On voice response: detect language from response via `faster-whisper`, confirm with user, proceed
5. If no response after one full rotation: default to English with a spoken explanation

### Profile Selection at Session Startup

After language is established, the app loads the child's profile.

**Single profile case:** If only one profile exists on the installation, it is loaded automatically with no further interaction.

**Multiple profile case:** The app speaks the available profiles — *"Who's practicing today? I have Lisa and John."* — and the child responds with their name. The standard intent recognition pipeline (ADR-017) fuzzy-matches the spoken response against the profile name list. The selected profile is confirmed audibly — *"Hi Lisa! Ready to practice?"* — before loading. The child can dissent ("no", "wait") to restart selection.

No verification beyond the name match is performed. Profile selection trusts the child to identify themselves correctly. This is sufficient for the typing tutor use case; data integrity stakes are low (worst case is some lost progress for one session) and stronger verification (passwords, biometrics, voice ID) is incompatible with the audio-first, low-friction design. If usage patterns later reveal a need for verification, an opt-in question/answer mechanism can be added per profile without breaking the existing data model.

### Profile Name Uniqueness

Profile names must be unique within an installation. Comparison is case-insensitive and accent-insensitive (so "Lisa", "lisa", and "Lísa" all collide — they sound identical at voice-selection time).

At creation:

1. If the new name is unique, accept it.
2. If it collides with an existing profile, the app prompts: *"There's already a Lisa on this computer. What should I call this one?"* The parent provides a distinguishing addition — "Lisa B", "Big Lisa", "Lisa from school", or anything else that works for that family.
3. If the proposed name still collides after the addition, the app re-prompts. The new profile is not created until a unique name is provided.
4. The original profile is never modified.

This invariant — every profile name in the system is unique — means selection-time fuzzy matching always resolves to exactly one profile. No tiebreaking logic is needed downstream.

### Alternatives Considered

- **Ask the user to choose from a spoken list of all 40 languages:** Rejected. Listening to 40 language names is not a good first experience.
- **Require a text/click setup before first use:** Rejected. Breaks the audio-first principle for visually impaired users.

---

## ADR-014: Progress Reporting

**Decision:** Support a simple spoken and printed progress summary for children, parents, and teachers. Available on demand at any time, not just at session end.

### Rationale

Progress visibility matters for three audiences with different needs:

- **The child** needs immediate positive reinforcement — hearing "You know 12 keys now, and your best speed today was 8 words per minute" is motivating and concrete.
- **The parent** needs to know the child is progressing and the tool is working, without needing to interpret raw data.
- **The teacher** needs enough detail to report to a school or make curriculum decisions.

All three are served by the same summary at different verbosity levels. The summary is generated from the SQLite data already being collected — no additional data capture is needed.

### Summary Levels

**Child summary** (spoken, brief, celebratory):
- Keys mastered
- Current layer active (drills only / drills + real words)
- Milestone level reached
- Vocabulary coverage percentage ("you can now type X% of everyday words") — reported as a live motivating signal between milestones
- Clean words today (words typed correctly on first attempt — a concrete accuracy signal meaningful to a child)
- Best execution speed today (reported only at Diamond milestone and above)
- Streak (days practiced in a row)

**Parent/teacher summary** (spoken + printable text file):
- Everything in child summary
- Per-key accuracy breakdown
- Session history (date, duration, keys practiced)
- Milestone dates
- Words per minute trend over time

The printable summary is a plain `.txt` file written to the desktop (or a configured folder), readable by any screen reader. No PDF, no formatting complexity, no dependencies.

### Alternatives Considered

- **Raw SQLite access only:** Rejected for v1. Teachers cannot reasonably be expected to query a database.
- **Web dashboard:** Rejected. Adds server complexity, breaks offline-first principle.
- **PDF report:** Rejected. Adds a dependency (PDF library) for no benefit over plain text for screen reader users.

---

## ADR-015: Piper Voice Model Distribution

**Decision:** The installer always bundles the English voice (out-of-box fallback). Additional voices are distributed as standalone downloads via the project website — the user's browser downloads the file and saves it to a known local folder; the app scans that folder on startup. No in-app download logic. SAPI is the last-resort fallback when no `.onnx` voice file is present at all.

Piper voices are hosted on HuggingFace (`rhasspy/piper-voices`), not GitHub releases.

### Bundled Voices

English (`en_US-lessac-low`, ~60 MB) is always included in the installer. It serves as the out-of-box voice for English lessons and as the fallback when no voice file for the lesson language is found.

**Beta:** English and German (`de_DE-thorsten-low`, ~60 MB) are both bundled. Total installer size: Whisper tiny+base (~220 MB) + two voices (~120 MB) ≈ 340 MB.

**V1:** Up to five voices may be bundled (decision deferred to V1). English is always one of them.

### Additional Voice Distribution

Voices for non-bundled languages are distributed as direct browser downloads from the project website. The website presents a table of supported languages with a download link per voice (pointing to the HuggingFace file URL) and a file size. Instructions tell the parent to save the downloaded `.onnx` file and its accompanying `.onnx.json` sidecar to `Documents\Takki\voices\`.

The app creates `Documents\Takki\voices\` on first run. If the lesson language voice is absent, the app speaks once: *"For a better voice in [language], visit the Takki website and download a voice file. Save it to the Takki voices folder in your Documents."*

Using the browser as the download agent is intentional: browsers handle retries, resume on failure, progress display, and file-size verification more reliably than a Python downloader, and they handle HuggingFace's changing download backends transparently.

### Voice Discovery

On startup the app scans `Documents\Takki\voices\` for `.onnx` files and matches them to the lesson language by filename prefix (e.g. `de_DE-*.onnx` for German). Bundled voices are stored in the app's own data directory and are always available without scanning.

### Fallback Hierarchy

1. Piper voice for the lesson language (from `Documents\Takki\voices\` or bundled)
2. Bundled English Piper voice (if lesson language is not English and no matching voice file is found)
3. pyttsx3 / SAPI (if no `.onnx` file is present at all — e.g. immediately after a fresh install for a non-bundled language before the parent has downloaded a voice)

### Voice Catalog

The app ships a hand-maintained `voice_catalog/{lang}.yaml` per supported language listing the curated voice choices for that language: a human-readable label (e.g. `"Female voice"`, `"Male voice"`), the Piper voice key, and the expected file size. `x_low` and multi-speaker voices are excluded — they are unsuitable for a primary audio interface. File sizes in the catalog are used to validate downloaded files against expected size.

A typical language has 1–3 curated voices. English has the most options; many languages have one or two.

### Alternatives Considered

- **In-app downloader:** Rejected. HuggingFace's Xet and hf_transfer backends have active Windows reliability bugs; standard HTTP requires workarounds (`HF_HUB_ENABLE_HF_TRANSFER=0`) and still has instability reports. The browser is a more reliable and familiar download agent.
- **Bundle all ~36 supported languages:** Rejected. ~2.1 GB for voices alone is unreasonable.
- **Per-language installers generated by the website:** Rejected as over-engineered for V1. Simple download links achieve the same outcome with no build infrastructure.
- **Stream audio from cloud TTS:** Rejected. Breaks offline-first principle.

---

## ADR-016: Visual Display Design

**Decision:** Optional secondary visual display, off by default, child-configured. Consistent two-line layout across both lesson layers. Visual cues appear after or simultaneously with audio — never before. Display shows only what is directly part of the current task.

### Rationale

Literature on learned helplessness in visually impaired children establishes that over-assistance from observers who have more information than the child is a documented harm. A visual display that surfaces per-keypress error data to an observer before the child has processed their own audio feedback creates exactly the information asymmetry that produces this effect. VI children themselves report feeling their independence limited by parents and support teachers who intervene on the basis of what they observe.

The governing principle is the **observer invariant**: nothing appears on screen during a session that the child has not already heard or is simultaneously hearing. The screen is a subtitle to the audio, not an additional information channel.

The display is opt-in and child-controlled — consistent with the finding that true independence means control over how and when support is received. Children with visual impairments typically know their preferred colors and contrast settings from other assistive tools; the setup workflow respects this prior knowledge.

### The Two-Line Layout

All visual display uses a consistent two-line structure:

- **Upper line** — the prompt: what the child is supposed to type
- **Lower line** — the response: what the child has typed, with the cursor marking the current position

**Layer 1 (character drills):**

```
        a              ← current target character, centered
    f g h |            ← up to 3 history characters left of centered cursor
```

- Upper line: current target character, large, centered. Appears simultaneously with TTS announcement.
- Lower line: up to 3 most recently correctly typed characters to the left of a centered cursor. Cursor sits directly below the target character in the upper line.
- On correct keypress: the correct character briefly occupies the cursor position, shifts left into history, oldest history character disappears off-screen, upper line updates to the next target.
- On wrong keypress: nothing changes. Cursor stays. Upper line stays. No error indicator of any kind.

**Layer 2 (real words):**

```
h o u s e             ← full word
h o u | _             ← typed characters aligned, cursor at next position
```

- Upper line: the full word, displayed from the start.
- Lower line: correctly typed characters aligned character-by-character with the upper line. Cursor at the next untyped position, directly below the corresponding character above.
- On correct keypress: character fills cursor position, cursor advances one step right.
- On wrong keypress: nothing changes. No error indicator.

### What the Display Never Shows

- Error indicators — no red X, no color change, no flash on wrong keypress
- What wrong key was pressed
- Real-time accuracy statistics or WPM
- A keyboard diagram or key highlighting
- Running session statistics
- Layer or mode indicator during a session
- Vocabulary coverage percentage during a session

All of the above are either available post-session in the parent/teacher summary (ADR-014) or serve only as observer-facing data that creates information asymmetry.

### Visual Setup Workflow

Setup is navigated entirely by audio. The child runs through five steps:

1. **On/off** — visual display is off by default. The child explicitly enables it.
2. **Text size** — named steps: Large, Very Large, Maximum. TTS names each; a sample character previews on screen.
3. **Background color** — see Color Selection below.
4. **Foreground color** — same flow; the chosen background is shown throughout so the child previews the actual combination as foreground changes.
5. **Cursor style** — Block, Underline, Blinking. TTS names each; cursor updates live in the preview.

After all five steps, the full combination is shown with a sample word:

> TTS: *"Here is how your screen will look — yellow background, black text, showing the word 'house'. Press Enter to save or Escape to change."*

Settings are stored per child profile in SQLite (see ADR-011).

### Color Selection

Children with visual impairments typically know their preferred colors from overlays and assistive tools used in school. The selection flow respects this prior knowledge:

1. TTS asks the child to name their preferred color.
2. `faster-whisper` transcribes the response. A fuzzy match is attempted against the palette and common synonyms (e.g. "navy" / "dark blue" → Navy; "ivory" / "off-white" → Cream).
3. If a match is found: the screen previews the color immediately. TTS confirms and asks the child to accept or try again.
4. If no match or no response: TTS moves to browse mode — each palette color is spoken in turn, the screen updates live, and the child confirms with Enter or voice.

Background is selected first, then foreground. The chosen background is shown throughout foreground selection so the child always previews the real combination.

**Palette:**

| Name | Hex |
|---|---|
| Black | #000000 |
| White | #FFFFFF |
| Yellow | #FFE600 |
| Orange | #FF6600 |
| Red | #CC0000 |
| Blue | #0055CC |
| Green | #008800 |
| Purple | #6600CC |
| Cream | #FFFACD |
| Navy | #001F5B |

Foreground and background are chosen independently. The only constraint: foreground and background may not be the same color — same-color entries are excluded from the browse list and rejected on voice match. No soft warning for near-similar colors — the live preview gives the child direct feedback on readability and they are the best judge of their own vision.

### Alternatives Considered

- **Pre-paired high-contrast presets:** Rejected. VI children's visual needs vary significantly by condition; free independent selection with a live preview respects individual needs and prior knowledge.
- **Real-time error indicators (red X, color flash):** Rejected. Creates information asymmetry — an observer sees error data before the child has processed their own audio feedback. Literature links this directly to learned helplessness in VI children.
- **Keyboard diagram with key highlighting:** Rejected. Undermines the touch-typing goal; creates a visual dependency that delays muscle memory formation.
- **Single-line display:** Rejected. Conflates prompt and response; requires a different layout metaphor for Layer 1 vs Layer 2, creating unnecessary cognitive overhead at the layer transition.
- **Observer-facing real-time dashboard:** Rejected. All observer data is post-session via the parent/teacher summary (ADR-014). Real-time observer data creates conditions for unsolicited intervention.

---

## ADR-017: Voice Command and Intent Recognition

**Decision:** Layered intent recognition pipeline running on top of Whisper transcriptions. Context-aware active intent sets per interaction mode. Confirmation-over-inference for setup. Rule-based core; optional LLM as tertiary fallback (ADR-004 / ADR-018).

### Rationale

Whisper gives the app a text transcription of what the child said. The intent recognition layer maps that transcription to an actionable command. This is a distinct problem with established patterns in open source voice interfaces (Mycroft Adapt/Padatious, Rhasspy, voice2json, Picovoice Rhino) and recent child-accessibility research (MEOWCROPHONE for Scratch, which demonstrated baseline free-speech recognition at 46.4% versus a layered pipeline at 82.8% — a 36-point accuracy gain critical for children's speech).

Children's speech is harder to recognize than adult speech: physiological differences in the vocal tract, lower pronunciation clarity (especially in younger children), higher intra-speaker and inter-speaker variability, and higher rates of disfluencies. Whisper handles these better than most engines but still imperfectly. A robust intent layer is what bridges the gap between transcription and action.

### The Layered Pipeline

For each utterance, the pipeline tries layers in order and returns on the first match above a confidence threshold:

**Layer 1 — Exact and synonym keyword match.** Intents are defined with keyword groups per language. "Faster" intent in English matches `{"faster", "speed up", "more speed", "quicker"}`; in German `{"schneller", "schneller bitte", "schnell"}`. This catches the majority of cases instantly with no inference cost.

**Layer 2 — Phonetic match.** When Whisper produces something close-but-wrong ("vaster" instead of "faster", "schnüller" instead of "schneller"), a phonetic algorithm (Metaphone, Double Metaphone, or language-appropriate equivalent) finds the intended keyword. This is the layer that gave MEOWCROPHONE its largest accuracy gain for child speech.

**Layer 3 — Fuzzy string match.** For transcription errors that are spelling-similar but not phonetically similar. Standard Levenshtein distance with a configurable per-intent threshold.

**Layer 4 — LLM fallback (optional, only if available).** For genuinely flexible phrasing ("can you slow down a bit", "I want to take a break"). Runs only when Layers 1–3 return no confident match. Uses the locally-installed LLM at whatever tier the hardware supports (ADR-004). Skipped entirely on Tier 0 installations.

If all available layers fail, the app responds with a clear "I didn't catch that — try again" — better than guessing wrong.

### Context-Aware Intent Sets

The active set of intents the pipeline considers varies by application state. The app knows what step of setup or interaction it's at, and only intents valid at that step are matched. For example:

- **At "choose background color"**, active intents are: COLOR_NAME, POSITION_REFERENCE, REPEAT, GO_BACK, START_OVER, HELP. All other intents are inactive.
- **At "type the spoken word"**, active intents are: REPEAT, READ_AGAIN, GO_BACK, RESTART_WORD, HELP, EXIT_SESSION.
- **At "select a profile"**, active intents are: PROFILE_NAME (one per existing profile), CREATE_NEW, REPEAT, HELP.

This dramatically improves accuracy because the pipeline is more aggressive within a smaller candidate set. "I think she said sky" wouldn't match a color outside color-selection context, but within it confidently resolves to Blue.

This pattern is borrowed from Rhasspy and voice2json's "scoping" model.

### Setup Interaction Modes

Setup is architecturally distinct from steady-state operation. The interaction modes:

**Mode 1 — Constrained choice (yes/no, color from palette, voice from catalog).**
Closed set, well-known synonyms per language. Fuzzy-match against the closed set. Yes-intent synonyms include "yes", "yeah", "okay", "sure", "go ahead", "fine", and equivalents in each language. Color palette entries each have 5–10 synonyms per language (e.g. "navy"/"dark blue" → Navy; "ivory"/"off-white" → Cream). Synonym lists are a contribution path for native-speaker contributors.

**Mode 2 — Free-form input (name).**
No closed set. The app captures Whisper's transcription, reads it back for confirmation — *"I heard Lukas — is that right?"* — and proceeds on affirmative response. On dissent, the app offers to spell the name letter-by-letter via voice, which doubles as familiar typing-tutor interaction.

**Mode 3 — Selection from a list (text size, voice catalog).**
Supports both name reference ("Large", "Amy") and position reference ("the second one", "number two"). Both are recognized at equal priority.

**Mode 4 — Universal escape commands (always active).**
"Repeat", "go back", "start over", "skip", "help" are recognized at the highest priority regardless of current mode. The pipeline checks these before any context-specific intent set.

### Setup Failure Modes to Avoid

- **Silent failure.** Every utterance must produce immediate audible acknowledgment — either the matched intent or a clear "I didn't quite catch that."
- **Wrong-match success.** Setup biases heavily toward confirmation over inference. A misheard color is corrected by the live preview (ADR-016); a misheard name is corrected by the read-back step.
- **Cascading confusion.** "Go back" and "start over" commands are available at every step via Mode 4 universal escapes.
- **Frustration loops.** After three failed attempts at the same step, the app offers a simpler path — for selection from a list, switch from name matching to spoken-number selection ("press 1, 2, or 3").

### Per-Language Intent Definitions

Intent definitions live in `intents/{lang}.yaml` files — one per language. The format is simple enough for non-programmer contributors. An English example:

    INCREASE_RATE:
      keywords:
        - faster
        - speed up
        - more speed
        - quicker
    DECREASE_RATE:
      keywords:
        - slower
        - slow down
        - less speed
    REPEAT:
      keywords:
        - repeat
        - say again
        - again
        - what

A contributor adding a new language provides a single YAML file. No code changes. This is the primary contribution path for language coverage of voice commands.

### Alternatives Considered

- **Whisper transcription + raw string equality:** Rejected. Fails on the predictable Whisper errors that the layered pipeline catches.
- **LLM-only intent recognition:** Rejected. Latency, hardware dependency, and unavailable on Tier 0 installations.
- **Single-mode pipeline (no context-aware intent sets):** Rejected. Loses meaningful accuracy gains for closed-set interactions like setup.
- **Picovoice Rhino:** High accuracy but proprietary; doesn't fit open-source-first stance.
- **Rhasspy as runtime dependency:** Considered but adds significant complexity for a project this size. Its intent definition patterns are borrowed; the runtime is not.

---

## ADR-018: Hardware-Adaptive LLM Tiering

**Decision:** At setup, Takki detects hardware capability and proactively offers the best LLM tier the machine can comfortably run. Re-evaluates on major events (new hardware, app update, user request). User is never required to know about parameters, quantization, or model selection.

### Rationale

Hardware capability varies enormously across target users — from 10-year-old school computers to modern home machines. The cost of getting this wrong in either direction is real: offering an LLM that won't run smoothly creates frustration; not offering one when the machine can handle it loses available quality.

Asking the user to figure this out themselves is the wrong answer. Most parents and teachers don't know what a parameter count is. The right pattern is: the app does the work, gives a recommendation, the user accepts or declines.

This shifts the LLM from an opt-in technical decision to a guided recommendation. Most users will say yes if offered, because the framing is "make the app better" rather than "configure a language model."

### Hardware Detection

Detection runs at install time and stores the result. Re-runs only on specific triggers (see below).

The detector combines several signals:

- **Available RAM** — `psutil.virtual_memory().available`, measured with Takki running so the number reflects actual headroom, not theoretical total.
- **CPU capability** — A short microbenchmark (small matrix multiplication, ~200ms run) gives a real-world capability number. More reliable than CPU model heuristics, which age poorly.
- **GPU presence** — Detected but only counted if a discrete CUDA-capable GPU with sufficient VRAM is present. Integrated graphics are ignored.
- **Disk space** — Available space in the app data directory. No point recommending a 4 GB model on a machine with 2 GB free.

The combination produces a single recommended tier (0, 1, 2, or 3). Tiers are defined in ADR-004.

### Whisper Model Auto-Selection

The same CPU microbenchmark that gates LLM tiers also selects the Whisper model at startup — no user decision required. Both `tiny` and `base` are bundled in the installer; the app picks the best one the hardware can run comfortably:

| matmul result | Whisper model | Typical latency |
|---------------|---------------|-----------------|
| < ~2ms        | `base`        | ~400–730ms      |
| ~2–10ms       | `tiny`        | ~400–800ms      |
| > ~10ms       | none          | below minimum spec; voice commands unavailable |

Thresholds are derived from measured spike data across three machines (Celeron G555, Ryzen 7 5700U, Intel Core Ultra 7 256V). The ~2ms threshold ensures `base` latency stays under ~800ms on mains power; above it, `tiny` provides comparable latency. The ~10ms floor reflects that SSE4.2-only CPUs (e.g. Celeron) cannot run even `tiny` within an acceptable latency budget.

`small` is explicitly excluded from the installer — it requires 1.4s+ even on the fastest tested CPU and offers no practical benefit over `base` for the narrow intent recognition task without a CUDA GPU.

### Tier Recommendation Flow

After language and visual settings are established, the app presents the recommendation:

**Tier 1 recommended (modest hardware):**
> *"I checked your computer and you have enough power for a smart helper that makes my setup easier and helps me understand you better. It would take about 800 megabytes of download. Want to add it?"*

**Tier 2 or 3 recommended (capable hardware):**
> *"I checked your computer and you have plenty of power. I can use a smart helper that makes me much better at understanding what you say. It would take about 2 gigabytes of download. Or I can use a smaller one that's about 800 megabytes. Or I can run without it. Which would you like?"*

**Tier 0 recommended (constrained hardware):**
> *"Your computer doesn't quite have the room for an extra helper, so I'll run in my simpler mode. Don't worry — I still work great this way."*

The reassurance on Tier 0 is essential. Silent absence of the offer would leave the user wondering if they're missing something.

### Re-Evaluation Triggers

Hardware changes over time — users upgrade RAM, replace machines, install in school labs on different machines. Triggers for re-evaluation:

- **Migration to new hardware** — if the stored machine ID changes, re-check
- **Major Takki update** — re-evaluate in case tier thresholds or available models have changed
- **User request** — settings option "Check if my computer can use a better helper" runs the check on demand
- **Failed LLM operation** — if the configured tier consistently fails to meet latency targets, suggest downgrading

The opposite direction is just as important: if a user upgrades their machine, Takki should notice at next startup and offer the better tier — *"It looks like your computer got faster! I can use a smarter helper now if you'd like."*

### What This Decision Does Not Cover

Tier definitions themselves (which model maps to which tier, what RAM thresholds gate each tier) are covered in ADR-004. This ADR covers the detection mechanism and the user interaction pattern.

### Alternatives Considered

- **Manual user selection:** Rejected. Asks the user to understand technical details that have nothing to do with their goal.
- **Static minimum requirements:** Rejected. Either too conservative (excludes capable users who would benefit) or too aggressive (recommends LLMs to users whose hardware can't run them well).
- **Always-offer regardless of hardware:** Rejected. Frustrating UX on constrained hardware; user installs a slow model, has a bad experience, may abandon the app.
- **Hide the option entirely on low-end hardware:** Rejected. Tier 0 reassurance is preferred over silent absence.

---

## ADR-019: Testing Strategy and I/O Isolation

**Decision:** All external-world interfaces are defined as `typing.Protocol` classes. Application logic depends on the Protocol, never on the concrete implementation. Tests use fake implementations by default. Hardware- and model-dependent tests are isolated via pytest markers and run on dedicated CI tiers via GitHub Actions.

### Rationale

The project has many awkward-to-test dependencies: Piper TTS (model download, Windows-confirmed), `faster-whisper` (model download, audio in), `pynput` (keyboard hardware), `pygame.mixer` (sound card), Windows locale and keyboard APIs (Windows-only), `llama-cpp-python` (GB-scale models). Without architectural discipline, testing the lesson engine, intent pipeline, and progression rules would require setting up these dependencies — slow, flaky, and incompatible with the headless Linux dev environment.

The fix is to push every external interface behind a `Protocol` boundary. The pattern is already proven by the three Windows-specific platform interfaces (ADR-005, ADR-006, ADR-013) — this ADR generalises it to every external interface in the system.

`typing.Protocol` is preferred over abstract base classes:
- No inheritance required — implementations are structurally typed
- No mocking framework overhead — fakes are trivial Python classes
- Static type checkers verify conformance
- The plugin architecture (LLM, optional cloud TTS in component overview) naturally drops in as alternative Protocol implementations

### Protocol Catalog

Each protocol is introduced when its consuming component is first built. Real implementations live in their domain module (`src/takki/audio/`, `src/takki/voice/`, etc.). Fakes live in `tests/fakes/`.

| Protocol | Real implementation(s) | Fake |
|---|---|---|
| `TTSEngine` | `PiperTTS`, `FallbackTTS` (pyttsx3/SAPI) | `RecordingTTS` |
| `SoundCuePlayer` | `PygameMixerCues` | `RecordingCues` |
| `KeyEventStream` | `PynputKeyStream` | `ScriptedKeyStream` |
| `VoiceTranscriber` | `WhisperTranscriber` | `ScriptedTranscriber` |
| `WordSource` | `WordfreqSource` | `FixedListSource` |
| `Clock` | `SystemClock` | `FakeClock` |
| `LLMRunner` | `LlamaCppRunner` | `ScriptedLLMRunner` |
| `HardwareProbe` | `RealHardwareProbe` | `FixedHardwareProbe` |

The three platform functions in CLAUDE.md (`get_system_language`, `get_home_row_keys`, `get_fallback_tts`) are the Windows-specific instances of this same pattern.

**The Protocol boundary is also the plugin boundary.** Any third-party or community-contributed alternative — a different TTS engine, an alternative wake-word handler, a cloud-LLM adapter forked downstream — is a new Protocol implementation drop-in. There is no separate plugin framework; the Protocol set above is the public extension surface.

### Test Pyramid

Default `uv run pytest` runs only Tiers 1 and 2 — fast, deterministic, no models, no hardware.

| Tier | Scope | Where | Trigger | Cost |
|---|---|---|---|---|
| 1. Unit | Logic against fakes — lesson engine, progression rules, intent layers 1–3, milestone gates, encouragement selection | Linux | every PR | seconds; ~80% of suite |
| 2. Integration (stubbed I/O) | SQLite in-memory, `wordfreq` for 2 languages, pyttsx3+espeak, pygame headless, Whisper on WAV fixtures | Linux | every PR | ~1 minute |
| 3. Platform smoke | Windows platform interfaces, `pynput`, Piper, SAPI | `windows-latest` | every PR | a few minutes |
| 4. Slow integration | Full Whisper corpus, all LLM tiers, all `wordfreq` languages | matrix | nightly | longer; off critical path |
| 5. Release | PyInstaller bundle + `.exe` smoke test | `windows-latest` | on tag | rare |

Pytest markers control inclusion: `audio`, `model`, `windows_only`, `slow`, `release`. `pyproject.toml` declares them so they're recognised. Default invocation:

    uv run pytest -m "not (audio or model or windows_only or slow or release)"

### GitHub Actions Strategy

CI covers the bits Linux dev cannot:

- **OS matrix.** `windows-latest` runs platform smoke tests every PR. `ubuntu-latest` runs the bulk of the suite. No macOS runner until ADR-006 scope expands.
- **Model caching.** `actions/cache` keyed on Piper, Whisper, and LLM model URLs. First run downloads; subsequent runs hit cache. Integration tests against real models cost seconds after warm-up.
- **Headless audio/video.** `SDL_AUDIODRIVER=dummy` and `SDL_VIDEODRIVER=dummy` let `pygame` initialise without a sound card or display. Catches code-path regressions; humans verify quality.
- **Synthetic audio fixtures.** A small WAV corpus committed to the repo covers common intents in each Beta-supported language. Whisper transcription is deterministic given a fixed model and fixed input — accuracy regressions on Whisper version bumps are visible.

  *Source of the corpus:* the fixtures are generated by TTS (Piper at varied rates and voices) and supplemented with adult-recorded clips read by maintainers and contributors. We do **not** collect or commit recordings of children's speech — both for ethical reasons and because we have no consent framework that could make it appropriate. The synthetic corpus catches regressions in transcription and intent resolution, but it does not represent the variability of real child speech. Evaluating recognition quality on actual children is therefore deferred to the Beta friends/family pilot, where informed parental consent and an appropriate testing protocol can be arranged per family.

### What CI Cannot Verify

- Audio quality and naturalness of Piper voices
- Keyboard latency feel
- Whether intent recognition resolves well on real child speech (high variability, disfluencies)
- Visual display readability across vision conditions

These require human testing. The Beta friends/family pilot in [roadmap.md](roadmap.md) is the venue.

### Alternatives Considered

- **Mocking framework (`unittest.mock` patching):** Rejected. Encourages patching at import time, which leaves real implementations available as accidental coupling vectors. Protocol+fake is more explicit and works with static type checking.
- **Dependency injection container:** Rejected. Overkill at this codebase size. Direct constructor injection of Protocol implementations is sufficient.
- **No isolation, real I/O in tests:** Rejected. Slow tests get skipped; skipped tests rot.
- **Abstract base classes instead of Protocols:** Rejected. Forces inheritance, blocks structural typing, more verbose for no benefit.

---

## ADR-020: Voice Input Trigger — Push-to-Talk

**Decision:** Voice input is gated by a dedicated push-to-talk key. The microphone is closed by default and opens only when the child presses the talk key. A short ascending chirp marks the start of listening; a short descending chirp marks the end. Wake-word and always-listening approaches are explicitly rejected.

### Rationale

The competing approaches all fail on at least one project constraint:

- **Always-listening.** Mic permanently hot. Contradicts the offline/privacy stance — even if no audio leaves the device, a parent or school IT explaining Takki cannot honestly say "the mic only opens when the child asks it to." That guarantee is a meaningful trust signal for the target audience.
- **Wake word ("Hey Takki").** Local wake-word engines (Porcupine, OpenWakeWord) are available and would preserve offline operation. But wake-word engines are trained predominantly on adult speech and have documented poor activation rates on children's voices. A child who already has limited feedback channels and has to repeat "Hey Takki" four times before the mic opens is a frustrated child. There is also no visual indicator a VI child can use to distinguish "the system heard the wake word but didn't understand the command" from "the system didn't hear the wake word at all" — both produce silence.
- **Push-to-talk.** Explicit control by the child. Audio cues (chirp on / chirp off) give a VI child unambiguous feedback that the mic is hot. The key itself is a learnable interaction — for a typing tutor, this is curriculum-adjacent rather than friction. Privacy guarantee is concrete: the mic is open exactly when the child holds or has just pressed the talk key.

The "extra key to learn" cost is genuinely small. VI children develop strong touch-locating muscle memory; a single dedicated key at a fixed location is well within the same skill set the app is teaching.

### Default Talk Key

**Right Ctrl** is the default. It is configurable per profile.

The key was selected against these constraints:

- Must not conflict with screen reader modifier conventions (Caps Lock and Insert are off-limits — these are used by NVDA, JAWS, and Windows Narrator and may collide if a screen reader is later installed alongside Takki)
- Must not conflict with characters the child types during lessons (rules out alphabet keys, Spacebar, Enter)
- Must be reliably findable by touch (rules out function keys on laptop keyboards where they share with brightness/volume, and Pause/Break which is missing on many keyboards)
- Single-press behaviour must be a no-op in normal use (so that accidental presses outside of intent-to-talk are harmless)
- Right Shift was considered and rejected — pressed often enough during typing that accidental triggering during practice is plausible.

No strong cross-tool convention exists in the VI community for this specific interaction; voice-input tools in the accessibility space (Talon Voice, Dragon) typically default to "configure your own." The Right Ctrl default will be validated during the Beta pilot, and the per-profile configurability means changing the default later is reversible without code change.

### Trigger Behaviour

**Press-and-release with auto-close** is the default:

1. Child presses and releases the talk key
2. Chirp-on plays (~150ms, ascending tone)
3. Microphone opens; recording begins
4. End-of-utterance is detected by VAD (see ADR-021) — typically 800ms of silence after speech
5. Chirp-off plays (~150ms, descending tone)
6. Recording ends; audio is passed to Whisper for transcription
7. Transcription is passed to the intent recognition pipeline (ADR-017)

A maximum recording length (default 10 seconds) caps any open-ended recording if VAD fails.

**Press-and-hold** is supported as a per-profile alternative. In this mode the mic is open while the key is held; release ends the recording immediately and skips the VAD-driven silence detection. Some children find walkie-talkie style more intuitive; some find press-and-release lower effort. The choice is part of profile setup.

### Audio Feedback Design

Chirp tones are distinct from the lesson engine's correct/error tones (ADR-012). They are:

- Short (~150ms each) — not interrupting the child's flow
- Tonally distinct from sound cues used elsewhere
- Identical across sessions and across lessons — predictable cue, not a varying signal

Together with the chirp-on/chirp-off pair, this gives a VI child unambiguous, time-bounded feedback about when the mic is hot. The mic is never in an ambiguous state from the child's perspective.

### Interaction With the Lesson Engine

- **During a lesson:** the talk key opens the mic for navigation commands (repeat, faster, slower, exit). The lesson pauses while listening. If a child presses the talk key mid-word, the current word is held in place, the command is resolved, then practice resumes from the same position. The word is not abandoned and progress is not lost.
- **During TTS output:** pressing the talk key cancels the current TTS utterance (consistent with the keypress-interrupts-TTS rule in ADR-012) and opens the mic immediately. The child should not have to wait for the prompt to finish before being able to interrupt.
- **During setup:** the talk key opens an additional command channel for universal escape intents (go back, help, skip). The setup script itself opens the mic during specific question prompts ("What's your name?", "What color do you want?") without the child needing the talk key.

### Alternatives Considered

- **Always-listening with intent threshold filter.** Rejected — keeps mic open, conflicts with privacy stance.
- **Wake word.** Rejected — see Rationale; child-speech activation rates are poor and the silent-failure mode is bad UX for VI children.
- **Push-to-mute (mic on by default, child turns it off).** Rejected — same privacy issue as always-listening, with worse defaults.
- **Touch a specific keyboard zone (multi-key combo).** Rejected — not different from a single key in practice, more complex to learn.
- **Hardware button (USB push-to-talk dongle).** Rejected for v1 — adds a peripheral dependency. May reconsider for v2 if pilot feedback suggests it.

---

## ADR-021: Voice Activity Detection

**Decision:** Use `webrtcvad` for end-of-utterance detection. With push-to-talk (ADR-020), start-of-speech is signalled by the talk key, so VAD is needed only to determine when the child has finished speaking. Neural VAD alternatives (`silero-vad`) are deferred.

### Rationale

VAD requirements are different under push-to-talk than under always-on listening:

- Start-of-speech is signalled by the talk key — no acoustic detection needed
- End-of-speech ("they stopped, send to Whisper now") is the only acoustic decision left
- End-of-utterance detection is exactly what energy + spectrum-based VAD is good at; the harder cases for VAD (distinguishing speech from speech-like noise during a long passive listening window) do not arise

`webrtcvad` is:

- A small native extension (~30 KB)
- The original Google WebRTC voice activity detector — mature, well-tested, widely deployed
- Pure C with thin Python bindings — no neural network, no model file, no GPU
- Fast enough to run frame-by-frame on the audio stream with negligible CPU cost

The cost of adding `silero-vad` (the obvious neural alternative) is substantial:

| | `webrtcvad` | `silero-vad` (via Torch) | `silero-vad` (via onnxruntime) |
|---|---|---|---|
| Install size | ~30 KB | ~200 MB (CPU-only Torch wheels) | ~50 MB |
| Bundle impact (PyInstaller) | negligible | +500 MB – 1 GB | ~60 MB |
| Cold-start time | instant | 1–2s Torch import | <500ms |
| ML runtime count | 0 | 3 (Torch + CTranslate2 + llama.cpp) | 3 (onnxruntime + CTranslate2 + llama.cpp) |
| Accuracy on quiet speech | OK | Better | Better |

For end-of-utterance under push-to-talk, the accuracy gain does not justify the added runtime weight. The most expensive part of the project's distribution story is already the PyInstaller bundle plus Piper models plus optional LLM models. Adding 500 MB+ for a marginal VAD upgrade would dominate the install size for a feature most children will never notice working correctly.

### How It Works in Takki

1. Talk key pressed → audio recording begins at 16 kHz mono (matching Whisper's native rate)
2. Audio is fed to `webrtcvad` in 20ms frames
3. VAD reports speech/non-speech per frame
4. After N consecutive non-speech frames (default 800ms after the first speech frame is seen), recording ends
5. A maximum recording length (default 10 seconds) caps the recording if VAD fails to detect silence
6. The full recording is passed to Whisper for transcription

### Sensitivity Setting

`webrtcvad` exposes an aggressiveness setting of 0–3:

- 0 = least aggressive (more permissive — more likely to declare speech, less likely to cut off quiet speakers)
- 3 = most aggressive (more likely to declare silence, more likely to cut off quiet speech)

**Default: 2** (moderate). Configurable per profile. A quiet child or noisy school environment may need a lower setting; an environment with continuous background noise may need a higher one.

### Failure Modes

- **VAD never detects silence (continuous noise).** The 10-second cap ends the recording, Whisper transcribes, and the intent layer handles whatever it can. If Whisper returns garbage, the standard "I didn't catch that — try again" response fires.
- **VAD declares silence immediately (mic level too low).** Whisper receives a too-short audio clip and returns nothing meaningful. Same response: "I didn't catch that — try again." Repeated occurrences may prompt the app to suggest reducing VAD aggressiveness during a future setup pass.
- **VAD declares silence during a long pause mid-utterance.** Acceptable failure mode — the child can simply press the talk key again. With push-to-talk, a "false cut" is annoying but not destructive.

### Future Upgrade Path

If Beta pilot testing reveals that `webrtcvad` consistently fails on real child speech in real environments (quiet speakers, noisy classrooms, accented speech), the upgrade path is `silero-vad` loaded via `onnxruntime` — **not** via Torch. `onnxruntime` is a much smaller dependency than Torch and remains compatible with the bundle-size constraint.

The VAD interface sits behind a Protocol (ADR-019), so swapping implementations is a localised change.

### Alternatives Considered

- **Naive energy threshold.** Works in quiet environments but doesn't distinguish speech from noise. Sensitive to mic gain — a child with a quiet mic gets cut off; a child with a hot mic gets noise recorded as speech. `webrtcvad` is barely heavier and meaningfully more robust.
- **`silero-vad` via Torch.** Quality gain doesn't justify Torch dependency and bundle inflation. See table above.
- **`silero-vad` via onnxruntime.** Viable but adds an ML runtime we don't currently need. Reserved as the upgrade path if `webrtcvad` proves insufficient.
- **Streaming Whisper / continuous transcription.** Out of scope — we are not building a dictation tool. Voice input is for short navigation commands, not continuous speech-to-text.

---

## ADR-022: Localisation Strategy

**Decision:** All localisation surfaces use YAML files per language. This applies uniformly to runtime UI strings, the encouragement phrase bank (ADR-012), intent definitions (ADR-017), and the voice catalog (ADR-015). No gettext, no `.po`/`.mo` workflow, no translation platform integration in v1.

### Rationale

The conventional choice for Python application localisation is gettext. For Takki specifically, gettext is a poor fit:

- **Every UI string is spoken, not displayed.** Gettext's strengths — handling display length, layout, RTL/LTR, character set quirks — do not apply. The visual display in Takki shows only the typing prompt and typed characters (ADR-016), no localised labels.
- **Multi-variant phrases are first-class.** The encouragement bank (ADR-012) requires multiple variants per phrase with random selection for natural variety. Many UI strings benefit from the same treatment ("Welcome back, Lisa" / "Hi Lisa! Ready to practice?" / "Hello Lisa, let's go" — picked at random keeps repeated sessions from sounding scripted). Gettext does not handle multi-variant naturally; YAML lists do.
- **Existing localisation surfaces already use YAML.** Intent definitions (ADR-017) and voice catalog (ADR-015) are YAML by design. Adding gettext for one surface fragments the contribution pattern; YAML across the board is one mental model.
- **Contributor audience.** Native-speaker volunteers (teachers, linguists, parents) edit YAML directly via PRs. They are not running professional localisation workflows. `.po`/`.mo` tooling is unnecessary friction.
- **Native-speaker review is more effective on a single readable file.** The language pack PR template requires a native-speaker review; a reviewer scanning one YAML file catches phrasing issues that a scattered `.mo` review would miss.

### Schema

Four files per language, each in its own directory:

```
strings/{lang}.yaml          # Runtime UI strings (this ADR)
encouragement/{lang}.yaml    # Encouragement phrase bank (ADR-012)
intents/{lang}.yaml          # Voice command intents (ADR-017)
voice_catalog/{lang}.yaml    # Curated Piper voice metadata (ADR-015)
```

UI strings (`strings/{lang}.yaml`) — single string or list of variants per key:

```yaml
ready_to_practice: "Ready to practice."

language_detected: "Language detected: {language}."

profile_loaded:
  - "Hi {name}! Ready to practice?"
  - "Welcome back, {name}."
  - "Hello {name}, let's go."

milestone_silver:
  - "You've reached Silver! You know one third of the alphabet now."
  - "Silver milestone! That's a third of your alphabet mastered."

didnt_catch_that:
  - "I didn't catch that — try again."
  - "Sorry, can you say that again?"
```

A list-valued key triggers random selection at lookup time. Single-value keys are returned verbatim.

### Pluralisation

For languages with rich plural categories (Polish, Russian, Arabic, etc.), explicit forms by CLDR plural category:

```yaml
keys_known:
  one: "You know one key now."
  few: "You know {count} keys now."
  many: "You know {count} keys now."
  other: "You know {count} keys now."
```

The string resolver picks the appropriate form using CLDR plural rules. The `babel` library (pure Python, widely available) provides the plural-rule lookup; `babel` is added as a runtime dependency when the localisation module lands.

A pluralised key may itself contain a list of variants per form:

```yaml
clean_words_today:
  one:
    - "One clean word today!"
    - "You typed one perfectly today."
  other:
    - "{count} clean words today!"
    - "You typed {count} perfectly today."
```

### Loading and Runtime Behaviour

- At app start, the active language's YAML files are loaded into memory. Files are small (kilobytes); the cost is negligible.
- A `tr(key, **params)` function returns the appropriate string. Multi-variant keys randomise per call.
- Format strings use Python's `str.format` style (`{name}`, `{count}`).
- Missing keys fall back to English (`en`) with a logged warning. The user-facing failure mode is "the app speaks English for this one phrase," not a crash.

### Contribution Path

1. A contributor (native speaker or working with a native-speaker reviewer) forks the repo
2. They add or edit the four YAML files for their language
3. They open a PR using the language pack template (`.github/ISSUE_TEMPLATE/language_pack.md`)
4. Native-speaker review is required for merge
5. No build step — YAML is read at runtime; the change is live in the next session

### Alternatives Considered

- **Gettext (`.po` / `.mo`).** Rejected. See rationale. Mature ecosystem, but mismatched with audio-first delivery and multi-variant requirements; adds compilation step and tooling burden for no benefit in this project.
- **Fluent (Mozilla).** Promising — natively handles plural categories, grammatical gender, and selectors. Adds `fluent.runtime` as a dependency. Reserved as a future option if YAML proves insufficient for languages with very complex morphology. The cost is a learning curve for contributors who don't already know Fluent.
- **Weblate / Crowdin integration.** Both support YAML in addition to .po. No integration at v1 scope — contributors edit YAML via PRs. Possible future addition without changing the file format.
- **Mixed approach (gettext for UI strings, YAML for everything else).** Rejected. Fragmenting the contribution pattern for one surface adds friction with no proportionate benefit.

---

## Component Overview

```
┌─────────────────────────────────────────────────────────┐
│                    App Core (Python)                    │
├──────────────────────┬──────────────────────────────────┤
│    Input Layer       │    Audio Layer                   │
│  • pynput            │  • Piper TTS (default)           │
│  • Windows layout    │  • pyttsx3/SAPI (fallback)       │
│    API               │  • pygame (sound cues)           │
│                      │  • Cloud TTS (optional plugin)   │
├──────────────────────┼──────────────────────────────────┤
│    Voice Input       │    Lesson Engine                 │
│  • faster-whisper    │  • Layer controller              │
│    (local)           │  • Adaptive key introducer       │
│  • Intent recognition│  • Drill sequence generator      │
│    pipeline (ADR-017)│  • Word selector                 │
│  • Optional LLM      │                                  │
│    fallback (ADR-004)│                                  │
├──────────────────────┼──────────────────────────────────┤
│    Language Layer    │    Feedback Layer                │
│  • wordfreq          │  • Rule-based (default)          │
│  • Letter freq       │  • LLM plugin (optional)         │
│  • Bigram model      │                                  │
│  • Word list filter  │                                  │
│  • Parent override   │                                  │
├──────────────────────┼──────────────────────────────────┤
│    Visual Layer      │                                  │
│  • Two-line display  │                                  │
│    (off by default)  │                                  │
│  • Per-profile config│                                  │
│  • pygame rendering  │                                  │
├──────────────────────┴──────────────────────────────────┤
│                  Config / State                         │
│  • Hardcoded language configs (40+ languages)           │
│  • language_override.yaml (edge cases)                  │
│  • custom_words.txt (parent additions/exclusions)       │
│  • SQLite: child profiles, progress, session history,   │
│            visual display settings per profile          │
│  • Global lesson progression rules config               │
│  • Piper model cache (per language, downloaded once)    │
│  • Hardware capability profile (LLM tier, see ADR-018)  │
└─────────────────────────────────────────────────────────┘
```

---

## Out of Scope

The following were explicitly considered and excluded from v1:

| Topic | Reason |
|---|---|
| macOS / Linux support | v1 is Windows only; architecture keeps future porting low-effort (see Cross-Platform Readiness) |
| Tablets / phones | Out of scope by requirement |
| IME-based languages (Chinese, Japanese, Vietnamese) | Architecturally different input model; different problem |
| Non-Latin direct-input scripts (Arabic, Cyrillic, Korean) | Compatible architecturally but requires TTS voices and lesson content not yet available |
| Keyboard shortcuts curriculum | Separate topic; addressed after core typing is established |
| One-handed typing support | Future implementation; architecture does not preclude it |
| Braille keyboard support | Future implementation; architecture is compatible |
| Narrative / quest framing | Evaluated as an audio-native engagement mechanism well-suited to visually impaired children. Deferred to v2 to avoid content maintenance burden and the requirement to author story content in 40+ languages. The LLM plugin path (ADR-004) is the intended community contribution entry point for this feature. |
| Cloud sync of progress | No server dependency; local SQLite is sufficient |
| Multiplayer / competitive modes | Not relevant for target audience |
| Cloud/online LLM integration | Explicitly rejected. See ADR-004. Users who want this can fork the project. |
| Fine-tuned Takki-specific intent model | Deferred. Generic instruction-tuned models are sufficient at this stage. See ADR-004. |

---

## Open Questions

The following questions remain unresolved and require research before or during implementation:

1. ~~**Minimum hardware spec**~~ — **resolved.** Measured across three machines (Celeron G555, Ryzen 7 5700U, Intel Core Ultra 7 256V). Minimum viable spec is AVX2 with a CPU microbenchmark under ~10ms (512×512 float32 matmul). Below that (e.g. Celeron, SSE4.2 only, ~16ms) even `tiny` takes ~2.6s — unusable. Above it, `tiny` runs at 400–800ms and `base` at 400ms–1.5s depending on power state. Both models are bundled in the installer and auto-selected by the matmul threshold (~2ms). See ADR-002 and ADR-018.

2. **Session pacing and fatigue** — Audio-only practice is more cognitively taxing than sighted practice. Research needed: do other VI-focused educational tools enforce session length limits, recommend breaks, or auto-pause after a period of inactivity? Should Takki proactively suggest a break, or trust the child and parent to manage pacing? Affects ADR-010 (lesson structure) and the steady-state session loop.

3. ~~**Piper voice download reliability**~~ — **resolved.** Both Whisper models and Piper voices are hosted on HuggingFace (`rhasspy/piper-voices`); HuggingFace's Xet and hf_transfer backends have active Windows reliability bugs and the domain is frequently blocked by school content filters. The solution is the same for both: bundle what is needed, delegate optional downloads to the user's browser. English voice is always bundled; additional voices are distributed as direct download links from the project website (browser → save to `Documents\Takki\voices\`). No in-app download logic. See ADR-015.

---

## Next Steps Before Implementation

This pre-ADR document captures agreed architectural decisions but is not sufficient to begin implementation. The following must be completed first:

**1. Open the Repository — Immediate**
- Create `SiggiSmara/takki` on GitHub
- Add this document as `docs/architecture.md`
- Add a README with project name, one-paragraph description, and a note that the project is in pre-implementation planning
- Select a license (MIT recommended for maximum adoption in educational settings)
- Add a CONTRIBUTING.md stub so early visitors understand contributions are welcome

**2. Implementation Roadmap**
See [roadmap.md](roadmap.md) for the agreed phased plan (Alpha, Beta, V1), the in/out-of-scope split per phase, dependency-ordered task lists within each phase, and the "done" criteria.

**3. Resolve Open Questions**
The session pacing and fatigue question (open question 2) should be resolved before implementing the session loop. Open questions 1 and 3 are now resolved.

**4. Repository and Contribution Setup**
Before any code, the open source scaffolding should be in place:
- Repository structure documented
- Language pack contribution format documented
- Issue templates for bug reports, language pack contributions, and feature requests
