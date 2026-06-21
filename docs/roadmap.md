# Takki — Implementation Roadmap

Initial phased roadmap. Decisions in [architecture.md](architecture.md) are assumed throughout. This document covers sequencing only — it does not redecide architecture.

## Phase boundaries

### Alpha — internal/dev-only

**Goal:** prove the core-loop logic on Linux against fakes/scripted I/O, then validate the real interactive loop — human typing, human listening — on Windows. The dev box is headless (no X display, no audio device) and `pynput` is currently win32-only, so the first human-in-the-loop run is necessarily on Windows; Linux carries the logic, progression, and persistence under test.

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

Every external-interface step below is implemented as a `typing.Protocol` + real implementation + fake implementation in `tests/fakes/`, per [ADR-019](adr/0019-testing-strategy-and-io-isolation.md). The fake lands in the same commit as the real implementation and is what downstream logic consumes during unit tests. This is not a separate step — it's the structure of every step that touches I/O.

### Alpha order

1. Platform interfaces — `get_system_language()`, `get_layout_positions()` (extended from the original `get_home_row_keys()` per [ADR-023](adr/0023-key-introduction-protocol.md)), `get_fallback_tts()`. Stubs first so the rest of the codebase can call through them; real implementations land alongside the first Windows validation pass.
2. SQLite schema + persistence module (single profile, key accuracy history, session log, per-key time-since-last-practised for the spaced re-exposure mechanism in [ADR-024](adr/0024-drill-content-and-lesson-granularity.md))
3. `wordfreq` wrapper — letter frequency ranking and bigram generator. Spike code in [spikes/wordfreq_coverage_spike.py](../spikes/wordfreq_coverage_spike.py) proves the API. Layout-invariant finger map and per-language layout tables — spike code in [spikes/key_introduction_order_spike.py](../spikes/key_introduction_order_spike.py).
4. Audio out: pyttsx3 TTS wrapper + pygame.mixer sound cues (independent of `pygame.display`)
5. `pynput` keyboard input wrapper, auto-reject on wrong key
6. Lesson engine: Layer 1 drill generator (per [ADR-024](adr/0024-drill-content-and-lesson-granularity.md) — four-phase ramp-up, freq-weighted bigrams, rare-key re-exposure, child-pace-adaptive drill blocks), adaptive key introducer (per [ADR-023](adr/0023-key-introduction-protocol.md) — home-row symmetric pairs then frequency-leader-per-hand, with spoken intro script), progression thresholds, Bronze milestone detection
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

- **Alpha done:** the core-loop logic runs green on Linux against fakes/scripted I/O, and a dev can run a Bronze-level English drill session end-to-end on Windows — close the app, reopen, and see progress restored.
- **Beta done:** a friend's child can install Takki, pick a language (English or German), pick a voice, set up a profile by voice, and practise to Silver or beyond — without sighted assistance after install.
- **V1 done:** parents/teachers download the PyInstaller bundle, install without admin rights, and a VI child can run the full audio-driven setup (including visual display configuration if desired), be offered the appropriate LLM tier for their hardware, and practise across all supported languages.

---

## Open corner cases (resolve before/during the affected phase)

Surfaced in a pre-implementation design review (2026-06-07). The architecture is sound; these are the residue — corner cases, unstated mechanisms, and a few places where two accepted ADRs quietly contradict each other. Grouped by severity, each tagged with the phase it bites and the ADRs involved. None invalidate the design; several need a decision before the affected module's data model is frozen.

The recurring pattern in the high-severity items: the composite-letter / modifier-key model ([ADR-023](adr/0023-key-introduction-protocol.md)/[ADR-024](adr/0024-drill-content-and-lesson-granularity.md)) collides with the pynput character-event reality ([ADR-005](adr/0005-keyboard-handling.md)), and the key-lifecycle + accuracy-counting semantics are assumed rather than specified, which then ripples into persistence, milestones, and the pair-vs-single ramp-up.

### A. Bites Alpha specifically (the next step)

