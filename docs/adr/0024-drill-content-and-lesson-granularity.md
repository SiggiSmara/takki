# ADR-024: Drill Content and Lesson Granularity

**Status:** Accepted  
**Date:** 2026-05-18

> Part of the [Takki architecture](../architecture.md).

---

**Decision:** When a new key is introduced (per [ADR-023](0023-key-introduction-protocol.md)), Layer 1 drill content for that key passes through four phases: pure repetition, alternation with a same-finger anchor key, short bigrams mixing the new key with 2–3 previously-known keys, and full frequency-weighted bigram drill. Steady-state drill content for the unlocked key set is bigram-frequency-weighted with no comfort-class adjustment — same-finger bigrams are practised, not avoided. Rare keys are kept fresh via a soft spaced re-exposure mechanism: at each drill block, the least-recently-practised key is given at least one appearance if its time-since-last-use exceeds a threshold. Lesson granularity is set by target wall-clock duration (~90–120 seconds per drill block), with keystroke count derived from the child's rolling pace; drill blocks always end on bigram or word boundaries.

### What ADR-010 already decided, and what was missing

[ADR-010](0010-lesson-structure-and-progression.md) decided that Layer 1 drill content is "weighted by letter and bigram frequency" and that lesson granularity should be calibrated so natural stopping points always sit close ahead of a tiring child. It did not specify:
- What drill content looks like *immediately after* a new key is introduced — the ramp-up from one new key to "this key is now part of the deck."
- Whether any bigram class (same-finger, awkward stretches) is biased against during selection.
- How the engine prevents rare keys (Z, Q, X in English; ð, þ in Icelandic; etc.) from being forgotten once frequency-weighted selection mostly stops surfacing them.
- What a "drill block" actually is, in concrete terms — how long, how many keystrokes, where it ends.

This ADR fills those gaps. The order in which new keys are introduced is the subject of [ADR-023](0023-key-introduction-protocol.md) and [ADR-032](0032-grapheme-led-introduction-and-selectable-ordering.md) — the protocol machinery in the former, the ordering and the grapheme-led rule in the latter. *(Pointer split 2026-08-23.)* Note that what arrives here is a **grapheme**, which for a composite letter is two keystrokes: the phases below drill the letter, not the keys.

### New-key ramp-up — four phases

A newly-introduced key is not immediately dropped into the frequency-weighted bigram pool. Bigram selection that included a brand-new key would force the child to practise that key in combination with several known keys at once, which loses the isolation needed to build the new motor pattern. Instead, drill content for that key passes through four phases:

**Phase A — pure repetition.** The child types the new key alone, repeatedly. The TTS prompts the letter, the child types it, the correct-keypress chime fires, the next prompt follows. Default threshold for advancing: 10 first-attempt-correct keypresses in succession. The threshold is configurable in the global lesson progression rules config (not per-language).

**Phase B — alternation with a same-finger anchor.** The child alternates the new key with a same-finger neighbour from the home row. For example, when E is introduced on QWERTY English (L-middle, row 2), alternation is with D (L-middle, row 3): D-E-D-E-D-E. This trains the finger to move between the two positions while the rest of the hand stays anchored. If the new key has no same-finger anchor that is already known (rare, but possible at very early steps in the curriculum), use the nearest known key on the same hand. Default threshold for advancing: 20 first-attempt-correct keypresses with no more than one rejection.

**Phase C — short bigrams with known keys.** The new key is mixed into 2-letter and 3-letter sequences with 2–3 of the most-frequent previously-known keys, chosen for actual bigram frequency in the language. For E in English, this would mean bigrams like "he", "be", "we", "the", "ed". The child now experiences the new key in natural contexts but still in a constrained mix. Default threshold for advancing: 30 keypresses at ≥ 85% first-attempt-correct. *(Implementation, 2026-08-23, alpha session 9: the partner count and how often a sampled bigram is grown into a 3-letter sequence are two configurable numbers in the same tier as the thresholds — `PHASE_C_PARTNERS`, `PHASE_C_TRIGRAM_CHANCE`. A sequence is grown in either direction, so "the" can come out of "he"; appending alone would only ever reach "het". A new letter whose corpus has no bigram pairing it with any of its partners — a rare letter early in a curriculum — alternates with the most frequent partner instead, rather than skipping the phase.)*

