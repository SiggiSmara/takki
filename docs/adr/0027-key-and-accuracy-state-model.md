# ADR-027: Key & Accuracy State Model

**Status:** Accepted. Amended 2026-11-08 for ADR-033 and ADR-024. Session (4) of alpha-plan #12m built its part on 2026-11-08 (the Anchor Gate retired, the `rest` rung, the bump keys' speed term); session (6) builds the presses that are not attempts.  
**Date:** 2026-06-14  
**Noted:** 2026-11-01 — § First-Attempt Counting: the held-key rule's two Windows assumptions, restated for key events taken from Takki's window (alpha #13). The rule itself is unchanged.  
**Amended:** 2026-11-08 — alpha-plan #12m, for [ADR-033](0033-rest-keys-and-keyboard-alignment.md) and [ADR-024](0024-drill-content-and-lesson-granularity.md): [§ Rest keys, the ladder's presses and the `rest` rung](#rest-keys-the-ladders-presses-and-the-rest-rung). § The Anchor Gate is retired.

> Part of the [Takki architecture](../architecture.md).  
> Closes roadmap issues A2, A3, and B6. Amends [ADR-010](0010-lesson-structure-and-progression.md) and [ADR-011](0011-persistence-and-state.md).

---

**Decision:** Define a two-state key lifecycle (Active / Known); pin counting semantics to prompts rather than keypresses; implement Known via a rolling 200-attempt window with a ≥ 90 attempt floor and ≥ 2 distinct practice days requirement grounded in graphomotor research; and settle the milestone denominator as typeable graphemes, not physical key actuations.

### Key States

A key character has two computational states:

| State | Meaning | Stored? |
|---|---|---|
| **Active** | Has been introduced as a Layer-1 drill target; a `key_stats` row exists | Implicit — row presence |
| **Known** | Derived: `attempt_count ≥ 90 AND correct_count / attempt_count ≥ 0.90 AND distinct_practice_days ≥ 2` (evaluated over the rolling window — see below). *Since 2026-10-04 the accuracy test is a lower confidence bound over decayed evidence ([§ Known reads decayed evidence against a confidence bound](#known-reads-decayed-evidence-against-a-confidence-bound)), and there is a fourth part, speed ([§ Known has a speed term](#known-has-a-speed-term)).* | No — always computed |

All characters start **Unseen** (no `key_stats` row). A character becomes **Active** when the lesson engine introduces it and the child answers the first prompt for it — the first counted keystroke creates the row (see § First-Attempt Counting). A character is **Known** when the criterion above is satisfied at query time.

Known is a derived attribute, not a stored flag. This avoids synchronisation drift and means accuracy drops below 90% are reflected automatically within the rolling window. Milestones are one-time events (stored in the `milestones` table); they are never reverted even if a key's live accuracy later dips. The Layer-1 weighting engine handles struggling keys through drill frequency, independently of Known status.

*(Amended 2026-11-08, alpha-plan #12m: a rest key has no key state, and a letter that takes ADR-024's ladder becomes Active at its first listened press, at Choose. [§ Rest keys, the ladder's presses and the `rest` rung](#a-rest-key-has-no-key-state).)*

**Terminology alignment:** "Introduced" in ADR-010/023/024 = became Active. "Mastered" in milestone descriptions = Known. There are only two computed states; the different words were used for narrative variety, not to denote distinct thresholds.

### Rolling Window — `key_attempts` Table

Known is evaluated over a rolling window of the most recent N attempts per (profile, key). The schema:

```sql
CREATE TABLE key_attempts (
    profile_id  INTEGER NOT NULL REFERENCES profiles(id),
    key_char    TEXT    NOT NULL,
    attempted_at TEXT   NOT NULL,  -- local time, ISO-8601, same convention as ADR-011
    correct     INTEGER NOT NULL   -- 1 = first keystroke correct, 0 = wrong
);
```

*(The schema above is as first written. `attempted_at` is UTC since 2026-09-30, and the table has since gained `latency_ms`, `prev_char`, `after_letter_ms` and `timeouts`; [ADR-011](0011-persistence-and-state.md) holds the current schema. Noted 2026-10-04, alpha-plan #12f.)*

**Window cap:** at most 200 rows per (profile_id, key_char). On every INSERT, delete the oldest row if the count exceeds 200. This is enforced by the persistence layer, not a SQL trigger. Default 200 is configurable: `config.ATTEMPT_WINDOW` (ADR-025).

**Why 200:** the research floor for robust long-term retention in children is ~180 repetitions. A window smaller than 180 allows a single intensive session to fill it entirely, so the child could reach Known without any sleep-consolidation evidence. 200 requires roughly 3–5 typical practice days at the ADR-010 session target of 45–90 key-attempts per active key per session, matching the distributed-practice model. A window above ~300 makes regression detection sluggish — a child who has lost a key stays Known for too long. See [motor-learning-repetitions.md](../research/motor-learning-repetitions.md).

**Known query:**

```sql
SELECT
    COUNT(*)                                   AS attempt_count,
    SUM(correct)                               AS correct_count,
    COUNT(DISTINCT date(attempted_at))         AS distinct_days
FROM key_attempts
WHERE profile_id = ? AND key_char = ?
```

Known = `attempt_count ≥ 90 AND correct_count * 1.0 / attempt_count ≥ 0.90 AND distinct_days ≥ 2`.

*(Amended 2026-11-01, alpha-plan #12m session 2, review finding E4 of [2026-10-06](../research/code-review-2026-10-06.md), decided by the developer on 2026-10-10: **the practice days are counted outside the window.** Read over the window, 200 presses of a key in one day took away its earlier days, so a Known key stopped being Known until the next day, and needed a slot again. The days are a fact about the calendar (the table below), and the window is built to forget. They are now kept in [ADR-011](0011-persistence-and-state.md)'s `practice_days`, one row per key per local day with an attempt, never trimmed, with the day fixed when the attempt is written. The query is:*

```sql
SELECT
    COUNT(*)     AS attempt_count,
    SUM(correct) AS correct_count,
    (SELECT COUNT(*) FROM practice_days
     WHERE profile_id = ? AND key_char = ?) AS distinct_days
FROM key_attempts
WHERE profile_id = ? AND key_char = ?
```

*The dose and the accuracy are still read over the window, and can still fall. The days floor, once met, stays met. Only an attempt (a `key_attempts` row) makes a practice day: a press that is not an attempt, such as ADR-024's predictable presses or ADR-033's landings, does not. ADR-011 § Records for the alignment, the rest keys and the ladder, "Practice days outside the window (E4)", has the tests.)*

**Why ≥ 90 attempts:** 90 reps per key is the graphomotor research floor — below it, children in the 7–8 age band retain essentially nothing at 4–5 week follow-up. See [motor-learning-repetitions.md](../research/motor-learning-repetitions.md). Configurable: `config.KNOWN_MIN_ATTEMPTS`, with `config.KNOWN_MIN_ACCURACY` for the 0.90 accuracy floor (ADR-025).

**Why ≥ 2 distinct practice days:** motor memory consolidates during sleep. A child who accumulates 90 attempts in one sitting has not yet had a sleep cycle to consolidate the skill. Two distinct calendar days guarantees at least one night between first and most recent practice. This is the minimum bar, not a high one — a child practicing on consecutive mornings clears it easily. The ≥ 2 floor is configurable: `config.KNOWN_MIN_DISTINCT_DAYS` (ADR-025). *(Noted 2026-10-04, alpha-plan #12f: the floor stands, and its reason is weaker than this paragraph says. The research read for #12f supports practice spread over days, and finds that in children the gain between sessions does not clearly depend on sleep: [known-decay-accuracy-speed.md](../research/known-decay-accuracy-speed.md) § 1b. Read "two days of practice", not "one night of sleep".)*

### Known reads decayed evidence against a confidence bound

*(Amended 2026-10-04, alpha-plan #12f, decided with the developer. The evidence is in [known-decay-accuracy-speed.md](../research/known-decay-accuracy-speed.md).)*

Known's three parts are three different kinds of thing, and only one of them was being read wrongly.

| Part | What it is | Since 2026-10-04 |
|---|---|---|
| `attempt_count ≥ KNOWN_MIN_ATTEMPTS` | A **dose**: the child has pressed the key that many times | Unchanged. Counted as rows in the window. Time does not undo a press |
| `distinct_practice_days ≥ KNOWN_MIN_DISTINCT_DAYS` | A fact about the calendar | Unchanged. *(Since 2026-11-01, counted outside the window: § Known query, the note under it.)* |
| accuracy `≥ KNOWN_MIN_ACCURACY` | An **estimate** | The lower confidence bound on the accuracy, over evidence that ages |

**The bound.** The accuracy test was a raw proportion, and 81 correct of 90 passed it. The lower confidence bound on that (Wilson, `CONFIDENCE_Z` = 1, the measure [ADR-024](0024-drill-content-and-lesson-granularity.md)'s need has used since #12e) is 0.864: Known certified "probably above 86%" while the planner worked toward "surely above 90%". Known now asks the planner's question. The bars keep their values, and the test is stricter exactly where the evidence is thin:

| Presses in the window | Correct needed at 0.90 | At 0.95 |
|---|---|---|
| 25 | 25 | 25 |
| 50 | 48 | 50 |
| 90 | 84 (93.3%) | 88 (97.8%) |
| 200 | 185 (92.5%) | 194 (97.0%) |

The 90-press floor does not give way to the bound, which #12e left open. They no longer answer one question two ways: the floor is the dose, the bound is the accuracy.

**Why not a higher bar instead.** The published accuracy figures for typists (1–2% errors) are measured after backspacing. Takki has no backspace and counts the first press, and the comparable figure before correction is roughly 2–7% of keystrokes for practised adults. So 0.90 and 0.95 sit inside real first-press performance, and nothing found supports moving them to another particular number. The mastery-criterion studies agree on a direction only: what is kept later sits at or just below what was demanded, so the criterion should sit above the level wanted. The bound does that, by about three points at 90 presses.

**The decay.** Each press in the window counts for `2^(−age / EVIDENCE_HALF_LIFE_DAYS)`, where age is the time since `attempted_at`. Thirty days by default, configurable ([ADR-025](0025-configuration-system.md)). The bound is taken over the weighted presses and the weighted correct ones. Time does not say the child got worse; it says Takki knows less, so the bound widens and the estimate under it stays where it was. A key therefore stops being Known after long enough away and returns after a few correct presses, because its history still partly counts.

How long "long enough" is follows from the arithmetic, since a bound over n all-correct presses is `n / (n + 1)`:

| Key's window | Bar | Idle time before the bound falls under the bar |
|---|---|---|
| 90 presses, 94.4% (only just Known) | 0.90 | about a month |
| 150 presses, 96% | 0.90 | about 11 weeks |
| 200 presses, 98% | 0.90 | about 16 weeks |
| 200 presses, 100% | 0.95 | about 14 weeks |

A long weekend costs nothing (each press keeps 93% of its weight after three days). Coming back, a key that has just dropped under its bar needs one or two correct presses; one whose evidence has gone completely needs about 10 in a row at 0.90 and 19 at 0.95.

**Why one half-life, and why a month.** Forgetting of a motor skill runs on months and shows first in accuracy: the current meta-analysis (adults) puts half of training's gain lost at about 6.5 months for accuracy and 13 for speed, and the one typing study with retention data found most of the loss within three months. A per-key half-life that started at a day and grew with practice was proposed first and withdrawn: four studies of children find that what one session teaches is kept for two to six weeks, so there is no evidence that a young key is forgotten in days. What a young key lacks is more days of practice, which is **learning**, a different process on a different clock, and Takki expresses it directly through the dose, the practice days and the speed term ([§ Known has a speed term](#known-has-a-speed-term)). Decay models retention and nothing else.

**What decay does not replace.** [ADR-024 § A key waiting for its second day](0024-drill-content-and-lesson-granularity.md) expected decay to make its rule unnecessary. It cannot: 90 correct presses on a key's first day keep their bound above the bar for more than three half-lives, so the next morning that key still has no need. The rule stays.

**What follows elsewhere.**

- **Slots** ([ADR-010](0010-lesson-structure-and-progression.md)): a key that stops being Known takes its slot back, so after a long break no new letter comes until old ones are confirmed again. This is the consequence ADR-010 recorded in advance.
- **Milestones** are still one-time events and are never revoked. A rung not yet earned counts the keys Known today.
- **The anchor rung** reads the same bound at `ANCHOR_MIN_ACCURACY`: see [§ The Anchor Gate](#the-anchor-gate). *(Retired 2026-11-08 with the Anchor Gate. The `rest` rung reads landings, not this bound: [§ The `rest` rung](#the-rest-rung).)*
- **The time is the system clock's**, read as UTC like every other timestamp ([ADR-011](0011-persistence-and-state.md)). A press stamped in the future, after a clock correction, has an age of zero.

**Relationship to `key_stats`:** `key_stats` retains its lifetime aggregate counters (`attempt_count`, `correct_count`, `last_practised_at`). Those are used for gamification displays (total attempts, milestone history) and are never the source of truth for Known. `key_attempts` is authoritative for Known.

### Known has a speed term

*(Added 2026-10-04, alpha-plan #12f, decided with the developer. The evidence, and the spike that chose the baseline, are in [known-decay-accuracy-speed.md](../research/known-decay-accuracy-speed.md).)*

A key the child answers correctly and still has to hunt for is not Known. Accuracy cannot see the difference: with no backspace and no time limit, a slow search ends on the right key. The research on how children learn a motor skill says the same from the other side: accuracy levels off early and the learning that continues over days shows in speed. So Known gets a fourth part.

| Part | What it is |
|---|---|
| The dose, the practice days, the accuracy bound | The **floors**, as above. A key that meets all three **meets the floors** |
| Speed | The key's own speed is at most `KNOWN_MAX_LATENCY_RATIO` (2.0) times the child's baseline |

**A key's speed** is the median time from the letter being sent to the first press (`latency_ms`, [ADR-011](0011-persistence-and-state.md)), over its latest `SPEED_SAMPLE` (30) timed **correct** first presses. Three rules sit inside that sentence:

- **Correct presses only.** A press made without listening is fast and usually wrong, and must not make a key look fast (see "A press before the letter could be heard is not an attempt").
- **An answer that sat through a timeout counts as the slowest there is.** It has no latency, because the letter was spoken again, and it is exactly the answer a speed term exists to notice. `key_attempts.timeouts` is what makes it visible.
- **Below `SPEED_MIN_SAMPLE` (10) timed presses a key has no speed.** A median of a handful is noise.

**The baseline** for a key is the median of the speeds of **`f`, `j` and every other key that meets the floors**, each counted once by its own median. The key being judged is never in its own baseline. Whether the other keys pass their own speed test is not asked.

**A ratio, never milliseconds.** An absolute figure would encode a sighted adult's reaction time into a blind child's curriculum, and nothing has been measured on a blind child. Two is wide on purpose. On the hands-on run of 2026-09-26 the median answer came 1,125 ms after the letter was sent, so the bar would have been 2,250 ms: a second of room, where the differences found between fingers are tens of milliseconds. The term is meant to catch a key the child searches for and nothing finer.

**No baseline or no speed, no term.** A key with too few timed answers, or a profile where nothing else has a speed yet, is judged on the floors alone. A measurement that cannot be made must not hold a key back.

**`f` and `j` are the root.** They are in every baseline from their first `SPEED_MIN_SAMPLE` timed presses, before they meet the floors, and they have no speed term themselves. Something has to be the root of a comparison, and these are the two keys the fingers rest on. *(Amended 2026-11-08: they stay in every baseline from their first timed presses, on a new reason, and they now have a speed term of their own. [§ Known's speed term after the ladder](#knowns-speed-term-after-the-ladder).)*

**Why this pool.** "The median over the child's Known keys", which is what Phase C's term used, is circular once Known itself has a speed term: whether a key is Known would depend on the baseline, and the baseline on which keys are Known. Three ways out were compared in a spike on 2026-10-04:

| Pool for the key being judged | Behaviour |
|---|---|
| **A.** `f`, `j` and every other key that meets the floors | No circle, no ordering. Measures a key against the child's typical key |
| B. `f`, `j` and the Known keys introduced before it | No circle. `f` and `j` stay the yardstick: the first keys after them are judged against the two index fingers alone, for good |
| C. `f`, `j` and every other Known key (the developer's first wording) | Circular. It has two consistent answers; solved from "nobody Known" it gives B's, from "everybody Known" A's |

A and B agree on an even child, on a gradient between fingers, on keys that get slower the later they were introduced, on one hunted key wherever it was introduced, and on a child who is slow on everything. They differ in one situation, a group of keys more than twice as slow as `f` and `j`. Under B a child who is twice as fast on the two home keys as anywhere else has nothing become Known, and with six slots the curriculum stops at the first six keys. Under A those keys outvote `f` and `j` once three of them meet the floors. **A is the decision**: the term is for finding the key that stands out from the child's own typing, and holding a child who is evenly slower away from home would put speed before accuracy.

**What this costs, stated plainly.**

- **The baseline moves with the child.** If everything slows down, nothing is called slow. That is what a ratio against one's own baseline means, and it is the same under B.
- **A slower group passes once it is the majority.** If a consistent sub-group of keys is more than twice as slow as the rest, its keys are held back while they are the minority of the pool and all pass when they become the majority. The split that matters is one hand against the other. The slot gate limits it, since at most `MAX_KEYS_IN_PROGRESS` keys can be short of Known at once, so a slower group can only become the majority while few keys meet the floors. The developer has asked for this to be looked at again for Beta ([roadmap § D](../roadmap.md#d-smaller-gaps-worth-a-line-in-the-relevant-adr), "A consistently slower group of keys").
- **A key's state can change because of other keys.** The pool is the other keys, so a key near the bar can gain or lose Known when another key joins the pool or gets faster.
- **A key near the bar flickers.** With 30 presses a key and a spread of a third between presses, a key truly at 1.8 times its baseline is called slow on about one evaluation in ten, whatever the size of the pool. Known is recomputed on every query, so such a key moves in and out. Milestones are one-time and unaffected; slots and the block plan follow the flicker. Left to #12h and the pilot to say whether it is noticeable.
- **It is lenient by construction.** The time runs from the sending, so it includes the letter's own length (1.1 to 1.3 s on SAPI). A child has to take about a second longer than their usual answer before a key is slow, and a letter with a long name is measured some 150 ms slower than one with a short name. The alternative, timing from the letter's end, gives a signed number that no ratio can be taken on, and needs a letter length that is not always known (ADR-011).

**What follows elsewhere.**

- **Slots** ([ADR-010](0010-lesson-structure-and-progression.md)): a key that only speed keeps from Known is in progress and holds its slot.
- **The block plan** ([ADR-024](0024-drill-content-and-lesson-granularity.md) § Need and Known read one measure) gives such a key a need of `SLOW_KEY_NEED`, since accuracy asks nothing more of it and speed comes from practice.
- **Phase C** of the ramp-up reads the same baseline at the same ratio. *(Since 2026-11-08: ADR-024's one bar, which replaces Phase C's. [§ Known's speed term after the ladder](#knowns-speed-term-after-the-ladder).)*
- **Milestones** count Known, speed included, and are still never revoked.
- **An answer after a re-read is not in a key's speed**, and this is a known gap, accepted by the developer on 2026-10-04. A prompt that timed out counts as the slowest answer; one the child asked to hear again is untimed and left out, because a re-read can mean "I did not hear it" as easily as "I cannot find it", and nothing yet says which is commoner. So a child who presses re-read on most prompts for a key they hunt for has too few timed answers for the term to apply, and the key can become Known on the floors alone. The pilot's data is where to see how often re-reads happen. The developer's note: the re-read matters more once words are practised, where it is the ordinary way to hear a word again ([roadmap § D](../roadmap.md#d-smaller-gaps-worth-a-line-in-the-relevant-adr), "Typing ahead is not counted").
- **The anchor rung has no speed term.** It asks whether the child finds home, and its criterion stays the bound and the days ([§ The Anchor Gate](#the-anchor-gate)). *(Retired 2026-11-08. The `rest` rung has no speed term either: the alignment is not timed. [§ The `rest` rung](#the-rest-rung).)*

Every number here is a starting value. None comes from the literature, and none has been heard by a child.

### First-Attempt Counting Semantics

`key_stats.attempt_count` = number of prompts in which this character was the expected target (one per Layer-1 drill invocation, or one per character position in a Layer-2 word).

`key_stats.correct_count` = number of those prompts where the first keystroke was the correct character.

The **first** keystroke response to a prompt determines the outcome for that prompt:

- First press correct → `attempt_count + 1`, `correct_count + 1`, advance.
- First press wrong → `attempt_count + 1`, `correct_count + 0`; auto-rejection fires; engine stays on the same character. All subsequent keypresses until the correct character is entered are ignored for `key_stats` — they do not increment either counter.

`key_stats.last_practised_at` is updated on every keystroke that answers a prompt — the counted first press, and every subsequent press until the correct character arrives — so it tracks recency of any engagement, not just successful ones. *(Clarified 2026-08-22, alpha session 7: this section previously said "on every prompt", which contradicts the timeout rule below — an unanswered prompt writes nothing, and the only write path that could create the row on prompt issue is `upsert_key_stat`, which would count an attempt nobody made. Recency is therefore written by keystrokes only, and a character becomes Active on its first counted keystroke rather than at prompt issue.)*

**A press before the letter could be heard is not an attempt** *(added 2026-10-04, alpha-plan #12f, decided with the developer).* A child can answer a prompt without hearing it, by following a pattern in the drill or by typing ahead of it. Such a press says nothing about whether the child knows the key, so it is never evidence.

**Rule: a press earlier than `HEARD_MIN_MS` (250 ms) after the letter was first sent to be spoken is not an attempt.** It creates no `key_stats` row, moves neither counter, appends no `key_attempts` row, and is not reported to the ramp-up or the block plan. Unlike a held key it still answers the prompt as far as the child can tell: the cue plays, a correct press moves on and a wrong one re-speaks the letter. After a wrong one the prompt is still open and its next press is the first attempt. The time runs from the *first* sending, so a re-read does not move it, and it needs no measured letter length, so it holds on a session's first prompt. One exception: a wrong press under the floor cuts the letter before it has sounded, so the letter re-spoken after it is the first the child can hear, and both the floor and the timing start again from that one. Without this a child hitting keys every 150 ms had every second press counted (found by the review of 2026-10-04). A keystroke typed ahead of a prompt lands on it the moment it opens and falls under this rule. That is right for a single spoken letter, which cannot be known before it is heard. It is wrong for a word, where the child hears the whole word once and typing ahead is the skill; Layer 2 needs its own rule before it uses this counter ([roadmap § D](../roadmap.md#d-smaller-gaps-worth-a-line-in-the-relevant-adr)).

**The 250 ms is physical, not statistical.** A voice needs 100 to 150 ms to start sounding after the letter is sent (measured on SAPI in #12b-2), and a reaction to any sound takes about 100 ms more (the usual cutoff for an anticipation in reaction-time work is 100 to 200 ms; Whelan 2008). Nothing earlier can be an answer to the letter, whoever is listening. On the hands-on run of 2026-09-26, 15 of 262 first presses were under it.

**Every later press is an attempt and is timed, however early.** A floor at half the letter's usual length was proposed first, from that run: 64 of its 262 first presses came between 170 and 454 ms after the letter was sent, the rest at 719 ms or later, none in between, and the letters took 1.1 to 1.3 seconds. The early group was typed from the fixed cycle #12d has since replaced. It was withdrawn the same day, on the developer's point that the gap is a sighted adult's gap. Blind listeners follow speech far faster than sighted ones (reported: about 22 syllables a second against about 8, Dietrich, Hertrich & Ackermann 2013; and a simple reaction to a sound of 0.21 s against 0.32 s in congenitally blind adults; both from search summaries, neither read in full). A listener like that can know a letter from its first sound and answer 350 to 450 ms after it was sent, which is inside the band the run called pattern presses. A floor there would discard the real answers of the children Takki is for.

**What removes a pattern press is that it is wrong.** The drill content is built so that the next prompt cannot be predicted ([ADR-024 § Ramp-up variability](0024-drill-content-and-lesson-granularity.md), property 1), so a press made without listening is a guess, and a guess is counted as the miss it usually is. *(Amended 2026-11-08: under ADR-024's ladder a press whose letter is predictable on purpose is not an attempt at all, and the reading here holds for the presses that are. [§ Presses that are not attempts](#presses-that-are-not-attempts).)* Two things follow:

- **The speed term reads correct first presses only** ([§ Known has a speed term](#known-has-a-speed-term)). A wrong guess is fast and must not make a key look fast.
- **Whether early answers are heard or guessed has to be visible.** The progress dump prints first-press accuracy by when the answer came: in the letter's first half, in its second half, after it. A first band well under the others means children are following a pattern and the content has failed.

This is accepted until there is more to go on. Nothing has been measured on a blind child, and #12h's run and the pilot are where the 250 ms and the reading above are checked. One thing they cannot check from the data: a press under the floor leaves no row, so nothing counts how often the floor removes one.

**Timeouts:** a configurable auto-advance timeout (Layer-1, see ADR-012) that fires when the child has not responded does not affect `key_stats`. The prompt is silently re-issued. Only a keystroke response triggers counting.

**Held keys and OS auto-repeat — resolved 2026-08-22 (alpha session 7; raised by session 6b).** Holding a key makes Windows emit repeated press events, and [ADR-005](0005-keyboard-handling.md)/session 5 pass them through faithfully. The focus model suppresses repeats only for its own *gesture* keys (Escape's tap/hold, the resume hold), because whether a held **character** counts as repeated attempts is a counting question, not a gating one — so the engine receives every repeat.

The rule above absorbs the harmless case: repeats of a *wrong* press are already ignored until the correct character arrives. The damaging case is a held *correct* key — the first press is counted and advances the prompt, and the repeats that follow land on the **next** prompt as wrong first presses, each one incrementing `attempt_count` with `correct_count + 0` and firing an auto-rejection. One key held a beat too long can therefore tank the accuracy of a character the child never actually got wrong, and on a rolling 200-attempt window that distortion persists for a long time.

**Rule: a press that repeats a character key still physically down is not an attempt.** It creates no `key_stats` row, moves neither counter, appends no `key_attempts` row, and does not bump `last_practised_at`. It does not answer the prompt either, and fires no auto-rejection — nothing happened, so the child hears nothing. A key held produces exactly one attempt no matter how long it is held.

**The doubled letter decides itself under this rule.** `ll` in "hello" is two prompts. A child who releases between them produces two distinct actuations, neither of which repeats a key that is down, so both count normally. A child who holds the key through both produces one attempt, and the second `l` stays open until they lift and press again — which is the thing being taught: a doubled letter is two keystrokes, and the tutor must not accept one held key as two. The rule is therefore *not* de-duplication by character or by elapsed time, either of which would have to choose between these two cases by guessing. It keys off physical down-state, which is exactly what separates them.

**Two Windows assumptions this rests on, unverified until alpha session 12.** Both are behaviours of the real pynput path that no Linux test can exercise, and the rule is wrong if either fails. (1) OS auto-repeat delivers repeated *press* events with no intervening release — if Windows or pynput synthesises a release between repeats, every repeat reads as a fresh actuation and the rule silently does nothing. (2) A press and its release report the same character for the same physical key. `KeyCode.char` is recomputed from live modifier state, so a Shift released a beat before the letter reports `A` down and `a` up; the focus model case-folds both sides to absorb that, which fails if release instead reports `None` or an unrelated character, leaking a down entry that costs one ignored press of that key. Confirm both by hand on Windows and correct here if either is wrong.

*(2026-11-01, alpha #13: key events move from pynput to Takki's own window ([ADR-028 § Event model](0028-composite-input-and-keyboard-ownership.md), "Decided"; [research/key-capture-source.md](../research/key-capture-source.md) § 2). The rule stands; how its two assumptions read changes.*
- *(1) Auto-repeat:*
  - *SDL flags every repeat, and pygame drops the repeat `KEYDOWN`s, so there is exactly one `KEYDOWN` per physical press. The characters repeat as `TEXTINPUT`s with no fresh `KEYDOWN`.*
  - *"Fresh exactly when a `KEYDOWN` arrived since the previous `TEXTINPUT`" agreed with SDL's own repeat flag for 764 of 764 `TEXTINPUT`s [measured].*
  - *`ll` released between presses gives two presses; held, it gives one [measured].*
- *(2) Press and release, same key:* down-state is keyed on the scan code, which is the same on both sides by construction, including with Shift released first [measured]. The case-folding workaround in the focus model is no longer what makes the release find its entry.
- *A release missed off the foreground:* SDL synthesises a `KEYUP` for every held key when focus leaves, so no down entry leaks [measured]. A key still held when focus comes back is invisible until it is pressed again [measured]. That costs nothing: the key counts on its next real press.
- *#14 builds it, and re-runs windows-validation tier C against the new source.)*

**Where each half lives.** The focus model labels the press — `TypedCharacter.repeat` — because down-state is a physical fact of the input stream and the gate already tracks it for gesture keys; it still suppresses nothing, so the engine sees every repeat. The counting decision, *repeat ⇒ not an attempt*, is this section's, implemented in `AttemptCounter` (`takki.lesson.attempts`). A release missed while Takki is off the foreground (the secure desktop) leaks one down entry, and the next release of that character clears it: the cost is one ignored press of one key, never a stuck prompt.

**Consequence:** `correct_count / attempt_count` is true first-attempt accuracy. It cannot be inflated by retry presses.

### Case is folded at the boundary

**Decided 2026-09-20 (pre-alpha-session-12a).** An upper-case answer is correct. `classify()` lower-cases every `Character` it produces (`takki.input.taxonomy`), so case never reaches the lesson engine: prompt targets are lower case, comparisons are lower case, and `key_attempts` rows are written against the lower-case target. Nothing downstream has to know this happened.

The question was raised by a review finding that `AttemptCounter.press` compared `char == target` exactly, so with Caps Lock on, every prompt produced an error cue and a first-attempt miss, forever, in silence. Three things settled it:

1. **Takki teaches typing, not the keyboard.** Shift and capitalisation are out of scope in every phase ([ADR-005](0005-keyboard-handling.md), [roadmap § What is deliberately never taught](../roadmap.md#what-done-looks-like-per-phase)). A child who types `F` when asked for `f` has found the right key. Marking that wrong scores them on a skill the curriculum does not teach and never intends to.
2. **A blind child has no Caps Lock LED.** The rejected alternative — refuse the keystroke but say why — needs a spoken boundary message that does not exist, and would need to be repeated on every keypress until an adult noticed. Rejecting in silence, which is what the code did, is the worst of the three.
3. **The counting semantics above are unaffected.** Folding happens before `AttemptCounter` sees anything, so "first keystroke correct" means what it always meant. The row written is the prompt target's, so an upper-case answer cannot open a second `key_stats` row that no threshold or milestone reads — pinned by `tests/test_session.py::TestCapsLock`.

**`str.lower()`, never `str.casefold()`.** Casefold maps `ß` to `ss` — two characters — and no prompt target is ever two characters, so casefolding would make the German curriculum untypeable. `str.lower()` is single-character for every letter in every alphabet Takki teaches, `ẞ` → `ß` included. Pinned by `tests/test_taxonomy.py::TestCaseFolding`. (Turkish `İ` lower-cases to two codepoints, but Turkish is outside the ADR-006 layout set; it would read as a wrong answer, not a crash.)

This also removes an assumption from the held-key rule above. The focus model folded case in its own down-state tracking to absorb pynput recomputing `KeyCode.char` from live modifier state — `A` down, `a` up for one physical key. That fold now happens once, upstream, so the down-state set is keyed on the physical key rather than on whichever case Shift happened to produce. Point (2) of the two Windows assumptions still needs hand-confirmation, but the failure it guards against is now a missing character rather than a case mismatch.

### Bronze Criterion

ADR-010 defines a key as Known when "first-attempt accuracy has been sustained above 90% **across multiple sessions**." The rolling window (§ above) and the ≥ 2 distinct practice days condition are the concrete implementation of that phrase.

**Resolution:** Known = `attempt_count ≥ 90 AND correct_count / attempt_count ≥ 0.90 AND distinct_practice_days ≥ 2` over the rolling window in `key_attempts`. The phrase "across multiple sessions" is now grounded in calendar days, not app-session count — sleep is the motor consolidation mechanism. A child who has 90 attempts at ≥ 90% accuracy spread across at least two calendar days has demonstrated genuine retention backed by at least one sleep cycle.

`session_key_stats` (previously deferred to Beta in ADR-011) is not needed for this criterion and has been dropped from the Beta plan. ADR-011 is updated accordingly.

**Superseded 2026-08-23 — Bronze is no longer positional.** The criterion above ("all home-row characters are Known") certified a skill it could not observe. `key_attempts` records one row per prompt with `correct` = first keystroke right, and nothing about what preceded the prompt — so it cannot distinguish a child who reached away and *found* F again from a child whose finger never left F. Under home-row-first drilling the second case is the common one, so a child could bank 90 correct F presses without their hand ever having moved. Bronze certified anchor security on evidence containing no anchoring.

Bronze is replaced by the six-rung ladder in [§ Milestone Ladder](#milestone-ladder) below, whose first rung is an explicit anchor gate that measures the reach. See [§ The Anchor Gate](#the-anchor-gate). *(Since 2026-11-08 the first rung is `rest`, read from where the fingers land: [§ The `rest` rung](#the-rest-rung).)*

### Milestone Denominator

ADR-010 says Silver and Gold count "distinct **alphabetic characters** on the layout." ADR-023 says thresholds count "**physical keys** known, composite graphemes excluded." These diverge for any language that uses a dead key or AltGr modifier, because the modifier is a physical key but not a character.

**Resolution:** All milestone denominators count distinct typeable **graphemes** (output characters) returned by `get_layout_positions()`, not physical key actuations. Modifier keys such as AltGr and dead keys are keystroke mechanics; they produce no character on their own and are excluded from the denominator. The characters they help produce — `á`, `é`, `ð`, `ž`, etc. — are in the denominator on the same footing as any other character.

ADR-010's "alphabetic characters" wording is authoritative. ADR-023's "physical keys" wording is superseded by this ADR on this point. The handling of modifiers as drill targets (if any) is deferred to ADR-028. *(Answered 2026-08-23 by [ADR-032](0032-grapheme-led-introduction-and-selectable-ordering.md): a modifier is never a drill target and never a prompt target; the **composite** is, so it acquires a `key_stats` row and counts towards this denominator like any other letter.)*

### Milestone Ladder

*(Rewritten 2026-08-23. Supersedes the four-gate table this section previously carried, and ADR-010's Bronze row.)*

Six key-count rungs, evenly spaced at sixths of the grapheme set, where N = the milestone denominator defined above. The first rung is the anchor gate and is not a fraction — it is six specific keys at a higher accuracy bar.

*(Amended 2026-11-08, alpha-plan #12m: rung 1 is `rest`, all eight fingers landing on their rest keys, and `anchor` is retired. Rungs 2 to 6 are unchanged. [§ The `rest` rung](#the-rest-rung) and [§ The ladder's first slot](#the-ladders-first-slot).)*

| # | Slug | Criterion |
|---|---|---|
| 1 | `anchor` | The six index-column keys Known at the anchor bar — see [§ The Anchor Gate](#the-anchor-gate) |
| 2 | `third` | ≥ ⌊N / 3⌋ graphemes Known |
| 3 | `half` | ≥ ⌊N / 2⌋ graphemes Known |
| 4 | `two_thirds` | ≥ ⌊N × 2 / 3⌋ graphemes Known |
| 5 | `five_sixths` | ≥ ⌊N × 5 / 6⌋ graphemes Known |
| 6 | `alphabet` | All N graphemes Known |

Diamond and Speed remain accuracy/fluency gates, not key-count gates, and are unaffected by this rewrite.

**The fractions are hard-coded, not configurable.** They are the shape of the ladder, in the same sense that ADR-024's four-phase ramp-up structure is not configurable even though its thresholds are. *(2026-11-08: ADR-024 reversed "the four-phase structure is the design" on 2026-10-10. Read the comparison as its four objectives and the order of its levels, which are not configurable while their numbers are.)* Exposing them would let a parent produce a profile whose "half the alphabet" milestone fires at a fifth.

**Rungs 2, 4 and 6 are the old Silver, Gold and Platinum gates unchanged** — 2/6 *is* 1/3 and 4/6 *is* 2/3 — so the rewrite inserts three rungs and replaces one; it does not move any existing threshold.

**Why no rung at 1/6.** For English ⌊26/6⌋ = 4, which would fire before the anchor gate's six keys are Known. The anchor gate occupies the first slot instead, which is also the honest description: it certifies orientation, not coverage. *(Restated 2026-11-08 for a first rung that is not a count of keys: [§ The ladder's first slot](#the-ladders-first-slot).)*

**Rung 2 is a real capability boundary, not just a fraction.** ADR-010 unlocks Layer 2 (real words) at ≥ 8 Active keys, and ⌊N/3⌋ is ≥ 8 for every layout in the v1 target set (en 8, de 10, is 12). So by rung 2 the child can type real words in any language — a claim the spoken framing can make without checking the layout. The middle rungs have no comparable intrinsic meaning and must not invent one: ADR-010 measured coverage at a fixed key-fraction varying from 5% to 35% across languages, which is why coverage was rejected as a gate in the first place. Their meaning comes from the spoken narrative, not from the arithmetic.

**Slugs are identifiers, never spoken.** The slug is what `milestones.level` stores and is stable for the life of a profile. The spoken name resolves through the per-language YAML tier ([ADR-022](0022-localisation-strategy.md)), with a per-profile override available from Beta onboarding. Three tiers — slug → language default → profile override — matching the shape of [ADR-025](0025-configuration-system.md)'s config tiers. Naming therefore stays reversible and can be tuned against real children during the pilot; a language pack may also choose its own metaphor rather than translating another language's.

### The Anchor Gate

> **Retired 2026-11-08**, for [ADR-033](0033-rest-keys-and-keyboard-alignment.md) (2026-10-10), by [§ Rest keys, the ladder's presses and the `rest` rung](#rest-keys-the-ladders-presses-and-the-rest-rung): the `anchor` rung, the anchor bar (`ANCHOR_MIN_ATTEMPTS`, `ANCHOR_MIN_ACCURACY`) and the lifelong hold of `f` and `j` to it all go. The section is kept as the record of what was decided. It is still what the code does until alpha-plan #12m session (4) builds the amendment. *(Removed from the code 2026-11-08 in session (4). A profile that earned `anchor` keeps its `milestones` row; nothing reads it, and the ladder no longer names it, so it is not re-earned and not counted.)*

The first rung certifies that the child can **find home by touch** — the F and J tactile bumps, the one orientation landmark present on essentially every physical keyboard, and the foundation every later key position is described against ([ADR-023](0023-key-introduction-protocol.md) § Location).

*(Since 2026-10-04, alpha-plan #12f: the accuracy in this criterion is the lower confidence bound over decayed evidence, as for Known. 24 correct of 25 no longer passes; it takes 19 presses with no miss, 52 with one, or 79 with two. [ADR-024](0024-drill-content-and-lesson-granularity.md)'s plan has held these six keys to that bound since #12e, so the rung follows what is already practised. Whether it is too strict is for #12h to hear.)*

**Criterion.** The six index home-column keys — positions (2,4) (3,4) (4,4) and (2,7) (3,7) (4,7), which are `r f v` / `u j m` on every QWERTY-derived layout in the target set — are each Known at the **anchor bar**: `attempt_count ≥ ANCHOR_MIN_ATTEMPTS AND accuracy ≥ ANCHOR_MIN_ACCURACY AND distinct_practice_days ≥ KNOWN_MIN_DISTINCT_DAYS`. Defaults: 25 attempts, 0.95 accuracy, 2 days. Fewer repetitions than the general Known floor of 90, at a higher accuracy bar — this is a shorter, stricter gate, because a child who is only 90% sure where home is has not got an anchor.

**Why plain accuracy is valid here, when it was not for Bronze.** The gate is evaluated over the Stage 0 drill, whose content is confined to one finger's home column and alternates the anchor with its own reaches (`f ↔ r`, `f ↔ v`). Every anchor prompt is therefore preceded by a keystroke that took the finger off home, so first-press accuracy on F *is* return-to-anchor accuracy. The measurement problem that sank the old Bronze was a property of home-row-only drill content, not of the metric — fix the content and the metric becomes sound. This is why the gate needs no new column in `key_attempts`, and it fires once on stage completion rather than as a rolling query, so ordinary drilling afterwards cannot dilute it.

**What the gate's validity actually rests on, stated as an invariant** *(added 2026-09-29, alpha-plan #12d.)* The paragraph above argues from Stage 0's *content* — a fixed `f ↔ r` cycle, in which every anchor prompt happens to follow a reach. [ADR-024 § Ramp-up variability](0024-drill-content-and-lesson-granularity.md) shuffles that order to stop the cycle teaching pattern-following, which means the property can no longer be read off the content by inspection. It is therefore promoted to an invariant the drill generator owes this gate, holding over the ramp-up's **cycle** blocks (Phases A and B, which is where Stage 0's own content lives) **for every hand those blocks contain a home key for** — which Stage 0's always do: **between two reach prompts of the same hand there is always an anchor prompt of that hand.** Phase C and steady state keep the statistical reading described below, since their content is sampled from the language rather than cycled. Under it, first-press accuracy on `f` remains return-to-anchor accuracy whatever order the units come in — and allowing the reversed unit direction (`r → f`) makes the return explicit rather than incidental. The gate still needs no new column and still fires once on stage completion. Nothing downstream can detect this being got wrong, which is why it is a property test over generated blocks rather than a comment.

**The latency baseline is the child's own** *(added 2026-09-29, alpha-plan #12d. Since 2026-10-04 `latency_ms` is counted from when the letter was sent, not from its end: [ADR-011](0011-persistence-and-state.md), "`latency_ms` runs from the letter being sent". The baseline is no longer the median over Known keys, the ratio is 2.0, and the term is part of Known as well as of Phase C: [§ Known has a speed term](#known-has-a-speed-term). The paragraph below is kept as written, for its reasoning against absolute thresholds.)* [ADR-011](0011-persistence-and-state.md)'s `key_attempts.latency_ms` gives ADR-024's Phase C a speed term. It is measured from **the end of the spoken prompt**, not from the moment the prompt was issued: a blind child cannot answer a letter they have not finished hearing, and letter names differ in length, so timing from the issue would fold a per-letter offset into a per-key bar — measured, a child genuinely 2.25 times slower than their own baseline came out at exactly the 1.5 ratio and passed. It is expressed as a ratio against the **median latency over this child's Known keys**, which makes this section's vocabulary load-bearing in a new place: Known is the only set with enough attempts across enough days to be a stable reference, and a profile with no Known keys has no baseline, so the term is skipped rather than failed. Absolute millisecond thresholds are rejected outright — they would encode a sighted adult's reaction time into a blind child's curriculum, and the spread between children on this measure is the thing nobody has measured yet.

**The stretch columns are excluded on purpose.** `t g b` / `y h n` (columns 5 and 6) train lateral displacement, a different skill from leaving home vertically and returning to the bump. Mixing them into the anchor stage blurs the one thing it exists to establish. They belong to the curriculum proper.

**Anchor accuracy is maintained, not just earned.** Losing the anchor degrades every key position that is described relative to it, so `f` and `j` are held to `ANCHOR_MIN_ACCURACY` for the life of the profile: when either falls below it in the rolling window, the drill generator re-injects anchor return-drills into the next block. This reuses [ADR-024](0024-drill-content-and-lesson-granularity.md)'s spaced re-exposure slot with an accuracy trigger in place of the staleness trigger, and needs no extra data — once drills mix keys, virtually every `f` press already follows a different key, so ordinary rolling accuracy is return accuracy from that point on. *(Since 2026-10-04, alpha-plan #12f, decided with the developer after both of that session's reviews raised it: "below it in the rolling window" means the same measure the anchor rung, Known and the block plan read, the lower confidence bound over decayed evidence, and no longer the raw share of correct presses. On the raw share `f` at 24 of 25 failed the rung and was not slipping, and an anchor left for months never was, because every one of its old presses was right. The cost is a return-drill more often: at most one slot per anchor per block.)*

**The milestone itself is never revoked.** Milestones are one-time events (§ Key States); a dropped anchor triggers remediation, not the withdrawal of something the child earned. The two mechanisms are deliberately separate.

**When the gate is actually evaluated** *(added 2026-09-10, alpha session 10, which built the detector.)* "Fires once on stage completion rather than as a rolling query" is not implementable as written, because the bar includes `KNOWN_MIN_DISTINCT_DAYS`. The moment Stage 0's last ramp-up ends is a moment at which a child who did the whole stage in one sitting *fails* the gate — so a literal once-on-completion evaluation makes the rung unreachable for exactly the children who did the stage most intensively.

`MilestoneDetector` therefore evaluates the anchor criterion on **every check until it passes, and never again after** — the one-time half of "fires once" is honoured by the persisted `milestones` row, the not-a-rolling-query half only from the moment it fires. Two consequences, both stated rather than hidden:

- **A late anchor is possible.** A child who ends Stage 0 just under the bar on one key earns the rung later, off a window that ordinary drilling has since refilled. § Anchor accuracy is maintained says that is still return-to-anchor accuracy ("once drills mix keys, virtually every `f` press already follows a different key"); the paragraph above says it must not happen ("ordinary drilling afterwards cannot dilute it"). **Those two sentences disagree**, and the detector sides with the first because the second has no cadence that satisfies the two-day floor. Pinned by `tests/test_milestones.py::TestAnchorRungDetection::test_an_anchor_missed_at_stage_0_fires_late_and_out_of_ladder_order`.
- **Ladder order is not guaranteed.** A late anchor can fire after `third`. The rungs are six one-time events, not a sequence with a precondition chain, so nothing in the engine breaks; what breaks is the spoken narrative ADR-010 § Milestone Levels records for the Beta voiceover pass, which tells the anchor story first. Naming that as the cost is the point — the fix is either the narrative or the roadmap § D decision below, not a change here.

Closing the evaluation window when Stage 0 ends would remove both, and would also decide roadmap § D's open "**Does the curriculum wait for the anchor gate?**" in code, by making the rung unreachable for any child the curriculum lets past six keys on day one. That decision belongs to whoever closes § D. **Until it closes, this section is the one place the rung's timing is defined.**

**Several rungs can land on one check.** A long gap between checks, or a session that carries a child from below `third` to past `half`, satisfies more than one rung at once. Every rung crossed is written and returned, in ladder order; none is skipped for having been overtaken, because each is a thing that was earned. How a caller spaces two celebrations is the session loop's problem (ADR-012), not the detector's — it hands back a tuple and says nothing about pacing.

### Rest keys, the ladder's presses and the `rest` rung

*(Amended 2026-11-08, alpha-plan #12m, the ADR-027 session. This is the amendment that [ADR-033 § Amendments this ADR requires](0033-rest-keys-and-keyboard-alignment.md#amendments-this-adr-requires) and [ADR-024 § The ramp-up restated](0024-drill-content-and-lesson-granularity.md#the-ramp-up-restated-four-objectives-and-a-ladder-of-three-levels) ("What this amendment requires elsewhere") ask of this ADR. It supersedes § The Anchor Gate as a whole, the `anchor` row of § Milestone Ladder with its "Why no rung at 1/6", and the root paragraph of § Known has a speed term. Each keeps its text, with a dated note pointing here, as the record of what was decided before.)*

**Not yet implemented.** The code still runs Stage 0, the anchor rung and the anchor bar, and `f` and `j` still have no speed term. Session (4) builds the retirement, the `rest` rung and the speed term. Session (6) builds the ladder, and with it the presses that are not attempts. Nothing writes landings or rest keys before session (7), so the `rest` rung cannot fire in a real session until then. This amendment changes no code.

*(**Built 2026-11-08, #12m session 4**, except the presses that are not attempts, which are session (6)'s. Stage 0, the `anchor` rung, the anchor bar and the maintenance path are gone from the code. `rest` is first in `LADDER`, its criterion is `milestones.rest_reached`, and its read is `Store.first_round_landings`, on both stores, with an index on `landings (profile_id, round)`. `KeyStates` gives `f` and `j` a speed term and keeps them in the pool from their first timed presses; the drill generator withholds Phase C's speed term from them in their own step, as the bar does. The rung's default tests are in `tests/test_milestones.py` (`TestRestRung`, `TestRestRungDayIsLocal`), on seeded stores: nothing writes landings or rest keys before session (7). Two readings were settled while building it; see "Built: how a day is read" below.)*

How to read the marks:

- **[D, ADR-033]**, **[S, ADR-033]**, **[D, ADR-024]** and **[S, ADR-024]**: decided in that ADR on 2026-10-10, with that ADR's mark. Quoted here, not decided again.
- **[S]**: settled with the developer in this session, 2026-11-08. Each was put as a question and answered.
- **[A]**: argued, not measured or tested.

A statement with no mark restates or works out something marked.

#### What changes

- A rest key has no key state, and a letter on the ladder becomes Active at its first listened press.
- A predictable press, a press answering a rest cue and an alignment landing are not attempts.
- ADR-024's bar reads Known's speed baseline in place of Phase C, and `f` and `j` now have a speed term of their own.
- The Anchor Gate is retired: the `anchor` rung, the anchor bar and the lifelong hold of `f` and `j` to it.
- The first rung is `rest`. It is read by day, against each finger's current rest key, and it also fires when the full round retires.
- The ladder keeps six rungs, and the first slot still certifies orientation.

#### A rest key has no key state

- **A rest key is not a key character in this model.** It is never prompted by character, never counted, and in no milestone denominator **[D, ADR-033]**. Active and Known are states of typing targets only. A landing, the key pressed to answer "which one do you want", and a press answering a rest cue write no `key_stats` row, so none of them makes a key Active **[S, ADR-033; S, ADR-024]**.
- **A rest letter is an ordinary typing target as well** **[D, ADR-033]**, with the ordinary states reached by the ordinary presses. That a key is a child's rest key changes nothing in this ADR's counting of its letter.
- **A letter that takes ADR-024's ladder becomes Active at its first listened press, which is at Choose.** For a letter with a Reach level that is its first Choose press **[S, ADR-024]**. A rest letter and the two bump letters start at Choose **[D, ADR-024]** and become Active the same way. This is § Key States' rule unchanged, "the first counted keystroke creates the row", because Reach presses are not counted (below).
- **While a step is at Reach, its new letter is not Active** **[A]**. Nothing that reads the Active set sees it: not the slots, the block plan, the session floor or Layer 2's unlock. That is ADR-024's "it cannot reach the bar, Known, the slots …". No new step can begin meanwhile, because ADR-010's first gate waits for the current step's ramp-up to end.

#### Presses that are not attempts

A press that is not an attempt creates no `key_stats` row, moves neither counter, appends no `key_attempts` row and adds no practice day. § First-Attempt Counting had two kinds. This amendment adds three, from ADR-024 and ADR-033.

| Press | Why it is not an attempt | Where it is kept ([ADR-011](0011-persistence-and-state.md)) |
|---|---|---|
| Earlier than `HEARD_MIN_MS` after the letter was sent | It cannot be an answer to the letter (unchanged) | Nowhere |
| A repeat of a key still down | It is not a new actuation (unchanged) | Nowhere |
| A **predictable press**: the letter at Reach, or a letter asked again after a miss | The child could know the letter without hearing it **[S, ADR-024]** | Reach presses in `reach_presses`; a re-ask nowhere |
| A press answering a **rest cue** | The cue asks by finger for a return, and is never counted, also when the rest key carries an Active letter **[S, ADR-024]** | Nowhere |
| An **alignment landing**, or the key pressed to answer "which one do you want" | There is no wrong answer **[S, ADR-033]** | `landings`; the answer as a `rest_keys` row chosen `answer` |

- **A listened press is an attempt, right or wrong**: a first press on a letter at Choose or Travel that is not a re-ask **[S, ADR-024]**. In general practice every first press is an attempt, as before. The 250 ms floor and the held-key rule apply to listened presses as to every other press.
- **"What removes a pattern press is that it is wrong" now holds where it was meant to** **[A]**. ADR-024 measured the old Phases A and B as predictable (review findings E1 to E3), so their counted presses were the pattern presses § First-Attempt Counting worried about. Under the ladder, Choose and Travel are unpredictable by construction, and a press that is predictable on purpose is not counted. The dump's first-press accuracy by when the answer came keeps its job, read on listened presses.
- **One counted press is still predictable** **[A]**. With a Choose set of two letters, in the first step and the one after it, the cap of two in a row (`MAX_SAME_IN_A_ROW`) makes the prompt after a double certain: about one prompt in three in the first step. ADR-024 kept the cap for #12h's ear and did not call that press predictable, and this amendment does not either. A cap of three would make it about one in seven.
- **The introduction's guided presses are not covered here** **[A]**. ADR-024's objective 1 names them and leaves them to ADR-023. If the child is told which letter to press, they are predictable by the same reading. ADR-024 names only two predictable presses, and this amendment does not add a third. ADR-023's amendment says what they are.

#### Known's speed term after the ladder

- **The bar reads Known's baseline, as Phase C did.** ADR-024's one bar replaces Phase C's, at `STABLE_MAX_LATENCY_RATIO` (2.0) against the same baseline **[S, ADR-024]**. Read "the bar" wherever § Known has a speed term says "Phase C". A speed is read over `key_attempts`, which holds no predictable press, so a Reach press never enters one.
- **`f` and `j` join every baseline from their first `SPEED_MIN_SAMPLE` (10) timed presses**, before they meet the floors **[S]**. This is unchanged, but the reason is new. "The two keys the fingers rest on" no longer picks them out, because under ADR-033 all eight fingers rest on keys. What does:
  - they are the only rest letters fixed by position, so they are the same for every child and in every language;
  - they are the first step under every ordering (ADR-032);
  - both are in every Choose set (ADR-024), so they are timed first.

  The first keys after them need something to be compared with, and only these two have timed presses early enough.
- **The other rest letters are ordinary** **[S]**. They have a speed term, and they join the baseline once they meet the floors, as any key does. Rest letters are per child and can change; the root should not.
- **`f` and `j` have a speed term of their own** **[S]**. Each is judged like any other key, against the baseline without itself: for `f`, that is `j` and every other key that meets the floors. Two reasons.
  - The exemption was never argued. The 2026-10-04 spike compared which keys go *into* the baseline. Joining it early does not require being exempt from it, and the pool is not circular: a key joins it by meeting the floors, which read no baseline.
  - ADR-033 makes `f` and `j` "ordinary letters at the ordinary Known bar" and retires the maintenance that watched them. Kept exempt, they would be the only keys whose speed nothing checks, while they are the keys the index fingers find first.
- **What it costs** **[A]**.
  - In the first steps `f` is compared with `j` alone, and `j` with `f`. A child whose one index finger is more than twice as slow as the other keeps that letter short of Known. It holds a slot, and the block plan gives it `SLOW_KEY_NEED` (ADR-024). With six slots the curriculum still moves on, and the comparison widens as other keys meet the floors.
  - The flicker of a key near the bar (above) is about the same with a pool of one: the 2026-10-04 spike found 12.0% of evaluations at a ratio of 1.8 with `f j` alone, against 9.9% with twenty keys ([known-decay-accuracy-speed.md](../research/known-decay-accuracy-speed.md)).
- **The bar still skips the two bump letters in their own step** **[S]**, as ADR-024 says. In the first step the only comparison it could make is one index finger against the other, and that step's job is to start. Known applies the term to `f` and `j`; the bar does not.

#### The Anchor Gate is retired

**[S, ADR-033]**, as a whole:

- **The `anchor` rung** and its criterion, the six index-column keys at the anchor bar.
- **The anchor bar**: `ANCHOR_MIN_ATTEMPTS` (25) and `ANCHOR_MIN_ACCURACY` (0.95). No key is held to a bar above Known's.
- **The lifelong hold of `f` and `j`**, with its maintenance path. No return-drills are injected for a slipping `f` or `j`. A slipping bump letter is practised more through its need, as any key is ([ADR-024 § Steady-state drill generation](0024-drill-content-and-lesson-granularity.md#steady-state-drill-generation), step 2's note of 2026-10-10).
- **The invariant the gate was owed**, "between two reach prompts of the same hand there is always an anchor prompt of that hand", went with ADR-024's property 2.

The word stays: "the ADRs keep 'anchor' for the two bumps" **[S, ADR-033]**. In the code, `home_anchor_keys` (row 3, columns 4 and 7) stays as the bump letters.

What § The Anchor Gate worked out about when a rung is evaluated carries over to `rest` below.

#### The `rest` rung

**The criterion** **[S, ADR-033]**: all eight fingers land on their rest keys at the first round of each of the last `REST_SETTLED_SESSION_STARTS` (5) sessions. The slug is `rest`, stored in `milestones` like any rung ([ADR-011 § The `rest` rung](0011-persistence-and-state.md#the-rest-rung)). This amendment settles how the criterion is read.

- **One session start per day** **[S]**. The rung reads the last five local days that have a complete first round, and on each of them only the first session whose first round is complete. A session is one run of the program, so read as sessions, five restarts in one sitting would pass. ADR-033's reason for counting session starts is that the hands come to the keyboard cold, and that "ingrained takes longer than two days"; a restart minutes later is not cold. A session's day is the local day of its first round, the same local day `practice_days` uses (ADR-011). The number keeps its name: it counts session starts, one a day.
- **A complete first round** has a landing for each of the eight fingers in round 1 **[S]**. A session whose round 1 was cut short is passed over, and a later session the same day can count. A day with no complete first round is passed over too, neither for nor against, so days away do not break the count.
- **A first round passes** when each of its eight landings is validated and is on that finger's **current** rest key, the key `rest_keys` holds for the finger when the rung is checked **[S]**. For an index finger that is its bump. A hand whose bump press missed has its other landings not counted ([ADR-033 § The alignment](0033-rest-keys-and-keyboard-alignment.md#the-alignment)), so that round fails. A finger with no current rest key fails.
  - **Why the current key, and not the key current at the time of the landing.** The rung certifies the position as it is now. If a finger changes key, the earlier days landed on the old key and the count restarts by itself. Judged against the key of the time, five days could straddle a change and certify a position that moved.
  - **It also lets the first day count.** No finger has a key at round 1 of the first session, because a key is chosen after round 2. If round 1 landed where the finger later settled, that is the cold landing the rung asks for.
  - The rung therefore does not need `replaced_at`. `rest_keys` keeps replaced keys anyway, as ADR-033's record.
  - The earliest the rung can fire is the fifth day with a complete first round.
- **Or: the full round retires** **[S]**. The rung also fires when every finger's current rest key has passed its own test, which is when ADR-033 retires the full round, whichever comes first.
  - Without this the rung can become unreachable. Once the full round retires, the first round is only the two bump presses, so no later day has a complete first round, and the last five such days are fixed for good. A strong rest letter passes its test by being Known, not by landings. A finger that landed wrong on one of those days, with its letter Known, would let the round retire and leave the rung unearned forever.
  - Retirement is ADR-033's judgement that the position is settled enough to stop checking it, and the rung accepts the same judgement.
  - It is read from the store as every finger having a current `rest_keys` row with `passed_at`. What writes `passed_at` for a strong rest letter is session (7)'s, and the rung reads it as written **[A]**.
- **No speed term and no accuracy bound.** The alignment is not timed **[S, ADR-033]**, and a landing has no wrong answer, only a key.
- **When it is evaluated** **[A]**, as § The Anchor Gate worked out for `anchor`: on every check until it fires, and never again after, the `milestones` row being the one-time half. Its inputs change only when a first round is written or a rest key changes or passes, so a check at every block boundary costs one narrow read.
- **It fires late and out of ladder order, routinely** **[A]**. It cannot fire before the fifth day, and `third` (8 Known letters in English) can come earlier. The rungs are one-time events with no order between them, and several on one check are returned in ladder order, `rest` first. Nothing in the engine breaks. The cost falls on the spoken story ([ADR-010 § Milestone Levels](0010-lesson-structure-and-progression.md#milestone-levels), "Narrative framing"), which tells the anchors first. ADR-010's amendment carries it.
- **Never revoked, and not a gate.** A child who later lands elsewhere keeps the rung; a changed rest key is handled by ADR-033, not by withdrawing a milestone. Nothing waits for the rung, as nothing waited for the anchor rung (ADR-010).

**Built: how a day is read** *(2026-11-08, #12m session 4)*.

- **A round's day is computed from its UTC stamp when the rung is checked**, in the machine's zone at that moment (`milestones.local_day`). It is not stored. *Decided by the developer in session (4), who put it as a rule: the database holds UTC only, because mixing UTC and local time has led to trouble before.* A machine moved to another zone moves the days already lived; a permanent move is the only case, and it is accepted. This differs from "the same local day `practice_days` uses" above, which fixes its day when written. **Until the next #12m session**: the developer decided both are replaced by a practice-day number on each session, set when the session starts, so that nothing local is stored and a sitting past midnight is one day ([alpha-plan](../alpha-plan.md), "From #12m session (4)"). The rung's rules do not change with it, only where the day comes from.
- **A session's day is the day of its round 1's first landing**, so a round 1 that crosses midnight belongs to the day it began **[A]**.
- **The days are taken in calendar order**, the last `REST_SETTLED_SESSION_STARTS` of them, and must all pass. A day earlier than another by the calendar but written later (a clock set back) is placed by its date **[A]**.
- **A finger with two landings in one round 1** has both judged; every landing must pass **[A]**. The alignment writes one per finger, so this is a guard, not a case.

#### The ladder's first slot

**Six rungs, `rest` first, and no rung at 1/6** **[S]**. The first rung certifies orientation, not coverage, which this ADR said of the anchor gate and is still true of `rest`. The old reason for having no 1/6 rung, that it would fire before the anchor gate's six keys were Known, no longer holds, because `rest` is not a count of keys. The new reason: a 1/6 rung would count letters and nothing else, and has no meaning of its own. Rung 2 is where words open (Layer 2 at 8 Active letters, ADR-010).

| # | Slug | Criterion |
|---|---|---|
| 1 | `rest` | All eight fingers on their rest keys at the first round of each of the last five days, or the full round retired (§ The `rest` rung) |
| 2–6 | `third` to `alphabet` | Unchanged |

**Considered and not taken: a `sixth` rung** **[S]**, making seven: ⌊N / 6⌋ graphemes Known, 4 in English. It would bring the first celebration early, perhaps on day 2, where it is otherwise `rest` from day 5 or `third`. It was not taken because when the first celebration comes is a question for the spoken story and pacing (ADR-010, ADR-012), not for what the ladder certifies, and the early days are not silent: introductions and Layer 2's unlock are heard. **What would bring it back:** #12h finding the first celebration late. Adding a rung touches no stored data, because a slug is written only when its rung fires.

#### What this amendment requires elsewhere

None of these is made here, except where the row says so.

| Where | What |
|---|---|
| Code, #12m session (4) | Goes: the `anchor` slug, `ANCHOR_CRITERION`, `anchor_reached`, `satisfied_rungs(anchor=...)`, `MilestoneDetector._anchor_reached`, `anchor_keys`, the two `ANCHOR_*` numbers, `DrillGenerator._anchor_drills`, `_anchor_slipping`, and `_bar`'s anchor case. Comes: the `rest` slug first in `LADDER`, its criterion as above, and the narrower read of first rounds with its index. `KeyStates._baseline` stops exempting the bump keys; `bump_keys` stays, for the early pool. Default tests pin the rung on the fake store and the fake clock: not on the fourth day, on the fifth; two sessions on one day count once; a cut-short round is passed over; a wrong landing restarts the count; a changed rest key restarts it; retirement fires it; and it is never evaluated again once fired. Tests that pin "a bump key has no speed term" change |
| Code, #12m session (6) | The presses that are not attempts: Reach presses to `reach_presses`, re-asks and rest-cue presses nowhere, and the first Choose press as the one that makes a letter Active |
| Code, #12m session (7) | Writes the landings, rest keys and `passed_at` the rung reads. Whether a weak rest key's own test, "passes when the landing is right at the first round of the last five sessions" (ADR-033 § The alignment), also reads days as the rung does is ADR-033's; put to the developer there |
| [ADR-033](0033-rest-keys-and-keyboard-alignment.md) | Its status line and its ADR-027 row say this amendment is made, made with it. Three differences from its text, recorded here and in that row: the rung counts one session start a day; a landing is judged against the finger's current rest key; and the rung also fires when the full round retires. Dated notes in § Stage 0 is removed ("The rest position is the ladder's first rung") are owed; session (4), which builds the rung, makes them |
| [ADR-024](0024-drill-content-and-lesson-granularity.md) | Its ADR-027 row says this is made, made with it. The bar's "skipped for the two bump letters" is unchanged and agrees. § Spaced re-exposure's "One slot, two triggers" and "The accuracy trigger needs a sample" still describe the anchor trigger retired here, with no dated note; session (4), which removes the trigger, adds one |
| [ADR-010](0010-lesson-structure-and-progression.md) | Session (4)'s amendment: the first row of § Milestone Levels' table, which mirrors this ADR; the narrative note, now that the first rung fires late and often after `third`; and "Why 6" |
| [ADR-011](0011-persistence-and-state.md) | A status-line note, made with this. § `rest_keys` says the rung needs replaced keys, and § `landings` says it reads the last five sessions; both read differently now, and dated notes are owed by session (4), which adds the narrower read. Session (4) also puts to the developer whether a first round's local day is computed when read, or stored when written as `practice_days` fixes its day |
| [ADR-023](0023-key-introduction-protocol.md) | What the guided presses are, with its amendment. If the child is told the letter, they are predictable and not attempts |
| [ADR-025](0025-configuration-system.md) | `ANCHOR_MIN_ATTEMPTS` and `ANCHOR_MIN_ACCURACY` removed, already in ADR-033's row |
| [alpha-plan](../alpha-plan.md) | Session (4)'s bullets, corrected with this: `f` and `j` get a speed term; the rung is read by day against the current key. #12h's row, with this: the rung needs five days, not five sittings; `REST_SETTLED_SESSION_STARTS` is set to 2 in `config.py` on the laptop for the run and set back after it; test configs and staged databases are decided when the run sheet is written; and the run notes when the first celebration comes |
