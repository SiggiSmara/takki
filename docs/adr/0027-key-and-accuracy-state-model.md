# ADR-027: Key & Accuracy State Model

**Status:** Accepted  
**Date:** 2026-06-14

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

**Why ≥ 90 attempts:** 90 reps per key is the graphomotor research floor — below it, children in the 7–8 age band retain essentially nothing at 4–5 week follow-up. See [motor-learning-repetitions.md](../research/motor-learning-repetitions.md). Configurable: `config.KNOWN_MIN_ATTEMPTS`, with `config.KNOWN_MIN_ACCURACY` for the 0.90 accuracy floor (ADR-025).

**Why ≥ 2 distinct practice days:** motor memory consolidates during sleep. A child who accumulates 90 attempts in one sitting has not yet had a sleep cycle to consolidate the skill. Two distinct calendar days guarantees at least one night between first and most recent practice. This is the minimum bar, not a high one — a child practicing on consecutive mornings clears it easily. The ≥ 2 floor is configurable: `config.KNOWN_MIN_DISTINCT_DAYS` (ADR-025). *(Noted 2026-10-04, alpha-plan #12f: the floor stands, and its reason is weaker than this paragraph says. The research read for #12f supports practice spread over days, and finds that in children the gain between sessions does not clearly depend on sleep: [known-decay-accuracy-speed.md](../research/known-decay-accuracy-speed.md) § 1b. Read "two days of practice", not "one night of sleep".)*

### Known reads decayed evidence against a confidence bound

*(Amended 2026-10-04, alpha-plan #12f, decided with the developer. The evidence is in [known-decay-accuracy-speed.md](../research/known-decay-accuracy-speed.md).)*

Known's three parts are three different kinds of thing, and only one of them was being read wrongly.

| Part | What it is | Since 2026-10-04 |
|---|---|---|
| `attempt_count ≥ KNOWN_MIN_ATTEMPTS` | A **dose**: the child has pressed the key that many times | Unchanged. Counted as rows in the window. Time does not undo a press |
| `distinct_practice_days ≥ KNOWN_MIN_DISTINCT_DAYS` | A fact about the calendar | Unchanged |
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
- **The anchor rung** reads the same bound at `ANCHOR_MIN_ACCURACY`: see [§ The Anchor Gate](#the-anchor-gate).
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

**`f` and `j` are the root.** They are in every baseline from their first `SPEED_MIN_SAMPLE` timed presses, before they meet the floors, and they have no speed term themselves. Something has to be the root of a comparison, and these are the two keys the fingers rest on.

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
- **Phase C** of the ramp-up reads the same baseline at the same ratio.
- **Milestones** count Known, speed included, and are still never revoked.
- **An answer after a re-read is not in a key's speed**, and this is a known gap, accepted by the developer on 2026-10-04. A prompt that timed out counts as the slowest answer; one the child asked to hear again is untimed and left out, because a re-read can mean "I did not hear it" as easily as "I cannot find it", and nothing yet says which is commoner. So a child who presses re-read on most prompts for a key they hunt for has too few timed answers for the term to apply, and the key can become Known on the floors alone. The pilot's data is where to see how often re-reads happen. The developer's note: the re-read matters more once words are practised, where it is the ordinary way to hear a word again ([roadmap § D](../roadmap.md#d-smaller-gaps-worth-a-line-in-the-relevant-adr), "Typing ahead is not counted").
- **The anchor rung has no speed term.** It asks whether the child finds home, and its criterion stays the bound and the days ([§ The Anchor Gate](#the-anchor-gate)).

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

**What removes a pattern press is that it is wrong.** The drill content is built so that the next prompt cannot be predicted ([ADR-024 § Ramp-up variability](0024-drill-content-and-lesson-granularity.md), property 1), so a press made without listening is a guess, and a guess is counted as the miss it usually is. Two things follow:

- **The speed term reads correct first presses only** ([§ Known has a speed term](#known-has-a-speed-term)). A wrong guess is fast and must not make a key look fast.
- **Whether early answers are heard or guessed has to be visible.** The progress dump prints first-press accuracy by when the answer came: in the letter's first half, in its second half, after it. A first band well under the others means children are following a pattern and the content has failed.

This is accepted until there is more to go on. Nothing has been measured on a blind child, and #12h's run and the pilot are where the 250 ms and the reading above are checked. One thing they cannot check from the data: a press under the floor leaves no row, so nothing counts how often the floor removes one.

**Timeouts:** a configurable auto-advance timeout (Layer-1, see ADR-012) that fires when the child has not responded does not affect `key_stats`. The prompt is silently re-issued. Only a keystroke response triggers counting.

**Held keys and OS auto-repeat — resolved 2026-08-22 (alpha session 7; raised by session 6b).** Holding a key makes Windows emit repeated press events, and [ADR-005](0005-keyboard-handling.md)/session 5 pass them through faithfully. The focus model suppresses repeats only for its own *gesture* keys (Escape's tap/hold, the resume hold), because whether a held **character** counts as repeated attempts is a counting question, not a gating one — so the engine receives every repeat.

The rule above absorbs the harmless case: repeats of a *wrong* press are already ignored until the correct character arrives. The damaging case is a held *correct* key — the first press is counted and advances the prompt, and the repeats that follow land on the **next** prompt as wrong first presses, each one incrementing `attempt_count` with `correct_count + 0` and firing an auto-rejection. One key held a beat too long can therefore tank the accuracy of a character the child never actually got wrong, and on a rolling 200-attempt window that distortion persists for a long time.

**Rule: a press that repeats a character key still physically down is not an attempt.** It creates no `key_stats` row, moves neither counter, appends no `key_attempts` row, and does not bump `last_practised_at`. It does not answer the prompt either, and fires no auto-rejection — nothing happened, so the child hears nothing. A key held produces exactly one attempt no matter how long it is held.

**The doubled letter decides itself under this rule.** `ll` in "hello" is two prompts. A child who releases between them produces two distinct actuations, neither of which repeats a key that is down, so both count normally. A child who holds the key through both produces one attempt, and the second `l` stays open until they lift and press again — which is the thing being taught: a doubled letter is two keystrokes, and the tutor must not accept one held key as two. The rule is therefore *not* de-duplication by character or by elapsed time, either of which would have to choose between these two cases by guessing. It keys off physical down-state, which is exactly what separates them.

**Two Windows assumptions this rests on, unverified until alpha session 12.** Both are behaviours of the real pynput path that no Linux test can exercise, and the rule is wrong if either fails. (1) OS auto-repeat delivers repeated *press* events with no intervening release — if Windows or pynput synthesises a release between repeats, every repeat reads as a fresh actuation and the rule silently does nothing. (2) A press and its release report the same character for the same physical key. `KeyCode.char` is recomputed from live modifier state, so a Shift released a beat before the letter reports `A` down and `a` up; the focus model case-folds both sides to absorb that, which fails if release instead reports `None` or an unrelated character, leaking a down entry that costs one ignored press of that key. Confirm both by hand on Windows and correct here if either is wrong.

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

Bronze is replaced by the six-rung ladder in [§ Milestone Ladder](#milestone-ladder) below, whose first rung is an explicit anchor gate that measures the reach. See [§ The Anchor Gate](#the-anchor-gate).

### Milestone Denominator

ADR-010 says Silver and Gold count "distinct **alphabetic characters** on the layout." ADR-023 says thresholds count "**physical keys** known, composite graphemes excluded." These diverge for any language that uses a dead key or AltGr modifier, because the modifier is a physical key but not a character.

**Resolution:** All milestone denominators count distinct typeable **graphemes** (output characters) returned by `get_layout_positions()`, not physical key actuations. Modifier keys such as AltGr and dead keys are keystroke mechanics; they produce no character on their own and are excluded from the denominator. The characters they help produce — `á`, `é`, `ð`, `ž`, etc. — are in the denominator on the same footing as any other character.

ADR-010's "alphabetic characters" wording is authoritative. ADR-023's "physical keys" wording is superseded by this ADR on this point. The handling of modifiers as drill targets (if any) is deferred to ADR-028. *(Answered 2026-08-23 by [ADR-032](0032-grapheme-led-introduction-and-selectable-ordering.md): a modifier is never a drill target and never a prompt target; the **composite** is, so it acquires a `key_stats` row and counts towards this denominator like any other letter.)*

### Milestone Ladder

*(Rewritten 2026-08-23. Supersedes the four-gate table this section previously carried, and ADR-010's Bronze row.)*

Six key-count rungs, evenly spaced at sixths of the grapheme set, where N = the milestone denominator defined above. The first rung is the anchor gate and is not a fraction — it is six specific keys at a higher accuracy bar.

| # | Slug | Criterion |
|---|---|---|
| 1 | `anchor` | The six index-column keys Known at the anchor bar — see [§ The Anchor Gate](#the-anchor-gate) |
| 2 | `third` | ≥ ⌊N / 3⌋ graphemes Known |
| 3 | `half` | ≥ ⌊N / 2⌋ graphemes Known |
| 4 | `two_thirds` | ≥ ⌊N × 2 / 3⌋ graphemes Known |
| 5 | `five_sixths` | ≥ ⌊N × 5 / 6⌋ graphemes Known |
| 6 | `alphabet` | All N graphemes Known |

Diamond and Speed remain accuracy/fluency gates, not key-count gates, and are unaffected by this rewrite.

**The fractions are hard-coded, not configurable.** They are the shape of the ladder, in the same sense that ADR-024's four-phase ramp-up structure is not configurable even though its thresholds are. Exposing them would let a parent produce a profile whose "half the alphabet" milestone fires at a fifth.

**Rungs 2, 4 and 6 are the old Silver, Gold and Platinum gates unchanged** — 2/6 *is* 1/3 and 4/6 *is* 2/3 — so the rewrite inserts three rungs and replaces one; it does not move any existing threshold.

**Why no rung at 1/6.** For English ⌊26/6⌋ = 4, which would fire before the anchor gate's six keys are Known. The anchor gate occupies the first slot instead, which is also the honest description: it certifies orientation, not coverage.

**Rung 2 is a real capability boundary, not just a fraction.** ADR-010 unlocks Layer 2 (real words) at ≥ 8 Active keys, and ⌊N/3⌋ is ≥ 8 for every layout in the v1 target set (en 8, de 10, is 12). So by rung 2 the child can type real words in any language — a claim the spoken framing can make without checking the layout. The middle rungs have no comparable intrinsic meaning and must not invent one: ADR-010 measured coverage at a fixed key-fraction varying from 5% to 35% across languages, which is why coverage was rejected as a gate in the first place. Their meaning comes from the spoken narrative, not from the arithmetic.

**Slugs are identifiers, never spoken.** The slug is what `milestones.level` stores and is stable for the life of a profile. The spoken name resolves through the per-language YAML tier ([ADR-022](0022-localisation-strategy.md)), with a per-profile override available from Beta onboarding. Three tiers — slug → language default → profile override — matching the shape of [ADR-025](0025-configuration-system.md)'s config tiers. Naming therefore stays reversible and can be tuned against real children during the pilot; a language pack may also choose its own metaphor rather than translating another language's.

### The Anchor Gate

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