**Phase D — full frequency-weighted mix.** The new key joins the steady-state pool. Bigram selection over the full known-key set, frequency-weighted, with no special treatment.

Phase thresholds are starting points. They are all configurable in the same global config that holds the ADR-010 thresholds. Empirical tuning during Alpha and Beta is expected. The phase boundaries themselves are *not* configurable — the four-phase structure is the design.

**Where the ramp-up phase lives, and what it costs** *(added 2026-08-23, alpha session 9.)* The phase is **session-local**, held by the drill generator for the life of one session and nowhere else — the same shape, and for the same reason, as the introducer's own record ([ADR-023](0023-key-introduction-protocol.md) § What the introducer remembers). It is not derived from the rolling window: Phase A counts a *streak* and Phase B a run with an error budget, and [ADR-011](0011-persistence-and-state.md)'s `key_attempts` is queried as aggregate counts, so deriving either would need a second definition of the same bar — the trap ADR-023 names — or a schema this ADR is not entitled to add.

The consequence is stated rather than hidden: **a child who closes the app halfway through Phase B loses the ramp-up.** The letter is Active, so next session the introducer does not re-introduce it, the generator has no ramp-up record for it, and it is drilled as an ordinary member of the steady-state pool — ADR-024's Phase D. What is lost is the remainder of the isolation, not the letter or its counters. The alternative costs a `key_stats` column carrying a state whose entire purpose is the first few minutes after an introduction, and which is meaningless the moment the letter is in the pool. If the pilot shows abandoned ramp-ups matter, persisting the phase is a small, self-contained change; nothing else depends on it being in memory.

**A pair advances phase together** *(added 2026-08-23, alpha session 9.)* Every threshold above is per-member and never shared ([ADR-028](0028-composite-input-and-keyboard-ownership.md) § Pair ramp-up: "a slow right hand cannot mask a poor left hand"), and the **step** advances when *every* member has met the bar. Within a phase a member that has met its bar keeps its result and keeps being prompted while its partner catches up — the bar was met, and taking it back for a later slip would make a two-key step harder than two one-key steps for no pedagogical reason.

**"Previously-known keys" here means Active, not Known** *(clarified 2026-08-23, alpha session 9.)* [ADR-027](0027-key-and-accuracy-state-model.md) § Key States aligns the vocabulary: this ADR predates it and uses "known" for *introduced*. Read as Known — 90 attempts at 90% over 2 distinct days — Phase B would have no anchor and Phase C no partners for the first weeks of a profile, and the spaced re-exposure below would never fire at all. Every "known" in this ADR is Active.

**A prompt is not a keystroke** *(added 2026-08-23, alpha session 9; ADR-024 predates [ADR-032](0032-grapheme-led-introduction-and-selectable-ordering.md).)* The phases drill the **grapheme**, and every count in this ADR — the ten, the twenty, the thirty, the block length, the session floor — is a count of **prompts**, which is what [ADR-027](0027-key-and-accuracy-state-model.md) § First-Attempt Counting counts. A composite is one prompt carrying two keystrokes, so a block's prompt count and its keystroke count are different numbers in any language with composites. Both sides of the pace formula below are prompts, so the arithmetic is self-consistent; only the word "keystrokes" was wrong.

### Steady-state drill generation

Once a key has passed through ramp-up, drill content for any block over the unlocked key set is generated by sampling bigrams weighted by their `wordfreq`-derived frequency in the child's language. This is the algorithm described in ADR-010, now made concrete.

**Comfort-class weighting is not applied at v1.** The keyboard-layout-design community (Colemak, Workman, Dvorak) classifies bigrams by hand/finger pattern (alternating hands > same-hand-different-finger > same-finger) and treats same-finger bigrams as low-comfort. There is empirical support for the *speed* difference (Dhakal et al. 2018, "Observations on Typing from 136 Million Keystrokes," CHI 2018 — same-finger bigrams have longer inter-key intervals than alternating-hand bigrams), but **there is no empirical evidence that practising same-finger bigrams during acquisition harms long-term skill**. The Colemak community's own training guidance is to practise through awkward bigrams, not avoid them ("alt-fingering" is recommended only after reaching ~50 WPM — well above Takki's Diamond target of 30 WPM, and certainly above anything early Takki users will see).

