# ADR-011: Persistence and State

**Status:** Accepted  
**Date:** 2026-05-17

> Part of the [Takki architecture](../architecture.md).  
> **Amended 2026-11-01 ([alpha-plan](../alpha-plan.md) #12m session 2):** the records [ADR-033](0033-rest-keys-and-keyboard-alignment.md) and [ADR-024](0024-drill-content-and-lesson-granularity.md#the-ramp-up-restated-four-objectives-and-a-ladder-of-three-levels) list, and practice days kept outside the window (review finding E4), in [§ Records for the alignment, the rest keys and the ladder](#records-for-the-alignment-the-rest-keys-and-the-ladder). The amendment ADR-033 asked of this ADR is made. The records exist in the store and nothing writes them yet; their writers are later #12m sessions.  
> **Noted 2026-11-08 ([alpha-plan](../alpha-plan.md) #12m, the ADR-027 session):** [ADR-027 § The `rest` rung](0027-key-and-accuracy-state-model.md#the-rest-rung) reads the first round of the last five *days*, one session a day, and judges each landing against the finger's *current* rest key. So § `landings`' "the last five sessions" and § `rest_keys`' "the `rest` rung will need [replaced keys]" no longer describe the rung. Dated notes in both are owed by #12m session (4), which adds the narrower read.

---

**Decision:** SQLite via Python's built-in `sqlite3` module. Local only, no server, no sync.

### Rationale

Child profiles and progress data need to persist across sessions. SQLite is the right choice because:
- Built into Python's standard library — no additional dependency
- Single file on disk, trivially backed up by parents
- No server, no network, no account required
- Sufficient for the data volumes involved (per-key accuracy history, session logs, milestone records)

Each child has a named profile selected at startup (spoken menu). Multiple children can share one installation.

**Profile portability:** the SQLite file *is* the profile data. It lives at `%LOCALAPPDATA%\Takki\takki.sqlite` on Windows (located via `platformdirs` — see ADR-025). *(Path corrected 2026-09-20: this said `%APPDATA%`, which is the roaming profile. A WAL-mode database must not roam — ADR-025 § App Data Directory carries the reasoning.)* To move a child's progress to another computer, copy that file to the same location on the destination machine, **after Takki has exited**. *(Added 2026-10-07, alpha-plan #12k: the database runs in WAL mode, so while Takki is running, and after it has been killed, part of the data is in `takki.sqlite-wal` beside the file. A copy of `takki.sqlite` alone taken then can be missing recent practice, or everything on a first run. `main()` now closes the store on the way out, which folds the WAL back into the one file. After a crash, starting Takki once and closing it does the same.)* No export/import flow is provided in v1 — the file is the export format. Parents are reminded of this in the parent/teacher summary (ADR-014).

### Schema

#### Alpha tables

```sql
CREATE TABLE profiles (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    language    TEXT    NOT NULL DEFAULT 'en',
    tts_voice   TEXT,               -- NULL → use system default
    tts_rate    REAL,               -- NULL → fall through to app-level config (ADR-025)
    talk_key    TEXT,               -- NULL → fall through to app-level config
    reread_key  TEXT,               -- NULL → fall through to app-level config
    restart_key TEXT,               -- NULL → fall through to app-level config
    ptt_mode    TEXT,               -- NULL → fall through to app-level config; "press_release" or "hold"
    created_at  TEXT    NOT NULL    -- local time, no TZ offset: "2026-05-23T14:30:00"
);

CREATE TABLE sessions (
    id          INTEGER PRIMARY KEY,
    profile_id  INTEGER NOT NULL REFERENCES profiles(id),
    started_at  TEXT    NOT NULL,
    ended_at    TEXT                -- NULL while session is in progress
);

CREATE TABLE key_stats (
    profile_id        INTEGER NOT NULL REFERENCES profiles(id),
    key_char          TEXT    NOT NULL,
    attempt_count     INTEGER NOT NULL DEFAULT 0,
    correct_count     INTEGER NOT NULL DEFAULT 0,
    last_practised_at TEXT,         -- NULL if never practised
    PRIMARY KEY (profile_id, key_char)
);

CREATE TABLE introductions (
    profile_id      INTEGER NOT NULL REFERENCES profiles(id),
    key_char        TEXT    NOT NULL,
    step            INTEGER NOT NULL,  -- per-profile ordinal: groups and orders steps
    position        INTEGER NOT NULL,  -- 0-based; ADR-023 puts the left hand first
    introduced_at   TEXT    NOT NULL,  -- UTC, ISO-8601
    stable_attempts INTEGER,           -- key_stats.attempt_count when ADR-024's bar was met; NULL = not yet
    stable_at       TEXT,              -- UTC; NULL = not yet
    PRIMARY KEY (profile_id, key_char)
);

CREATE TABLE ramp_up_levels (          -- ADR-024's ladder; one row per run of a level
    id                INTEGER PRIMARY KEY, -- the order begun
    profile_id        INTEGER NOT NULL REFERENCES profiles(id),
    key_char          TEXT    NOT NULL,
    level             TEXT    NOT NULL,   -- "reach", "choose", "travel"
    session_id        INTEGER NOT NULL REFERENCES sessions(id),  -- where the step reached it
    started_presses   INTEGER NOT NULL,   -- the presses the level reads, counted at its start
    started_at        TEXT    NOT NULL,   -- UTC
    completed_presses INTEGER,            -- the same count when the letter met the level's rule
    completed_at      TEXT,               -- UTC; NULL = not met in this run
    UNIQUE (profile_id, key_char, level, session_id)
);

CREATE TABLE reach_presses (           -- predictable presses at Reach, apart from key_attempts
    id         INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    key_char   TEXT    NOT NULL,
    correct    INTEGER NOT NULL,       -- 1 = first press right
    pressed_at TEXT    NOT NULL        -- UTC
);

CREATE TABLE landings (                -- ADR-033's alignment, one row per landing
    id         INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    round      INTEGER NOT NULL,       -- 1 = the session's first round
    finger     TEXT    NOT NULL,       -- "L-pink" ... "R-pink" (COL_TO_FINGER)
    key_row    INTEGER NOT NULL,       -- the cell pressed, never a character
    key_col    INTEGER NOT NULL,
    validated  INTEGER NOT NULL,       -- 1 = that hand's bump press this round was the bump
    landed_at  TEXT    NOT NULL        -- UTC; no latency, the alignment is not timed
);

CREATE TABLE rest_keys (               -- one row per finger per key it has rested on
    id          INTEGER PRIMARY KEY,
    profile_id  INTEGER NOT NULL REFERENCES profiles(id),
    finger      TEXT    NOT NULL,
    key_row     INTEGER NOT NULL,
    key_col     INTEGER NOT NULL,
    chosen_by   TEXT    NOT NULL,      -- "landings", "answer", or "bump" for an index finger
    chosen_at   TEXT    NOT NULL,      -- UTC
    ready_at    TEXT,                  -- UTC; NULL = not ready
    passed_at   TEXT,                  -- UTC; NULL = has not passed its session-start test
    replaced_at TEXT                   -- UTC; NULL = the finger's current rest key
);
-- At most one current key per finger:
-- UNIQUE INDEX ON rest_keys (profile_id, finger) WHERE replaced_at IS NULL

CREATE TABLE practice_days (           -- every local day a key had an attempt
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    key_char   TEXT    NOT NULL,
    day        TEXT    NOT NULL,       -- the child's local date, fixed when the attempt was written
    PRIMARY KEY (profile_id, key_char, day)
);

CREATE TABLE ramp_up_phases (
    profile_id         INTEGER NOT NULL REFERENCES profiles(id),
    key_char           TEXT    NOT NULL,
    phase              TEXT    NOT NULL,   -- "A", "B", "C" (ADR-024's ramp-up)
    started_attempts   INTEGER NOT NULL,   -- key_stats.attempt_count when the step reached the phase
    started_at         TEXT    NOT NULL,   -- UTC, ISO-8601
    completed_attempts INTEGER,            -- key_stats.attempt_count when it was passed; NULL = in the phase
    completed_at       TEXT,               -- UTC, ISO-8601; NULL = in the phase
    PRIMARY KEY (profile_id, key_char, phase)
);

CREATE TABLE milestones (
    profile_id  INTEGER NOT NULL REFERENCES profiles(id),
    level       TEXT    NOT NULL,   -- slug: "anchor", "third", "half", "two_thirds",
                                    -- "five_sixths", "alphabet", "diamond", "speed";
                                    -- "rest" (ADR-033) replaces "anchor" from #12m session 4.
                                    -- Never spoken; the name resolves via ADR-022 YAML.
    achieved_at TEXT    NOT NULL,   -- Rungs fired at one block boundary share a stamp.
                                    -- Read back by achieved_at, then rowid: the
                                    -- order earned (alpha-plan #12k, 2026-10-10).
    PRIMARY KEY (profile_id, level)
);

CREATE TABLE key_attempts (
    profile_id   INTEGER NOT NULL REFERENCES profiles(id),
    key_char     TEXT    NOT NULL,
    attempted_at TEXT    NOT NULL,  -- local time, ISO-8601
    correct      INTEGER NOT NULL,  -- 1 = first keystroke correct, 0 = wrong
    latency_ms   INTEGER,           -- the letter being sent to the first press; NULL = unmeasured
    prev_char    TEXT,              -- the preceding prompt; NULL = first prompt of a session
    after_letter_ms INTEGER,        -- the same press from the letter's usual end, signed; NULL = no length known
    timeouts     INTEGER NOT NULL DEFAULT 0  -- prompt timeouts before the first press
);

CREATE TABLE letter_lengths (       -- one row per playback of a letter that ran to its end
    profile_id  INTEGER NOT NULL REFERENCES profiles(id),
    key_char    TEXT    NOT NULL,
    voice       TEXT    NOT NULL,   -- the voice id it was spoken with
    rate        REAL    NOT NULL,   -- the tts_rate it was spoken at
    length_ms   INTEGER NOT NULL,   -- from the letter being sent to its finish
    recorded_at TEXT    NOT NULL    -- UTC; when the row was written, at a block boundary
);

PRAGMA user_version = 1;            -- the schema's version (#12m session 2); a database below it is refused
```

### Timestamps are UTC

*(Added 2026-09-30, alpha-plan #12d.)* Every timestamp in this schema is **UTC**, ISO-8601. Local time is a presentation concern: reports and any spoken or displayed date convert on the way out.

Two things forced it. Naive local strings are not an ordering — an hour repeats every autumn — and this schema is now read positionally by the derived ramp-up and trimmed by the same key, so an ordering that goes backwards is a correctness problem rather than a cosmetic one. And "the same instant" has to survive a machine moving timezone, which a child's laptop does.

**The one place local time is still the meaning is a practice *day*.** ADR-027's Known criterion counts distinct practice days, and that is the child's day at the keyboard, not UTC's — an evening session either side of midnight UTC is one day. So `window_stats` groups by `date(attempted_at, 'localtime')`, and the fake mirrors it by converting rather than by slicing the string. Getting that wrong would move a Known gate by a day for anyone east or west of Greenwich. *(Since 2026-11-01, alpha-plan #12m session 2: the same conversion is made once, when the attempt is written, into `practice_days`, and `window_stats` counts that table's rows. The day is now the one in force at the write, not at the read. See "Practice days outside the window (E4)" below.)*

Rows written before this rule are naive local. They are not migrated: Alpha data is disposable, and a converted timestamp would be a guess at the offset in force when it was written.

**The rule is enforced, not only followed** *(added 2026-10-02, alpha-plan #12i).* Takki creates every timestamp and is their only reader, so a timestamp without UTC is always a mistake and never data.

- **On the way in.** Every `Store` method that takes a timestamp passes it through `takki.persistence.utc_stamp`, which raises `ValueError` unless the value is a UTC instant in the one form the store writes: ISO-8601, whole seconds, offset `+00:00`. A bare time, a time with another offset, a date alone, a non-date and an empty string are all refused, and nothing is written. So are the other spellings of UTC, `Z` and fractional seconds, because `milestones` is ordered by this text and two spellings of the same instant sort differently.
- **On the way out.** `SqliteStore` runs the same check on every timestamp it returns (`Profile.created_at`, `KeyStat.last_practised_at`, `Attempt.attempted_at`, `Introduction.introduced_at`). A database that holds a bare timestamp therefore fails at its first read, which at startup is the profile list. That includes any database written before 2026-09-30: it is deleted, not opened.
- **The fake does the same.** `FakeStore` checks on write with the same function and counts practice days by converting from UTC to the local day, with no second path for bare values. The branch it used to have for them is what let the fake and the real store disagree: SQLite reads a bare value as UTC and converts it, and the fake took it as written.

Why it has to be checked and cannot be left to SQLite: `date(x, 'localtime')` accepts a bare value without complaint and reads it as UTC, so a local time written by mistake would move a practice day silently. The limit is the system clock. UTC is only as right as the clock it is read from, and an offline app cannot tell that the clock is wrong.

The tests follow the same rule. Every timestamp in the suite carries the UTC offset. Tests that count days use instants a minute apart or 24 hours apart, which give the same answer in every timezone, and one test sets the process timezone to show that the same two instants are one day at Greenwich and two in Auckland. The default suite passes under UTC, `Pacific/Auckland`, `Pacific/Kiritimati`, `Pacific/Pago_Pago` and `America/Los_Angeles`.

The `key_attempts` table is a rolling window: at most 200 rows per (profile_id, key_char). The persistence layer deletes the oldest row on each INSERT when the cap is exceeded. This table is authoritative for the Known criterion — see ADR-027.

**`latency_ms`, `prev_char` and the `introductions` table** *(added 2026-09-29, alpha-plan #12d, for [ADR-024 § Ramp-up variability, derived exit bars, and the "I know this one" probe](0024-drill-content-and-lesson-granularity.md).)* Two columns and one table, all for one reason: the ramp-up's exit bars stop being session-local state and become queries over what is already stored, which is what makes a ramp-up survive the app closing. What each buys, since none is speculative:

- **`latency_ms`** is the only signal that separates retrieval from anticipation. Correctness cannot: a child following a predictable cycle presses the right key without hearing the prompt. It is read as a **median ratio against the child's own baseline over their Known keys**, never as an absolute figure — an absolute threshold would encode a sighted adult's reaction time. NULL where no prompt time was available, and a NULL never fails a bar.
- **`prev_char`** makes "correct when the next prompt could not be predicted" derivable after a restart rather than only inside the session that generated it. It is also what lets a later reader check ADR-024's anchor invariant against the stored history instead of trusting the generator. *(Corrected 2026-10-07, alpha-plan #12k: the schema comment said NULL means the first of a block. It means the first prompt of a session, which is what the code has always written. One block follows the next without a break and the hands stay where the last prompt left them, so the prompt before a block's first is real information; only a start of the program has none. A reader who wants block starts cannot get them from this column.)*

**A counted attempt is one transaction** *(added 2026-10-07, alpha-plan #12k.)* A first press writes two things, the lifetime counters in `key_stats` and a row in `key_attempts`. They were two commits, and a process killed between them left the count one ahead of the rows for good. Since `ramp_up_phases` (above), a phase's evidence is the rows since the lifetime count at its start, so that tear moved a phase's evidence by one row: a bar could be met one answer early, or a miss from before the phase charged to it. `Store.count_attempt` writes both in one transaction and `AttemptCounter` calls only that. `upsert_key_stat` and `append_attempt` remain for what writes one without the other.
- **`introductions`** answers *which step is current*, which nothing could answer before: Active is row presence in `key_stats`, and insertion order was recoverable only from an implicit `rowid`. The **`step` ordinal** is what groups a step's members and orders the steps — deliberately not the timestamp. A timestamp cannot do either job: two steps introduced inside one clock tick read as one step of four members, and `max()` over clock strings picks the wrong step for good whenever the clock has stepped backwards, at which point the genuinely current step can never be resumed again. **UTC removes the seasonal case and not the general one:** there is no fall-back hour in UTC, but `datetime.now(UTC)` reads the system clock, which is not monotonic — an NTP correction, a manual fix, or a boot with a dead CMOS battery all step it back. An ordinal is not a clock and needs none of this to be true. `position` keeps the member order ADR-023 defines, since the drill generator reads `members[0]` as the left-hand member.

- **`ramp_up_phases`** records that a member has **passed** a phase of ADR-024's ramp-up, write-once *(and, since 2026-10-04, where the phase began: see "`ramp_up_phases` records both ends of a phase" below)*. See ADR-024 § A phase completion is an event for why this is stored rather than re-derived; the short version is that `key_attempts` is a window built to forget, so a phase read off it un-passes itself when the window rolls, and the curriculum can lock. `completed_attempts` (named `attempts_at` until 2026-10-04) is the key's lifetime `key_stats.attempt_count` at that moment, a count no rolling window can evict.

  **It is its own table rather than an `introduced_at` column on `key_stats`, and that is not a filing preference.** A `key_stats` row *is* Active ([ADR-027](0027-key-and-accuracy-state-model.md) § Key States), so stamping the introduction there would make a key Active before the child had answered a single prompt on it. The introducer reads Active as "already had", so the step would never be offered again and its script — which [ADR-023](0023-key-introduction-protocol.md) § What the introducer remembers calls that letter's only teaching moment — would be silently spent on a child who heard it once and typed nothing. That case is not hypothetical: it is in the #12b-2 log, where `u` was introduced, never answered, and correctly introduced again next session. Keeping introductions separate leaves Active, the milestone denominators, the Layer-2 unlock and ADR-010's gate exactly as they were.

**`ramp_up_phases` records both ends of a phase** *(amended 2026-10-04, alpha-plan #12j, finding O1.)* A row was written when a phase was passed, and the next phase's evidence was read from that count. For a pair that is the wrong starting point: the member that passes first keeps being prompted with the same phase's content while its partner catches up ([ADR-024](0024-drill-content-and-lesson-granularity.md) § A pair advances phase together), and those presses were read as evidence for a phase whose content it had not been given. The row is now **one record per key per phase**: `started_attempts` and `started_at` are written when the *step* reaches the phase, and `completed_attempts` and `completed_at` (the former `attempts_at`) stay NULL until the key passes it. The start has its own columns, not a marker row beside the completion, so that a later in-phase event is a column to add and not a new kind of row to tell apart. Each end is written once. A completion for a phase that was never begun is refused by the real store and the fake alike.

**No migration for this change.** A database written before it has the old `ramp_up_phases` and is deleted, not opened (the store refuses it when it is opened, saying so), as with #12i's timestamps: only development machines have one, and #12h's run starts from a new database.

**What NULL in `latency_ms` covers** *(amended 2026-10-04, alpha-plan #12j, finding O4.)* Still one meaning, the answer was not timed from a letter the child had just heard, and now applied in every case that has it: a press while the prompt is being spoken again (after a timeout, a re-read or a wrong press), a press after returning from PAUSED and before the prompt has been re-spoken, and a press after a letter that failed or was cancelled. Before this the first two were timed from the *earlier* version of the letter, which recorded the whole timeout or the whole time away as the child's reaction time. A press before the letter has finished is unmeasured as before; whether it should instead be a negative latency is #12f's question ([research/code-review-2026-10-01.md](../research/code-review-2026-10-01.md) § Decisions on O1 to O4). *(Answered the same day: it is. See "`latency_ms` runs from the letter being sent" below.)*

**`latency_ms` runs from the letter being sent, and `after_letter_ms` and `timeouts` stand beside it** *(amended 2026-10-04, alpha-plan #12f, decided with the developer; this answers the early-press question #12j handed over.)* A press before the letter had finished was unmeasured. On the hands-on run of 2026-09-26 that was 60% of the answers that were given to a letter actually heard: the letters took 1.1 to 1.3 seconds and the median answer came 1.1 seconds after the letter was sent. The early press is the ordinary answer of anyone who knows the key, and discarding it left the slow tail as the only data.

- **`latency_ms`** is the time from the moment the letter was **sent to be spoken** to the first press. It is the one thing the core can always measure, it has a true zero, and it is what the speed term reads ([ADR-027 § Known has a speed term](0027-key-and-accuracy-state-model.md#known-has-a-speed-term)). It needs nothing from the TTS worker or from Windows.
- **`after_letter_ms`** is the same press counted from the letter's **usual end**: `latency_ms` minus that letter's usual length, so it is negative when the child answered while the letter was still sounding. It is the developer's proposal of 2026-10-03, kept as a column of its own for reading and analysis; the progress dump uses it to say in which part of the letter answers come. Nothing in the engine reads it, because a ratio cannot be taken on a signed number (twice a baseline of −79 ms is a stricter bar, not a looser one). It is NULL while no length is known for the letter. The length itself is the difference of the two columns, so a row carries the one it was timed against.
- ~~**The usual length** of a letter, in this order: the median over the playbacks of that letter that ran to the end in this session; else the median over the other letters measured this session; else what the letter's latest stored row says it took, so a session does not begin knowing nothing. A press cuts the letter ([ADR-012](0012-audio-feedback-design.md)), so a letter that is always answered early never finishes by itself. Anything measured today comes before a stored length because a stored one is from whatever voice and rate that session had, and may itself have been borrowed; used first, it would be written back on every row and never corrected. It is read when the prompt opens, not at the press, so that no store read stands between a press and its cue.~~ **Replaced 2026-10-06 (alpha-plan #12l)** by one rule over stored measurements; see "A letter's length is a stored measurement" below.
- **`timeouts`** counts how often the prompt timed out and was spoken again before the first press. #12j rightly stopped timing an answer across a re-spoken letter, which leaves the slowest answers unmeasured: a child who needs twelve seconds to find a key is exactly the one a speed term exists to notice. The count says so without changing what `latency_ms` means. It has its own column, not a large value in `latency_ms`, because an event belongs in a column of its own. The speed term counts a correct answer with `timeouts > 0` as the slowest there is. A timeout that follows a letter which failed to play is not counted: that wait was the voice's failure.

**NULL in `latency_ms` still means one thing**, the answer was not timed from a first hearing of the letter: no clock; the press came while the letter was being spoken again or after it; the press came after returning from PAUSED; the letter failed or was cancelled. A press earlier than `HEARD_MIN_MS` after the letter was sent is not in this list because it writes no row at all ([ADR-027](0027-key-and-accuracy-state-model.md), "A press before the letter could be heard is not an attempt").

**How this was arrived at, the same day.** The first form stored the signed number in `latency_ms` and the length beside it, and the speed term added the two. That session's review found the flaw: an answer could then only be timed once some letter had run to its end in the session, so a child who answers every letter early, the fast listener the early-press question is about, produced whole sessions of untimed rows. The developer then chose the plain time from the sending as the measure and the signed number as a separate column.

**A length for every letter before its first prompt** is the piece still missing: a profile's very first presses, and a child who never lets any letter finish, have no `after_letter_ms`. The developer's answer is the introduction, which is the one time every letter is always spoken in full; it is planned as [alpha-plan](../alpha-plan.md) #12l. *(Done 2026-10-06; the next paragraph.)*

**A letter's length is a stored measurement** *(amended 2026-10-06, alpha-plan #12l, decided with the developer.)* The three-step order above had two weak steps. The median over other letters gave `f` the length of `j`, and letter names differ in length. The stored value was not a measurement: it was a row's two timings subtracted, which gave back whatever length that row had been written with, measured or borrowed, under whatever voice. And a row could not say which of the three its length came from. The developer's proposal replaces all three:

- **Every playback of a letter that runs to its end is stored**, in `letter_lengths`. It may be the letter inside an introduction ([ADR-023](0023-key-introduction-protocol.md) § The key introduction script), or a prompt's letter that the child let finish.
- **The usual length is the median over the letter's latest `LETTER_LENGTH_SAMPLE` (10) stored playbacks**, under the voice and rate in use. Playbacks from this session and from earlier ones count alike, so a letter introduced on another day has a length on an early press today.
- **A letter with no such playback has no length**, and `after_letter_ms` is NULL. Nothing is borrowed from another letter and nothing is read back out of `key_attempts`.
- **A length belongs to a voice and a rate**, so each row carries both and only rows that match the session's are read. A new voice or rate starts with no lengths. What the earlier one measured is kept, for a child who goes back to it. The table is trimmed to the latest `LETTER_LENGTH_SAMPLE` rows per profile, letter, voice and rate.
- **No letter stays without a length**, because a prompt whose letter has none is spoken so that a press cannot cut it ([ADR-012](0012-audio-feedback-design.md), "A letter with no measured length is played so that it cannot be cut"). That covers a new voice, a new rate, an introduction whose letter failed or was cut, and a database from before this table.
- **Written at the block boundary and when the session ends**, not as each letter finishes. A letter often ends just before the child's press, and a write there is delay ahead of the cue. A session that is killed loses at most one block's measurements, and those letters are measured again. `recorded_at` is therefore the time of the write.
- **Read once per letter per session**, when its first prompt opens, for the same reason as before: no store read stands between a press and its cue. The length used for a row is the one known at the press, so a letter that ran to its end before the press is already in it.

`rate` is compared for equality, so Beta's spoken "faster" and "slower" ([ADR-003](0003-text-to-speech.md)) must land on the same stored values each time; a rate that differs in its last digit is a new rate and costs one more measurement of each letter. In Alpha the rate is the one constant `TTS_RATE`, which the SAPI rate is now derived from. **The key and the engine are joined only by that constant** *(the review of 2026-10-06)*: the voice is handed both to the engine and to the session, the rate only to the session, and the Linux development voice ignores it. When Beta makes the rate a per-profile setting it has to reach the engine by the same route as the voice, or lengths are stored under a rate nothing was spoken at.

**A length is taken on the main thread**, as the time from sending the letter to handling its `SpeechFinished` *(the same review)*. Work the loop does while a letter is ending makes that one sample longer: usually under a frame, and up to the pause at a block boundary. It matters most for a letter that cannot be cut, where a press overlaps the letter by design, and for a child who never adds a second playback. Accepted for now, since nothing in the engine reads `after_letter_ms`; filed in [roadmap § D](../roadmap.md#d-smaller-gaps-worth-a-line-in-the-relevant-adr).

**No migration for `letter_lengths`, and no database is refused.** The table is added to a database that lacks it and starts empty, which the rule above fills. *(Since 2026-11-01, alpha-plan #12m session 2: a database from before #12l is refused all the same, by the schema version in § Records for the alignment, the rest keys and the ladder. A table missing from a database at the current version is still created when it is opened.)*

**No migration, as on 2026-10-04 for `ramp_up_phases`.** A database without `after_letter_ms` is refused when it is opened. Its `latency_ms` values were counted from the end of the letter and floored at zero, and nothing in the row says which meaning a value has.

**This makes explicit what `key_attempts` already was:** an append-only event log with a windowed trim. What is added is a **read** that returns the window's rows in order; every query before this one wanted aggregates, and a streak or a run-with-a-budget cannot be computed from aggregates. That read takes an optional row limit, because a bar knows how many rows it can possibly need and pulling two hundred to decide a ten-long streak is work done on every keypress.

**The window is ordered by `rowid`, not by `attempted_at`** *(2026-09-29.)* Both the ordered read and the trim order by insertion. A timestamp is not an ordering: a clock that steps backwards makes a later answer sort earlier, and then the derived ramp-up reads a child's answers in an order they never typed them in — measured, it can declare a ramp-up complete off a stretch that was never the last thirty answers. The trim was worse: with rows stamped ahead of the clock (a first boot in the wrong zone, a dead CMOS battery), every newly written row was the lexicographic oldest, so the trim deleted the row just written and the window froze. Insertion order is what every consumer actually means by "the child's answers, in order".

**Migration is two `ALTER TABLE ... ADD COLUMN` statements** on `key_attempts`, both nullable, plus the two new tables. An existing profile keeps every row it has and has no latency or predecessor history for attempts recorded before the change — which is correct, because it does not. **There is no backfill of `introductions`**, and the consequence is stated rather than hidden: the first session after an upgrade has no step to resume, so it introduces a new key as it would have before #12d, once, and is correct from then on. Alpha's databases are development data and disposable; a pilot profile would need a backfill written, and it would have to guess at step boundaries `key_stats` does not record.

### Records for the alignment, the rest keys and the ladder

*(Amended 2026-11-01, alpha-plan #12m session 2. This is the amendment [ADR-033 § What must be recorded](0033-rest-keys-and-keyboard-alignment.md#what-must-be-recorded) and [ADR-024 § The ramp-up restated, "What must be recorded"](0024-drill-content-and-lesson-granularity.md#the-ramp-up-restated-four-objectives-and-a-ladder-of-three-levels) asked for. It also closes review finding E4 ([research/code-review-2026-10-06.md](../research/code-review-2026-10-06.md)). Marks: **[T]** pinned by a default test; **[A]** argued, not tested.)*

All of this is one schema change, so a database is refused once and not once per record. The store can write and read every record below. **Nothing writes them yet.** The writers are later #12m sessions: the `rest` rung's criterion is session (4), the ladder is session (6) and the alignment is session (7). No engine code changed. `progress_dump` shows the practice days.

**What holds for every record here.**

- **Every timestamp is UTC.** It is checked on the way in and on the way out, as § Timestamps are UTC says, and the columns that stay NULL until their event are checked too **[T]**.
- **Rows come back in the order written, never by the clock**, for the reason § The window is ordered by `rowid` gives **[T]**. The new tables have an explicit `id INTEGER PRIMARY KEY` and are ordered by it, because `VACUUM` may renumber the rowids of a table without one. The older tables (`key_attempts`, `letter_lengths`, `milestones`) are ordered by bare `rowid`; nothing in Takki runs `VACUUM`, so that is left as it is **[A]**.
- **Landings and rest keys are stored by position and finger.** No character is stored. A finger is `COL_TO_FINGER`'s id (`L-pink` to `R-pink`), and a cell is the grid's row and column ([ADR-026 § Every cell of the grid](0026-platform-interface-abstraction.md#every-cell-of-the-grid)). Nothing in these tables is per language. **[T]** for what is stored. That the writers pass layout positions is theirs to keep **[A]**.
- **The fake behaves as the real store.** Every new test runs against `SqliteStore` and `FakeStore` with the same assertions, except those about SQLite's own mechanics: the stamps read back, the transactions and rollbacks, the partial unique index, and opening a database. That matters because the writers will be tested on the fake.
- **A landing or a level run must name the profile's own session.** Both stores refuse one that does not exist or that belongs to another profile, with `ValueError` **[T]**. The foreign key alone asks only that the session exists, and the `rest` rung reads one profile's sessions.
- **These checks, and the check that a letter was introduced, are made by the store before it writes, not by the schema.** Takki has one connection, so nothing can write between a check and its write. A second writer is not supported. If one ever is, composite foreign keys would put the same rules in the schema; the review of this amendment suggested them **[A]**.
- **A rest key for a profile that does not exist** is refused by both, by foreign key in SQLite and by a check in the fake, with `sqlite3.IntegrityError` **[T]**. A Reach press is refused earlier, for a letter that was never introduced, which a profile that does not exist cannot have **[T]**. The fake still does not check the profile on the records from before this amendment, as before **[A]**.
- **The fake converts a stamp to its local day when the attempt is written**, where it used to do so when the days were read. On Windows that conversion raises `OSError` for a stamp before 1970, which SQLite accepts. The divergence is not new; it has moved from the read to the write. The fake converts before it writes anything, so such a stamp leaves no partial attempt **[A]**.
- **A write-once refusal rolls back** the UPDATE it ran, so no transaction, and no lock, outlives the `ValueError`. That holds for `record_phase` as well, which had the same gap **[T]**. The five write-once events share one helper (`SqliteStore._write_once`). An INSERT that SQLite itself refuses (a CHECK or a foreign key) rolls back as well **[T]**.

#### `landings`

One row for each landing in ADR-033's alignment: profile, session, round, finger, the cell pressed, whether it was validated, and a UTC time **[T]**.

- **No latency.** The alignment is not timed (ADR-033), so the table has no column for it.
- **`round` starts at 1 in each session.** The `rest` rung reads the first round of each of the last five sessions, so the session is a column of its own and rounds are not numbered across sessions **[T]** for keeping sessions apart.
- **`validated`** says whether that hand's bump press in the same round was on the bump. For the bump press itself, it says whether that press was the bump. A landing on a hand that was not validated is still written, with 0: the flag is what lets a reader leave it out, as ADR-033's "not counted" asks **[T]** for the round trip, **[A]** for the reading.
- **What is not a landing has no row**: a press outside the finger's column, a press on a key that produces no character, and the key pressed in answer to "which one do you want", which is a rest key chosen `by answer` (below). That is the alignment's rule, session (7) **[A]**.
- **A landing writes nothing else**: no `key_stats`, no `key_attempts`, no practice day **[T]**.
- **The read is the profile's landings, in order.** At the cap of eight rounds that is at most 64 rows a session, and the table is never trimmed: about 32,000 rows after 500 sessions. The `rest` rung needs only round 1 of the last five sessions, so session (4), which writes that reader, adds a narrower read and its index **[A]**. The review of this amendment raised it.

#### `rest_keys`

One row per finger per key that finger has rested on. The finger's current key is the row with no `replaced_at`. SQLite also holds that to at most one per finger with a partial unique index **[T]**. Each of ADR-033's events has its own column: `chosen_at` with `chosen_by`, `ready_at`, `passed_at` and `replaced_at`. Each is written once **[T]**.

- **`chosen_by`** is `landings` (two rounds in a row on the same key), `answer` (the finger was asked), or `bump`. **An index finger gets a row with `bump`.** Its key is not chosen, but it becomes ready and passes its session-start test like every other finger, and those events need a row to go in **[A]**. The Protocol's type allows only these three, which pyright checks at every call, and both stores refuse a fourth with `sqlite3.IntegrityError`: SQLite by a CHECK constraint, the fake by the same test **[T]**. Choosing the key a finger already has writes nothing, so it is not checked, in either store.
- **Choosing the key a finger already has changes nothing.** The key keeps its events and how it was first chosen **[T]**. ADR-033 asks the question again of a ready finger that has wandered, and the child may answer with the key they had.
- **Choosing a different key replaces the current one.** The old key gets `replaced_at`, the new one is added with `chosen_at`, both with the same stamp, in one transaction **[T]**, including a failure between the two writes, which leaves the old key current **[T, SQLite]**. The old key keeps its events. **The new key starts not ready and not passed**: ready and passed describe a key, and the new key has shown neither **[A]**.
- **A ready or passed mark for a finger with no current key is refused** **[T]**.
- **The store does not put the events in order.** A key can be marked passed before it is marked ready. ADR-033 does not say that a key must be ready to pass its session-start test, and session (7), which writes both, decides **[A]**.
- **Replaced keys are kept** because ADR-033 asks for them, and because the `rest` rung will need them: it judges the first round of each of the last five sessions, and a session before a change has to be judged against the key that was current then **[A]**.

#### The `rest` rung

A row in `milestones` under the slug `rest`, stored and ordered like any rung **[T]**. That is the whole record. The criterion, the slug's constant and the place in the ladder where `rest` replaces `anchor` are session (4)'s. The `anchor` slug stays until then.

#### The ladder: `ramp_up_levels`, the bar and `reach_presses`

**`ramp_up_levels`** has one row per **run** of a level of a letter, with the level stored by name (`reach`, `choose`, `travel`; the Protocol's `Level` type allows only these, and both stores refuse another name **[T]**). A level the letter does not take has no row. It records the session the step reached the level in, the press count and time at that start, and the press count and time when the letter met the level's rule **[T]**. A run for a letter that was never introduced is refused, as the bar is **[T]**.

- **Why a run, keyed by session.** ADR-024 starts Reach again after a restart, from nothing, for a member that had met Reach's rule as well, and keeps the earlier Reach as history. One write-once row per letter and level cannot hold two Reaches, and overwriting the row would lose the first. So `begin_level` is write-once within a session, and a begin in a new session is a new run **[T]**. `complete_level` names the run by its session, as the key does, and writes its completion once **[T]**. It is refused for a run never begun, including a Choose begun in an earlier session and completed under today's **[T]**. A run that never completed keeps `completed_at` NULL. Keying the run by session assumes that Reach begins at most once per step in a session: ADR-024 starts it again only after a restart. If the ladder ever restarts Reach within a session, the second begin is ignored, and the key has to change **[A]**.
- **What the store does not enforce:** that Choose and Travel are begun once. They survive a restart (ADR-024), so the ladder begins them only when it has no record of them. A second begin in a later session would make a second run, and the store would accept it. `ramp_up_phases`'s `INSERT OR IGNORE` stopped this for phases. A store that does not know which level is which cannot both allow it for Reach and refuse it for the others. Session (6) keeps the rule and pins it **[A]**.
- **The press counts** are lifetime counts, which no window can evict, and they bound a level's evidence as `ramp_up_phases.started_attempts` does. At Reach the count is the letter's `reach_presses` rows. At Choose and Travel it is the letter's `key_stats.attempt_count`. The store stores what it is handed, so this meaning is the writer's **[A]**.

**The bar met is its own event**, in `introductions.stable_attempts` and `stable_at`, and not Travel's completion. It is written once, and refused for a letter that was never introduced **[T]**. It is on `introductions` because there is already one row per letter there, and "the current step is the newest `introductions` group whose members have not all met the bar" then reads one table **[A]**.

**Reach presses are kept in `reach_presses`**, apart from `key_attempts` **[T]**. There is one row per Reach prompt, with whether its first press was right and a UTC time.

- They are not timed. ADR-024 reads a predictable press for one thing, whether the child reaches the key reliably, and that is its correctness **[A]**.
- They are never trimmed, and the attempt window does not reach them **[T]**. A Reach run is about ten to twenty rows, and ADR-033's open question (is a child with an unusual rest key slower to learn that finger's other keys?) wants all of them **[A]**.
- They write no `key_stats` row, so they make no key Active, and they add no practice day **[T]**.
- A press for a letter that was never introduced is refused, as a level run and the bar are **[T]**.

**Two presses are not stored at all** **[A]**: the press that answers a rest cue (ADR-024: "the return is not measured"), and a re-ask after a miss ("nothing reads it").

**`prev_char` after a rest cue holds the id of the finger the cue asked for**, for example `R-mid` **[A; the writer is session (6)]**.
- It is not NULL, which means the first prompt of a session.
- It is not the rest key's letter. The cue asks by finger, and a rest key may carry no letter.
- A finger id contains `-` and is longer than one character, so it cannot be mistaken for a letter prompt.
- Today `AttemptCounter` is the only writer of `prev_char`, and nothing in the engine reads it (found by searching the source on 2026-11-01).

**`ramp_up_phases` stays as it is until session (6).** The code still runs the four phases, and they write it. Session (6) replaces the phases with the ladder. It then:
- stops writing `ramp_up_phases`;
- removes the table from the schema and the phase API (`begin_phase`, `record_phase`, `phase_records`, `PhaseRecord`);
- moves `progress_dump`'s ramp-up table to the levels.

A database that still has the old table is not refused: nothing reads it. So there is no second refusal **[A]**.

`progress_dump` prints none of these records yet, except the practice days below. Printing them is session (8)'s, which is the dump tool's session.

#### Practice days outside the window (E4)

`practice_days` holds one row per key per local day on which the key had an attempt (a `key_attempts` row) **[T]**.

- **It is written with the `key_attempts` row**, in `_append_attempt`. So `count_attempt` writes the count, the row and the day in one transaction, and `append_attempt` the row and the day: a failure at the day leaves none of them **[T]**.
- **It is never trimmed.**

**The day is fixed when it is written**: `date(attempted_at, 'localtime')` in the zone of that moment. Until now it was derived again at every read, in the zone of the read. Fixing it means that moving the machine to another zone does not split or merge days already lived **[T, POSIX only: the test sets the process timezone, which Windows cannot. It did not run in this session, which ran on the Windows laptop]**. A day is not a timestamp. It is the one place this ADR already says local time is the meaning.

**The Known query reads the days from this table**, so `window_stats().distinct_days` is every practice day of the key. The attempt and correct counts are still the window's. A key with three earlier days and 200 presses today has four days, where reading the window gave it one. It stays Known **[T, both stores, and through `KeyStates`; both tests fail on the window count]**.

- **The days floor, once met, stays met.** That is what [ADR-027](0027-key-and-accuracy-state-model.md) calls the days: "a fact about the calendar". The dose and the accuracy are still read over the window and can still fall **[A]**.
- **Only an attempt makes a practice day**: a `key_attempts` row, written by `count_attempt` or `append_attempt`. A Reach press or a landing does not **[T]**.
- **`DrillGenerator`'s "waiting for a day"** reads the same count, so a long day can no longer send a key back to waiting **[A]**.
- **`progress_dump` shows the count** in its lifetime table, as `days` **[T]**. Its per-day table still groups the window, so it shows only the window's days.

**No migration. A database from before this change is refused when it is opened**, with "this Takki database has schema version 0, older than this Takki's 1, and cannot be used; delete it" **[T]**. Opening it with the new tables simply created would be wrong. Its earlier days are only in its window, so an empty `practice_days` would count days only from then on, and its keys would read back with fewer days than they had. A backfill from the window would recover every day the old code counted, and none beyond them, with two `ALTER TABLE`s for `introductions`. It is not written because the developer decided there is no migration: only development machines hold such a database, and #12h starts from a new one, as it already must (the review of this amendment raised the backfill).

- **The schema has a version**, in `PRAGMA user_version`, written in the same transaction as the tables. This change is version 1, and every database from before it reads 0. A database that has tables and a version below the store's is refused **[T]**. One above it, written by a newer Takki, is refused as well, and is not stamped back down, which would make the newer Takki refuse its own database **[T]**.
- **The check runs before anything is written.** A refused database is left as it was found: without the new tables, and not even switched to WAL **[T]**. Whatever fails while the store opens, a refusal or a file that is not a database, the connection is closed, so the file the message says to delete is not held open **[T]**.
- **It covers the two earlier refusals.** A database old enough for #12j's `ramp_up_phases` or #12f's `key_attempts` refusal is older than this change too, and is refused by this check, with the same message: **[T]** for #12j's table, and #12f's database is a version-0 database like any other. Their own checks (`SqliteStore._migrate`) could no longer fire for any real database and are removed. The paragraphs above that say those databases are refused remain true.
- **A new database's schema is created in one transaction**, so a first launch killed part-way through leaves no tables and no version. Created table by table, it left some tables, and the next launch refused a new database as an old one **[T]**. The transaction is `IMMEDIATE`, so a second launch at the same moment waits for the first's lock rather than failing on it **[A]**.
- **A database at the current version is opened without a transaction**, as before this change. The schema script then creates only a table that is missing, and takes no write lock, so opening does not fail while another connection is writing **[T]**.
- **The next schema change that an older database cannot be opened under raises the version.** It does not need a check of its own. The review of this amendment suggested the version, in place of a check on whether `practice_days` existed.
- **Nothing speaks the refusal.** It is a `RuntimeError` after the window and the mixer are up, as the earlier refusals were, and [roadmap § D](../roadmap.md#d-smaller-gaps-worth-a-line-in-the-relevant-adr) "Error surfacing for blind parents" has it. `progress_dump` can still read a database from just before this change, and shows `-` where the days would be **[T]**. One from before #12f or #12j still fails on its missing columns, as roadmap § D says.

#### Deferred to Beta

- `word_stats (profile_id, word, clean_count, attempt_count, last_seen_at)` — per-word performance for Layer 2.
- Visual display columns on `profiles` (added via `ALTER TABLE`): `display_enabled`, `display_text_size`, `display_bg_color`, `display_fg_color`.

`session_key_stats` (previously listed here) is dropped entirely. Its two stated uses — WPM trend reporting and Layer 2 word-length gate — are covered by `sessions` + `word_stats`. The multi-day Known criterion is computed from `key_attempts.attempted_at` timestamps without any per-session breakdown. See ADR-027.

#### Design notes

- All timestamps are local time, no timezone offset (`datetime.now().isoformat(timespec='seconds')`). This is a fully offline, single-device app with no cross-device sync; timezone-aware timestamps would add complexity with no benefit. Session ordering, duration calculation, and parent report display all work correctly with local time.
- A NULL value in any nullable `profiles` column means "fall through to the app-level config" (ADR-025). The persistence layer never writes a default value into the database — it writes NULL and lets the config resolution layer supply the effective value at runtime.
- `key_stats` retains lifetime aggregate counts for gamification displays (total attempts ever, milestone history). It is not the source of truth for Known. `key_attempts` is authoritative for Known — see ADR-027.
- Milestone detection reads `key_attempts`: the key-count rungs need ≥ 90 attempts at ≥ 90% accuracy across ≥ 2 distinct practice days per grapheme, and the Stage 0 anchor rung needs ≥ 25 attempts at ≥ 95% across ≥ 2 days on each of its six keys. *(Since 2026-10-04 the accuracy in both is the lower confidence bound over decayed evidence: [ADR-027](0027-key-and-accuracy-state-model.md), "Known reads decayed evidence against a confidence bound". No schema change for that: the weights are computed from `attempted_at` on read.)* The old "≥ 50 presses from `key_stats`" criterion is superseded by ADR-027. *(Updated 2026-08-23: this line previously read "Bronze milestone detection (all home-row graphemes Known)". Bronze was retired with the positional criterion — see [ADR-027 § Milestone Ladder](0027-key-and-accuracy-state-model.md#milestone-ladder). **No schema change:** the anchor rung fires once on stage completion and stores a row in `milestones` like any other.)*
