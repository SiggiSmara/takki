# Research note: repetitions, retention, and the session concept in motor learning

> **Status:** Decisions made — see [ADR-027](../adr/0027-key-and-accuracy-state-model.md), [ADR-010](../adr/0010-lesson-structure-and-progression.md), [ADR-024](../adr/0024-drill-content-and-lesson-granularity.md)
> **Date:** 2026-06-14
> **Sources:** see [references.md](references.md)

**One-line summary:** The closest research analog (graphomotor learning in 7–8 year olds)
puts the minimum for robust long-term retention at ~180 repetitions total, with the
effective distributed protocol using 90 reps/day across multiple days — which sets the
Known floor at 90, the rolling window at 200, the per-session target at 45–90 per active
key, and reframes "multiple sessions" as "multiple calendar days" (sleep is the
consolidation mechanism, not session count).

---

## The question

At the time of writing, [ADR-027](../adr/0027-key-and-accuracy-state-model.md) set the Known criterion at
`attempt_count ≥ 50 AND correct_count / attempt_count ≥ 0.90` over a rolling window,
with the window size deferred as "a few hundred, needs research." This note does that
research and surfaces follow-on design questions ADR-027 did not close:

1. What minimum attempt count is empirically defensible for Known?
2. What is the rolling window size that meaningfully spans "multiple sessions"?
3. What does "session" actually mean for motor retention — and does Takki's current
   session concept align with it?

## What the research shows

### Closest analog: graphomotor learning in 7–8 year olds

Letter-formation (graphomotor) research on children aged 7–8 is the best available
proxy for per-key touch-typing — same age band, same task structure (single character,
repeated), same fine motor system.

Danna et al. tested practice dose in a single training session:

| Repetitions | Outcome at 4–5 weeks |
|---|---|
| 90 (6 blocks × 15) | No long-term retention gains |
| 180 (12 blocks × 15) | Robust long-term speed and accuracy gains |
| 360 (24 blocks × 15) | Similar gains to 180 but *less accurate* — massed practice past the threshold hurts precision |

**The 90-rep floor is hard:** below it, children retain essentially nothing at follow-up.
**The 180-rep threshold is the target** for robust single-session learning.
**Over-drilling past 180 is counterproductive** for accuracy — relevant to drill pacing.

The distributed-practice result requires one careful reading. The distributed group was
6 blocks/day × 4 days = 24 blocks total (360 reps) — the same total as the massed-24
group, not the massed-12. So the comparison is equal total reps distributed vs. massed,
not less-distributed vs. more-massed.

At end-of-training and at 24h, the massed-24 group led on speed. By 4–5 weeks, the
distributed group had caught up in speed and was more accurate — and critically the
massed-24 group *deteriorated* between 24h and 4–5 weeks while the distributed group
continued to improve. The distributed group also outperformed on transfer tasks.

**The direct comparison between distributed 6×4 (360 total) and massed-12 (180) at
4–5 weeks is not reported in available abstracts — the full paper is needed to close
this.** What we can infer: massed-12 ≈ massed-24 in speed at 4–5 weeks (but more
accurate); distributed ≥ massed-24 at 4–5 weeks. So distributed likely approaches or
surpasses massed-12 at 4–5 weeks and beyond, and the trajectory (still improving vs.
declining) favours distributed strongly over the longer term.

**Children need more than adults.** Multiple papers note that practice doses producing
long-term gains in adults produce only short-term gains in children. The adult literature
cannot be scaled down directly.

### Sleep consolidation

Motor memory consolidation after practice is consistently documented across the motor
learning literature. Skills improve *between* sessions without additional practice —
termed "offline gains." The mechanism is sleep-dependent replay and myelination of motor
sequences. This is not a minor effect: performance the day after practice is reliably
better than at the end of the practice session itself.

For Takki, this means the design goal should be to ensure each key accumulates evidence
across multiple days, not multiple sessions on the same day. Two practice sessions before
bed produce one sleep cycle of consolidation; the same two sessions spread across two
days produce two.

### Finger-tapping sequence studies

The dominant experimental paradigm for human finger motor learning uses sequential
5-key taps (analogous to typing, but sequences rather than individual characters). Typical
protocols use 36 trials per session. Critically: 95% of within-session learning gains
occur by around trial 11. The remaining trials in a session yield diminishing within-
session returns — their value is consolidation setup, not immediate performance gain.

This reinforces that within-session attempt counts above ~30–40 per key have low marginal
within-session value. The cross-session (sleep) effect is where durable memory forms.

### Power law of practice

Performance improves as the logarithm of repetition count — fast initial gains, then
diminishing returns. This is well-established across motor tasks. The practical
implication: the first 50 attempts on a key produce the most learning per attempt; the
next 150 still matter for consolidation and regression detection, but the curve has
flattened significantly.

## Design implications

### 1. The Known minimum should be ~90, not 50

50 attempts is below the research floor for any long-term retention in children (90 reps
= no gains in the graphomotor study). A child who accumulates 50 attempts at ≥90%
accuracy has demonstrated good within-session performance — not durable motor memory.
**Revise ADR-027's Known minimum from 50 to 90.** This is a direct, evidence-grounded
number.

### 2. Rolling window of ~200 is the right order of magnitude

The 180-repetition threshold for robust single-session retention is the natural anchor
for the window:

- Window < 180: a single intensive session can fill the entire window and trigger Known.
  That child has not demonstrated multi-day retention.
- Window ≈ 200: requires roughly 4–7 typical practice days at 45–90 key-attempts per
  session (the target range per ADR-010). Aligns with the distributed-practice evidence.
  Regression detection is responsive (a genuinely struggling key moves below threshold
  within 2–3 sessions).