The case against comfort weighting:
- Same-finger bigrams exist in the language. The child must type them in real words eventually. Avoiding them in drills is a debt that comes due in Layer 2.
- Avoidance reshapes the frequency distribution the child experiences, which is the very thing Takki's word-and-bigram-frequency approach is trying to faithfully expose.
- No evidence of acquisition harm to justify the distortion.

This may change. If a future empirical study (a Takki Beta study, or external research) shows that early SFB exposure causes measurable harm to retention or final speed, this decision can be revisited via amendment.

### Spaced re-exposure for rare keys

Frequency-weighted bigram selection naturally re-exposes common letters. The problem it creates: rare keys (English Z, Q, X; Polish less-frequent letters; Icelandic less-common diacritic stems) appear so seldom in frequency-weighted drills that they decay between exposures. This is the part of the curriculum where general spaced-repetition principles for motor memory most clearly apply — and where the lack of regular practice is most likely to cause skill loss between sessions.

**Mechanism.** The engine tracks per-key time-since-last-practised. When generating a drill block, after frequency-weighted bigram selection produces the candidate set, the engine checks the least-recently-practised known key. If its time-since-last exceeds a threshold (default: 5 minutes of session time, configurable), the engine replaces one of the more frequent bigrams in the candidate set with a bigram involving the stale key. The replacement preserves block length and structure.

**Note (Beta scope):** The "5 minutes of session time" clock resets at session start, so every session opens with all rare keys stale and the first block floods with re-exposures. The better anchor is `key_stats.last_practised_at` (cross-session wall-clock time from ADR-011) — a rare key last seen two days ago is genuinely stale; one seen 10 minutes before the session started is not. Switching the clock to wall-clock elapsed since `last_practised_at` fixes this. Deferred to Beta; the within-session clock is acceptable for Alpha where English is the only language and rare keys are few.

