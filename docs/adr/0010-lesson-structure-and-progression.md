# ADR-010: Lesson Structure and Progression

**Status:** Accepted  
**Date:** 2026-05-17

> Part of the [Takki architecture](../architecture.md).

---

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

### Session Pacing and Fatigue

**Decision:** No enforced session limits, no proactive break prompts. The lesson structure provides natural stopping points, and lesson granularity is calibrated so those stopping points occur frequently enough to be useful.

Audio-primary interaction produces measurable listening fatigue in children — research on children with hearing loss (who rely heavily on auditory processing, directly analogous to VI children) finds sustained audio tasks are more cognitively taxing than visual tasks. Children do not self-regulate proactively: they disengage or become irritable rather than requesting a pause.

However, no VI typing tool reviewed (TypeAbility, Talking Typer, Typio/Accessibyte, APH products) enforces session limits or suggests breaks, and no accessibility standard requires it. The evidence-aligned practice is to design lessons with clear natural endpoints.

Takki's lesson structure already provides this: each drill set completes, each word session ends, each milestone triggers a celebration — all natural pause points. The design constraint that follows is that individual lessons must be short enough that these stopping points occur frequently. A lesson unit should be completable in a few minutes under normal performance, so a child who is tiring always has a natural exit close ahead of them rather than mid-session.

Explicit break enforcement is rejected: it is patronising for motivated children and adds complexity with no evidence of benefit over well-granulated lesson design.

### Why Lessons Are Not Authored Per Language

The lesson engine is entirely language-agnostic. The same code drives German, French, English, and Polish lessons because all content is derived from frequency data at runtime. The only language-specific inputs are:
- The filtered word list (from `wordfreq` + parent override)
- The letter frequency ranking (computed from `wordfreq`)
- The bigram/trigram model (computed from `wordfreq`, used for drill sequence generation)

This means adding a new language requires no lesson authoring — only the minimal config entry from ADR-009.
