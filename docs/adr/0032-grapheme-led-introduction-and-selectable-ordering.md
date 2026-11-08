# ADR-032: Grapheme-Led Introduction and Selectable Ordering

**Status:** Accepted. Decision 2 amended 2026-11-08; the amendment is not yet implemented.
**Date:** 2026-08-23
**Amended:** 2026-11-08 — alpha-plan #12m, for [ADR-033](0033-rest-keys-and-keyboard-alignment.md): [§ Decision 2 restated](#decision-2-restated-rest-keys-and-ordering-c-as-the-default).

> Part of the [Takki architecture](../architecture.md).
> **Supersedes** [ADR-023](0023-key-introduction-protocol.md) §§ Phase 1, Phase 2, and the modifier-placement rule in § Composite letters. **Amends** [ADR-028](0028-composite-input-and-keyboard-ownership.md) § Modifier introduction. **Closes** roadmap B8 and completes the structural half of roadmap B9.
> Everything else in ADR-023 stands — Stage 0, the introduction script, the step semantics, the finger map, the composite data model, the Latvian resolution and the milestone denominators are unchanged and remain authoritative. *(2026-11-08: not all of it. [ADR-033](0033-rest-keys-and-keyboard-alignment.md) supersedes Stage 0, and changes the location rule (keys are described from the finger's rest key) and the script for a rest letter. Its row for ADR-023 lists them; that amendment is not yet made.)*
> **See [ADR-033](0033-rest-keys-and-keyboard-alignment.md) (2026-10-10):** it removes Stage 0 and specifies the probe Ordering C was waiting for. *Decision 2 is amended for it on 2026-11-08, in [§ Decision 2 restated](#decision-2-restated-rest-keys-and-ordering-c-as-the-default): no Stage 0, Ordering C restated and made the default, Ordering B retired, the strategy takes the child's rest state, and a key's share of key presses is defined.*

---

**Decision:** Order the curriculum over **graphemes**, not physical keys — the character the child produces is what pushes for introduction, and the keys it needs (a modifier included) are pulled in by it. And stop deciding the ordering *below Stage 0* in an ADR at all: set out the candidate orderings at equal depth, make the choice a selectable strategy, and leave the selection to the Beta pilot.

*(2026-11-08: the second half no longer holds. ADR-033 chose the default ahead of the pilot, and Stage 0 is gone. See [§ Decision 2 restated](#decision-2-restated-rest-keys-and-ordering-c-as-the-default). Decision 1 is unchanged.)*

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

*(Amended 2026-11-08. This section is kept as the record of 2026-08-23. What replaces its parts is in [§ Decision 2 restated](#decision-2-restated-rest-keys-and-ordering-c-as-the-default), and each part it replaces carries a dated note. The paragraph just below no longer holds either: ADR-033 decided the order, so it is no longer "not decided by this ADR", nor only an implementation choice. The strategy seam itself stands.)*

Which graphemes come first, once Stage 0 has established the anchor, is **not decided by this ADR either**. The three live candidates are set out below at equal depth. The engine takes the ordering as a strategy; Alpha ships one as a compiled default, and that is an implementation choice, not a finding.

*(Withdrawn 2026-11-08: Stage 0 is gone, so the paragraph below, "What Stage 0 already settles", no longer holds. Each ordering pays its own anchor cost again. See "No Stage 0 above the orderings" in [§ Decision 2 restated](#decision-2-restated-rest-keys-and-ordering-c-as-the-default).)*

**What Stage 0 already settles, whichever ordering follows.** The research note's largest and most robust result was *anchor cost* — home-row keys learned before the child's first reach off the home row: **9–10** for the home-row-first orderings against **2** for the F/J-seeded ones, holding across all seven languages measured. [ADR-023 § Stage 0](0023-key-introduction-protocol.md) pays that cost up front: its six keys are `f j`, then `r u`, then `v m`, so the first off-home reach is the **third key introduced, for every ordering below it**. The measured gap that most sharply separated the candidates is closed before any of them starts. What remains between them is real-word onset and the shape of the coverage curve — modest in English, large in vowel-poor layouts.

| | Ordering | Anchor cost *(as measured, no Stage 0)* | English: 25 real 3-letter words | French: same | Status |
|---|---|---|---|---|---|
| **A** | Home-row fill → frequency leader per hand *(O1)* | 9–10 | ~7 keys | 11 keys | **Alpha default** — the control arm |
| **B** | F/J-seeded, full-finger coverage *(O5)* | 2 | ~7 keys, first real word at 3–5 | ~5 keys | Live candidate; the note's recommendation |
| **C** | Per-child calibrated | 2 | unmeasured | unmeasured | Live candidate; needs a probe and children |
| — | F/J → vowel priority *(O2)* | 2 | ~7 keys | ~5 keys | Measured variant of B; weaker early word quality |
| — | Whole home row → vowel first *(O4)* | 9–10 | ~7 keys | 11 keys | Measured variant of A |
| — | Coverage-greedy, no anchor *(O3)* | 0 | best | best | Upper bound only — no anchor, not shippable |

*(2026-11-08: the Status column is superseded. C is the default, A is selectable, and B is retired with its variant O2. The measured columns stand as they were measured, except row C, whose figures described the old C and were taken from B. For the restated C, the first reach is the second step's, as measured in "No Stage 0 above the orderings". See "The candidates" in [§ Decision 2 restated](#decision-2-restated-rest-keys-and-ordering-c-as-the-default).)*

#### Ordering A — home-row fill, then frequency leader per hand

The historical order, moved here from ADR-023 §§ Phase 1–2. Its two phases are **Ordering A's internal structure, not concepts of the protocol**: another ordering may have different phases or none.

*Phase 1 — the rest of the home row, as symmetric pairs by physical column* (the index home columns are Stage 0's, so A opens at the middle fingers): `(3,8)` → `(2,9)` → `(1,10)` → `(5,6)`, then any remaining row-3 letters solo, ascending by column. A column with no letter gives a solo step. The full table, the tie-breaks and the worked per-language rows are in ADR-023 § Phase 1 and are unchanged except that its first row is now Stage 0's. *(2026-11-08: with Stage 0 gone, A opens at its own first column pair, (4, 7), which is the bump letters. The code already keeps that pair first in `_PHASE1_COLUMN_PAIRS`. The rest-state rules in [§ Decision 2 restated](#decision-2-restated-rest-keys-and-ordering-c-as-the-default) bind A as well.)*

*Phase 2 — frequency leader per hand*, beginning when the Phase 1 segment is exhausted (a positional boundary, not a state to evaluate): rank the graphemes, drop the introduced and the ineligible, partition into a left and a right pool by the finger of the key each grapheme newly requires, take the top of each, and continue with solo steps until both pools empty.

**The claim this ordering used to make for itself is gone.** ADR-023 justified Phase 1 as a **location-anchoring** exercise — "establishing the resting position to which fingers return between strokes, and giving the child a fixed reference frame." That is now Stage 0's job, done more directly and in six keys rather than ten. What remains is a symmetric-pair sequence inherited from sighted touch-typing curricula, whose motor argument reduces to keeping both hands developing in parallel and whose mirroring argument is, by ADR-023's own words, "not available to a blind child." Its measured cost is real: symmetric pairs lag 4–9 steps at 75% coverage. **It is the default because it is the control arm the pilot measures against, not because the evidence favours it.** *(2026-11-08: Stage 0 is gone, and A is no longer the default. Placing the hands is now the alignment's job (ADR-033), and A stays selectable as the control arm. See [§ Decision 2 restated](#decision-2-restated-rest-keys-and-ordering-c-as-the-default).)*

#### Ordering B — F/J-seeded, full-finger coverage

*(Retired 2026-11-08, decided by the developer. The reasons are in "The candidates" in [§ Decision 2 restated](#decision-2-restated-rest-keys-and-ordering-c-as-the-default). The text below is the record.)*

Continue from Stage 0 by **round-robin across the eight fingers**, taking each finger's highest-frequency remaining grapheme in turn — L-index, R-index, L-middle, R-middle, L-ring, R-ring, L-pinky, R-pinky — and repeating the cycle until the layout is exhausted. This is O5 in the order-comparison spike, and the note's recommendation.

Every finger owns a key within the first cycle, so the child's map of the keyboard grows outward from the anchor by usefulness rather than by filling a row. Measured: it reaches contentful three-letter words (`ten, net, jet`) sooner than a vowel-priority order's `fee, off, joe`, because spreading across fingers picks up productive consonants early. The price is a small *late*-coverage tax — the weak fingers are touched early. The note's bounded conclusion calls it the sweet spot: it "captures most of the unanchored upper bound's prize while keeping a real anchor."

#### Ordering C — per-child calibrated

*(Restated 2026-11-08 as ADR-033's per-hand order, and made the default: "Ordering C, restated" in [§ Decision 2 restated](#decision-2-restated-rest-keys-and-ordering-c-as-the-default). It is no longer Ordering B with a measured seed. Its probe is ADR-033's keyboard alignment.)*

Ordering B with the resting position measured rather than assumed. The note observes that a child's middle finger may rest more naturally on `e` than on `d` — columnar-stagger ergonomics and a finger-length/typing-speed correlation both point that way — and proposes a short calibration probe at profile setup that records where each finger actually falls, then seeds the round-robin from that. Standard home positions stay recoverable, so the child can always re-find conventional home on a school machine.

C cannot be specified further without the probe, and the probe cannot be designed without children to run it on. It is listed as a sibling because it is a genuine third candidate, not a variant of B.

#### What Alpha ships

*(Superseded 2026-11-08: Alpha ships Ordering C as the default, and a strategy also takes the child's rest state. See "The strategy takes the child's rest state" and "What Alpha ships, restated" in [§ Decision 2 restated](#decision-2-restated-rest-keys-and-ordering-c-as-the-default). The rule that a strategy filters `had` itself stands.)*

**Ordering A, as the compiled default**, selected by a constructor argument on the introducer. Alpha's job is to be the instrument the pilot measures with, so it ships the control arm and makes the others cheap to add. A strategy is a callable `(layout, source, had) → list[IntroductionSlot]` returning the order below Stage 0 as grapheme names; the introduction script, the composite rules, the finger map and the location metric are shared by every ordering and live outside them. The selection moves to [ADR-025](0025-configuration-system.md)'s per-profile tier when there is a pilot to feed it — a global config key would be the wrong tier, and a `profiles` column has nothing to store until then. One rule binds every strategy: it filters `had` itself, because pairing happens after filtering, so a strategy that ignored it would mispair the survivors rather than merely repeat itself.

### Decision 2 restated: rest keys, and Ordering C as the default

*(Amended 2026-11-08, alpha-plan #12m, the ADR-032 session. This is the amendment that [ADR-033 § Amendments this ADR requires](0033-rest-keys-and-keyboard-alignment.md#amendments-this-adr-requires) asks of this ADR. In Decision 2 it supersedes "What Stage 0 already settles", the Status column of the candidates table, Ordering B, Ordering C and What Alpha ships. Each of those keeps its text, with a dated note pointing here, as the record of what was decided on 2026-08-23.)*

**Not yet implemented.** The code still runs Stage 0, with Ordering A as the default. The builds are alpha-plan #12m session (3), the key share; (4), Stage 0 and the `stage` field removed; and (5), the order, the rest state and the rules below. This amendment changes no code.

How to read the marks:

- **[D, ADR-033]** and **[S, ADR-033]**: decided in ADR-033 on 2026-10-10, with that ADR's mark. Quoted here, not decided again.
- **[S]**: settled with the developer in this session, 2026-11-08. Each was put as a question and answered.
- **[M]**: measured by a spike run in this session: [key_share_definition_spike.py](../../spikes/key_share_definition_spike.py), [results](../../spikes/results/key_share_definition_results.txt). It reads wordfreq and the product layout tables (`build_en`, `build_de`, `build_is`), and uses the engine's word filter and ranking (`_eligible_words`, `compute_grapheme_weights`, `rank_graphemes`), so its numbers move if those change. Its orders come from its own implementation of Ordering C's count rule, with every finger ready; the engine's is session (5)'s, so a test that pins them pins the spike's reading of the rule, not the rule in every state. It ran on the Windows laptop, which does not matter for what it reads.
- **[A]**: argued, not measured or tested.

A statement with no mark restates or defines something marked.

#### What changes

- There is no Stage 0 above the orderings.
- Ordering C is restated as ADR-033's per-hand order and becomes the default. Ordering A stays selectable. Ordering B is retired.
- A strategy takes the child's rest state, and three rules about it bind every strategy.
- A key's share of key presses is defined, from language data.

#### No Stage 0 above the orderings

- **Every ordering opens at the two bump letters**, the keys at row 3, columns 4 and 7, `f j` on QWERTY **[D, ADR-033]**.
- **The bump letters are the first step under every ordering, together, once both index fingers are ready** **[S]**. Nothing is introduced before them, because they are the anchors: the hands are found from them. Until both index fingers are ready, the strategy returns nothing.
  - **This overrides [ADR-033 § The alignment](0033-rest-keys-and-keyboard-alignment.md#the-alignment) in one case.** ADR-033 says "After it, fingers that are ready get keys and the others continue next session. If neither index finger is ready, no key is introduced that session." Read together, those allow keys when one index finger is ready: the ready hand's fingers would get them. Under this rule they do not, until both index fingers are ready. For the same reason the "Chosen" row of ADR-033's table, "The letter on that key may be introduced", holds only once the bump letters are had. Rest rule 3 below is the other place this amendment reads ADR-033's text a particular way.
  - The rule binds only before the first step. An index finger's `ready_at` is written once, and a bump is never replaced (ADR-011, ADR-033), so once both are ready they stay ready **[A]**. That needs retiring the bumps (ADR-033) to stop the bump round without writing `replaced_at` on the index fingers' rows; otherwise both would drop out of `rest` and the order would stop. Whoever builds the retirement, with the "Takki key", keeps that.
  - So on a first day, a child whose one index finger does not find its bump three rounds in a row within the cap (about eight rounds) gets no letter. How often that happens is not known **[A]**.
  - **What the session does then is not decided here.** ADR-033's "no key is introduced that session" has the same gap. Today's loop would end the session at once, with nothing said: with nothing Active the block is empty (`DrillGenerator._steady_units` returns `[]`), and `SessionLoop._begin_block` then stops the loop, under a comment that says this is "reachable only from an empty curriculum", which stops being true (found by reading the code on 2026-11-08). Session (7), which builds the alignment into the loop, has to say what follows the cap when there is no letter: at least a spoken line before the session ends. It is in the table at the end of this section.
- **"What Stage 0 already settles" is withdrawn.** It said Stage 0 made the first reach off the home row the third key for every ordering. Without Stage 0, each ordering pays its own cost again, as the order-comparison spike measured it before Stage 0 existed, at the conventional rest position ([anchor-and-introduction-order.md](../research/anchor-and-introduction-order.md)).
  - Ordering A learns every home-row letter before its first reach, because its Phase 1 is the home row: 9 to 10 in the research note, and on the product tables, at the conventional rest position with every finger ready, 9 for English, 11 for German (`ö` and `ä` are on row 3) and 10 for Icelandic **[A, counted by reading `build_en`, `build_de` and `build_is`; no spike computes it]**.
  - Under Ordering C, the step after the bumps is each hand's most useful letter. For en, de and is, both letters of that step are off row 3: `e n`, `e n` and `r i` **[M]**.

#### The candidates

| | Ordering | Status |
|---|---|---|
| **C** | ADR-033's per-hand order, from the child's rest keys | **The default** **[S, ADR-033]**. ADR-033 chose it ahead of the pilot, and the pilot may still change it |
| **A** | Home-row fill, then the frequency leader per hand | Selectable. The control arm, if the pilot compares orders |
| **B** | Round-robin across the eight fingers | **Retired** **[S]** |

The variants measured beside them (O2, O3, O4) stay in the 2026-08-23 table as a record. None is a candidate.

**Why B is retired** **[S]**, the reasons as put to the developer:

- On 2026-08-23, C was "Ordering B with the resting position measured". ADR-033 restates C as per-hand alternation, so C no longer contains B, and B is left alone.
- B as written no longer fits. It continued from Stage 0, which is gone, and its defining property, every finger owning a key within the first cycle, clashes with readiness: a finger that is not ready is passed over.
- What B was measured to bring, an early reach and early real words, C now has **[A]**, from the measurements above and in ADR-033's spike. That spike, which ADR-033's order rests on, never ran B.
- Kept, B would be a specification to keep current that nobody plans to build.

#### Ordering C, restated

Ordering C builds the order from what the child has and from the child's current rest keys.

1. **The bump letters first**, as above.
2. **Each hand's other letters go into two queues.**
   - **Strong rest letters**: the letters on the hand's current rest keys, leaving out the bumps, whose key carries at least `REST_LETTER_MIN_SHARE` (2%) of key presses **[D, ADR-033]**, strongest first by that share **[S, ADR-033]**. Equal shares are taken in the grapheme ranking's order, so the order never depends on how a set iterates **[A]**; a small test corpus makes ties likely.
   - **Useful letters**: every other letter of the hand, in ADR-032's grapheme ranking (`letter_ranking`) **[D, ADR-033]**. A weak rest letter is here, at its ordinary rank **[D, ADR-033]**. A composite is in its base stroke's hand, as Decision 1 says.
3. **Whose turn it is** **[S]**. A hand's next letter is a strong rest letter when the hand has had more useful letters than strong rest letters. Otherwise it is a useful letter. The bump letters count as neither, although `f` is above the floor in English (2.21%) and Icelandic (2.93%) **[M]**: they are the first step, not a turn. So a hand's first turn is useful, as ADR-033 says ("useful first").
   - When the turn's queue has nothing the hand may introduce, the hand takes from the other queue. When neither has anything, the hand has no letter in that step.
   - **Why a count.** The introducer works the whole order out again at every step from `had`, which is a set and does not say in what order the letters came. A count of the two kinds needs only that set and the current rest keys. So nothing is stored, as Decision 1 already does for the modifier.
   - **It gives the rest-letter spike's alternation.** Over the whole order, for en and de, with every finger ready at the conventional rest position, under a ranking by key share (as the rest-letter spike ranked, though over this spike's corpus) and under the engine's ranking **[M]**. With every finger ready the two rules are meant to agree, so this checks that the rule is stated right. It does not show how the rule behaves when fingers are passed over, which no spike has run. Icelandic is not compared, because that spike ranked the dead key as a key of its own and the engine is grapheme-led.
   - **Where it differs from strict alternation.** Whenever one kind could not be taken for a while, the count gives the other kind several turns in a row until it evens out **[A]**. For example, a finger that gets its rest key late can bring two rest letters in a row. This was accepted with the rule.
   - **Useful and rest are read off the rest keys current at the time**, in both directions **[A]**. A letter introduced as a rest letter on a key the child later replaces counts as useful from then on, and a letter introduced as useful that becomes the letter on a new rest key counts as a strong rest letter if that key is strong. A weak one stays in the useful count. Either way a change can move the hand's next turns. Letters already learned are left alone, as ADR-033 says; only the count moves.
4. **A step is one letter per hand** **[D, ADR-033]**, left hand first, as every step has been since ADR-032 (`IntroductionStep`). A hand with no letter gives a step of one letter. The order ends when neither hand has a letter.

The orders this gives, with every finger ready at the conventional rest position, on the product tables **[M]**:

| | After the bumps |
|---|---|
| en | `e n`, `a l`, `t o`, `s i`, `r h`, `d u`, `c m` |
| de | `e n`, `s l`, `r i`, `a h`, `t u`, `d m`, `c o` |
| is | `r i`, `a l`, `e n`, `s k`, `t u`, `g m`, `v ð` |
| en, left middle finger resting on `e` | `t n`, `e l`, `r o`, `a i`, `d h`, `s u`, `c m` |

In the last row `e` is a rest letter and `d` an ordinary one, as ADR-033 says of such a child **[M]**.

**English differs from ADR-033's illustration.** [ADR-033 § Consequences](0033-rest-keys-and-keyboard-alignment.md#consequences) gives `e o`, `a l`, `t i` as the first three steps after `f j`. That is the rest-letter spike's order, which ranked usefulness by key share. The engine's ranking counts a letter once per word, and gives `e n`, `a l`, `t o`. German and Icelandic come out the same under both rankings in this spike, over the steps shown **[M]**. Neither matches the rest-letter spike exactly. German differs at the fourth step after the bumps, `a h` here against `d h` there, because `d`'s share over the top 3000 words is 6.7% (6.73% with this spike's word filter, so the filter is not the cause) against 5.14% over the whole word list. So `a` now comes before it. Icelandic differs at the third, because that spike put the dead key in the order **[M, against [its results](../../spikes/results/rest_letter_order_results.txt)]**. Later in the Icelandic order the two must differ, though the spike prints only the first eight steps: ranked by key share, a composite scores nothing, because it has no key of its own **[A]**. ADR-033 marks its figure as direction only. The order to build is the one here.

#### The strategy takes the child's rest state

A strategy is a callable `(layout, source, had, rest) → list[IntroductionSlot]` **[S]**.

**`rest` holds each finger's current rest key, as `rest_keys` holds it** ([ADR-011](0011-persistence-and-state.md#rest_keys)) **[S]**:

- **chosen**: the finger has a current row, one with no `replaced_at`. A finger with no current row is absent from `rest`, so a finger that is present is chosen, and no field is needed for it;
- **the cell**: the row and column of that key;
- **ready**: that row has `ready_at`.

An index finger with a `bump` row is present in `rest` like any finger with a current row, although ADR-011 says its key is not chosen by the child. For it only **ready** is read: its rest letter is a bump letter, which rest rule 1 below governs, and its other letters need it ready **[A]**.

Fingers are `COL_TO_FINGER`'s ids and cells are positions, so nothing in it is per language **[D, ADR-033]**. `passed_at` and replaced keys are not read: passing a session-start test is the alignment's business, not the order's **[A]**.

**`rest` is read when the order is worked out**, from the store, as `had` is read from the key states, and once per block boundary is enough: `upcoming` and `introduce_next` at one boundary can share it. It is not fixed when the introducer is built: the alignment opens the session and marks fingers ready, and an order read before it would find every finger not ready and return nothing **[A]**. How the introducer reaches the store is session (5)'s. The step builder needs `rest` as well, because ADR-033 describes each key from its finger's rest key (the ADR-023 amendment). A step resumed at session start and built before the alignment would be described from yesterday's rest key **[A]**.

**A finger's rest letter** is the letter on the cell of its current rest key, when the cell carries one (`letters_by_position`). A cell with punctuation or a modifier gives the finger no rest letter: such a key is a place to rest **[S, ADR-033]**. A composite is never a rest letter, because a composite has no cell of its own: `Layout.keys` holds cells and `Layout.graphemes` holds letters **[A, from `takki.platform.layout`]**.

**Three rest rules that bind every strategy** **[S]**, beside filtering `had` and Decision 1's two composite rules. They are called rest rules 1 to 3, so that they are not confused with Decision 1's rules 1 and 2:

1. **The bump letters first**, together, once both index fingers are ready. Before that the strategy returns nothing.
2. **A finger absent from `rest`, with no current rest key, has no rest letter, and every letter on it is passed over.** This follows from rest rule 3, because a finger that is not chosen is not ready. It is stated because it is what a strategy does for a finger with no chosen key.
3. **A rest letter needs its finger chosen. Every other letter needs its finger ready** **[D, ADR-033, the two states]**. A rest letter here is the letter on the finger's rest key, strong or weak. A weak one waits in Ordering C's useful queue for its rank, but needs only its finger chosen, as ADR-033's table says: "Chosen: the letter on that key may be introduced". This settles a tension inside ADR-033, whose [§ Introduction order and slots](0033-rest-keys-and-keyboard-alignment.md#introduction-order-and-slots) also says "A letter on a finger that is not ready is passed over", and whose § The alignment says at the cap that "fingers that are ready get keys". Rest rule 3 reads both as meaning the finger's letters other than its rest letter, which is what the table's two states are for **[S]**.

The rules decide which letters may be introduced now. How a step is filled around a letter passed over is each ordering's own. Under C the letter keeps its place, and the hand takes its next letter that may be introduced **[S, ADR-033]**. Under A it is as below.

**Why every strategy, and not only C.** The developer chose it **[S]**. The reasons put with the question **[A]**:

- ADR-033 locates every key from its finger's rest key, whatever the ordering. A letter on a finger with no rest key has nothing to be described from.
- The strategy has to apply rest rules 2 and 3 itself, for the reason it filters `had` itself: pairing happens inside the strategy, so a step built and then thinned afterwards would be mispaired. Rest rule 1 is a gate and a first step, the same for every strategy, so it can be applied once above them, in `introduction_sequence`, as Stage 0 was. Where it lives is session (5)'s.

**What a composite would need.** This is worked out here and not decided **[A]**. English has no composite, but Icelandic is a product layout (`build_is`) with tests, so session (5) cannot leave composites without a behaviour. Read literally, rest rule 3 makes a composite "every other letter": its base finger must be ready and its modifier's finger is not checked. What is worked out here differs on both points. Session (5) puts the choice to the developer before it builds the rules. A composite's base stroke needs its finger ready, as any letter that is not a rest letter does, unless the base is that finger's rest key, where there is no reach and chosen is enough. The first composite of a mechanism class also brings in its modifier, which is located from its own finger's rest key, so that finger would need to be ready as well. The exception is a modifier that *is* that finger's rest key, where chosen is enough. ADR-028's row below takes this to the first dead-key language.

**A changed rest key starts not ready** (ADR-011). Under rest rule 3 its letter may be introduced at once, because the finger is chosen, and the finger's other letters not yet introduced wait until the new key is ready. The old rest letter, if it was not introduced, becomes an ordinary letter of the finger and waits too. While the full round runs the key can become ready again; whether the rounds that led to the change count towards it is the alignment's, session (7) **[A]**. After the full round has retired no rounds run, so a key changed then would never become ready, and its finger's remaining letters would wait for ever. In Alpha that cannot happen: after the full round retires, a change comes only at the child's request through the "Takki key", which is not built (ADR-033).

**A finger can also still be not ready when the full round retires, and that can happen in Alpha** **[A]**. ADR-033 retires the full round when every rest key has passed its own test: a strong one by its letter being Known, the others by landing right at the first round of five sessions. Neither needs three rounds in a row on the same key. A finger chosen by answer at the cap, whose landings keep varying while its strong rest letter becomes Known, passes, and the round can retire with the finger never ready. Its other letters would then wait for ever. Both cases are open question 6.

**The order is a forecast.** The strategy returns the steps it can see now, as if the rest keys stay as they are. Letters waiting on a finger that is not ready are not in it, so a short or empty order does not mean the curriculum is finished **[A]**: anything that asks whether the child has every letter has to read the layout, not the order. The introducer uses only the first step (`KeyIntroducer.upcoming` takes `remaining[0]`) and works the order out again at the next one. So a finger that becomes ready changes the order from then on **[A, from `takki.lesson.introducer`]**.

**Ordering A under the rules.** Its first symmetric pair is already columns 4 and 7 (`_PHASE1_COLUMN_PAIRS`), so it opens at the bump letters itself. A's steps are pairs by column, not by hand, so A does not take the hand's next letter in place of one passed over. A Phase 1 member that is passed over leaves its partner as a one-letter step, and comes back as a one-letter step at the head of Phase 1 once its finger can take it, because Phase 1 is worked out again from `had` **[A, from `phase1_slots`]**. That holds only if the rules keep the letter out of both phases. `home_row_fill` hands Phase 2 only what Phase 1's slots hold, so a letter dropped from its Phase 1 pair alone would turn up in Phase 2's pools as well **[A, from `home_row_fill`]**.

Phase 2 is a frequency leader per hand, so there a letter passed over is handled as under C: the hand takes its next letter that may be introduced, and the order ends when neither hand has one. Today `phase2_slots` raises `ValueError` when neither pool has an eligible leader, because until now that meant a layout whose composite has no base letter. Under the rules it can also mean letters waiting on fingers that are not ready, so session (5) has to tell the two apart and raise only for the first **[A, from `phase2_slots`]**.

#### What Alpha ships, restated

- **Ordering C is the compiled default**, chosen by the introducer's constructor argument as today. Ordering A is selectable the same way **[S, ADR-033]**.
- **The selection moves to ADR-025's per-profile tier** when there is a pilot to feed it. That is unchanged.
- **`REST_LETTER_MIN_SHARE` is a configuration number** ([ADR-033 § Numbers](0033-rest-keys-and-keyboard-alignment.md#numbers), ADR-025). How the strategy is handed it is session (5)'s.
- **The 2026-08-23 reason for shipping A is withdrawn**: "Alpha's job is to be the instrument the pilot measures with". It goes with ADR-033's decision to choose ahead of the pilot.

#### A key's share of key presses

**The definition** **[S]**: a key's share is the frequency-weighted count of its presses in the language's words, divided by the same count for every key.

- **The words.** Every word in the language data (wordfreq's frequency list for the layout's language) that is alphabetic and whose letters, in lower case, are all letters of the layout. Each word is weighted by its frequency.
  - **No length floor** **[S]**: a short word's presses are presses like any other.
  - This is the word filter that the letter ranking and the bigram table already use (`_eligible_words`), without their length floors: three letters for the ranking, two for the bigrams. A walk shared with either has to count the shorter words too.
- **A press.** Each occurrence of a letter in a word presses each key the letter needs (`prereq_keys`) once. A direct letter presses its key. A composite presses its modifier and its base **[S]**, as the rest-letter spike counted. A doubled letter is two presses.
- **Not a press:**
  - **Shift.** The language data has no case. Of 321,180 English, 634,502 German and 42,304 Icelandic words, none has an upper-case letter **[M]**. Takki folds case and never teaches Shift (ADR-005; [ADR-027](0027-key-and-accuracy-state-model.md), case is folded).
  - **Space** **[S]**. It would be 18.3% of English presses, 16.1% of German and 17.8% of Icelandic **[M]**, and every letter's share would fall by that fraction. That is the same as raising the 2% floor to about 2.4% of letter presses, which is not the floor that was decided.
  - **Digits and punctuation.** No word that passes the filter contains one.
- **Every key of the layout has a share**, zero when no such word uses it, and zero for every key when no word fits the layout at all, as with an empty test corpus **[A]**. A modifier's presses are in the total. Nothing reads a modifier's own share, because a modifier rest key is never a rest letter (ADR-033) **[A]**.
- **Strong** means a share at or above `REST_LETTER_MIN_SHARE`, ADR-033's "at least".
- **Nothing is per language**: the share comes from the language data and the layout, and the floor is one number **[D, ADR-033]**.
- **It is not the ranking.** The ranking (`grapheme_weights`) counts a letter once for each word it is in, over words of three letters or more, which says how many words a letter opens. The share counts presses, which says how much a key is used. ADR-033 uses the ranking for "most useful" and the share for "strong", and so does this order.

What the share gives for the conventional rest keys, on the product tables **[M]**:

| | L-pink | L-ring | L-mid | R-mid | R-ring | R-pink |
|---|---|---|---|---|---|---|
| en | `a` 8.29% | `s` 6.33% | `d` 3.65% | `k` 0.90% | `l` 4.17% | `;` no letter |
| de | `a` 5.99% | `s` 6.75% | `d` 5.14% | `k` 1.37% | `l` 3.62% | `ö` 0.27% |
| is | `a` 10.74% | `s` 5.17% | `d` 1.45% | `k` 2.93% | `l` 4.12% | `æ` 0.72% |

The strong ones are `a s d l` in English and German and `a s k l` in Icelandic. They are the same as in the rest-letter spike that ADR-033 cites **[M]**.

**What the choices changed** **[M]**. The alternatives put to the developer were:
- words of three letters or more;
- a key counting only its own letter, so that a composite counts toward no key at all, its modifier included, and leaves the total;
- space counted;
- the old spike's corpus, wordfreq's top 3000 words.

Under none of them does a conventional rest letter of en, de or is change class. Two English cells that a child may rest on sit at the floor, and the choices move them:
- `w` (the left ring finger, one row up) is 1.96% and weak. It is strong over words of three letters or more (2.06%) and over the old spike's corpus (2.37%);
- `p` (the right little finger, one row up) is 2.03% and strong. It is weak with space counted (1.66%) and over the old spike's corpus (1.69%).

**Cost** **[A]**. Counted on its own it is a third full pass over the corpus at startup, beside the two that `warm()` already makes, which together cost about 1,383 ms for English and 3,936 ms for German on the dev box ([concurrency-model.md § Startup](../concurrency-model.md#startup), 2026-09-10). Session (3) measures a separate pass against that, and decides whether to share a walk over the words with the other tables, which today are built and cached separately.

#### Open question 4, answered

The question was whether ADR-024's Phase B fallback, the nearest known key on the same hand, becomes the common path under Orderings B and C, where the same-finger anchor is not on the home row.

ADR-024's ladder removes it ([ADR-024 § The ramp-up restated](0024-drill-content-and-lesson-granularity.md#the-ramp-up-restated-four-objectives-and-a-ladder-of-three-levels)). There is no Phase B. At Reach, the return to the rest key is asked for by finger with a rest cue, so nothing has to stand in for a rest key without a letter. The fallback lives in `drills.py`'s Phase B anchor and goes with Phase B in session (6).

Of the two orderings, B is retired and C is built in session (5). The other use of "nearest key", describing a new key from the closest key the child has (`_locate`), is replaced by ADR-033's location rule from the rest key, which is the ADR-023 amendment's.

#### What this amendment requires elsewhere

None of these is made here, except where the row says so.

| Where | What |
|---|---|
| Code, #12m session (3) | The share in the language layer: a `WordSource` method keyed by physical key name, computed by `WordfreqSource` and by the fake `FixedListSource`, and covered by `warm()` |
| Code, #12m session (4) | `IntroductionStep.stage` and `IntroductionSlot.stage` are removed with Stage 0 **[S]** |
| Code, #12m session (5) | The strategy's new argument, the three rules in every strategy, Ordering C and the new default. Nothing writes rest keys before session (7), and under rest rule 1 every strategy returns nothing without them, so (5) has to say how the loop and its tests run until then |
| [ADR-033](0033-rest-keys-and-keyboard-alignment.md) | Its status line and its ADR-032 row say this amendment is made, made with it. Five differences from its text, recorded here and in that row: the bump-letter rule overrides § The alignment's "fingers that are ready get keys" when one index finger is ready, and the table's "Chosen" row until the bump letters are had; § Consequences' English order is the spike's; Ordering C's turn is decided by a count, which is ADR-033's alternation except where one kind could not be taken for a while; and rest rule 3 reads [§ Introduction order and slots](0033-rest-keys-and-keyboard-alignment.md#introduction-order-and-slots)'s "a letter on a finger that is not ready is passed over", and the cap's "fingers that are ready get keys", as not covering the rest letter. Dated notes in those sections are owed. They are not made here: this session changed other ADRs only in their status lines and amendment tables. #12m session (5) makes them |
| [ADR-028](0028-composite-input-and-keyboard-ownership.md) | What readiness a composite's step needs, worked out above. Session (5) puts it to the developer, because Icelandic is already a product layout; ADR-028 is amended with the first dead-key language. Roadmap § D has a line pointing here, so that it is found from ADR-028's side |
| [ADR-025](0025-configuration-system.md) | `REST_LETTER_MIN_SHARE`, already in ADR-033's row for ADR-025 |
| #12m session (7), with [ADR-012](0012-audio-feedback-design.md) and [ADR-022](0022-localisation-strategy.md) | What a session does when the alignment ends with no letter to introduce and nothing Active. Today's loop would end the session with nothing said (above) |

### What this changes in the engine

Alpha's English and German sequences do not move — every grapheme in both is direct-strike, so grapheme order and key order are the same list. *(2026-11-08: true of Decision 1. The Decision 2 amendment does move them: no Stage 0, and Ordering C in place of A.)* The changes are structural, and land as one chunk before the drill generator:

1. **Ranking is over graphemes.** The Phase 2 pools rank `source.letter_ranking` / `grapheme_weights`, not `key_frequencies`. `compute_key_frequencies`' modifier-aggregation rule — a modifier scored by the summed weight of its composites — has no remaining consumer and is retired with the decision it existed to serve.
2. **A composite is an introduction step.** `KeyIntroduction` describes a grapheme and the keys it requires, rather than a physical key; the modifier rides along in the step that first needs it, flagged as the mechanism to explain.
3. **`IntroductionStep.phase` becomes `stage`.** Phase 1 and Phase 2 are Ordering A's internal structure, so a field on the shared type must not claim them: the step carries `0` for Stage 0 and `1` for the curriculum below it. ADR-024's Phase A–D ramp-up is unaffected and keeps its names — those are drill phases, a different axis. *(2026-11-08: with Stage 0 gone the field marks nothing. It is removed with Stage 0 in #12m session (4), decided by the developer: [§ Decision 2 restated](#decision-2-restated-rest-keys-and-ordering-c-as-the-default).)*
4. **ADR-028 § Pair ramp-up keys off the step, not the phase.** It applies to any step carrying two keys, whichever ordering or stage produced it — Stage 0's three pairs included. *(2026-11-08: Stage 0 is gone, and ADR-024's ladder now says how a step of two letters climbs: [ADR-024 § The ramp-up restated](0024-drill-content-and-lesson-granularity.md#the-ramp-up-restated-four-objectives-and-a-ladder-of-three-levels), "Pairs".)*
5. **The B8 regression pin goes.** `tests/test_introducer.py::TestModifierIntroduction::test_a_modifier_repeats_every_session_until_roadmap_b8_is_resolved` exists to fail when the hole closes. It closes here.
6. **Icelandic's sequence changes shape.** `dead-acute` stops being the 20th key introduced and stops being a key in the order at all; `á é í ó ú ý` enter at their own frequency ranks, and the accent key is announced inside the first of them to come due.

### What implementation found (alpha session 8c, 2026-08-23)

This ADR was one day old and had had no implementation pressure on it. Four things it left implicit, recorded here rather than left to be rediscovered:

- **Rule 1 assumes a composite's base is itself a grapheme of the layout**, not merely a physical key. The eligibility gate is stated as "once its base letter is Active", and Active is a property of graphemes — so a layout declaring a composite whose base key produces no standalone letter would leave that composite permanently ineligible. Every layout in the v1 target set satisfies the assumption. The introducer raises rather than dropping the letter silently, on the same reasoning as [ADR-023 § Stage 0](0023-key-introduction-protocol.md)'s unguarded anchor lookup: session 12 is where real layout data first arrives, and a curriculum quietly missing a letter is the failure nobody notices.
- **Rule 2 produces steps that mix a composite with a direct-strike letter.** Pooling a composite by its base stroke puts it in an ordinary hand pool, so it can lead one hand while a plain letter leads the other: real Icelandic yields `á`+`ð` at step 10 — two members and *three* physical keys, the first time a step's member count and its key count differ. [ADR-028 § Pair ramp-up](0028-composite-input-and-keyboard-ownership.md) covered a two-key step and a composite step but not the combination, and has been amended to say the combination takes the ordinary pair treatment.
- **"Has this modifier been announced" is derivable and is not stored.** The introducer already tracks the physical keys behind the graphemes the child has, because the location metric needs a pool of keys to point at; a modifier enters that set exactly when the first composite carrying it is introduced. The one case where a derived answer and a session-local record would differ — a composite introduced and never answered — resolves in favour of derivation, which re-announces the modifier next session because the introduction script is that letter's only teaching moment. Recorded in [ADR-023 § What an introduction step is, and what the introducer remembers](0023-key-introduction-protocol.md#what-an-introduction-step-is-and-what-the-introducer-remembers). The *mechanism* explanation is retired per mechanism class while the modifier's name and location are retired per key: identical in the v1 target set, different in a layout with two dead keys.
- **`key_frequencies` left the `WordSource` Protocol entirely**, not just its modifier-aggregation rule. Item 1 above retires the rule; the method had no other job and no other caller, and a Protocol method nobody calls is a trap for the next implementer. `compute_key_frequencies`, `WordfreqSource.key_frequencies` and `FixedListSource.key_frequencies` all went with it. Grapheme weights and `rank_graphemes` are what the ordering consumes now.

### Consequences

- **Alpha is unaffected in behaviour and slightly simplified in code.** No composite exists in English or German; the work is the model change, not a new capability. *(2026-11-08: true of Decision 1 only. The Decision 2 amendment changes what Alpha introduces and in what order.)*
- **The first dead-key language is unblocked.** It was not, before this ADR: B8 made composites permanently unreachable.
- **The milestone denominator gets more honest.** ADR-027 counts typeable graphemes and excludes modifiers; now the introduction order counts the same things the ladder does, instead of ordering one set and measuring another.
- **A language whose composites are frequent gets them earlier**, which is the point: Icelandic `á` is a common letter, and under the old rule the child met the accent key long before any accented letter and then waited for one.
- **The pilot can A/B orderings without an engine change**, and Alpha is not silently an arm of that experiment. *(2026-11-08: the second half no longer holds. Alpha ships Ordering C, ADR-033's choice made ahead of the pilot. See [§ Decision 2 restated](#decision-2-restated-rest-keys-and-ordering-c-as-the-default).)*

### Open questions

1. **Which ordering the pilot picks.** Unchanged and deliberate; this ADR exists to keep the question open rather than to answer it. Supersedes ADR-023 open question 6. *(2026-11-08: ADR-033 chose ahead of the pilot. C is the default, A stays selectable as the control arm, and B is retired ([§ Decision 2 restated](#decision-2-restated-rest-keys-and-ordering-c-as-the-default)). The pilot may still change the choice.)*
2. **The calibration probe for Ordering C.** *(Answered 2026-10-10 by [ADR-033](0033-rest-keys-and-keyboard-alignment.md): the probe is the keyboard alignment that opens a session.)* What it measures, how long it takes, and whether a blind child can complete it without sighted help. Beta.
3. **Whether an eligible-but-not-yet-due composite should ever be pulled forward** to retire a modifier the child keeps meeting in text they cannot yet type. Not an Alpha question; revisit with the first dead-key language.
4. **Ordering B and C are specified but not implemented.** They ship as strategies when the pilot needs them; writing them now would be building an experiment with no subjects. Whoever implements one must re-read [ADR-024](0024-drill-content-and-lesson-granularity.md) § Phase B, whose same-finger anchor is assumed to come from the home row: under Ordering A that assumption holds by construction, and under B or C it does not, so ADR-024's fallback — *nearest known key on the same hand* — stops being the rare path and becomes the common one. It is a fallback that already exists, not a gap; the point is that its frequency changes by an order of magnitude and it should be tested as a main path, not an edge case. *(Answered 2026-11-08: ADR-024's ladder has no Phase B, and the return to the rest key is asked for by finger, so nothing stands in for a same-finger anchor. B is retired, and C is built in #12m session (5). See "Open question 4, answered" in [§ Decision 2 restated](#decision-2-restated-rest-keys-and-ordering-c-as-the-default).)*
5. **Whether composite ordering should ever consider stroke pattern.** Decided *no* above, with the cost accepted. The signal that would reopen it is a child stalling repeatedly on a composite whose base stroke shares a hand with the modifier — particularly the one carrying the mechanism explanation. Watch for it in the pilot; if it appears, the narrowest possible fix is to choose the *mechanism-bearing* composite for motor ease and leave the rest on frequency, which is one rule firing once per mechanism class per language rather than a general comfort weighting.
6. **A finger that is not ready once the full round has retired.** *(Raised 2026-11-08 by the Decision 2 amendment.)* Readiness is earned only by rounds, and none run after the full round retires, so under the rest-state rules such a finger gets no more letters. It happens two ways. A rest key changed after retirement starts not ready (ADR-011); that needs the "Takki key", which is not built, so it is not an Alpha case. And the full round can retire with a finger chosen but never ready, because no rest key's test needs readiness; that can happen in Alpha. Candidates to put to the developer: the full round does not retire while a finger is not ready (an ADR-033 change), or a finger still not ready when it retires is counted as ready (a change to rest rule 3). Session (5) or (7) raises it, whichever comes first; until then it is not decided.