**A1. The whole Alpha loop rests on TTS pronouncing isolated letter names — and Alpha's default TTS is the weakest one.**
*Phase: Alpha. ADRs: [009](adr/0009-language-configuration.md), [012](adr/0012-audio-feedback-design.md), roadmap Alpha.*
The core loop is "TTS says the letter → child types it" ([ADR-012](adr/0012-audio-feedback-design.md)). [ADR-009](adr/0009-language-configuration.md) deleted "character spoken names" from config on the grounds that "neural TTS pronounces letter names correctly." But the roadmap makes pyttsx3/SAPI the *default* for Alpha — not neural Piper. SAPI handed a bare `"a"` may say the article /ə/, not the letter name /eɪ/; single-character SAPI output is notoriously inconsistent. If the prompt for the most fundamental loop is ambiguous, Alpha doesn't work. Needs a one-hour spike *before* writing the lesson engine: feed pyttsx3+SAPI (and espeak on Linux) the 26 isolated letters and listen. If unreliable, this re-introduces the per-language letter-name map ADR-009 thought it had eliminated — new scope not currently in the roadmap.

**A2. Bronze's "sustained across multiple sessions" is not computable from the Alpha schema, and the key lifecycle is undefined.**
*Phase: Alpha. ADRs: [010](adr/0010-lesson-structure-and-progression.md), [011](adr/0011-persistence-and-state.md).*
[ADR-010](adr/0010-lesson-structure-and-progression.md) defines a key as "known" only when accuracy is "sustained above 90% **across multiple sessions**," and Bronze = home-row keys known. But [ADR-011](adr/0011-persistence-and-state.md) ships only aggregate `key_stats` (lifetime `correct_count/attempt_count`) for Alpha and *explicitly defers* the per-session breakdown to Beta — then claims "Bronze milestone detection is computable from `correct_count / attempt_count` directly." Lifetime aggregate accuracy is **not** "sustained across multiple sessions" — the aggregate collapses exactly the per-session dimension Bronze needs. Either Bronze's definition relaxes for Alpha (e.g. "≥90% over lifetime presses"), or `session_key_stats` is pulled into Alpha.
Underneath this: **there is no defined lifecycle for a key.** "Introduced," "current," "known," "mastered" are used interchangeably across ADR-010/023/024, but Layer-2 unlock keys off "known," milestones off "mastered," and key-introduction off "accuracy on current keys." Is a key that dipped below 90% still "known"? How many sessions is "multiple"? That threshold isn't in `config.py` ([ADR-025](adr/0025-configuration-system.md)), which has the *introduce-next-key* threshold but not the *declare-known* one. Pin the state machine down before writing progression — almost everything downstream reads it.
**Resolved by [ADR-027](adr/0027-key-and-accuracy-state-model.md):** Two states only — Active (row exists in `key_stats`) and Known (derived). Known = `attempt_count ≥ 90 AND accuracy ≥ 0.90 AND distinct_practice_days ≥ 2`, evaluated over a rolling window of the last 200 attempts stored in a new Alpha table `key_attempts (profile_id, key_char, attempted_at, correct)`. "Across multiple sessions" is now grounded in calendar days (sleep is the consolidation mechanism, not app-session count). `session_key_stats` is dropped entirely — the calendar-day count comes from `key_attempts.attempted_at` timestamps with no per-session breakdown needed. ADR-010 and ADR-011 are amended.

**A3. `attempt_count` / `correct_count` don't obviously encode "first-attempt accuracy."**
*Phase: Alpha. ADRs: [010](adr/0010-lesson-structure-and-progression.md), [011](adr/0011-persistence-and-state.md), [012](adr/0012-audio-feedback-design.md).*
Every progression gate is *first-attempt* accuracy with auto-rejections counted as failures. The two integer columns can mean per-keypress *or* per-prompt, and only one yields first-attempt accuracy. Wrong-then-right on one prompt should score as one first-attempt miss — not 1/2 = 50% per-keypress. Decide and write down: `attempt_count` = number of prompts, `correct_count` = prompts correct on the first keystroke. The field names currently suggest per-keypress, which would silently corrupt the progression math.
**Resolved by [ADR-027](adr/0027-key-and-accuracy-state-model.md):** `attempt_count` = prompts shown (one per drill invocation or character position in a word); `correct_count` = prompts where the first keystroke was correct. All subsequent wrong presses after a first-keystroke failure are ignored for counting purposes. The `correct` column in `key_attempts` uses the same semantics. Timeouts do not affect either counter. ADR-027 "First-Attempt Counting Semantics" section is the canonical definition.

