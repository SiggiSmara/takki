# Takki
## Typing Tutor for Visually Impaired Children

> **Status:** Implementation in progress  
> **Scope:** Open source hobby project, Windows desktop only  
> **Target users:** Visually impaired children, their parents, and teachers  
> **Repository:** github.com/SiggiSmara/takki  
>
> *Takki (Icelandic): a key or mechanical button.  Implies the sound of a button being pressed.*

---

## Project Context

This project fills a gap in the accessibility software landscape: a free, open source, multilingual touch typing tutor designed specifically for visually impaired children.

### Educational Grounding

Touch typing for children with vision impairment is named as a required skill in the two largest English-language VI education frameworks:

- **UK — Curriculum Framework for Children and Young People with Vision Impairment (CFVI, 2022)**, jointly developed by VICTAR (University of Birmingham), RNIB, VIEW, and the Thomas Pocklington Trust. Touch typing appears in two of the eleven teaching areas: *Area 4 — Communication* (under "Writing and use of appropriate technology") and *Area 8 — Technology* ("Touch typing, including keyboard shortcuts, navigation skills, scrolling, searching, tabbing through documents"). The CFVI is being pushed toward statutory status in the UK.
- **USA — Expanded Core Curriculum (ECC)** (originated 1996, maintained by APH, AFB, Perkins, and state schools for the blind). Keyboarding is explicitly named as a priority within the *Assistive Technology* area. The ECC literature states VI students "need to start learning skills such as keyboarding **well before their peers** in order to be proficient in these areas."

Both frameworks specify outcomes, not pedagogy. Takki's adaptive lesson engine is a pedagogical mechanism for skills that the field has already named as required.

**Empirical motivation.** Douglas & Long (2003), *An observation of adults with visual impairments carrying out copy-typing tasks* (Behaviour & Information Technology, 22(3): 141–153), observed ten VI adults during copy-typing and reported poor touch-typing across the cohort, rare use of keyboard shortcuts, no adjustment of equipment or copy material, and inefficient working habits. Two decades on, this skill gap is still being reported in the field. The training pipeline that produced those adults — by their own institution's later analysis — was not effective. The earlier *Touch Typing Tutor* (Douglas & Gamble, 1990s/2000, distributed via the University of Birmingham as Windows freeware, no formal efficacy study, download link now broken) was the most direct predecessor in spirit; it is effectively orphaned and unmaintained. Takki is an attempt to do this work again with modern tooling, an open development model, and a curriculum mandate to point at.

### Design Principles

- **Fully offline.** The app works completely without internet access after installation. Nothing about a child's voice, typing, or progress is ever sent anywhere. Some optional components (Piper voice models, optional local LLM models) are downloaded once at setup; after that, the app never needs network access.
- **Zero elevated privileges.** Installation and operation must not require administrator rights. This is a hard constraint for school deployment.
- **Minimal setup friction.** The fewer decisions required of a parent or teacher at setup, the better. The ideal is: install, hand to child, done.
- **Audio is the primary interface.** All interaction — instructions, feedback, navigation — must work without any visual reference.
- **Useful early, not perfect late.** Takki's lesson engine prioritises early real-word typing (Layer 2 unlocks at 8 keys) over completing a textbook touch-typing curriculum before any practical output. The piano analogy is deliberate: a child who has learned a handful of chords on a piano can play songs from day one, while a child still working through scales cannot. The same logic applies to typing — early utility motivates continued practice, and full alphabet mastery still arrives in time. This principle is provisional pending empirical evidence to the contrary, but no current evidence contradicts it for the audio-first VI case.
- **Open source contribution friendly.** Architecture should make it easy for teachers, linguists, and developers to contribute word lists and lesson content without deep Python knowledge.
- **Start focused, don't block the future.** Build for Windows first, but architect for everywhere. Avoid Windows-specific patterns where a cross-platform alternative costs nothing extra. Platform-specific code lives behind clean interfaces so future contributors can add macOS or Linux support without unpicking assumptions throughout the codebase.

### Platform Constraints (Fixed)