**One slot, two triggers** *(added 2026-08-23, alpha session 9, implementing [ADR-027](0027-key-and-accuracy-state-model.md) § The Anchor Gate's maintenance path.)* Anchor maintenance is not a second mechanism: it is this slot with an accuracy trigger in place of the staleness one, exactly as ADR-027 says. The two are **ordered rather than merged**, because they answer different questions and can both be true at once. A slipping anchor is served first — every later key position is described against it, so losing it degrades everything — and a stale rare key second; a key served by the anchor trigger is not also considered for the staleness one. Each trigger replaces exactly **one** unit, so a block is the same length whether one fires, both fire, or neither does, and there are at most three claims in a block by construction (two bump keys and one stale letter).

The unit replaced is the highest-weight one in the candidate set, which is where the ADR's "one of the more frequent bigrams" points: the child meets those again in the same block anyway.

**The accuracy trigger needs a sample, and takes ADR-027's.** A bump key is treated as slipping only once its rolling window holds at least `ANCHOR_MIN_ATTEMPTS` attempts. Below that a single early slip reads as a lost anchor; and below that the child is still inside Stage 0, where every block is anchor drill already, so nothing is missed.

**Ramp-up blocks are left alone.** Their content is deliberately isolated (§ New-key ramp-up), and a ramp-up is at most a few tens of prompts, so no claim waits long for its slot.

The threshold is deliberately short. In a 5–10 minute session, rare keys may be seen exactly once; in longer sessions, they're refreshed every few minutes. The replacement happens silently — the child does not get an "OK now we're going to practise Z" announcement, since the goal is normalised re-exposure, not call-it-out drill.

For very rare keys (frequency < 0.5% of language letters, e.g. English Z and Q), the mechanism is the only practice they get during steady-state drilling. Without it, those keys can lose accuracy across days of practice on the more common parts of the alphabet — a known pattern in motor-skill literature (motor patterns decay without rehearsal, more so for less-grooved patterns).

### Lesson granularity — child-pace-adaptive duration

ADR-010 commits to "individual lesson units must be short enough that natural stopping points occur frequently." This ADR makes that concrete.

**Drill block.** A drill block is the atomic unit of Layer 1 content. The engine targets a wall-clock duration of **90–120 seconds per block** (configurable, default 100s). The keystroke count is computed at the start of each block from the child's rolling average pace over the last 3 blocks:

```
target_keystrokes = target_seconds × recent_keystrokes_per_second
```

For a brand-new child typing at 0.3 keystrokes/second, a 100-second block contains ~30 keystrokes. For a child with 8 known keys typing at 1.2 keystrokes/second, the same 100 seconds contain ~120 keystrokes. The block's wall-clock duration stays roughly constant; the volume of practice scales with the child's capability.

For the first block of any session (no rolling pace yet), the engine uses the language's typical-first-block default from the global config (initially 30 keystrokes), and recalibrates from block 2 onwards.

**Block boundaries.** Drill blocks always end at bigram or short-sequence boundaries — the engine does not cut a child off in the middle of a sequence. If the keystroke target is reached partway through a bigram, the bigram completes, then the block ends.

*(Added 2026-08-23, alpha session 9.)* Two consequences of that rule, in the ramp-up phases where the content is a fixed cycle rather than a sample:

- **A ramp-up block ends on a whole cycle**, not merely a whole unit, so a pair's two members always leave a block with the same number of prompts. Ending mid-cycle would hand the left-hand member one extra prompt per block, forever.
- **Pace is measured over the gaps between answers, not over the block's wall-clock span**, and a gap longer than `PACE_IDLE_GAP_SECONDS` (default 30 s) is not one of them — the child had stopped typing. A PAUSED interval ([ADR-028](0028-composite-input-and-keyboard-ownership.md) § C8), a walk-away and a conversation all pass through the monotonic clock the deadline model is built on ([concurrency-model.md](../concurrency-model.md) § Timers), and charging them to the child would read as a collapse in pace and shrink every block after the interruption. The answer that ends such a gap contributes neither time nor count, so an interruption leaves the measured pace exactly where it was; a block nobody answered contributes no sample at all. *(Added 2026-08-23, alpha session 9, from its code review.)*
- **A ramp-up block is capped by the phase's own remaining requirement** as well as by the pace target — there is no point emitting 120 prompts of Phase A repetition when ten more correct in a row ends the phase. The cap is optimistic: an error simply means the next block carries the remainder.

**Stage 0's blocks are not ordinary ramp-up.** The stage's content is [ADR-023](0023-key-introduction-protocol.md) § Stage 0's and [ADR-027](0027-key-and-accuracy-state-model.md) § The Anchor Gate's: each anchor alternates with its own column reach (`f ↔ r`, `f ↔ v`), in Phase A as well as Phase B. Phase A's pure repetition is *replaced* there, not supplemented — a Phase A of `r r r r` never returns the finger to home, and first-press accuracy on `f` would then no longer be return-to-anchor accuracy, which is the entire argument for the gate's metric. The stage's home pair has no reach behind it yet, so its Phase A is the ordinary L-R interleave of `f` and `j`, which is alternation already. Nothing downstream can detect this being got wrong.

**Per-key session floor.** The engine tracks per-key attempt counts within the session (Layer 1 drills + Layer-2 character positions combined, per ADR-027). The session floor is 45 attempts per active key (configurable in `takki_config.yaml`). When every active key has reached the floor, the engine signals "session complete" — the child hears an end-of-session prompt and can stop or continue. This is a soft signal, not an interrupt: a child who wants to keep typing can. The 45-attempt floor matches the lower bound of the distributed-practice target range (45–90/key/day) established by graphomotor research on 7–8 year olds (see ADR-010 Session Pacing, [motor-learning-repetitions.md](../research/motor-learning-repetitions.md)).

**Lesson.** A lesson is one or more drill blocks plus, once Layer 2 unlocks (per ADR-010), an interleaved real-word session. The end-of-lesson trigger is either (a) a child-initiated stop, (b) milestone completion, (c) the end of a Layer 2 word that completes a configured target word count for the session, or (d) the per-key session floor reached (all active keys at ≥ 45 attempts). No upper-bound enforcement, consistent with ADR-010's decision against session limits.

**Why this approach.** A fixed-keystroke block punishes slow typists with disproportionately long blocks. A fixed-time-with-counter-on-screen would be visual feedback. Child-pace-adaptive duration with bigram-boundary cutoffs gives the same wall-clock cadence to fast and slow learners alike — the slow child does not feel they are "doing more work than expected" simply because they're early in the curriculum.

### Research grounding

The decisions above lean on a set of empirical findings from the typing-acquisition and motor-learning literature, surveyed during May 2026. None of them are direct VI-specific findings (as a search of the literature confirmed, no formal efficacy studies exist for any VI typing tutor), so each is being applied by analogy from sighted-typist or general-motor-skill research.

- **Distributed practice over massed practice.** Baddeley & Longman (1978), *The influence of length and frequency of training session on the rate of learning to type* (Ergonomics, 21(8)), trained 72 postal workers to type and found that 1 hour/day for 1 session outperformed 2 hours/day, 1 hour twice/day, and 2 hours twice/day. Strongest typing-specific evidence we have for short, frequent sessions. Drives the wall-clock-bounded drill block decision.
- **Interleaved over blocked practice.** Multiple meta-analyses (e.g. Pan & Rickard, 2018; Brady et al. 2024) find interleaved practice improves long-term retention and transfer at the cost of slower acquisition. Layer 1/Layer 2 interleaving (per ADR-010) is consistent with this. The four-phase ramp-up is, technically, a small amount of *blocked* practice for a new key — this is intentional, as motor pattern acquisition appears to benefit from early isolation before interleaved drill. The shift from Phase A's blocked repetition to Phase D's full mixing reflects this gradient.
- **Spaced repetition for motor memory.** Mixed evidence: clear positive results for simple motor tasks, weaker results for complex ones (e.g. piano: Donovan & Radosevich 1999 meta-analysis; Krigolson et al. 2021). For our application — keeping a learned simple motor pattern (a single keypress) from decaying — the evidence base is most aligned with positive results. The rare-key re-exposure mechanism is the design's response.
- **Same-finger bigrams.** Slower at steady state (Dhakal et al. 2018, CHI). No evidence of learning harm during acquisition. Drives the "do not avoid SFBs" decision.

The honest summary: motor-learning research supports short sessions, mixed practice, and spaced exposure as design directions, but does not specify the parameters with the precision we need. The numbers in this ADR — 10 keypresses to advance Phase A, 100-second drill blocks, 5-minute rare-key threshold — are reasoned starting points, not empirically established optima. They are configurable specifically so Alpha and Beta can tune them.

### Open questions and future work

1. **Empirical tuning of phase thresholds.** The Phase A/B/C/D thresholds (10, 20, 30 keypresses) are starting points, not derived from data. Alpha and Beta sessions should record per-phase keypress counts, error rates, and time-spent so the thresholds can be revisited. Likely outcome: per-phase thresholds become language-aware (English child progresses through Phase C faster than German child due to bigram complexity differences).
2. **Comfort weighting if SFB harm is shown.** If a future study demonstrates same-finger bigrams during acquisition cause measurable retention or speed problems, the steady-state bigram generator can be re-weighted. The decision is reversible — selection is a function inside the drill generator, not a deep architectural commitment.
3. **Rare-key threshold per-language.** The 5-minute default for re-exposure is heuristic. In languages with very long tails (more rare letters), the threshold may need to scale with the alphabet size, otherwise rare keys never refresh fast enough.
4. **Lesson-level granularity.** This ADR sets drill-block granularity. Whether multiple blocks should be grouped into a named "lesson" (with its own celebration / pause prompt) is a UX decision deferred to the implementation of the milestone celebration system (Beta-phase work per the roadmap).
5. **Validation against the Douglas & Long (2003) findings.** That paper documents what VI adults do badly with computers. Takki's drill engine should produce graduates who do not match that profile. Specific things to track during Beta: home-row finger placement under stress, shortcut-key use as it's introduced (post-v1), keyboard return-to-home behaviour after stretch reaches.