**A4. "Prove the core loop end-to-end on Linux" overstated what the dev box can do. — framing resolved; one open decision remains.**
*Phase: Alpha. ADRs: [019](adr/0019-testing-strategy-and-io-isolation.md), [026](adr/0026-platform-interface-abstraction.md).*
[pyproject.toml](../pyproject.toml) pins `pynput` to `sys_platform == 'win32'`, the dev box is a *headless* Linux machine (no X display, no audio device), and pyttsx3 needs espeak + an output device. So on the actual dev box there is **no real key-event source and nothing to hear**: "end-to-end on Linux" can only mean "driven by `ScriptedKeyStream` + recording fakes," and the first human-in-the-loop run is necessarily on Windows.
**Resolved:** the Alpha goal and done criteria above now state this explicitly (logic on Linux against fakes/scripted I/O; interactive validation on Windows).
**Still open:** whether to unpin `pynput` for a Linux *desktop* dev path (a contributor on a Linux laptop could then run the interactive loop locally), or commit to headless-Linux-plus-fakes with Windows as the only interactive target. Low urgency — the fakes path is sufficient for Alpha — but it determines whether a non-Windows contributor can dogfood without a Windows machine.

### B. Places where two accepted ADRs disagree

**B5. Dead keys / AltGr: ADR-005 says the app never sees them; ADR-023/024 try to teach and drill them as keys.**
*Phase: resolve before the lesson-engine data model is frozen (Alpha); bites non-English (Beta). ADRs: [005](adr/0005-keyboard-handling.md), [023](adr/0023-key-introduction-protocol.md), [024](adr/0024-drill-content-and-lesson-granularity.md), [026](adr/0026-platform-interface-abstraction.md).*
The sharpest one. [ADR-005](adr/0005-keyboard-handling.md): *"Dead keys and AltGr combinations are handled by Windows before the app sees them… the app never needs to know which physical key was pressed, only which character produced."* But [ADR-023](adr/0023-key-introduction-protocol.md) makes `altgr` and `dead-acute` **first-class physical keys with their own introduction step**, and [ADR-024](adr/0024-drill-content-and-lesson-granularity.md)'s four-phase ramp-up opens with *"the child types the new key alone, repeatedly."* You cannot type AltGr alone (no character event), and a dead key alone produces a pending compose state, not a clean per-key event pynput surfaces as a typeable unit. Concretely unhandled:
- **Phase A pure-repetition has no meaning for a modifier key.** What does "drill `dead-acute` 10 times in a row" emit?
- **Dead-key state leaks across prompts.** If the engine prompts a composite, the child presses `dead-acute`, then the engine advances or the child hesitates — Windows is still armed and will accent the *next* keypress, including the next prompt's first letter. Nothing disarms it.
- **Two-keystroke graphemes and the auto-reject/first-attempt model.** Is a wrong second keystroke one rejection? Does a half-typed `´`+wrong corrupt accounting?

ADR-023's own composite *script* ("press the accent key first, then the base letter") suggests composites are introduced as a *unit* — the sane resolution — but that contradicts the Phase-2 *sequence* that orders the modifier as a standalone step ranked by aggregate frequency, and contradicts ADR-024's per-key ramp-up. Needs an explicit reconciliation: composites introduced and drilled **only as whole graphemes**; the modifier never gets its own Phase-A/B; Windows' compose state explicitly flushed at every prompt boundary. English-only through Alpha buys time, but it must be resolved before the lesson-engine data model is frozen, because it changes what `get_layout_positions()` consumers iterate over.
**Resolved by [ADR-028](adr/0028-composite-input-and-keyboard-ownership.md):** The lesson engine processes only complete character events (KeyCode with a non-None printable char). Modifier arm events (dead-key presses, AltGr alone) are filtered at the event consumer before any lesson logic runs. Composites are drilled as whole graphemes: Phase A = whole grapheme repeated; Phase B = alternate composite with its base letter (e.g., `á ↔ a`). The modifier receives a spoken introduction at its Phase 2 step but no Phase A/B. No explicit compose-state flush is needed — stale compose events are just wrong answers, consumed by the existing auto-reject model. Pre-V1 spike required to verify suppress=True + dead-key composition on Windows before the first dead-key language is added (English and German are both direct-strike).