- Windows only (no macOS, no Linux, no tablets, no phones) — **for v1**
- Physical keyboard required (no touchscreen input)
- No IME-based languages (see [ADR-006](adr/0006-language-and-keyboard-layout-scope.md))

### Cross-Platform Readiness

The v1 target is Windows, but the architecture is intentionally portable. Almost the entire chosen stack — `faster-whisper`, Piper TTS, `pynput`, `wordfreq`, SQLite, `pygame`, PyInstaller — runs on Windows, macOS, and Linux without modification.

The three areas that are genuinely Windows-specific are isolated behind clean interfaces from the start:

| Interface | Windows | macOS (future) | Linux (future) |
|---|---|---|---|
| `get_system_language()` | Windows NLS locale API | `NSLocale` | `$LANG` / `locale` |
| `get_layout_positions()` | `MapVirtualKeyW` / `VkKeyScanExW` | Carbon / IOKit | xkb |
| `get_fallback_tts()` | pyttsx3 → SAPI | pyttsx3 → nsss | pyttsx3 → espeak |

A `select_platform_interface()` factory maps `sys.platform` to the right implementation; new platforms slot in there without touching any other code. See [ADR-026](adr/0026-platform-interface-abstraction.md).

---

## Architecture Decision Records

Individual decisions are recorded in `docs/adr/`. Each ADR is self-contained and links back here.

| ADR | Title | Summary |
|---|---|---|
| [ADR-001](adr/0001-runtime-and-distribution.md) | Runtime and Distribution | Python 3.11+, PyInstaller standalone bundle |
| [ADR-002](adr/0002-speech-recognition.md) | Speech Recognition | `faster-whisper` local Whisper; `tiny`+`base` bundled, auto-selected by CPU benchmark |
| [ADR-003](adr/0003-text-to-speech.md) | Text-to-Speech | Piper TTS default; pyttsx3/SAPI fallback |
| [ADR-004](adr/0004-llm-integration.md) | LLM Integration | Local only, optional, hardware-adaptive tiers 0–3; intent fallback only |
| [ADR-005](adr/0005-keyboard-handling.md) | Keyboard Handling | `pynput`; rely on Windows layout translation; no custom layout files |
| [ADR-006](adr/0006-language-and-keyboard-layout-scope.md) | Language and Keyboard Layout Scope | Latin-script, direct-input only; IME languages excluded |
| [ADR-007](adr/0007-language-data-word-frequency.md) | Language Data — Word Frequency | `wordfreq` for word/letter/bigram frequency; derived at startup |
| [ADR-008](adr/0008-word-list-strategy.md) | Word List Strategy | Algorithmic default from `wordfreq`; parent override file; no LLM filtering |
| [ADR-009](adr/0009-language-configuration.md) | Language Configuration | Hardcoded minimal config for ~40 languages; override YAML for edge cases |
| [ADR-010](adr/0010-lesson-structure-and-progression.md) | Lesson Structure and Progression | Two-layer engine (drills + real words); milestone levels; no session limits |
| [ADR-011](adr/0011-persistence-and-state.md) | Persistence and State | SQLite via built-in `sqlite3`; local only, no server |
| [ADR-012](adr/0012-audio-feedback-design.md) | Audio Feedback Design | Sound cues for immediate feedback; TTS for spoken content; auto-reject wrong keys |
| [ADR-013](adr/0013-onboarding-and-profile-selection.md) | Onboarding and Profile Selection | Auto-detect language from Windows locale; spoken profile selection |
| [ADR-014](adr/0014-progress-reporting.md) | Progress Reporting | Spoken child summary + plain text parent/teacher report |
| [ADR-015](adr/0015-piper-voice-model-distribution.md) | Piper Voice Model Distribution | English always bundled; additional voices via browser download links |
| [ADR-016](adr/0016-visual-display-design.md) | Visual Display Design | Optional, off by default; observer invariant; two-line layout |
| [ADR-017](adr/0017-voice-command-and-intent-recognition.md) | Voice Command and Intent Recognition | Layered pipeline: keyword → phonetic → fuzzy → LLM fallback |
| [ADR-018](adr/0018-hardware-adaptive-llm-tiering.md) | Hardware-Adaptive LLM Tiering | Auto-detect at setup; Whisper model also auto-selected by CPU benchmark |
| [ADR-019](adr/0019-testing-strategy-and-io-isolation.md) | Testing Strategy and I/O Isolation | `typing.Protocol` for all external I/O; fakes in `tests/fakes/`; tiered CI |
| [ADR-020](adr/0020-voice-input-trigger-push-to-talk.md) | Voice Input Trigger — Push-to-Talk | Right Ctrl default; chirp-on/chirp-off cues; no wake word |
| [ADR-021](adr/0021-voice-activity-detection.md) | Voice Activity Detection | `webrtcvad` for end-of-utterance; start signalled by talk key |
| [ADR-022](adr/0022-localisation-strategy.md) | Localisation Strategy | YAML per language for strings, encouragement, intents, voice catalog |
| [ADR-023](adr/0023-key-introduction-protocol.md) | Key Introduction Protocol | Home-row symmetric pairs as location anchor; post-home freq-leader-per-hand; modifier keys (AltGr, dead-acute) ranked by aggregate composite frequency; AltGr preferred over dead-key for dual-mechanism layouts (Latvian); spoken intro script with finger + relative location |
| [ADR-024](adr/0024-drill-content-and-lesson-granularity.md) | Drill Content and Lesson Granularity | Four-phase new-key ramp-up; freq-weighted bigrams; SFBs not avoided; spaced re-exposure for rare keys; child-pace-adaptive ~100s drill blocks |
| [ADR-025](adr/0025-configuration-system.md) | Configuration System | Three-tier config: `config.py` defaults → `takki_config.yaml` (parent) → per-profile SQLite; sound cues overridable; Alpha tones generated in pure Python |
| [ADR-026](adr/0026-platform-interface-abstraction.md) | Platform Interface Abstraction | `PlatformInterface` Protocol with three methods; `select_platform_interface()` factory; `DevStubInterface` fallback for non-Windows dev |

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
│    pipeline          │  • Word selector                 │
│  • Optional LLM      │                                  │
│    fallback          │                                  │
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
│  • Hardware capability profile (LLM tier)               │
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
| Narrative / quest framing | Evaluated as an audio-native engagement mechanism well-suited to visually impaired children. Deferred to v2 to avoid content maintenance burden and the requirement to author story content in 40+ languages. The LLM plugin path ([ADR-004](adr/0004-llm-integration.md)) is the intended community contribution entry point for this feature. |
| Cloud sync of progress | No server dependency; local SQLite is sufficient |
| Multiplayer / competitive modes | Not relevant for target audience |
| Cloud/online LLM integration | Explicitly rejected. See [ADR-004](adr/0004-llm-integration.md). Users who want this can fork the project. |
| Fine-tuned Takki-specific intent model | Deferred. Generic instruction-tuned models are sufficient at this stage. See [ADR-004](adr/0004-llm-integration.md). |

