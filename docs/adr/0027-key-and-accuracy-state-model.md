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
| **Known** | Derived: `attempt_count ≥ 90 AND correct_count / attempt_count ≥ 0.90 AND distinct_practice_days ≥ 2` (evaluated over the rolling window — see below) | No — always computed |

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

**Why ≥ 2 distinct practice days:** motor memory consolidates during sleep. A child who accumulates 90 attempts in one sitting has not yet had a sleep cycle to consolidate the skill. Two distinct calendar days guarantees at least one night between first and most recent practice. This is the minimum bar, not a high one — a child practicing on consecutive mornings clears it easily. The ≥ 2 floor is configurable: `config.KNOWN_MIN_DISTINCT_DAYS` (ADR-025).

**Relationship to `key_stats`:** `key_stats` retains its lifetime aggregate counters (`attempt_count`, `correct_count`, `last_practised_at`). Those are used for gamification displays (total attempts, milestone history) and are never the source of truth for Known. `key_attempts` is authoritative for Known.

### First-Attempt Counting Semantics

`key_stats.attempt_count` = number of prompts in which this character was the expected target (one per Layer-1 drill invocation, or one per character position in a Layer-2 word).

`key_stats.correct_count` = number of those prompts where the first keystroke was the correct character.

The **first** keystroke response to a prompt determines the outcome for that prompt:

- First press correct → `attempt_count + 1`, `correct_count + 1`, advance.
- First press wrong → `attempt_count + 1`, `correct_count + 0`; auto-rejection fires; engine stays on the same character. All subsequent keypresses until the correct character is entered are ignored for `key_stats` — they do not increment either counter.

`key_stats.last_practised_at` is updated on every keystroke that answers a prompt — the counted first press, and every subsequent press until the correct character arrives — so it tracks recency of any engagement, not just successful ones. *(Clarified 2026-08-22, alpha session 7: this section previously said "on every prompt", which contradicts the timeout rule below — an unanswered prompt writes nothing, and the only write path that could create the row on prompt issue is `upsert_key_stat`, which would count an attempt nobody made. Recency is therefore written by keystrokes only, and a character becomes Active on its first counted keystroke rather than at prompt issue.)*

**Timeouts:** a configurable auto-advance timeout (Layer-1, see ADR-012) that fires when the child has not responded does not affect `key_stats`. The prompt is silently re-issued. Only a keystroke response triggers counting.

