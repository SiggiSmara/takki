# Research note: anchoring and key-introduction order

> **Status:** Research / pre-decision (informs a future [ADR-023](../adr/0023-key-introduction-protocol.md) amendment — not itself a decision)
> **Date:** 2026-06-07
> **Updated:** 2026-06-14 — order-comparison spike results folded in (see "What the order-comparison spike showed").
> **Sources:** see [references.md](references.md)

**One-line summary:** Frequency data, keyboard ergonomics, and actual VI teaching
practice all point the same way — anchor on the F/J tactile bumps and grow the
keyboard map outward *by usefulness* (vowels early) rather than by drilling the
full home row first. The single thing none of them settle is the child-specific
motor outcome, which is a Beta-pilot question. A per-child middle-finger
calibration probe (below) is the proposed way to turn that unknown into a feature.

---

## The question

[ADR-023](../adr/0023-key-introduction-protocol.md) Phase 1 teaches the entire
home row (as physical-position symmetric pairs) before any other key, framed as a
*location-anchoring* exercise. The motivation to revisit this is engagement: get a
visually impaired child to tangible real-word output sooner, consistent with the
architecture's "useful early, not perfect late" principle (the same logic as
unlocking Layer 2 real words at 8 keys).

The trigger was empirical — see the C13 results in the
[word-list reality spike](../../spikes/word_list_reality_spike.py)
([results](../../spikes/results/word_list_reality_results.txt)).

## What the word-list spike showed

At the 8-key (home-row) mark the typeable word pool is not *count*-starved but
*quality*-starved: weighted coverage is ~0–4% across languages, and the typeable
3-letter words are dominated by acronyms/initialisms (English: `ads, aka, fda,
afl, aaa`; French AZERTY: **100% non-words, 0.0% coverage — its home row has no
vowels at all**). Real words only come online around k=12–16, once `e/i/o/u`
arrive. QWERTY/QWERTZ home rows have exactly one vowel (`a`); AZERTY has none.

(The spike also surfaced that wordfreq is contaminated with acronyms/internet-isms
that ADR-008's frequency+length filter does not remove — tracked separately as a
word-list filtering gap.)

## What the order-comparison spike showed

The follow-up spike
([intro_order_comparison_spike.py](../../spikes/intro_order_comparison_spike.py),
[results](../../spikes/results/intro_order_comparison_results.txt)) ran five
candidate orderings across seven languages — **O1** status-quo (home-row →
frequency-per-hand), **O2** F+J → vowel-priority, **O3** coverage-greedy with no
anchor (the engagement *upper bound*), **O4** whole-home-row → vowel-first, and
**O5** F+J → full-finger-coverage (the per-child-calibration order proposed
below) — and scored each on the three metrics this note cares about: anchor cost,
real-word onset, and weighted coverage. Critically it applies the missing
real-word filter, so counts are not inflated by the acronym junk above.

**Finding 1 — the contamination is worse than the count metric suggested, and a
cheap heuristic can't see all of it.** With a real English dictionary, only **11%**
of wordfreq's 3-letter alpha strings are actual words (1,287 of 11,707). The
vowel-plus-not-all-same heuristic recovers the consonant-only junk (`sms`, `dsl`)
— its pass rate climbs sharply with length — but a second, larger noise source it
*cannot* detect (proper nouns, foreign tokens, web spellings) keeps the
dictionary-real fraction low at every length:

| word length | heuristic pass (en/de/fr/fi) | dictionary-real (en) |
|---|---|---|
| 3 | 59–68% | 11% |
| 4 | 92–98% | 17% |
| 5 | ~100% | 17% |
| 6 | ~100% | 19% |

So longer words are cleaner of consonant junk but still ~80% non-dictionary
words. 3-letter is kept as the primary onset band (it is Layer 2's entry per
[ADR-010](../adr/0010-lesson-structure-and-progression.md)); the takeaway is that
its absolute counts must be read through a dictionary, which is the
[ADR-008](../adr/0008-word-list-strategy.md) word-list-filter work, not a reason to
move the band.

**Finding 2 — anchor cost is the robust, filter-independent win.** Home-row keys
learned before the first off-home reach: O1/O4 force **9–10**, the F+J orderings
(O2/O5) force **2**, the unanchored upper bound (O3) forces **0**. This is the
"barren home row" penalty made concrete, and it holds across all seven languages.