---

## Pre-Implementation Open Questions

All three pre-implementation questions are resolved:

1. ~~**Minimum hardware spec**~~ — **resolved.** Minimum viable spec is AVX2 with CPU microbenchmark under ~10ms (512×512 float32 matmul). Both `tiny` and `base` bundled in installer, auto-selected by matmul threshold (~2ms). See [ADR-002](adr/0002-speech-recognition.md) and [ADR-018](adr/0018-hardware-adaptive-llm-tiering.md).

2. ~~**Session pacing and fatigue**~~ — **resolved.** No enforced limits or break prompts. Natural lesson endpoints are the evidence-aligned mechanism. The design constraint is lesson granularity: individual lesson units must be short enough that a natural stopping point is always close. See [ADR-010](adr/0010-lesson-structure-and-progression.md).

3. ~~**Piper voice download reliability**~~ — **resolved.** English voice always bundled; additional voices distributed as direct download links from the project website (browser → save to `Documents\Takki\voices\`). No in-app download logic. See [ADR-015](adr/0015-piper-voice-model-distribution.md).

---

## Implementation Roadmap

See [roadmap.md](roadmap.md) for the agreed phased plan (Alpha, Beta, V1), dependency-ordered task lists, and done criteria.

New ADRs during implementation: add a file to `docs/adr/` and a row to the table above.