- Window > 300: regression detection becomes sluggish; a child who has lost a key stays
  Known for too long.

**Default window: 200 attempts, configurable (ADR-025).**

### 3. "Multiple sessions" should mean "multiple calendar days"

This is the sharpest finding. Takki's current session concept (app open → app close) does
not align with what the motor learning literature means by "session." The literature's
"session" is defined by its relation to sleep: sessions separated by sleep produce
independent consolidation cycles; sessions within the same day share one.

A child who opens Takki three times in an evening has three app sessions but one sleep
cycle. A child who opens Takki once each morning for three days has three sessions and
three sleep cycles — much stronger consolidation.

**The consolidation-relevant unit is the calendar day, not the app session.**

With timestamps stored in `key_attempts`, this is directly queryable without any
additional schema:

```sql
SELECT COUNT(DISTINCT date(attempted_at))
FROM key_attempts
WHERE profile_id = ? AND key_char = ?
```

This gives "number of distinct practice days in the rolling window." The Known criterion
can then be:

```
attempt_count ≥ 90
AND correct_count / attempt_count ≥ 0.90
AND DISTINCT practice days ≥ 2
```

The ≥ 2 days floor is the minimum for at least one sleep consolidation cycle. It is a
soft gate, not a high bar — a child practicing two days in a row easily clears it.

### 4. ~90 attempts per key per session is a practical ceiling

The massed-practice results reveal a per-session diminishing-returns cliff: massed-24
(360 reps in one session) was less accurate than massed-12 (180 reps) and its gains
deteriorated over time. The distributed group's advantage is not just that it has
multiple sleep cycles — it is also that each session is *shorter*, staying in the zone
where practice reinforces rather than degrades precision.

Approximately 90 attempts per key per session appears to be the ceiling beyond which
single-session practice starts to cost accuracy. Above ~180, the evidence is clearly
negative for children (accuracy penalty, deterioration at follow-up).

This has a direct implication for lesson design (ADR-010): the engine should not drill
any single key more than approximately 90 times in one session. The ceiling is a soft cap
configurable in ADR-025; default ~90.

The distributed protocol's per-day dose (90 reps/character/day) is also the design
target — not merely an upper bound. ADR-010 and ADR-024 set the per-session target range
at **45–90 attempts per active key** (cumulative across Layer 1 drills and Layer-2 word
practice). Multi-key rotation in Takki's natural operation lands sessions in this range
without artificial enforcement.

### 5. The per-session target is 45–90 per active key

The distributed protocol that produced the best outcomes used **90 reps per character per
day**. That is the per-day dose the research directly supports. Takki cannot replicate
the single-character focus of the research (children practice multiple keys in rotation),
but it can target the same per-key per-day count across both layers combined.

The finger-tapping finding (95% of within-session *performance* gains by trial ~11,
diminishing returns above 30–40) is consistent with this: the value of attempts above
30–40 is not additional within-session performance gain, but consolidation setup —
ensuring enough signal exists for sleep-dependent replay. The graphomotor evidence
suggests 90/day is the threshold where that consolidation reliably occurs.

**Design target: 45–90 attempts per active key per session** (ADR-010, ADR-024). 45 is
the soft floor (session-complete signal fires when all active keys reach it); 90 is the
soft ceiling (over-drilling guard). A session in this range matches the researched
distributed protocol's per-day dose. Below 45, a session may not provide enough signal
for that night's sleep consolidation to operate on.

## What this leaves open

**Does the Takki session table serve any purpose for Known computation?**

With calendar days computed directly from `key_attempts.attempted_at`, the `sessions`
table is not needed for the Known criterion. Its remaining uses are:

- Session duration (for parent progress reports — ADR-014)
- `ended_at` for WPM trend (sessions + `word_stats`)
- Identifying "sessions in progress" (NULL `ended_at`)

None of these require `session_key_stats`. That table has been dropped from the Beta plan in ADR-011.

**Is the ≥ 2 days floor the right policy, or should it be higher?**

The research supports "at least one sleep cycle" (≥ 2 days). A stricter ≥ 3 days floor
would require two sleep cycles before Known — more evidence of durable retention but a
slower path. This is a configurable parameter under ADR-025; the default of 2 is
research-grounded and conservative enough for Alpha.

**Does "calendar day" behave oddly at session boundaries near midnight?**

A child practicing from 11:45 pm to 12:15 am straddles two calendar days and might
artificially satisfy the 2-day criterion in one sitting. `datetime.now().date()` at
attempt time is the natural implementation; this edge case is real but rare and
low-stakes (the child is accumulating genuine practice regardless of the date boundary).

## Status of decisions informed by this note

1. ✓ **ADR-027 amended** — Known minimum 90; ≥ 2 distinct practice days; window 200; `key_attempts` schema.
2. ✓ **ADR-010 amended** — per-key session target 45–90; ceiling ~90; session length adaptive (10–20 min); "few minutes" applies to blocks not sessions.
3. ✓ **ADR-024 amended** — 45/key session floor as session-complete signal; spaced re-exposure clock to switch to `last_practised_at` in Beta.
4. ✓ **`session_key_stats` dropped** from ADR-011 Beta plan.
5. ✓ **`sessions` table kept** — still serves duration and WPM reporting.
6. **Open: obtain the full Danna et al. paper** — need the direct 4×90-distributed vs. 180-massed comparison at 4–5 weeks to confirm the per-session ceiling number.
7. **Open: pilot data** — will let us calibrate the window size and day-floor empirically against real children's practice patterns; both are configurable without a schema change.
