# Unverified findings from the code review of 2026-10-01

> **Status:** Open list. Twelve candidate findings from a review that was cut off before it could verify them. Three are closed. O1 to O4 are confirmed and decided (2026-10-03). O5 and O6 are still unverified, and U1 to U3 stay filed. Verification and the agreed fixes are alpha-plan #12j.
> **Date written:** 2026-10-02.
> **Scope:** code from alpha sessions #12d and #12e, already committed. Nothing here is about #12g or #12i, which were reviewed separately and are closed.

## Where the list comes from

On 2026-10-01 a `/code-review max` was started on the #12g working tree. It hit the account's spend limit before finishing and returned nothing. Its working files and agent transcripts were still on disk, and this list was recovered from them on 2026-10-02.

Two facts about that run decide how much weight the list deserves:

- **It reviewed far more than #12g.** It took its scope as everything not yet pushed to `origin/development`: seven commits plus the working tree, 4,384 diff lines in 21 files. That is #12d, #12e and #12g together, and nearly every candidate is about #12d or #12e.
- **The candidates were never verified.** Ten finder agents ran to completion and produced them. The twelve verifier agents were all cut off. Each finder was told to favour recall, so some of these will be wrong.

The wording below is the review's claim, shortened. Line numbers are approximate and were correct on 2026-10-01.

## Closed

| # | Claim | Outcome |
|---|---|---|
| C1 | `SessionLoop.start()` crashes when the profile's newest introduced step has no letter on the current layout (`ValueError: a step carries one or two graphemes, not 0`) | **Confirmed** by repro on 2026-10-02. Filed for Beta in [roadmap § D](../roadmap.md#d-smaller-gaps-worth-a-line-in-the-relevant-adr), "A profile reused under another language can crash at startup". Not fixed, on purpose: the right behaviour depends on how Beta handles a profile that changes language |
| C2 | The fake store and the real store count practice days differently for a timestamp without a timezone, and the default suite fails outside UTC | **Confirmed**: one test failed under `Pacific/Auckland`. Fixed by alpha-plan #12i, which makes both stores refuse any timestamp that is not UTC |
| C3 | `progress_dump` crashes on a database written before #12d (missing `latency_ms` column and `introductions` table) | **Dropped.** Since #12i a database from before 2026-09-30 is deleted, not opened |

## Open: could be wrong behaviour

Each needs a short repro before anything else is decided.

| # | Claim | Where | Why it would matter |
|---|---|---|---|
| O1 | A pair's faster member records Phase B and Phase C completions while the step is still drilling Phase A content, because `_refresh_ramp` advances every member on its own evidence | `lesson/drills.py`, `_refresh_ramp` | A member can finish its ramp-up without ever meeting Phase B's or Phase C's material. Audible in #12h |
| O2 | A resumed step is rebuilt without its location and modifier clauses and handed to `KeyIntroducer.remember()`, so the re-read key speaks a shortened introduction | `lesson/introducer.py`, `resume_step`; `session.py`, `_resume_ramp_up` | The child hears less than the script they were given |
| O3 | A half-answered pair is split on resume: `resume_step` refuses the pair, the introducer re-emits only the unanswered member, and the answered member never gets a ramp-up | `lesson/drills.py`, `resume_step`; `lesson/introducer.py` | Changes what is practised after a restart |
| O4 | Latency is recorded wrongly in three cases: the start time is stale after a prompt is re-spoken (timeout, pause, re-read); a letter that failed to play is counted as heard; a press before the letter finishes is recorded as no measurement | `lesson/attempts.py`; `speech.py`, `Speaker.on_finished` | Feeds Phase C's speed term, and alpha-plan #12f will reason about a speed term for Known from these numbers |
| O5 | The evidence read is capped at 90 rows, which changes Phase B's run-with-a-budget result for a child who stays more than 90 attempts in Phase B | `lesson/rampup.py`, `EVIDENCE_ROWS` | Narrow: only a child who is struggling in Phase B |
| O6 | `spikes/c7_trace_vs_dump.py` breaks on UTC timestamps | `spikes/` | Only if #12h's run sheet uses that script |

