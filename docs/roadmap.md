# Takki — Implementation Roadmap

Initial phased roadmap. Decisions in [architecture.md](architecture.md) are assumed throughout. This document covers sequencing only — it does not redecide architecture.

## Phase boundaries

### Alpha — internal/dev-only

**Goal:** prove the core loop end-to-end on Linux, then validate on Windows.

A single child sits down, hears a letter in English, types it, hears immediate feedback, completes a Layer 1 drill session, and progress persists across runs.

**In scope:**
- Platform interfaces (Linux stubs + Windows implementations)
- SQLite persistence for a single profile
- `wordfreq`-derived letter and bigram frequencies (English)
- pyttsx3 / SAPI TTS (fallback path used as default for Alpha)
- pygame.mixer sound cues
- `pynput` keyboard capture
- Layer 1 drill generator with adaptive key introduction
- Bronze milestone detection
- Contributor scaffolding: issue and PR templates, language pack contribution template (pulled forward from V1 — they pay off as soon as the first contributor appears)

**Out of scope:**
- Voice control, Whisper, intent pipeline
- Piper TTS (download/catalog adds infra weight before the loop is proven)
- Layer 2 real words
- Visual display
- Multi-profile, multi-language
- LLM, hardware detection
- Milestones beyond Bronze
- PyInstaller packaging

**Rationale for cuts:** pyttsx3 + espeak gives a working voice instantly on both Linux dev and Windows target, with no model downloads. Layer 2 adds a second loop before the first one is proven correct. Voice control and Piper are large pieces of infrastructure that don't change whether the core drill loop works.

---

### Beta — friends/family pilot

**Goal:** a real VI child can use Takki for actual typing practice.

**In scope (additions on top of Alpha):**
- Piper TTS wrapper + voice catalog + first-run model download → becomes default TTS
- Layer 2 real-word selector + key-set-constrained word-list filter
- Layer controller with weighted mix per ADR-010
- Milestones: Silver, Gold, Platinum, Diamond (key-count based)
- Two-phase encouragement messaging (coverage framing → countdown framing)
- `faster-whisper` wrapper
- Intent pipeline Layers 1–3 (exact, phonetic, fuzzy) + per-language YAML loader + context-aware active intent sets
- Onboarding: locale detection → language selection → profile selection (multi-profile, voice-driven)
- Parent override file (`custom_words.txt`) and `language_override.yaml`
- Basic progress reporting (child summary spoken, parent text file)
- Second language pack: **German** — pressure-tests language-agnostic claims (QWERTZ, ä/ö/ü/ß, German intent YAML)
- Bundled sound asset set: correct-keypress chime, error tone, boundary tone for disabled keys. Source from CC0 libraries (Freesound.org) or commission/generate. License and attribution captured in `assets/AUDIO_LICENSES.md`.
- Decide and enable a community channel (likely GitHub Discussions) before pilot invitations go out
- Begin VI community outreach for pilot recruitment — RNIB (UK), AFB (US), Perkins, local schools for the blind. Goal: 3–5 participating families by end of Beta.

**Out of scope:**
- Visual display
- LLM tier and Layer 4 intent fallback
- Hardware detection
- PyInstaller bundle
- Milestone audio celebrations polish (placeholder cues acceptable for Beta)
- Per-key accuracy breakdown / WPM trend in parent summary

**Rationale for cuts:** Visual display is opt-in per profile and does not block a VI child from practising. LLM is strictly a tertiary fallback in the intent pipeline — the rule-based pipeline must be proven sufficient first. Hardware detection only matters once the LLM tier exists.

---

### V1 — public release

**Goal:** ship-ready for parents and teachers downloading from GitHub.