**B6. Milestone denominator: "alphabetic characters" (ADR-010) vs "physical keys incl. modifiers" (ADR-023).**
*Phase: decide now, bites Beta (Silver/Gold). ADRs: [010](adr/0010-lesson-structure-and-progression.md), [023](adr/0023-key-introduction-protocol.md).*
[ADR-010](adr/0010-lesson-structure-and-progression.md): Silver/Gold use "distinct **alphabetic characters** on the layout." [ADR-023](adr/0023-key-introduction-protocol.md): "thresholds count **physical keys** known, composite graphemes excluded." A modifier (`dead-acute`, `altgr`) is a physical key but not an alphabetic character — so the two rules give *different denominators* for Icelandic, Polish, French, Latvian (for Icelandic, shifts the gate by one via dead-acute). Decide whether modifier keys count toward milestone fractions and make both ADRs agree.
**Resolved by [ADR-027](adr/0027-key-and-accuracy-state-model.md):** Denominator = distinct typeable graphemes (output characters) returned by `get_layout_positions()`. Modifier keys (AltGr, dead keys) produce no character on their own and are excluded. The characters they help produce (`á`, `ð`, `ž`, etc.) are included on the same footing as any direct-strike character. ADR-010's "alphabetic characters" wording is authoritative; ADR-023's "physical keys" wording is superseded on this point.

**B7. ADR-023 introduces two keys per step; ADR-024 ramps up one key at a time; ADR-012 talks about "your next letter" (singular).**
*Phase: Alpha (lesson engine). ADRs: [012](adr/0012-audio-feedback-design.md), [023](adr/0023-key-introduction-protocol.md), [024](adr/0024-drill-content-and-lesson-granularity.md).*
[ADR-023](adr/0023-key-introduction-protocol.md) Phase 2 adds "the top-remaining left-hand letter **together with** the top-remaining right-hand letter" — a *pair* per step. [ADR-024](adr/0024-drill-content-and-lesson-granularity.md)'s ramp-up is written for "a newly-introduced key" (singular): Phase A is one key alone. Unspecified: when a step introduces L+R together, do both run Phase A simultaneously (interleaved), or A–D for one then A–D for the other? Knock-on effects:
- **The "≥8 keys" Layer-2 unlock** assumes per-key granularity, but key count now jumps in 2s (7→9, may never equal 8). Same for per-key milestone fractions.
- **ADR-012's Phase-1 encouragement** ("learn your next *letter* and you'll type X% more words," X = marginal gain of *the* next letter) is singular, but the engine commits to a pair. Is X the pair's combined gain? Does the framing survive?
- A Phase-2 step could pair a *modifier* on one hand with a *letter* on the other — colliding directly with B5's "you can't drill a modifier alone."
**Resolved by [ADR-028](adr/0028-composite-input-and-keyboard-ownership.md):** When both pair members are typeable characters, Phase A runs interleaved (L-R-L-R), threshold 10 consecutive correct each. Phase B runs four-way (L-anchor, L-new, R-anchor, R-new). When one member is a modifier, the typeable member runs Phase A/B solo; the modifier gets a spoken introduction only. The ≥ 8 Layer-2 unlock is satisfied by count 9 on English (7→9); the ≥ 8 threshold does not need changing. Encouragement framing uses the plural form ("your next two letters…") for typeable pairs. ADR-024 amended for composite and pair ramp-up semantics.

### C. Genuinely unhandled corner cases (mostly voice/Beta, but cheap to decide now)

**C8. With the visual display off (the default), who owns the keyboard?**
*Phase: Alpha (pynput wrapper). ADRs: [005](adr/0005-keyboard-handling.md), [012](adr/0012-audio-feedback-design.md), [016](adr/0016-visual-display-design.md).*
`pynput`'s listener is a *global* hook. If Takki has no focused window (display off → likely no window), every letter the child mashes also goes to **whatever app is focused** — a browser, a rename field, the desktop. The Windows key opens the Start menu and steals focus mid-lesson; a child holding keys could trigger arbitrary OS behavior. pynput can `suppress=True`, but that's all-or-nothing system-wide capture (its own risks — trapping the user). Nothing defines a **focus/ownership model** or a **keypress taxonomy**: which keys are accepted, which are "errors" (wrong char), which are "boundary" (disabled, e.g. Backspace per ADR-012), and which must be *swallowed* (Win, Tab, Alt+Tab, F-keys). Both a safety and a correctness gap, most acute in the default audio-only configuration. Worth an ADR before the pynput wrapper lands.
**Resolved by [ADR-028](adr/0028-composite-input-and-keyboard-ownership.md):** pynput started with `suppress=True`; the app owns the keyboard exclusively during lessons. Listener created once at startup, runs until exit. Keypress taxonomy: talk-key → voice subsystem; Escape → lesson controller (re-read/restart); printable char matching prompt → correct; printable char not matching → auto-reject; char=None or non-printable → discard (compose in progress); Backspace/Tab/Delete/Enter → suppress and ignore; all remaining Key.* events → suppress and ignore. Emergency keyboard exit (e.g., hold Escape) deferred to Beta — Alpha uses signal handlers + Task Manager.

