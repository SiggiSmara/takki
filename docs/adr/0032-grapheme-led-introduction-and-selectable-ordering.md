# ADR-032: Grapheme-Led Introduction and Selectable Ordering

**Status:** Accepted
**Date:** 2026-08-23

> Part of the [Takki architecture](../architecture.md).
> **Supersedes** [ADR-023](0023-key-introduction-protocol.md) §§ Phase 1, Phase 2, and the modifier-placement rule in § Composite letters. **Amends** [ADR-028](0028-composite-input-and-keyboard-ownership.md) § Modifier introduction. **Closes** roadmap B8 and completes the structural half of roadmap B9.
> Everything else in ADR-023 stands — Stage 0, the introduction script, the step semantics, the finger map, the composite data model, the Latvian resolution and the milestone denominators are unchanged and remain authoritative.

---

**Decision:** Order the curriculum over **graphemes**, not physical keys — the character the child produces is what pushes for introduction, and the keys it needs (a modifier included) are pulled in by it. And stop deciding the ordering *below Stage 0* in an ADR at all: set out the candidate orderings at equal depth, make the choice a selectable strategy, and leave the selection to the Beta pilot.

### Why this ADR exists rather than another amendment to ADR-023

ADR-023 was accepted 2026-05-23 with a home-row-first ordering as its body. [anchor-and-introduction-order.md](../research/anchor-and-introduction-order.md) (2026-06-07, confirmed by an order-comparison spike on 2026-06-14) measured that ordering as the weaker one and assigned the choice to the Beta pilot — and nothing linked the note to the ADR, so alpha session 8 implemented the superseded model faithfully ([roadmap B9](../roadmap.md#b-places-where-two-accepted-adrs-disagree)). Session 8b added Stage 0 and a strategy seam by amendment.

Two more amendments would not fix what is wrong with the document. ADR-023 states one ordering as *the* protocol and files the alternatives as an open question, and that framing is the thing that failed: it is what let a reader — human or model — take the body as decided and the note as background. Amending the body again would also destroy the record of what was decided when, which is precisely the defect B9 diagnosed. So the ordering decision is lifted out of ADR-023 and restated here, where the candidates can be siblings and the default can be named as an implementation choice rather than a finding. ADR-023 remains the protocol document; it keeps the machinery and loses the ordering.

### Decision 1 — Introduction is grapheme-led

**The entity that pushes for introduction is the character the child produces, not the key they press.** The curriculum is ordered over **graphemes** — the letters of the language as they appear in text, ranked by their frequency in it. A physical key is the *mechanism* by which a grapheme is produced. Keys are pulled in by the grapheme that needs them and are never scheduled in their own right.

For a direct-strike grapheme the distinction is invisible: `e` is one letter produced by one key, and ordering the two is the same act. English and German are direct-strike throughout, so this decision changes nothing about their sequences. It becomes visible exactly where a language stops being one key per letter:

- A **composite** grapheme (`á`, `ą`, `ê`) is introduced at **its own frequency rank**, as a letter, with the composite script in ADR-023 § Composite letters.
- The **modifier** it requires — a dead key, AltGr — has **no rank, no step and no place in the order**. It is announced *inside* the step that introduces the first composite needing it, as part of explaining how that letter is typed.

**What this replaces.** ADR-023 gave a modifier an effective frequency of its own — the summed weight of every composite depending on it — and placed it in the sequence at that rank: Icelandic `dead-acute` as the 18th key introduced, before any of `á é í ó ú ý` was due. That rule needed the surrogate score because a modifier's own text frequency is zero. Ordering graphemes removes the need for a surrogate rather than improving it.

**Why the old rule was wrong on its own terms.** A step that introduces a dead key teaches a mechanism with nothing to apply it to. The child is told "this key adds an accent to the next letter you press" at a moment when no accented letter is due, spends a step of attention on it, and a real letter is displaced from the sequence to make room. The rule also produced a key that could not be practised: ADR-028 § Modifier introduction item 2 already says the modifier gets no Phase A and no Phase B, so its "step" was an announcement and nothing else. A step with no drill behind it is not an introduction; it is a fact stated early.

**And wrong in the data model.** A modifier can never become Active — it is never a prompt target, and ADR-027 § First-Attempt Counting creates the `key_stats` row on the first counted keystroke against a character — so ADR-028's composite-availability test ("both modifier and base letter have `key_stats` rows") could never be satisfied, and no composite could ever unlock. That was roadmap B8. Alpha session 8 found the second half of it: the introducer's session-local record can never retire a key that cannot become Active either, so the accent key was re-announced at the head of the right-hand pool in *every* session, forever, once the rest of the sequence was exhausted.

Grapheme-led introduction dissolves both. Nothing gates on a modifier being Active, because the composite's own introduction is the event that makes it typeable, and a composite **is** a prompt target like any other letter — it acquires a `key_stats` row, becomes Active, becomes Known, and counts towards the milestone denominator, all by the ordinary rules. **B8 is closed by removing the state it asked about, not by defining a second kind of Active** — which is what that roadmap entry warned every candidate resolution against.

**Two rules keep a composite's step to one new motor demand.**

1. **A composite is eligible only once its base letter is Active.** `á` may not precede `a`. Otherwise the step would teach a new finger position *and* a new mechanism at once, which is what [ADR-024](0024-drill-content-and-lesson-granularity.md)'s ramp-up exists to prevent. A base letter outranks its own composites in every language measured, so the gate rarely binds; it is there for the case where it does.
2. **A composite's step introduces at most one new key** — the modifier, and only for the first composite of that mechanism class. Every later composite on the same modifier introduces **no key at all**: it is a new letter made of two keys the child already has.

A composite step still belongs to a **hand**: the one that performs its **base** stroke — `á` is a left-hand step, `ó` a right-hand one. The modifier stroke is identical for every composite of a class and so balances nothing; the base stroke is the one that varies and carries the load. This keeps composites inside the ordinary hand-balancing rule instead of carving out a third category for them. *(Corrected 2026-08-23: an earlier draft of this rule said such a step "claims no hand, because it adds no reach to either", which confused* introduces no new position *with* exercises no hand. *Only the first is true — `ó` teaches no new key, but the right hand does all of its work.)*

**Composites are ordered by frequency, and that can introduce them in a motorically awkward order.** *(Decided 2026-08-23, in answer to the question put directly: what is the difference between `á`, `é`, `í`, `ó`, `ú` and `ý`?)*

They differ in exactly one thing — the hand and finger of the base stroke — because the modifier stroke is the same for all six. On the Icelandic layout the dead key is R-pink at column 11:

| | base | finger | stroke pattern | frequency rank |
|---|---|---|---|---|
| **á** | a | L-pink | cross-hand | #20 · 1.35% |
| **í** | i | R-mid | same hand, cols 11→8 | #23 · 1.16% |
| **ó** | o | R-ring | same hand, cols 11→9 — adjacent fingers | #26 · 0.92% |
| **ú** | u | R-idx | same hand, cols 11→7 | #29 · 0.52% |
| **é** | e | L-mid | cross-hand | #30 · 0.50% |
| **ý** | y | R-idx | same hand, cols 11→6 | #31 · 0.23% |

Two alternate hands; four make the right hand strike twice running, starting on the pinky. **Two-hand engagement is taken as easier than one-hand** — uncontroversial, and consistent with the inter-key-interval evidence [ADR-024](0024-drill-content-and-lesson-granularity.md) § Steady-state already cites, though as there, no evidence says the harder pattern harms *acquisition*. And **difficulty does not track frequency**: the easiest pattern here is the second-rarest letter, the tightest sits mid-ranking.

**The decision is to order composites by frequency anyway, exactly like every other grapheme.** A character's frequency is how often the child will actually meet it in real text, so it is also the right measure of how much practice the letter deserves and how early. Ordering by stroke pattern would buy a marginal comfort gain for a stack of conditional rules — an ease metric, a tie-break against frequency, a special case for whichever composite carries the mechanism explanation — each one defined per layout and maintained forever. That trade is not worth making, and it runs against ADR-024's settled position that awkward patterns exist in the language, the child has to type them eventually, and avoiding them in drills is a debt that comes due.

**The cost is acknowledged rather than argued away: suboptimal introductions cannot be ruled out.** Two are visible already. The first composite of a mechanism class carries the explanation of the whole concept — what a dead key *is* — and frequency alone decides which letter that lands on; Icelandic draws `á`, the easiest of its six, by luck rather than design, and another language's most frequent composite could as easily be its most awkward. And the same-hand composites sit together in the middle of the frequency ranking, so a child can meet several of them in a row. Neither is a defect to be fixed silently later: they are the accepted price of a rule that stays simple, and the pilot is where they would show up. See open question 5.

**What a modifier still gets.** Its spoken introduction, inside the composite's step: name, location relative to a key the child has, and mechanism — *"New letter: á. Press the accent key, then A. The accent key lives one position right of Æ, and makes no sound on its own."* The location metric and the rule that a modifier may receive a reference but never serve as one are ADR-023's and are unchanged.

### Decision 2 — The ordering below Stage 0 is selectable, and its candidates are siblings

Which graphemes come first, once Stage 0 has established the anchor, is **not decided by this ADR either**. The three live candidates are set out below at equal depth. The engine takes the ordering as a strategy; Alpha ships one as a compiled default, and that is an implementation choice, not a finding.

**What Stage 0 already settles, whichever ordering follows.** The research note's largest and most robust result was *anchor cost* — home-row keys learned before the child's first reach off the home row: **9–10** for the home-row-first orderings against **2** for the F/J-seeded ones, holding across all seven languages measured. [ADR-023 § Stage 0](0023-key-introduction-protocol.md) pays that cost up front: its six keys are `f j`, then `r u`, then `v m`, so the first off-home reach is the **third key introduced, for every ordering below it**. The measured gap that most sharply separated the candidates is closed before any of them starts. What remains between them is real-word onset and the shape of the coverage curve — modest in English, large in vowel-poor layouts.

| | Ordering | Anchor cost *(as measured, no Stage 0)* | English: 25 real 3-letter words | French: same | Status |
|---|---|---|---|---|---|
| **A** | Home-row fill → frequency leader per hand *(O1)* | 9–10 | ~7 keys | 11 keys | **Alpha default** — the control arm |
| **B** | F/J-seeded, full-finger coverage *(O5)* | 2 | ~7 keys, first real word at 3–5 | ~5 keys | Live candidate; the note's recommendation |
| **C** | Per-child calibrated | 2 | unmeasured | unmeasured | Live candidate; needs a probe and children |
| — | F/J → vowel priority *(O2)* | 2 | ~7 keys | ~5 keys | Measured variant of B; weaker early word quality |
| — | Whole home row → vowel first *(O4)* | 9–10 | ~7 keys | 11 keys | Measured variant of A |
| — | Coverage-greedy, no anchor *(O3)* | 0 | best | best | Upper bound only — no anchor, not shippable |

#### Ordering A — home-row fill, then frequency leader per hand

The historical order, moved here from ADR-023 §§ Phase 1–2. Its two phases are **Ordering A's internal structure, not concepts of the protocol**: another ordering may have different phases or none.

*Phase 1 — the rest of the home row, as symmetric pairs by physical column* (the index home columns are Stage 0's, so A opens at the middle fingers): `(3,8)` → `(2,9)` → `(1,10)` → `(5,6)`, then any remaining row-3 letters solo, ascending by column. A column with no letter gives a solo step. The full table, the tie-breaks and the worked per-language rows are in ADR-023 § Phase 1 and are unchanged except that its first row is now Stage 0's.

*Phase 2 — frequency leader per hand*, beginning when the Phase 1 segment is exhausted (a positional boundary, not a state to evaluate): rank the graphemes, drop the introduced and the ineligible, partition into a left and a right pool by the finger of the key each grapheme newly requires, take the top of each, and continue with solo steps until both pools empty.

**The claim this ordering used to make for itself is gone.** ADR-023 justified Phase 1 as a **location-anchoring** exercise — "establishing the resting position to which fingers return between strokes, and giving the child a fixed reference frame." That is now Stage 0's job, done more directly and in six keys rather than ten. What remains is a symmetric-pair sequence inherited from sighted touch-typing curricula, whose motor argument reduces to keeping both hands developing in parallel and whose mirroring argument is, by ADR-023's own words, "not available to a blind child." Its measured cost is real: symmetric pairs lag 4–9 steps at 75% coverage. **It is the default because it is the control arm the pilot measures against, not because the evidence favours it.**

#### Ordering B — F/J-seeded, full-finger coverage

Continue from Stage 0 by **round-robin across the eight fingers**, taking each finger's highest-frequency remaining grapheme in turn — L-index, R-index, L-middle, R-middle, L-ring, R-ring, L-pinky, R-pinky — and repeating the cycle until the layout is exhausted. This is O5 in the order-comparison spike, and the note's recommendation.

Every finger owns a key within the first cycle, so the child's map of the keyboard grows outward from the anchor by usefulness rather than by filling a row. Measured: it reaches contentful three-letter words (`ten, net, jet`) sooner than a vowel-priority order's `fee, off, joe`, because spreading across fingers picks up productive consonants early. The price is a small *late*-coverage tax — the weak fingers are touched early. The note's bounded conclusion calls it the sweet spot: it "captures most of the unanchored upper bound's prize while keeping a real anchor."

#### Ordering C — per-child calibrated

Ordering B with the resting position measured rather than assumed. The note observes that a child's middle finger may rest more naturally on `e` than on `d` — columnar-stagger ergonomics and a finger-length/typing-speed correlation both point that way — and proposes a short calibration probe at profile setup that records where each finger actually falls, then seeds the round-robin from that. Standard home positions stay recoverable, so the child can always re-find conventional home on a school machine.

C cannot be specified further without the probe, and the probe cannot be designed without children to run it on. It is listed as a sibling because it is a genuine third candidate, not a variant of B.

#### What Alpha ships

**Ordering A, as the compiled default**, selected by a constructor argument on the introducer. Alpha's job is to be the instrument the pilot measures with, so it ships the control arm and makes the others cheap to add. A strategy is a callable `(layout, source, had) → list[IntroductionSlot]` returning the order below Stage 0 as grapheme names; the introduction script, the composite rules, the finger map and the location metric are shared by every ordering and live outside them. The selection moves to [ADR-025](0025-configuration-system.md)'s per-profile tier when there is a pilot to feed it — a global config key would be the wrong tier, and a `profiles` column has nothing to store until then. One rule binds every strategy: it filters `had` itself, because pairing happens after filtering, so a strategy that ignored it would mispair the survivors rather than merely repeat itself.

### What this changes in the engine

Alpha's English and German sequences do not move — every grapheme in both is direct-strike, so grapheme order and key order are the same list. The changes are structural, and land as one chunk before the drill generator:

1. **Ranking is over graphemes.** The Phase 2 pools rank `source.letter_ranking` / `grapheme_weights`, not `key_frequencies`. `compute_key_frequencies`' modifier-aggregation rule — a modifier scored by the summed weight of its composites — has no remaining consumer and is retired with the decision it existed to serve.
2. **A composite is an introduction step.** `KeyIntroduction` describes a grapheme and the keys it requires, rather than a physical key; the modifier rides along in the step that first needs it, flagged as the mechanism to explain.
3. **`IntroductionStep.phase` becomes `stage`.** Phase 1 and Phase 2 are Ordering A's internal structure, so a field on the shared type must not claim them: the step carries `0` for Stage 0 and `1` for the curriculum below it. ADR-024's Phase A–D ramp-up is unaffected and keeps its names — those are drill phases, a different axis.
4. **ADR-028 § Pair ramp-up keys off the step, not the phase.** It applies to any step carrying two keys, whichever ordering or stage produced it — Stage 0's three pairs included.
5. **The B8 regression pin goes.** `tests/test_introducer.py::TestModifierIntroduction::test_a_modifier_repeats_every_session_until_roadmap_b8_is_resolved` exists to fail when the hole closes. It closes here.
6. **Icelandic's sequence changes shape.** `dead-acute` stops being the 20th key introduced and stops being a key in the order at all; `á é í ó ú ý` enter at their own frequency ranks, and the accent key is announced inside the first of them to come due.

### Consequences

- **Alpha is unaffected in behaviour and slightly simplified in code.** No composite exists in English or German; the work is the model change, not a new capability.
- **The first dead-key language is unblocked.** It was not, before this ADR: B8 made composites permanently unreachable.
- **The milestone denominator gets more honest.** ADR-027 counts typeable graphemes and excludes modifiers; now the introduction order counts the same things the ladder does, instead of ordering one set and measuring another.
- **A language whose composites are frequent gets them earlier**, which is the point: Icelandic `á` is a common letter, and under the old rule the child met the accent key long before any accented letter and then waited for one.
- **The pilot can A/B orderings without an engine change**, and Alpha is not silently an arm of that experiment.

### Open questions

1. **Which ordering the pilot picks.** Unchanged and deliberate; this ADR exists to keep the question open rather than to answer it. Supersedes ADR-023 open question 6.
2. **The calibration probe for Ordering C.** What it measures, how long it takes, and whether a blind child can complete it without sighted help. Beta.
3. **Whether an eligible-but-not-yet-due composite should ever be pulled forward** to retire a modifier the child keeps meeting in text they cannot yet type. Not an Alpha question; revisit with the first dead-key language.
4. **Ordering B and C are specified but not implemented.** They ship as strategies when the pilot needs them; writing them now would be building an experiment with no subjects. Whoever implements one must re-read [ADR-024](0024-drill-content-and-lesson-granularity.md) § Phase B, whose same-finger anchor is assumed to come from the home row: under Ordering A that assumption holds by construction, and under B or C it does not, so ADR-024's fallback — *nearest known key on the same hand* — stops being the rare path and becomes the common one. It is a fallback that already exists, not a gap; the point is that its frequency changes by an order of magnitude and it should be tested as a main path, not an edge case.
5. **Whether composite ordering should ever consider stroke pattern.** Decided *no* above, with the cost accepted. The signal that would reopen it is a child stalling repeatedly on a composite whose base stroke shares a hand with the modifier — particularly the one carrying the mechanism explanation. Watch for it in the pilot; if it appears, the narrowest possible fix is to choose the *mechanism-bearing* composite for motor ease and leave the rest on frequency, which is one rule firing once per mechanism class per language rather than a general comfort weighting.