**In scope (additions on top of Beta):**
- Native alphabet derivation from keyboard layout (replaces the statistical approximation used in the wordfreq spike)
- Visual display: two-line layout for both lesson layers
- Visual setup workflow with audio-driven color palette selection
- Hardware capability detection (ADR-018)
- LLM tier offer flow + `llama-cpp-python` integration + per-tier model download
- Intent pipeline Layer 4 (LLM fallback)
- Milestone audio celebrations
- Expanded parent/teacher printable summary (per-key accuracy, WPM trend, session history, milestone dates)
- Validation pass over remaining ~40 language configs
- PyInstaller Windows bundle + install testing
- Code signing for the Windows `.exe` (or distribution path that avoids SmartScreen warnings — winget / Microsoft Store). Budget item if using a cert (~$200–500/yr).
- Milestone audio celebrations (final assets, replacing placeholder cues from Beta)
- Language pack contribution documentation (template was already in place from Alpha)

---

## Order within each phase

Within each phase, work proceeds by dependency depth: foundation → glue → user-facing.

Every external-interface step below is implemented as a `typing.Protocol` + real implementation + fake implementation in `tests/fakes/`, per [ADR-019](architecture.md#adr-019-testing-strategy-and-io-isolation). The fake lands in the same commit as the real implementation and is what downstream logic consumes during unit tests. This is not a separate step — it's the structure of every step that touches I/O.

### Alpha order

1. Platform interfaces — `get_system_language()`, `get_home_row_keys()`, `get_fallback_tts()`. Stubs first so the rest of the codebase can call through them; real implementations land alongside the first Windows validation pass.
2. SQLite schema + persistence module (single profile, key accuracy history, session log)
3. `wordfreq` wrapper — letter frequency ranking and bigram generator. Spike code in [spikes/wordfreq_coverage_spike.py](../spikes/wordfreq_coverage_spike.py) proves the API.
4. Audio out: pyttsx3 TTS wrapper + pygame.mixer sound cues (independent of `pygame.display`)
5. `pynput` keyboard input wrapper, auto-reject on wrong key
6. Lesson engine: Layer 1 drill generator, adaptive key introducer, progression thresholds, Bronze milestone detection
7. Session loop glue, runnable end-to-end

### Beta order

1. Piper TTS wrapper + voice catalog (`voice_catalog.yaml`) + download flow → swap as default TTS
2. Layer 2 word selector + key-set-constrained word-list filter (loanwords excluded)
3. Layer controller — weighted mix between Layer 1 and Layer 2 per ADR-010 table
4. Milestones Silver/Gold/Platinum/Diamond (key-count gates)
5. Two-phase encouragement messaging
6. `faster-whisper` wrapper
7. Intent pipeline Layers 1–3 + intent YAML loader + context-aware active intent sets per interaction mode
8. Onboarding: locale detection → language fallback rotation → profile selection (multi-profile)
9. Parent override (`custom_words.txt`) + `language_override.yaml`
10. Basic progress summary (child spoken + parent text file)
11. German language pack: intent YAML, voice catalog entry, exclude list, end-to-end test

### V1 order

1. Native alphabet from keyboard layout (replaces wordfreq statistical approximation; updates ADR-007 implementation note)
2. Visual display module: two-line layout for Layer 1 and Layer 2
3. Visual setup workflow + color palette voice selection (background-first, foreground-second with live preview)
4. Hardware detection (RAM, CPU microbenchmark, GPU presence, disk space)
5. LLM tier offer + `llama-cpp-python` integration + per-tier model download
6. Intent pipeline Layer 4 (LLM fallback, skipped on Tier 0)
7. Milestone audio celebrations + general polish pass
8. Parent/teacher summary expansion (per-key accuracy, WPM trend)
9. Validation pass: remaining language configs (`LANGUAGE_CONFIGS` dictionary)
10. PyInstaller Windows build + install testing on target hardware
11. Contributor scaffolding: language pack contribution docs, GitHub issue templates

---

## What "done" looks like per phase

- **Alpha done:** dev can run a Bronze-level English drill session end-to-end on Windows, close the app, reopen, and see progress restored.
- **Beta done:** a friend's child can install Takki, pick a language (English or German), pick a voice, set up a profile by voice, and practise to Silver or beyond — without sighted assistance after install.
- **V1 done:** parents/teachers download the PyInstaller bundle, install without admin rights, and a VI child can run the full audio-driven setup (including visual display configuration if desired), be offered the appropriate LLM tier for their hardware, and practise across all supported languages.
