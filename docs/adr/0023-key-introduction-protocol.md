# ADR-023: Key Introduction Protocol

**Status:** Accepted  
**Date:** 2026-05-18 (revised 2026-05-18 — see [revision history](#revision-history))

> Part of the [Takki architecture](../architecture.md).

---

**Decision:** New keys are introduced into Layer 1 of the lesson engine in two phases. Phase 1 (home row) introduces the eight to ten home-row letters as physical-position symmetric pairs (F+J, D+K, S+L, A+pinky, G+H), treating the home row as a location-anchoring exercise. Phase 2 (post-home row) uses **frequency-leader-per-hand**: at each introduction step the engine adds the top-remaining left-hand letter together with the top-remaining right-hand letter, derived from the child's language's letter frequency over the layout's available characters. Each new key is introduced with a spoken script identifying its name, the responsible finger, and its location relative to keys the child already knows. Finger assignment is layout-invariant — derived from physical column position, not character — and the character-to-finger mapping is computed by overlaying the language's keyboard layout onto a single position-keyed finger map.

**Modifier keys (AltGr, dead-key acute, dead-circumflex, dead-macron, etc.) are first-class participants in the Phase 2 sequence**, ranked alongside letter keys by aggregate composite frequency — the summed wordfreq weight of all composite graphemes that depend on the modifier as a prerequisite. Composite letters (Polish `ą` via AltGr + a, Icelandic `á` via dead-acute + a, Latvian `ā` via either) become typeable automatically once all their prerequisite physical keys are known; they do not require a separate introduction step. **When a language's standard layout supports both an AltGr-chord and a dead-key path for the same diacritic letters (Latvian LVS 24-93 is the only case in the v1 target set), the AltGr path is preferred** — see [§ Composite letters — first-class participants](#composite-letters--first-class-participants) for the empirical basis and the per-profile override flagged as an open question.

### What ADR-010 already decided, and what was missing

[ADR-010](0010-lesson-structure-and-progression.md) decided:
- Layer 1 is always active; drills are weighted by letter and bigram frequency.
- A new key is introduced when first-attempt accuracy on current keys exceeds 90% over at least 50 presses.
- Home row keys are introduced first, "one hand at a time."

What ADR-010 did not specify:
- *Which* new key is chosen at each introduction step once accuracy passes the threshold.
- How keys are paired (or not) across hands.
- What the child hears when a new key is introduced — name, finger, location.
- Where finger assignment data lives in the codebase.
- How layout-specific composite characters (dead-key acutes, AltGr letters) are treated.

This ADR fills those gaps. The drill content played *after* a key has been introduced — that is, how the new key is interleaved with previously-known keys, the bigram selection algorithm, and lesson granularity — is the subject of [ADR-024](0024-drill-content-and-lesson-granularity.md).

### Phase 1 — Home row, symmetric pairs by physical position

The home row is treated differently from the rest of the curriculum. Its purpose is **location anchoring**: establishing the resting position to which fingers return between strokes, and giving the child a fixed reference frame ("F is where my left index finger lives"). For this purpose, the symmetric-pair tradition inherited from sighted touch-typing curricula is fit for purpose: the child learns that each finger has a home position, and pairs make the structure audible ("F is for the left index, J is for the right index — they're partners").

Pairs are defined by **physical column position**, not character, so the same rule applies across every Latin-script keyboard layout. The introduction order is:

| Step | Left position | Right position | English (QWERTY) | German (QWERTZ) | Icelandic |
|------|---------------|-----------------|------------------|------------------|------------|
| 1 | L-IDX home (col 4) | R-IDX home (col 7) | F + J | F + J | F + J |
| 2 | L-MID (col 3) | R-MID (col 8) | D + K | D + K | D + K |
| 3 | L-RING (col 2) | R-RING (col 9) | S + L | S + L | S + L |
| 4 | L-PINK (col 1) | R-PINK home (col 10) | A | A + Ö | A + Æ |
| 5 | L-IDX stretch (col 5) | R-IDX stretch (col 6) | G + H | G + H | G + H |
| 6+ | Remaining row-3 letters (e.g. German Ä at col 11) introduced solo | | | | |

If a column has no letter assigned in the layout (e.g. English `;`, German `-`), the partner letter is introduced solo at that step.

### Phase 2 — Post-home row, frequency-leader-per-hand

After the home row is established, the engine departs from the symmetric-pair tradition. The reason: **QWERTY/QWERTZ geometry was not optimised for typing pedagogy.** It was determined by mechanical jam constraints on 19th-century typewriters. The symmetric-pair sequence that traditional curricula inherit from that geometry has no specific pedagogical claim beyond visual mirroring — and visual mirroring is, by definition, not available to a blind child. The motor argument for symmetric pairs reduces to "keep both hands developing in parallel," and a hand-balanced frequency-driven algorithm achieves that without dragging high-frequency letters to the end of the curriculum.

At each post-home introduction step:

1. Compute the letter-frequency ranking for the child's language over the layout's available characters (already derived from `wordfreq` per [ADR-007](0007-language-data-word-frequency.md)).
2. Filter to unknown letters.
3. Partition the filtered list into a left-hand pool and a right-hand pool via the finger map.
4. Take the top of each pool. Both are introduced at this step.
5. If only one pool has a remaining letter, introduce that letter solo and end the phase.

**Why this over single-key pure-frequency introduction.** The spike (`spikes/key_introduction_order_spike.py`, results in `spikes/results/`) compared three rules across English, German, Icelandic, and Polish:

- Coverage milestones (steps to reach 25%/50%/75% frequency-weighted vocabulary coverage) under frequency-leader-per-hand are within 0–1 step of pure single-key frequency across all four languages. The cost of hand-balancing is negligible.
- Coverage milestones under symmetric pairs lag 4–9 steps at the 75% milestone — a meaningful pedagogical cost.
- Symmetric pairs additionally produce "cliffs": in German, coverage jumps from 53.8% to 96.4% at the very last symmetric step because N is structurally delayed (right-index row-4 stretch is the last position visited). Frequency-led approaches smooth this distribution.

Frequency-leader-per-hand is therefore the sweet spot: near-pure-frequency coverage gain, with a predictable cadence and approximately balanced hand development.

### The key introduction script

When the engine introduces a new key, the child hears a short structured prompt before drill content begins. The structure is:

> *"New letter: \<name\>. Use your \<finger\>. \<Location relative to known keys\>."*

For example, on QWERTY English at the step that introduces E (left middle, top row):

> *"New letter: E. Use your left middle finger. Reach one row up from D."*

Components:

- **Name.** The letter's spoken name in the child's language. For ASCII letters, the letter-name pronunciation (e.g. English "E", German "E" pronounced /eː/). For diacritics, the language-specific pronunciation (Icelandic "æ" said /ai/, German "ä" said /ɛː/). The name uses the spoken form, not a phonetic-disambiguation form ("E as in echo") — the disambiguation form is reserved for cases where two letters are phonetically similar enough to confuse, in which case the script falls back to "E as in \<example word\>." The example words live in the per-language YAML files alongside intent definitions ([ADR-022](0022-localisation-strategy.md)).
- **Finger.** The responsible finger, spoken in everyday language ("left index", "right ring finger"). The full list of finger names per language lives in the per-language YAML.
- **Location.** A spatial description relative to a key the child already knows. The reference key is chosen as the closest already-known key on the same finger. If the new key is in row 2 (above home), the script says "one row up from \<ref\>"; if in row 4, "one row down from \<ref\>"; if it's a stretch reach (e.g. T from R), "one position to the right of \<ref\>"; etc. If no same-finger reference is available, fall back to the closest known key.

The introduction script plays only once when the key is first introduced. The drill loop that follows uses the short per-keypress prompt format from [ADR-012](0012-audio-feedback-design.md) ("E", then the child types E, then the sound cue fires). The child can re-hear the introduction script via the re-read key.

### Finger map — layout-invariant, position-keyed

Finger assignment is a property of the physical keyboard, not the layout printed on the keycaps. Every Latin-script layout (QWERTY, QWERTZ, AZERTY, Dvorak, Colemak, the various national variants) rearranges *characters* on the same physical position grid. The position-to-finger map is therefore defined once and applied to every layout.

The map is defined over the three letter rows by column, where columns are numbered left-to-right starting at 1:

| Column | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11+ |
|---|---|---|---|---|---|---|---|---|---|----|-----|
| Finger | L-pinky | L-ring | L-middle | L-index (home) | L-index (stretch) | R-index (stretch) | R-index (home) | R-middle | R-ring | R-pinky (home) | R-pinky (stretch) |

The character-to-finger function is `finger(char) = finger_map[layout_position(char)]`. The layout position comes from the keyboard layout via the existing platform interface; the finger map is a single constant module-level dictionary.

This implies a small extension to the platform interface from [ADR-005](0005-keyboard-handling.md): `get_home_row_keys()` becomes `get_layout_positions()`, returning a mapping from `(row, column)` to the character produced at that position. The home-row subset can be derived by filtering on row 3. The Windows implementation reads keyboard scan codes via the existing layout-translation path; the Linux/macOS implementations come along for free with the same data shape.

### Composite letters — first-class participants

A composite letter is one whose input is more than a single keypress on its own dedicated key: Icelandic `á` (dead-acute then `a`), Polish `ą` (AltGr held + `a`), French `ê` (dead-circumflex then `e`), Latvian `ā` (either AltGr + `a` or a dead-macron prefix). The original ADR draft deferred composites to a follow-up ADR; the v2 spike (see [§ Spike validation](#spike-validation)) measured composite-aware introduction orders across nine layouts and found the deferral unnecessary. Composites can be handled within the existing protocol with one extension to the data model.

**Data model.** A keyboard layout decomposes into:

- **Physical keys** — single keystroke units with a `(row, col)` position. Letter keys (`a`, `þ`, `é`-on-the-AZERTY-number-row), modifier keys (`altgr`, `dead-acute`, `dead-macron`), and ergonomic punctuation keys all fit here uniformly.
- **Graphemes** — letters as they appear in text, each with a `mechanism` (`direct`, `dead-key`, `altgr-chord`) and a tuple of physical-key prerequisites. A direct grapheme `a` needs only key `a`; `á` (dead-key) needs `dead-acute` and `a`; `ą` (AltGr-chord) needs `altgr` and `a`.

A grapheme is **typeable** once all its prerequisite physical keys are known. The Phase 2 sequence orders *physical keys*; composite graphemes become available implicitly when their last prerequisite is introduced.

**Modifier key placement.** A modifier's own text frequency is zero — `altgr` and `dead-acute` never appear in a word — so the per-hand frequency ranking would never select them. The extension: a modifier key's effective score is the **sum of wordfreq weights of all composite graphemes that include it as a prerequisite**. This makes Polish `altgr` (which participates in ą/ć/ę/ł/ń/ó/ś/ź/ż) rank high enough to enter the sequence around step 12–15 in the spike, alongside the high-frequency letter keys. Icelandic `dead-acute` (participates in á/é/í/ó/ú/ý) lands at step 18. Both placements coincide with what reading-instruction practice in transparent orthographies would put as the threshold for "now the child can read whole pages of native text" — coincidence in the right direction.

**The introduction script for composites.** A composite is *not* introduced at its own step; it is introduced **implicitly** when the modifier and the base letter are both known. The first time the child's drill content surfaces a composite, the script extends the per-keypress prompt from [ADR-012](0012-audio-feedback-design.md):

> *"New letter: `<composite name>`. Press `<modifier description>` and `<base letter>` together."* (AltGr-chord case)

> *"New letter: `<composite name>`. Press `<dead-key description>` first, then `<base letter>`."* (dead-key case)

The modifier description uses friendly language from the per-language YAML — "the right Alt key" or "the right of-the-space-bar key" for AltGr, "the accent key" for dead-acute. The first time the child encounters any composite of a given mechanism class, the script also explains the mechanism briefly: *"The accent key doesn't make a sound on its own — it adds an accent to the next letter you press."* Subsequent composites of the same mechanism class skip the explanation.

**Latvian dual-mechanism resolution.** Latvian LVS 24-93 uniquely supports both paths for the same letters — `ā` can be typed as AltGr+a or as dead-macron then a, user's choice. The v2 spike modelled both as independent layout variants and ran all algorithms on each:

| Milestone | AltGr path | Dead-key path | Δ (cost of dead-key) |
|---|---|---|---|
| 50% per-grapheme | 18 | 19 | +1 step |
| 75% per-grapheme | 21 | 22 | +1 step |
| 90% per-grapheme | 22 | 24 | +2 steps |
| 90% per-keystroke | 22 | 25 | +3 steps |
| Total physical keys to teach | 23 | 25 | +2 modifier keys (3 dead-keys vs 1 AltGr) |

The AltGr path wins on every metric. The per-keystroke gap widens beyond the per-grapheme gap because the dead-key composite costs two keystrokes per grapheme while the AltGr chord costs one — once the child reaches running-text fluency, the dead-key path adds roughly 12% to the keystroke count of a typical word containing one accented vowel. **Decision: when a language's standard layout supports both paths for the same diacritic letters, the AltGr path is preferred.**

A per-profile override is flagged as an open question — a Latvian-speaking adult who already touch-types via dead-keys may prefer to keep the existing motor pattern when learning to type with a screen reader. Defaulting to AltGr for the v1 child-learner case is the simpler position and matches the empirical winner.

**Shift composites — still deferred.** Uppercase remains out of scope for v1 per [ADR-005](0005-keyboard-handling.md). Capitalisation is a separate skill, addressed after the base alphabet (including composite letters) is mastered. This is unchanged from the original ADR draft.

**Milestone denominators.** Bronze/Silver/Gold thresholds count physical keys known, with composite graphemes excluded from the denominator. A child who has introduced 14 of 24 Icelandic physical keys (= 14/24 = 58%) is the same Silver percentage regardless of how many composite graphemes have become typeable in passing. This keeps the milestone metric a measure of *motor progress* rather than *vocabulary unlock*, which would otherwise inflate Silver scores in composite-heavy languages and incentivise the engine to push modifier keys early to game the metric.

### Spike validation

The introduction order for each algorithm, the resulting frequency-weighted coverage curve, and per-finger usage distribution were computed empirically. See `spikes/key_introduction_order_spike.py` (script) and `spikes/results/key_introduction_order_spike_results.txt` (results). The v2 spike covers **nine layouts** — English, German, Finnish, Icelandic, French (AZERTY), Spanish, Czech (QWERTZ), Polish (programmer's), and Latvian (LVS 24-93, both paths) — and **five algorithms**:

| Code | Algorithm | Scoring | Hand balance |
|---|---|---|---|
| A | Symmetric pairs | physical position, then aggregate frequency | symmetric |
| B | Pure frequency | aggregate frequency | none |
| C | Freq-leader-per-hand | aggregate frequency | one pick per hand |
| D | Coverage-greedy | marginal coverage gain | none |
| E | Coverage-per-hand | marginal coverage gain | one pick per hand |

Key findings:

- **C remains the chosen algorithm.** Across all nine layouts, C reaches every coverage milestone (10%, 25%, 50%, 75%, 90%) within 0–1 step of pure single-key frequency (B), confirming the original ADR's headline finding.
- **The traditional symmetric-pair sequence (A) lags 4–9 steps at 75% coverage** in the same four languages originally measured (English, German, Icelandic, Polish), and the same gap persists in the five new languages.
- **Coverage-greedy (D) reaches milestones 1–3 steps earlier than C** on most languages, which initially looked like a reason to revisit the algorithm choice. Algorithm E was added to test the hypothesis that D's advantage was the relaxed hand-balance constraint, not the dynamic scoring. **E ties C in 18 of 20 measured milestone cells** across nine layouts; the two remaining cells differ by a single step. This proves D's apparent advantage was hand imbalance, paid for in asymmetric motor development, not in any genuine intelligence of the scoring signal. **C's parallel hand development is therefore not bought at a coverage cost — it is free.**
- **Modifier keys enter the sequence at sensible positions** when scored by aggregate composite frequency. Polish `altgr` lands at step 12–13 (B/C) — between `e` and `i` in the per-hand sequence — which is where its share of running Polish text would put it. Icelandic `dead-acute` lands at step 18 (B/C). French `dead-circumflex` lands later because circumflexed vowels are individually less frequent than the pre-composed `é`/`è`/`ç`/`à`. No anomalous placements were observed across the nine layouts.
- **Latvian dual-path comparison favours AltGr** on every metric (see the table in [§ Composite letters](#composite-letters--first-class-participants)).
- **No algorithm produced a "+2 new keys to the same finger in a single step" outcome** on any of the nine languages, so the same-finger-consecutive-introduction guard mentioned during design discussion is not required at v1; it can be added later as a tiebreaker if a future language surfaces the problem. The Latvian dead-key variant comes closest because three different dead-key modifiers (macron, caron, cedilla) all land on the right pinky stretch — but they introduce on separate steps, never two in one round.

### Alternatives considered

**Coverage-greedy (algorithm D)** picks the unknown key that yields the largest marginal increase in frequency-weighted typeable words at each step, ignoring hand balance. It reaches coverage milestones 1–3 steps earlier than C on most languages and was therefore a serious candidate during the v2 spike. The hand-balanced variant (algorithm E) was added to test whether the gain was the scoring criterion or the relaxed balance constraint; E ties C in 18 of 20 measured milestone cells, demonstrating the gain was entirely the hand-imbalance. Future contributors revisiting the algorithm choice should consult this finding before re-running the comparison — the spike script retains all five algorithms and will regenerate the same result on the same wordfreq corpus. The hand-balance argument is therefore not a soft preference but a measured property of the trade-off.

### Open questions and future work

Each of these is genuinely undecided. None of them block implementation of the protocol described above; they are flagged so future contributors do not assume the matter is settled.

1. **Per-profile mechanism override for dual-mechanism languages.** Latvian (and any future language with a similarly dual-path standard layout) defaults to the AltGr path per [§ Composite letters](#composite-letters--first-class-participants). A user who already touch-types via dead-keys may want to keep that motor pattern. Whether to expose this as a per-profile setting, hardcode AltGr, or detect the user's existing preference from system layout configuration is undecided.
2. **Same-finger consecutive new-key guard.** Not required on the nine spiked languages, but if a future language puts two high-frequency keys on the same finger such that they end up adjacent in the introduction order, a "skip one step if the same finger received a new key in the previous step, unless skipping would empty that hand's pool" guard may be worth adding. The Latvian dead-key path comes closest by piling three dead-key modifiers on the right-pinky stretch, but they introduce on separate steps in all algorithms.
3. **Phonetic-disambiguation examples per language.** The fallback "E as in echo" form requires example words in each language's YAML. The example words must use only characters that the child has already learned at the moment the disambiguation is needed — which is a chicken-and-egg constraint that needs to be handled at the YAML-authoring stage.
4. **Finger naming conventions.** "Left index" works in English; some languages may prefer a different convention (numbered fingers, named fingers, or simply "the finger you use for F" — relative naming). The per-language YAML should not force a single convention.
5. **Modifier description in the per-language YAML.** The composite-introduction script needs a friendly name for each modifier in each language ("the right Alt key", "the accent key", etc.). These names live alongside finger names and example words in the per-language YAML. Drafting them is a per-language native-speaker task, parallel to the example-word work in question 3.

### Revision history

- **2026-05-18 (initial draft).** Original ADR proposing two-phase introduction with home-row symmetric anchor and post-home frequency-leader-per-hand. Composite letters explicitly deferred to a follow-up ADR.
- **2026-05-18 (revision 2).** Composite letters lifted from deferred to in-scope: modifier keys enter Phase 2 as first-class members ranked by aggregate composite frequency; composite graphemes become typeable implicitly when prerequisites are known. Latvian dual-mechanism case added with empirical comparison favouring the AltGr path. Spike validation section expanded to nine layouts and five algorithms; algorithm E added to demonstrate that coverage-greedy's apparent edge over C was hand imbalance rather than smarter scoring. Open questions list updated to remove the resolved composite-letter item and add the per-profile-override and modifier-description items.