**Held keys and OS auto-repeat — resolved 2026-08-22 (alpha session 7; raised by session 6b).** Holding a key makes Windows emit repeated press events, and [ADR-005](0005-keyboard-handling.md)/session 5 pass them through faithfully. The focus model suppresses repeats only for its own *gesture* keys (Escape's tap/hold, the resume hold), because whether a held **character** counts as repeated attempts is a counting question, not a gating one — so the engine receives every repeat.

The rule above absorbs the harmless case: repeats of a *wrong* press are already ignored until the correct character arrives. The damaging case is a held *correct* key — the first press is counted and advances the prompt, and the repeats that follow land on the **next** prompt as wrong first presses, each one incrementing `attempt_count` with `correct_count + 0` and firing an auto-rejection. One key held a beat too long can therefore tank the accuracy of a character the child never actually got wrong, and on a rolling 200-attempt window that distortion persists for a long time.

**Rule: a press that repeats a character key still physically down is not an attempt.** It creates no `key_stats` row, moves neither counter, appends no `key_attempts` row, and does not bump `last_practised_at`. It does not answer the prompt either, and fires no auto-rejection — nothing happened, so the child hears nothing. A key held produces exactly one attempt no matter how long it is held.

**The doubled letter decides itself under this rule.** `ll` in "hello" is two prompts. A child who releases between them produces two distinct actuations, neither of which repeats a key that is down, so both count normally. A child who holds the key through both produces one attempt, and the second `l` stays open until they lift and press again — which is the thing being taught: a doubled letter is two keystrokes, and the tutor must not accept one held key as two. The rule is therefore *not* de-duplication by character or by elapsed time, either of which would have to choose between these two cases by guessing. It keys off physical down-state, which is exactly what separates them.

**Two Windows assumptions this rests on, unverified until alpha session 12.** Both are behaviours of the real pynput path that no Linux test can exercise, and the rule is wrong if either fails. (1) OS auto-repeat delivers repeated *press* events with no intervening release — if Windows or pynput synthesises a release between repeats, every repeat reads as a fresh actuation and the rule silently does nothing. (2) A press and its release report the same character for the same physical key. `KeyCode.char` is recomputed from live modifier state, so a Shift released a beat before the letter reports `A` down and `a` up; the focus model case-folds both sides to absorb that, which fails if release instead reports `None` or an unrelated character, leaking a down entry that costs one ignored press of that key. Confirm both by hand on Windows and correct here if either is wrong.

**Where each half lives.** The focus model labels the press — `TypedCharacter.repeat` — because down-state is a physical fact of the input stream and the gate already tracks it for gesture keys; it still suppresses nothing, so the engine sees every repeat. The counting decision, *repeat ⇒ not an attempt*, is this section's, implemented in `AttemptCounter` (`takki.lesson.attempts`). A release missed while Takki is off the foreground (the secure desktop) leaks one down entry, and the next release of that character clears it: the cost is one ignored press of one key, never a stuck prompt.

**Consequence:** `correct_count / attempt_count` is true first-attempt accuracy. It cannot be inflated by retry presses.

### Bronze Criterion

ADR-010 defines a key as Known when "first-attempt accuracy has been sustained above 90% **across multiple sessions**." The rolling window (§ above) and the ≥ 2 distinct practice days condition are the concrete implementation of that phrase.

**Resolution:** Known = `attempt_count ≥ 90 AND correct_count / attempt_count ≥ 0.90 AND distinct_practice_days ≥ 2` over the rolling window in `key_attempts`. The phrase "across multiple sessions" is now grounded in calendar days, not app-session count — sleep is the motor consolidation mechanism. A child who has 90 attempts at ≥ 90% accuracy spread across at least two calendar days has demonstrated genuine retention backed by at least one sleep cycle.

`session_key_stats` (previously deferred to Beta in ADR-011) is not needed for this criterion and has been dropped from the Beta plan. ADR-011 is updated accordingly.

**Superseded 2026-08-23 — Bronze is no longer positional.** The criterion above ("all home-row characters are Known") certified a skill it could not observe. `key_attempts` records one row per prompt with `correct` = first keystroke right, and nothing about what preceded the prompt — so it cannot distinguish a child who reached away and *found* F again from a child whose finger never left F. Under home-row-first drilling the second case is the common one, so a child could bank 90 correct F presses without their hand ever having moved. Bronze certified anchor security on evidence containing no anchoring.

Bronze is replaced by the six-rung ladder in [§ Milestone Ladder](#milestone-ladder) below, whose first rung is an explicit anchor gate that measures the reach. See [§ The Anchor Gate](#the-anchor-gate).

### Milestone Denominator

ADR-010 says Silver and Gold count "distinct **alphabetic characters** on the layout." ADR-023 says thresholds count "**physical keys** known, composite graphemes excluded." These diverge for any language that uses a dead key or AltGr modifier, because the modifier is a physical key but not a character.

**Resolution:** All milestone denominators count distinct typeable **graphemes** (output characters) returned by `get_layout_positions()`, not physical key actuations. Modifier keys such as AltGr and dead keys are keystroke mechanics; they produce no character on their own and are excluded from the denominator. The characters they help produce — `á`, `é`, `ð`, `ž`, etc. — are in the denominator on the same footing as any other character.

ADR-010's "alphabetic characters" wording is authoritative. ADR-023's "physical keys" wording is superseded by this ADR on this point. The handling of modifiers as drill targets (if any) is deferred to ADR-028.

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

**Criterion.** The six index home-column keys — positions (2,4) (3,4) (4,4) and (2,7) (3,7) (4,7), which are `r f v` / `u j m` on every QWERTY-derived layout in the target set — are each Known at the **anchor bar**: `attempt_count ≥ ANCHOR_MIN_ATTEMPTS AND accuracy ≥ ANCHOR_MIN_ACCURACY AND distinct_practice_days ≥ KNOWN_MIN_DISTINCT_DAYS`. Defaults: 25 attempts, 0.95 accuracy, 2 days. Fewer repetitions than the general Known floor of 90, at a higher accuracy bar — this is a shorter, stricter gate, because a child who is only 90% sure where home is has not got an anchor.

**Why plain accuracy is valid here, when it was not for Bronze.** The gate is evaluated over the Stage 0 drill, whose content is confined to one finger's home column and alternates the anchor with its own reaches (`f ↔ r`, `f ↔ v`). Every anchor prompt is therefore preceded by a keystroke that took the finger off home, so first-press accuracy on F *is* return-to-anchor accuracy. The measurement problem that sank the old Bronze was a property of home-row-only drill content, not of the metric — fix the content and the metric becomes sound. This is why the gate needs no new column in `key_attempts`, and it fires once on stage completion rather than as a rolling query, so ordinary drilling afterwards cannot dilute it.

**The stretch columns are excluded on purpose.** `t g b` / `y h n` (columns 5 and 6) train lateral displacement, a different skill from leaving home vertically and returning to the bump. Mixing them into the anchor stage blurs the one thing it exists to establish. They belong to the curriculum proper.

**Anchor accuracy is maintained, not just earned.** Losing the anchor degrades every key position that is described relative to it, so `f` and `j` are held to `ANCHOR_MIN_ACCURACY` for the life of the profile: when either falls below it in the rolling window, the drill generator re-injects anchor return-drills into the next block. This reuses [ADR-024](0024-drill-content-and-lesson-granularity.md)'s spaced re-exposure slot with an accuracy trigger in place of the staleness trigger, and needs no extra data — once drills mix keys, virtually every `f` press already follows a different key, so ordinary rolling accuracy is return accuracy from that point on.

**The milestone itself is never revoked.** Milestones are one-time events (§ Key States); a dropped anchor triggers remediation, not the withdrawal of something the child earned. The two mechanisms are deliberately separate.
