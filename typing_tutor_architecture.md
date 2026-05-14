# Takki
## Typing Tutor for Visually Impaired Children
### Pre-Implementation Architecture Document

> **Status:** Pre-ADR — decisions agreed, implementation not yet started  
> **Scope:** Open source hobby project, Windows desktop only  
> **Target users:** Visually impaired children, their parents, and teachers  
> **Repository:** github.com/SiggiSmara/takki  
>
> *Takki (Icelandic): a key or mechanical button. Also the sound of fingers finding their keys.*

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
14. [ADR-013: Onboarding Language Detection](#adr-013-onboarding-language-detection)
15. [ADR-014: Progress Reporting](#adr-014-progress-reporting)
16. [ADR-015: Piper Voice Model Distribution](#adr-015-piper-voice-model-distribution)
17. [Component Overview](#component-overview)
18. [Out of Scope](#out-of-scope)
19. [Open Questions](#open-questions)
20. [Next Steps Before Implementation](#next-steps-before-implementation)

---

## 1. Project Context

This project aims to fill a gap in the accessibility software landscape: a free, open source, multilingual touch typing tutor designed specifically for visually impaired children. The only known comparable product (TypeAbility) is proprietary, English-language focused, and has limited support for other languages.

### Design Principles

- **Offline first.** The app must work completely without internet access after installation. Many target users are in school or home environments where internet reliability cannot be assumed.
- **Zero elevated privileges.** Installation and operation must not require administrator rights. This is a hard constraint for school deployment.
- **Minimal setup friction.** The fewer decisions required of a parent or teacher at setup, the better. The ideal is: install, hand to child, done.
- **Audio is the primary interface.** All interaction — instructions, feedback, navigation — must work without any visual reference.
- **Open source contribution friendly.** Architecture should make it easy for teachers, linguists, and developers to contribute language packs, word lists, and lesson content without deep Python knowledge.
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

By calling these functions rather than the platform APIs directly, adding macOS or Linux support becomes an exercise in implementing three functions — not refactoring the codebase. The practical effort to port to either platform, once Windows is stable, is estimated at 2-4 days of focused work plus platform-specific packaging and testing.

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
- **Practical hardware requirements** — the `tiny` or `base` model runs adequately on modest hardware; `small` gives better accuracy on mid-range machines

The small startup latency (model load time) is acceptable given that the app is not a real-time dictation tool — voice is used for navigation commands, not continuous input.

### Alternatives Considered

- **Windows Speech Recognition API:** Rejected. Requires per-language configuration, poor multilingual support, inconsistent accuracy.
- **Cloud APIs (Google, Azure):** Rejected. Require internet, API keys, ongoing cost, and raise data privacy concerns for children.
- **Pre-recorded command matching:** Rejected. Would require pre-recording commands in every supported language, which defeats the multilingual goal.

---

## ADR-003: Text-to-Speech (Audio Feedback)

**Decision:** Piper TTS as default, with pyttsx3/Windows SAPI as automatic fallback. Optional cloud TTS as a user-configured plugin.

### Rationale

Audio feedback is the primary output modality. Quality matters — a robotic or mispronouncing voice is demotivating for children.

**Piper TTS** is chosen as the default because:
- High-quality neural voices, substantially better than SAPI
- Runs fully locally, no internet
- Pre-built voice models available for many languages
- Lightweight enough to bundle or download at first run

**pyttsx3/SAPI** is retained as fallback because:
- Zero additional installation — uses built-in Windows voices
- Guarantees the app works even if Piper model download fails
- Some users may prefer it for familiarity

**Character and key name pronunciation** is handled directly by TTS rather than through lookup tables. Neural TTS engines correctly pronounce letter names and common special characters in their target language (e.g., a German TTS voice pronounces "ä" as "A-Umlaut" correctly). Explicit overrides are added only when testing reveals specific mispronunciations — this list is expected to be very small.

### Alternatives Considered

- **Pre-recorded audio files:** Rejected. Would require recording every letter, word, and phrase in every supported language. Eliminates multilingual flexibility and creates an enormous maintenance burden.
- **Cloud TTS only:** Rejected. Breaks offline-first principle.
- **SAPI only:** Rejected. Voice quality is insufficient for a primary audio interface, especially for children.

---

## ADR-004: LLM Integration

**Decision:** Optional, pluggable, offline-first. Default operation requires no LLM. LLM role is limited to encouragement phrase variation and contextual sentence generation.

### Rationale

LLMs add genuine value in specific places but introduce risk if overused:

**Where LLMs help:**
- Generating varied, warm encouragement responses (avoiding the repetition of "Well done!" becoming meaningless)
- Generating simple age-appropriate sentences for advanced lesson phases
- Onboarding conversation ("What is your name? What language would you like to practice?")

**Where LLMs were explicitly rejected:**
- **Word list filtering for age-appropriateness** — LLMs have baked-in cultural bias, inconsistent results between runs, and impose value judgements that belong to parents and teachers, not the software. See ADR-008.

The integration is designed as a clean interface (`FeedbackGenerator`, `SentenceGenerator`) with a rule-based default implementation. Users can optionally configure a local LLM backend (via Ollama) or a cloud backend (OpenAI, Anthropic) through a config file. The app never requires or assumes an LLM is present.

### Alternatives Considered

- **LLM as core dependency:** Rejected. Breaks offline-first principle, adds hardware requirements, creates ongoing cost dependency.
- **No LLM at all:** Viable for v1 but the pluggable interface is low-cost to build and high-value for contributors who want to enhance the experience.

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
- **Letter frequency ranking** — computed by iterating over frequency-weighted words, determines the order in which new keys are introduced in lessons
- **Bigram and trigram frequencies** — computed from the same source, drives pseudo-word generation for the middle lesson phase
- **Filtered word list** — top N words by frequency meeting length and character criteria

All three are recomputed at every application startup. The computation is fast (milliseconds for a few thousand words) and this approach avoids cache invalidation complexity. If performance ever becomes a concern, caching can be added later.

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
- **Special key spoken names** — handled by TTS engine directly (Spacebar, Backspace, Enter are ordinary words in each language)

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

**Decision:** Three-phase adaptive lesson engine with named milestone levels. Lesson content is generated algorithmically from frequency data. Progression rules are language-agnostic. Per-language YAML files contain only the minimal config from ADR-009.

### The Three Phases

**Phase 1 — Character drills**  
Pure motor learning. Home row keys only initially, introduced one hand at a time. Character pairs and short sequences weighted by letter frequency. No real words. Goal: accurate finger placement through repetition.

**Phase 2 — Pseudo-words**  
Pronounceable nonsense sequences generated from bigram/trigram frequencies. More natural rhythm than random characters but no word-recognition shortcut — the child must actually locate each key. Begins when the child has demonstrated proficiency on 8+ keys. This phase was validated by the Keybr approach to adaptive typing practice.

**Phase 3 — Real words**  
Words from the filtered word list, initially constrained to words using only keys the child has already mastered. Word length progression: 3 letters → 4 → 5 → 6. Eventually simple sentences. Hearing a real word spoken, then typing it, reinforces phonics and spelling alongside motor skill — a documented dual benefit for visually impaired children.

### Progression Rules

Progression is adaptive and continuous, not fixed-step:
- A new key is introduced when accuracy on current keys exceeds 90% over a minimum of 50 presses
- A key is considered "known" when accuracy has been sustained above 90% across multiple sessions
- Word length increases when accuracy on current length exceeds 85% over 20 words
- All thresholds are configurable in a single global config file (not per-language)

### Milestone Levels

Named milestones wrap the adaptive engine to give parents, teachers, and children concrete progress markers:

| Level | Criterion |
|---|---|
| **Bronze** | All home row keys known |
| **Silver** | Full alphabet known |
| **Gold** | Real words at 30+ WPM with 95% accuracy |
| **Platinum** | Sentences at 40+ WPM with 95% accuracy |

Each milestone triggers a distinct audio celebration — an important engagement mechanism for visually impaired children who cannot see progress bars or badges.

### Why Lessons Are Not Authored Per Language

The lesson engine is entirely language-agnostic. The same code drives German, French, English, and Polish lessons because all content is derived from frequency data at runtime. The only language-specific inputs are:
- The filtered word list (from `wordfreq` + parent override)
- The letter frequency ranking (computed from `wordfreq`)
- The bigram/trigram model (computed from `wordfreq`)

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

Each child has a named profile selected at startup (spoken menu). Multiple children can share one installation.

---

## ADR-012: Audio Feedback Design

**Decision:** Two-tier audio feedback — TTS for spoken content, bundled sound cues for immediate correctness feedback.

### Rationale

For a visually impaired child, the timing and nature of feedback is critical:

**Immediate sound cues** (not TTS): A short pleasant chime for a correct keypress, a gentle low tone for incorrect. These play within milliseconds of the keypress — fast enough to feel like direct cause and effect. Implemented via `pygame.mixer` with small bundled `.wav` files. TTS latency (even with fast local models) is too slow for this feedback loop.

**TTS for spoken content:** Everything else — what to type next, encouragement, instructions, milestone announcements, menu navigation — uses Piper TTS (or SAPI fallback). This content is not latency-sensitive.

**Encouragement variety:** The default rule-based feedback generator cycles through a set of varied encouragement phrases per language. The optional LLM plugin can replace this with dynamically generated responses for more natural variety.

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
│  • faster-whisper    │  • Phase controller              │
│    (local)           │  • Adaptive key introducer       │
│                      │  • Pseudo-word generator         │
│                      │  • Word selector                 │
├──────────────────────┼──────────────────────────────────┤
│    Language Layer    │    Feedback Layer                │
│  • wordfreq          │  • Rule-based (default)          │
│  • Letter freq       │  • LLM plugin (optional)         │
│  • Bigram model      │                                  │
│  • Word list filter  │                                  │
│  • Parent override   │                                  │
├──────────────────────┴──────────────────────────────────┤
│                  Config / State                         │
│  • Hardcoded language configs (40+ languages)           │
│  • language_override.yaml (edge cases)                  │
│  • custom_words.txt (parent additions/exclusions)       │
│  • SQLite: child profiles, progress, session history    │
│  • Global lesson progression rules config               │
└─────────────────────────────────────────────────────────┘
```

---

## ADR-013: Onboarding Language Detection

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
- Current phase (drills / pseudo-words / real words)
- Milestone level reached
- Best speed today
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

**Decision:** Download Piper voice models at first run per language, not bundled in the installer. The installer ships with one small default voice (English) only.

### Rationale

Piper voice models are language-specific files ranging from tens to hundreds of MB each. Bundling models for all 40 supported languages would produce an installer of several gigabytes — unreasonable for a hobby project and a significant barrier for users on slow connections or with limited disk space.

Downloading at first run per language is the better tradeoff:
- Installer remains small and fast to download
- Only the models actually needed are downloaded
- Models are cached locally after first download — subsequent runs are fully offline
- Users who need multiple languages download each model once

### Download Behaviour

1. On first run (or when a new language is selected), app checks local cache for the required Piper model
2. If not cached: announce audibly that the voice model needs to be downloaded, state the approximate size, and ask for confirmation before proceeding
3. Download with a simple progress indication (spoken percentage or periodic "still downloading" message)
4. On failure: fall back to pyttsx3/SAPI automatically with a spoken notice
5. Once cached: fully offline, no further internet access needed

### Fallback

The SAPI fallback (via pyttsx3) means the app is never non-functional due to a missing Piper model. Users on restricted networks or with no internet at setup get a lower-quality but working voice immediately, and can download the Piper model later when connectivity is available.

### Alternatives Considered

- **Bundle all models:** Rejected. Multi-gigabyte installer is unreasonable.
- **Bundle the selected language's model only:** Partially viable but complicates the installer significantly — the language may not be known at install time in a school deployment scenario.
- **Stream audio from cloud TTS:** Rejected. Breaks offline-first principle.

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
│  • faster-whisper    │  • Phase controller              │
│    (local)           │  • Adaptive key introducer       │
│                      │  • Pseudo-word generator         │
│                      │  • Word selector                 │
├──────────────────────┼──────────────────────────────────┤
│    Language Layer    │    Feedback Layer                │
│  • wordfreq          │  • Rule-based (default)          │
│  • Letter freq       │  • LLM plugin (optional)         │
│  • Bigram model      │                                  │
│  • Word list filter  │                                  │
│  • Parent override   │                                  │
├──────────────────────┴──────────────────────────────────┤
│                  Config / State                         │
│  • Hardcoded language configs (40+ languages)           │
│  • language_override.yaml (edge cases)                  │
│  • custom_words.txt (parent additions/exclusions)       │
│  • SQLite: child profiles, progress, session history    │
│  • Global lesson progression rules config               │
│  • Piper model cache (per language, downloaded once)    │
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
| Cloud sync of progress | No server dependency; local SQLite is sufficient |
| Multiplayer / competitive modes | Not relevant for target audience |

---

## Open Questions

The following questions remain unresolved and require research before or during implementation:

1. **Minimum hardware spec** — `faster-whisper` with the `base` model requires ~1GB RAM and has CPU inference latency. Research needed: what is the realistic minimum spec in target schools and homes across different countries, and which Whisper model size should be the default recommendation? This affects installation documentation and potentially the choice of default model.

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
A phased implementation plan is required before any code is written. It should define:
- Milestone phases (e.g., Phase 1: core engine + single language; Phase 2: full language support; Phase 3: voice control; etc.)
- Dependencies between components (what must exist before what can be built)
- What constitutes "done" for each phase
- How the project will be structured for open source contribution from the start

**3. Resolve Open Questions**
The minimum hardware spec question should be researched before finalising the choice of default Whisper model, as this affects the installation experience for the target audience.

**4. Repository and Contribution Setup**
Before any code, the open source scaffolding should be in place:
- Repository structure documented
- Language pack contribution format documented
- Issue templates for bug reports, language pack contributions, and feature requests