**C9. The algorithmic word list will dictate profanity to a blind child before any parent can react.**
*Phase: Beta (Layer 2 / word list). ADRs: [007](adr/0007-language-data-word-frequency.md), [008](adr/0008-word-list-strategy.md).*
[ADR-008](adr/0008-word-list-strategy.md) rejects values-filtering and says contested words "tend to be longer and lower-frequency." But [ADR-007](adr/0007-language-data-word-frequency.md)'s `wordfreq` blends **Twitter and subtitle** corpora, where short, common profanity is *very* high frequency — exactly the 3–4-letter band Layer 2 starts with. The mitigation (parent `custom_words.txt` exclusions) is **reactive**: the child hears the word spoken and spelled before the parent knows to exclude it. There's a real distinction between "the app shouldn't make age-appropriateness judgments for families" (defensible) and "the app actively reads slurs/profanity aloud to a blind 7-year-old as a typing target." Reconsider a *minimal, default-on, per-language profanity blocklist* (another YAML contribution surface) as a floor, independent of the family-values exclude file. The one place the review pushes back on a decided ADR.

**C10. No decision on the microphone capture library.**
*Phase: Beta. ADRs: [002](adr/0002-speech-recognition.md), [020](adr/0020-voice-input-trigger-push-to-talk.md), [021](adr/0021-voice-activity-detection.md).*
[ADR-021](adr/0021-voice-activity-detection.md) says "recording begins at 16 kHz mono" and frames are fed to `webrtcvad`, but **nothing names what records the audio** — `sounddevice`? `pyaudio`? It's in no ADR and not in [pyproject.toml](../pyproject.toml). `webrtcvad`, `platformdirs`, and `babel` are at least named as "added when X lands"; the capture lib isn't named at all. A Beta dependency with Windows install/latency characteristics worth a small spike, same as Piper/Whisper. Don't let it fall through the gap between ADR-020 (trigger), ADR-021 (VAD), and ADR-002 (Whisper) — none owns "get bytes from the mic."

**C11. Onboarding ignores the one input device guaranteed to be present and the one it's teaching: the keyboard.**
*Phase: Beta. ADRs: [013](adr/0013-onboarding-and-profile-selection.md), [017](adr/0017-voice-command-and-intent-recognition.md).*
[ADR-013](adr/0013-onboarding-and-profile-selection.md) makes first-run entirely voice-driven, which means the hardest possible ASR task — a child speaking a **proper name** (often non-English), then *spelling it by voice* as the fallback — gates the very first experience, on the weakest speakers (children). Meanwhile the child is sitting at a keyboard. Letting the child *type* their name (and confirm/choose language by keypress) is the most reliable channel available and is curriculum-adjacent. Two related happy-path holes:
- When the Windows locale **is** found, the flow proceeds in that language and **never asks if it's right** (ADR-013 step 2). A German child on a school PC set to English locale gets English lessons with no offered switch — and there's no documented in-app language-change flow afterward (`profiles.language` is set once at creation).
- "Spell it by voice" as the name fallback needs Whisper to map spoken letter names to letters — the same unreliable single-letter recognition as A1, in reverse.

**C12. "TTS interrupt on keypress" is hard to honor with the Alpha TTS specifically.**
*Phase: Alpha. ADRs: [012](adr/0012-audio-feedback-design.md), [026](adr/0026-platform-interface-abstraction.md).*
[ADR-012](adr/0012-audio-feedback-design.md) requires immediate per-utterance TTS cancellation on keypress. With Piper you own the buffer and can stop. With **pyttsx3/SAPI** (Alpha default), `runAndWait()` is blocking and `stop()` is famously flaky — interrupting mid-utterance often doesn't work cleanly. The requirement may simply be unmet on the Alpha path. Decide whether Alpha relaxes the interrupt rule (acceptable — confident typers are rare among absolute beginners) or whether SAPI is driven in a way that supports interruption.