**Finding 3 — the real-word-onset prize is real but modest in English and large in
vowel-poor layouts.** With the honest English dictionary, *all* orderings reach 25
real 3-letter words around step 7 — English's home row carries `a` plus productive
consonants (`all, ask, add, dad, sad, lad`), so it is not as barren as feared. The
F+J wins there are narrower but real: first real word at step **3–5 vs 7**, and the
50-word mark at step **7–8 vs 10**. The decisive case is **French**, whose home row
has no vowel at all: O1/O4 need **11** keys to reach 25 real words; O2/O5 need
**~5**.

**Word quality, not just count.** O3's early words are the best (`see, she, the,
set, eat`) but it has no anchor at all. O5 reaches contentful words (`ten, net,
jet`) sooner than O2's vowel-cluster (`fee, off, joe`), because spreading across
fingers hits productive consonants early — at the cost of a small *late*-coverage
tax (it touches the weak fingers early). **Net: O5 — the per-child-calibration
order — is the sweet spot**: anchor cost 2, good early words, near-status-quo word
timing, only a minor late-coverage cost.

## Evidence

### 1. The "middle finger rests higher" intuition is a designed-for ergonomic principle

Ergonomic keyboards do two separable things. **Splitting/tenting** the halves
fixes *ulnar deviation* (wrist angle) — not relevant to Takki, which doesn't
control the hardware. **Columnar stagger** is the relevant one: columns are offset
*by finger length* because "the middle finger is the highest, and the two smallest
fingers… are lower" (ring column up ~5 mm, middle a further ~2.5 mm; Kinesis
concave wells do the same in 3-D). The literature explicitly notes traditional
row-staggered keyboards "force fingers into unnatural alignment on the home row."

→ "Index on F/J, middle fingers fall on E/I" is the columnar-stagger truth showing
through on a standard board, not an idiosyncrasy. E and I are the middle fingers'
upper-row keys in the standard map, and both are high-frequency vowels. Finger
length is not just comfort, either: a study of Grade 6–12 students found
**middle-finger length** moderately predicts typing speed (r=0.43) and accuracy
(r=0.366) — measurable, in our age range, on the specific finger at issue (AIJFR
2025).

### 2. The anchor is the F/J bumps — and VI practice already treats position as flexible

The F and J raised bars are the universal tactile orientation landmark — verified
in the primary sources: "Every keyboard I've encountered has built-in tactile
indicators on the F and J keys … to help typists—sighted and blind—position their
hands correctly" (NFB). And VI teaching practice explicitly individualizes the
resting position and decouples it from the home row: **"Usually, that position is
on the home row, but really any consistent position to start from is fine"**
(Perkins); "Feel free to experiment with location, every student is unique"
(See It Our Way). Readiness is defined as holding *a* resting position for 5–10 s
(Perkins) — a stable anchor, not specifically the 8-key home row. The rigid home
row is a convention layered on top of the two real landmarks.

### 3. Home-row-first is convention, not evidence — and can backfire

The literature justifies home-row-first purely as a *reference-point* argument
("the home row will be the reference point from which you learn all other keys"),
**not** as a claim it must be mastered first, and with no comparative study showing
it beats a usefulness/frequency order. QWERTY's home row carries only ~30% of
English letter frequency (vs ~74% for optimized layouts — unverified figure, see
[references.md](references.md)) — consistent with the spike's barrenness being a
structural property of QWERTY, not an artifact of our method. And a VI typing
instructor warns the opposite of safe: "starting from the beginning (home row,
basic keyboard orientation) will frustrate your student to the point that he/she
shuts down" (Perkins) — practitioner support, from the target population, for not
front-loading the barren home row.

## Caveats (why we can't just hard-code the posture)

- **Children's hands ≠ an adult hand.** Children's hands are substantially smaller
  than adults', while the keyboard is built to adult standards — so a child works an
  oversized board with a hand whose finger lengths vary widely child-to-child (the
  AIJFR study above found enough finger-length variation among students to move
  typing speed). The *direction* (middle finger longest → rests higher) holds
  anatomically, but the *magnitude and exact key* won't map to "E/I" for every
  child, and some small hands won't span the posture an adult feels.
  *We deliberately do not depend on population anthropometry figures here.* Precise
  per-age hand-size statistics would only matter for choosing a universal default —
  which the per-child calibration below rejects. The only claim the design needs from
  this evidence is the qualitative one (hands are smaller and vary), which AIJFR
  already supports in our age range. So the unobtained/paywalled child-hand
  percentages are **not a blocker** and are not worth chasing (see
  [references.md](references.md)).
- **The keys aren't where the fingers want them.** Column stagger says the natural
  home is a finger-length *curve*; a standard board has straight rows. The "natural
  rest" is always an approximation on the hardware our users actually have.

## Bounded conclusion

The three strands converge, so the design move is well-founded — but scoped. The
order-comparison spike above sizes it: the anchor-cost saving is large and
language-independent (9–10 home keys before the first reach → 2), while the
real-word-onset gain is modest in English but large where the home row is
vowel-poor (French: 11 keys → 5). O5 (F+J → full-finger-coverage) captures most of
the unanchored upper bound's prize while keeping a real anchor.

- **Keep:** F/J bumps as *the* anchor; the standard finger→key map (transfer-safe
  for school machines, screen-reader docs, other keyboards).
- **Adopt:** grow the mental model from F/J *by usefulness*, not by filling a row;
  introduce the middle-finger vowels (E/I) early.
- **Don't hard-code:** a child-universal "natural rest" posture or a non-standard
  idle key. Make the anchor/introduction order a *configurable strategy*, consistent
  with the field's "every student is unique."
- **Watch:** idling the middle finger on E vs returning to D is the one genuine
  divergence from the world's convention — keep F/J recoverable so a child can
  always re-find standard home.

## Proposed mechanism: per-child middle-finger calibration

Rather than *us* choosing the posture (which the children's-hand caveat says we
can't do universally), **calibrate it per child at setup** — turning the
variability from a problem into a feature, and giving the child agency
(consistent with [ADR-016](../adr/0016-visual-display-design.md)'s
independence/anti-learned-helplessness stance).

Two separable changes — do the safe one now, pilot-validate the other:

1. **Introduce E/I early for everyone (low risk, universal).** Pure introduction-
   order change; the finger map and F/J anchor are untouched. This alone fixes most
   of the spike-3 barrenness.
2. **Per-child home/idle position for the middle finger (higher value, needs the
   pilot).** Let the child's comfort decide whether the middle finger idles on
   D/K (standard) or E/I (raised).

**Calibration by observation, not introspection.** A 5–7-year-old cannot reliably
answer "does D or E feel more natural?" — abstract proprioceptive preference is
beyond most young children and they tend to pick whatever was offered last. So
probe *behaviorally*: "Put your fingers on the bumps. Now, without moving your
hand, let your middle finger drop straight down and press." Record which key fired
(left: D/E/C ↔ right: K/I/comma), repeat 2–3× for stability, and set the profile's
middle-finger home to the observed key. Re-check occasionally (hands grow).

This keeps the F/J anchor fixed and the finger→key ownership standard; only the
idle key and the per-profile introduction order shift.

## Open questions (the pilot owns these)

- Does growing from F/J by usefulness build a *better* spatial map for a real
  child than home-row-fill — measured how (return-to-home accuracy, time-to-first-
  real-word, retention)?
- Does early reaching help or harm anchor formation? (Hypothesis from the earlier
  discussion: reaching-and-returning is what actually *trains* the anchor, which
  home-row-only drilling never exercises.)
- Is the behavioral calibration probe stable enough session-to-session, and across
  a child's growth, to be worth the per-profile complexity?
- Record return-to-home behavior in the schema to answer these (ties to
  [ADR-024](../adr/0024-drill-content-and-lesson-granularity.md) open Q5 and the
  Douglas & Long 2003 profile in [architecture.md](../architecture.md)).

## Next steps

1. ~~**Content spike**~~ — **done**
   ([intro_order_comparison_spike.py](../../spikes/intro_order_comparison_spike.py),
   [results](../../spikes/results/intro_order_comparison_results.txt)). Five
   F/J-seeded / vowel-early orderings vs the status quo, with the non-word filter.
   Folded into "What the order-comparison spike showed" above: O5 is the sweet
   spot; the prize is modest in English, large in vowel-poor layouts. It also
   quantified the contamination (only ~11–19% of short wordfreq strings are real
   dictionary words), which is now evidence for the
   [ADR-008](../adr/0008-word-list-strategy.md) word-list filter.
2. **Keep introduction order a swappable strategy** so the pilot can A/B
   home-row-fill vs F/J-seed vs calibrated-per-child.
3. **Beta pilot:** run the calibration probe as an instrument; collect the human
   evidence above.
4. **Then** amend [ADR-023](../adr/0023-key-introduction-protocol.md) — the
   amendment is the *output* of 1–3, not the input. Note the ripple: Bronze is
   currently "home row known," which must be redefined under an F/J-seed model
   (ties to the milestone-model work tracked in [roadmap.md](../roadmap.md) §A2/B6).