### Repro results for O1 to O4 (2026-10-02, alpha-plan #12j)

All four are **confirmed**: the code does what the review said. None is fixed yet. What to do about each is decided with the developer, and the outcome is added here.

**O1, confirmed.** A pair was driven with one member answered correctly every time and the other wrong every time, for eight blocks. The step stayed in Phase A throughout, and every block was single-letter Phase A content. The correct member recorded Phase A at 10 attempts, Phase B at 30 and Phase C at 60. Same result for Stage 0's `f j` and for the curriculum pair `d k`. The scenario is the extreme case. The general form is that a member that is ahead by *n* presses carries those *n* presses into the next phase's evidence, on the previous phase's content.

**O2, confirmed.** Session 1 introduced `f j` and was quit after six answers. In session 2 the introducer's remembered step describes `j` as *"New letter: J. Use your right index finger."* The original was *"New letter: J. Use your right index finger. Reach three positions to the right from F."* The location clause is lost. It is heard only when the re-read key is pressed while no prompt is open (between blocks, or during a celebration) in a session that resumed a ramp-up. With a prompt open, re-read speaks the letter, as intended.

**O3, confirmed.** Session 1 introduced `f j` and was quit after one answer, to `j`. Session 2 introduced `f` alone, with a different script (*"…Reach three positions to the left from J."*), and ran a solo ramp-up for `f`. Over 150 answers `j` was asked 67 times as `f`'s partner and recorded **no phase completion at all**; `f` recorded all three; and the next step, `r u`, was then introduced. So `j` never has a ramp-up of its own. It needs the session to end after exactly one member of a new pair has been answered, which is within the first two prompts after an introduction.

**O4, confirmed in all three cases**, with a baseline of 600 ms for a press 0.6 s after the letter ends:

- **Re-spoken prompt.** After a 10 s timeout the prompt is spoken again. A press 0.1 s *after* the re-spoken letter ends is recorded as 99 ms. A press 0.1 s *before* it ends is recorded as 10,300 ms, because nothing clears the earlier start time when the re-speak begins. Two presses 0.2 s apart are recorded 10 s apart.
- **Failed letter.** `Speaker.on_finished` sets `letter_finished` for a letter whose `SpeechFinished` has status `failed` (and `cancelled`, if its id still matches), so the answer is timed from a letter the child did not hear.
- **Early press.** A press before the letter has finished sounding is recorded as no measurement. That is the documented meaning of NULL, but it removes the fastest answers from the data, so a median over what is left is biased upward. Alpha-plan #12f needs to know this before it reasons about a speed term.

### Decisions on O1 to O4 (2026-10-03, with the developer)

| # | Decision | Where |
|---|---|---|
| O1 | **Fix.** A member is judged only for the phase the step is in. Its evidence for the next phase starts when the step reaches that phase, not when the member passed its own bar. Recording that moment needs one new stored value per member in `ramp_up_phases`, with no table change, and an ADR-011 and ADR-024 amendment | #12j |
| O2 | **Fix.** A resumed step is rebuilt with its full script, location and modifier clauses included, so the re-read key speaks what the child first heard | #12j |
| O3 | **Fix.** A step is resumed as a pair when either member has been answered. The script is spoken again for the member that was never answered, and the pair's ramp-up continues | #12j |
| O4, re-spoken prompt | **Fix.** The start time is cleared when a prompt begins to be re-spoken, so a press is always timed from the version the child heard last | #12j |
| O4, failed letter | **Fix.** Only a letter whose `SpeechFinished` has status `completed` makes the prompt audible | #12j |
| O4, early press | **Handed to #12f**, with the developer's proposal below | #12f |

**The early-press question, as handed to #12f.** Today latency runs from the end of the letter, and a press before the end is recorded as no measurement. That removes the fastest answers, so a median over the rest is biased upward. Setting them to zero would be wrong in a different way: every early answer becomes a tie at the fastest possible value.