**C13. Layer 2 can starve: ≥8 keys does not guarantee typeable 3-letter words exist.**
*Phase: Beta. ADRs: [010](adr/0010-lesson-structure-and-progression.md).*
[ADR-010](adr/0010-lesson-structure-and-progression.md) unlocks Layer 2 at 8 keys and immediately allocates it 40% of the session. But coverage at the 8-key mark ranges from ~5% (Slovenian) upward, and the constrained 3-letter-word list at exactly the first 8 frequency-leader keys could be nearly empty in some languages. No defined behavior for "Layer 2 is due but the typeable word list is empty/tiny" (fall back to 100% Layer 1? widen length? wait?). Gate Layer 2 on **word availability**, not just key count.

### D. Smaller gaps worth a line in the relevant ADR

- **Reread and Restart are both Escape** ([ADR-025](adr/0025-configuration-system.md): tap = reread, hold/double-tap = restart). The tap/hold/double-tap disambiguation algorithm (hold threshold? double-tap window?) is unspecified, fiddly on pynput's press/release, and makes accidental word-loss (slightly-long Escape) easy for exactly the population least able to modulate key timing. Consider two distinct keys. *(Alpha)*
- **Layer-1 auto-advance timeout** ([ADR-012](adr/0012-audio-feedback-design.md): "next char follows after a correct keypress *or a configurable timeout*") — does a timeout *advance* (letters scroll past a thinking child) or *re-prompt*? And does a timed-out prompt count in `attempt_count`? Currently ambiguous; affects accuracy math. *(Alpha)*
- **Spaced re-exposure clock** ([ADR-024](adr/0024-drill-content-and-lesson-granularity.md)): the "5 minutes of **session** time" threshold conflicts with the cross-day motor-decay it's meant to fix, and at *every session start* all rare keys are stale → the first block floods with rare keys. Resolution noted in ADR-024: switch the clock anchor to `key_stats.last_practised_at` (wall-clock elapsed since last seen, cross-session) rather than within-session elapsed time. Deferred to Beta; within-session clock is acceptable for Alpha. *(Beta)*
- **Phase A vs Phase B counting** ([ADR-024](adr/0024-drill-content-and-lesson-granularity.md)): Phase A is "10 correct **in succession**" (reset on error) but Phase B is "20 correct with **no more than one rejection**" (cumulative-with-tolerance). Adjacent phases use different counting models — confirm intentional. *(Alpha)*
- **Error surfacing for blind parents** ([ADR-025](adr/0025-configuration-system.md) "unknown keys ignored with a startup **warning**"; [ADR-026](adr/0026-platform-interface-abstraction.md) DevStub "logs a warning"). In an audio-first app a blind parent never sees stderr. Define one *spoken* channel for setup/config errors vs developer logs — currently some errors are spoken (missing voice file) and some logged (bad config), inconsistently. *(Beta)*
- **Profile portability oversells** ([ADR-011](adr/0011-persistence-and-state.md)): "copy `takki.sqlite` to move a child's progress" actually moves *every* child and clobbers any profiles on the destination. Fine as whole-installation backup; not a single-profile move. Reword, or note the limitation in the parent summary. *(Beta)*
- **Sound-cue channel policy** ([ADR-012](adr/0012-audio-feedback-design.md)): a fast typist generates correct-chimes faster than they finish playing. Define pygame.mixer channel/voice-stealing policy so chimes don't pile up or drop. *(Alpha)*

### Suggested resolution path

These don't all need ADRs, but the high-severity clusters do. Candidate write-ups, once the team agrees on direction:

1. **ADR-027 "Key & accuracy state model"** ✓ *Written and accepted 2026-06-14.* — the introduced→known→mastered lifecycle, first-attempt counting semantics, rolling `key_attempts` window, and reconciling Bronze with the Alpha schema (A2, A3, B6).
2. **ADR-028 "Composite input & keyboard ownership"** ✓ *Written and accepted 2026-06-14.* — dead-key/AltGr drilling, compose-state flushing, focus/suppression, the keypress taxonomy, and the pair-vs-single ramp-up integration (B5, B7, C8).
3. The remainder (A1, A4, C9–C13, all of D) are amendments to existing ADRs or roadmap-scope notes; each is tracked above until closed.