The developer's proposal is to time each press from the moment the letter is *expected* to finish, so an early press gets a negative value. A negative value carries real information: the child recognised the letter before it had finished sounding, which is a sign of fluency. A signed latency keeps the ordering right (faster is smaller), loses no answers, and works with a median and with a ratio against the child's own baseline. It is equivalent to timing from the start of the letter and subtracting that letter's usual length, which removes the per-letter bias ("double-you" against "E") that the end-of-letter rule exists for.

What #12f has to settle before it is built:

- **When the letter started.** The TTS worker reports only when an utterance finishes. Either it also reports when one starts, or the start is estimated from the enqueue time plus SAPI's start-up delay (measured at about 100 to 150 ms in #12b-2).
- **How long the letter is expected to last.** Measured from the child's own completed letters, per letter and voice, for example as a running median of start-to-finish.
- **A floor for anticipations.** A press before the letter could have been recognised, or before it started at all (a typed-ahead key), is not a reaction to it. Reaction-time research normally excludes presses within roughly 100 to 150 ms of onset. Those would stay unmeasured.
- **The stored meaning of `latency_ms`.** A negative value changes what the column means, so it is an ADR-011 amendment, and Phase C's speed term and its baseline have to be re-read under the new meaning.

## Open: upkeep, no wrong behaviour claimed

| # | Claim |
|---|---|
| U1 | **Performance at block boundaries and per keypress.** `window_stats`' local-time conversion is said to make each call about 8 times slower, adding about 50 ms per block boundary. The boundary re-reads the same windows several times. Phase C's baseline is computed for every block (about 33 ms). `_refresh_ramp` re-reads both pair members on each keypress. `RampUpProgress.member()` fetches the whole `key_stats` table. `window_attempts`' `LIMIT` does not bound the SQL work. `_carrier` is rebuilt for each slot. None of these figures has been measured by us |
| U2 | **Untested wiring.** `SpeechFinished` → `letter_finished` → `mark_audible`; the `clock` passed to `AttemptCounter`; `_baseline` → `bar_met`. The real store's `record_phase`, `completed_phases` and `window_attempts(limit)` have no test that runs against both stores. `FakeStore.window_attempts(limit=0)` returns everything |
| U3 | **Dead or stale code.** `RampUpProgress.step_phase` and `live_run`'s `max_rejections` parameter are unused. `record_attempt`'s `correct` parameter is unused. The `begin_step` returns-False branch in `SessionLoop._introduce` is said to be unreachable. Stale comments about local time and re-exposure. `prev_char` is carried across blocks although ADR-011 says NULL means the first of a block. Multi-paragraph docstrings against the project's one-line rule. Duplicated test helpers. The planner's `_need` and `_bar` are a second definition of Known beside `KnownCriterion` |

One part of U1 was checked on 2026-10-02 for #12g: building the remaining introduction sequence costs about 0.5 ms and happens once per block boundary, so it was left as it is.

## Recommendation

Agreed with the developer on 2026-10-02.

1. **Verify O1 to O4 before #12f**, inline and without review agents. Each is a short repro script, like the one that confirmed C1. O4 comes before #12f for the reason in its row.
2. **Verify O5 and O6 before #12h**, since they matter only for that run.
3. **Leave U1 to U3 filed.** Act on one only if a measurement or a later change gives a reason.
4. **Report each repro before fixing anything.** C1 turned out to be a design question and not a missing guard, and some of these may too. A confirmed finding is fixed, filed in the roadmap, or dropped, and this note records which.

## How to review next time

The cost of the cut-off run came from its scope and its size, and both are avoidable:

- **Review the working tree, not the unpushed backlog.** Commit and push finished chunks, or point the review at named files.
- **`high` finished in minutes on #12g and found seven real points.** `max` started at least 22 agents with about 150 turns each for the ten that finished.
- **For more depth than `high`, use a few agents with one question each**, each given the diff and a short list of files, with findings checked inline.
