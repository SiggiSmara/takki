# ADR-011: Persistence and State

**Status:** Accepted  
**Date:** 2026-05-17

> Part of the [Takki architecture](../architecture.md).

---

**Decision:** SQLite via Python's built-in `sqlite3` module. Local only, no server, no sync.

### Rationale

Child profiles and progress data need to persist across sessions. SQLite is the right choice because:
- Built into Python's standard library — no additional dependency
- Single file on disk, trivially backed up by parents
- No server, no network, no account required
- Sufficient for the data volumes involved (per-key accuracy history, session logs, milestone records)

Each child has a named profile selected at startup (spoken menu). Multiple children can share one installation.

**Profile portability:** the SQLite file *is* the profile data. It lives at `%LOCALAPPDATA%\Takki\takki.sqlite` on Windows (located via `platformdirs` — see ADR-025). *(Path corrected 2026-09-20: this said `%APPDATA%`, which is the roaming profile. A WAL-mode database must not roam — ADR-025 § App Data Directory carries the reasoning.)* To move a child's progress to another computer, copy that file to the same location on the destination machine. No export/import flow is provided in v1 — the file is the export format. Parents are reminded of this in the parent/teacher summary (ADR-014).

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
    profile_id    INTEGER NOT NULL REFERENCES profiles(id),
    key_char      TEXT    NOT NULL,
    step          INTEGER NOT NULL,  -- per-profile ordinal: groups and orders steps
    position      INTEGER NOT NULL,  -- 0-based; ADR-023 puts the left hand first
    introduced_at TEXT    NOT NULL,  -- UTC, ISO-8601
    PRIMARY KEY (profile_id, key_char)
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
                                    -- "five_sixths", "alphabet", "diamond", "speed".
                                    -- Never spoken; the name resolves via ADR-022 YAML.
    achieved_at TEXT    NOT NULL,
    PRIMARY KEY (profile_id, level)
);

CREATE TABLE key_attempts (
    profile_id   INTEGER NOT NULL REFERENCES profiles(id),
    key_char     TEXT    NOT NULL,
    attempted_at TEXT    NOT NULL,  -- local time, ISO-8601
    correct      INTEGER NOT NULL,  -- 1 = first keystroke correct, 0 = wrong
    latency_ms   INTEGER,           -- the letter being sent to the first press; NULL = unmeasured
    prev_char    TEXT,              -- the preceding prompt; NULL = first of a block
    after_letter_ms INTEGER,        -- the same press from the letter's usual end, signed; NULL = no length known
    timeouts     INTEGER NOT NULL DEFAULT 0  -- prompt timeouts before the first press
);
```

### Timestamps are UTC

*(Added 2026-09-30, alpha-plan #12d.)* Every timestamp in this schema is **UTC**, ISO-8601. Local time is a presentation concern: reports and any spoken or displayed date convert on the way out.

Two things forced it. Naive local strings are not an ordering — an hour repeats every autumn — and this schema is now read positionally by the derived ramp-up and trimmed by the same key, so an ordering that goes backwards is a correctness problem rather than a cosmetic one. And "the same instant" has to survive a machine moving timezone, which a child's laptop does.

**The one place local time is still the meaning is a practice *day*.** ADR-027's Known criterion counts distinct practice days, and that is the child's day at the keyboard, not UTC's — an evening session either side of midnight UTC is one day. So `window_stats` groups by `date(attempted_at, 'localtime')`, and the fake mirrors it by converting rather than by slicing the string. Getting that wrong would move a Known gate by a day for anyone east or west of Greenwich.

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
- **`prev_char`** makes "correct when the next prompt could not be predicted" derivable after a restart rather than only inside the session that generated it. It is also what lets a later reader check ADR-024's anchor invariant against the stored history instead of trusting the generator.
- **`introductions`** answers *which step is current*, which nothing could answer before: Active is row presence in `key_stats`, and insertion order was recoverable only from an implicit `rowid`. The **`step` ordinal** is what groups a step's members and orders the steps — deliberately not the timestamp. A timestamp cannot do either job: two steps introduced inside one clock tick read as one step of four members, and `max()` over clock strings picks the wrong step for good whenever the clock has stepped backwards, at which point the genuinely current step can never be resumed again. **UTC removes the seasonal case and not the general one:** there is no fall-back hour in UTC, but `datetime.now(UTC)` reads the system clock, which is not monotonic — an NTP correction, a manual fix, or a boot with a dead CMOS battery all step it back. An ordinal is not a clock and needs none of this to be true. `position` keeps the member order ADR-023 defines, since the drill generator reads `members[0]` as the left-hand member.

- **`ramp_up_phases`** records that a member has **passed** a phase of ADR-024's ramp-up, write-once *(and, since 2026-10-04, where the phase began: see "`ramp_up_phases` records both ends of a phase" below)*. See ADR-024 § A phase completion is an event for why this is stored rather than re-derived; the short version is that `key_attempts` is a window built to forget, so a phase read off it un-passes itself when the window rolls, and the curriculum can lock. `completed_attempts` (named `attempts_at` until 2026-10-04) is the key's lifetime `key_stats.attempt_count` at that moment, a count no rolling window can evict.

  **It is its own table rather than an `introduced_at` column on `key_stats`, and that is not a filing preference.** A `key_stats` row *is* Active ([ADR-027](0027-key-and-accuracy-state-model.md) § Key States), so stamping the introduction there would make a key Active before the child had answered a single prompt on it. The introducer reads Active as "already had", so the step would never be offered again and its script — which [ADR-023](0023-key-introduction-protocol.md) § What the introducer remembers calls that letter's only teaching moment — would be silently spent on a child who heard it once and typed nothing. That case is not hypothetical: it is in the #12b-2 log, where `u` was introduced, never answered, and correctly introduced again next session. Keeping introductions separate leaves Active, the milestone denominators, the Layer-2 unlock and ADR-010's gate exactly as they were.

**`ramp_up_phases` records both ends of a phase** *(amended 2026-10-04, alpha-plan #12j, finding O1.)* A row was written when a phase was passed, and the next phase's evidence was read from that count. For a pair that is the wrong starting point: the member that passes first keeps being prompted with the same phase's content while its partner catches up ([ADR-024](0024-drill-content-and-lesson-granularity.md) § A pair advances phase together), and those presses were read as evidence for a phase whose content it had not been given. The row is now **one record per key per phase**: `started_attempts` and `started_at` are written when the *step* reaches the phase, and `completed_attempts` and `completed_at` (the former `attempts_at`) stay NULL until the key passes it. The start has its own columns, not a marker row beside the completion, so that a later in-phase event is a column to add and not a new kind of row to tell apart. Each end is written once. A completion for a phase that was never begun is refused by the real store and the fake alike.

**No migration for this change.** A database written before it has the old `ramp_up_phases` and is deleted, not opened (the store refuses it when it is opened, saying so), as with #12i's timestamps: only development machines have one, and #12h's run starts from a new database.

**What NULL in `latency_ms` covers** *(amended 2026-10-04, alpha-plan #12j, finding O4.)* Still one meaning, the answer was not timed from a letter the child had just heard, and now applied in every case that has it: a press while the prompt is being spoken again (after a timeout, a re-read or a wrong press), a press after returning from PAUSED and before the prompt has been re-spoken, and a press after a letter that failed or was cancelled. Before this the first two were timed from the *earlier* version of the letter, which recorded the whole timeout or the whole time away as the child's reaction time. A press before the letter has finished is unmeasured as before; whether it should instead be a negative latency is #12f's question ([research/code-review-2026-10-01.md](../research/code-review-2026-10-01.md) § Decisions on O1 to O4). *(Answered the same day: it is. See "`latency_ms` runs from the letter being sent" below.)*

**`latency_ms` runs from the letter being sent, and `after_letter_ms` and `timeouts` stand beside it** *(amended 2026-10-04, alpha-plan #12f, decided with the developer; this answers the early-press question #12j handed over.)* A press before the letter had finished was unmeasured. On the hands-on run of 2026-09-26 that was 60% of the answers that were given to a letter actually heard: the letters took 1.1 to 1.3 seconds and the median answer came 1.1 seconds after the letter was sent. The early press is the ordinary answer of anyone who knows the key, and discarding it left the slow tail as the only data.

- **`latency_ms`** is the time from the moment the letter was **sent to be spoken** to the first press. It is the one thing the core can always measure, it has a true zero, and it is what the speed term reads ([ADR-027 § Known has a speed term](0027-key-and-accuracy-state-model.md#known-has-a-speed-term)). It needs nothing from the TTS worker or from Windows.
- **`after_letter_ms`** is the same press counted from the letter's **usual end**: `latency_ms` minus that letter's usual length, so it is negative when the child answered while the letter was still sounding. It is the developer's proposal of 2026-10-03, kept as a column of its own for reading and analysis; the progress dump uses it to say in which part of the letter answers come. Nothing in the engine reads it, because a ratio cannot be taken on a signed number (twice a baseline of −79 ms is a stricter bar, not a looser one). It is NULL while no length is known for the letter. The length itself is the difference of the two columns, so a row carries the one it was timed against.
- **The usual length** of a letter, in this order: the median over the playbacks of that letter that ran to the end in this session; else the median over the other letters measured this session; else what the letter's latest stored row says it took, so a session does not begin knowing nothing. A press cuts the letter ([ADR-012](0012-audio-feedback-design.md)), so a letter that is always answered early never finishes by itself. Anything measured today comes before a stored length because a stored one is from whatever voice and rate that session had, and may itself have been borrowed; used first, it would be written back on every row and never corrected. It is read when the prompt opens, not at the press, so that no store read stands between a press and its cue.
- **`timeouts`** counts how often the prompt timed out and was spoken again before the first press. #12j rightly stopped timing an answer across a re-spoken letter, which leaves the slowest answers unmeasured: a child who needs twelve seconds to find a key is exactly the one a speed term exists to notice. The count says so without changing what `latency_ms` means. It has its own column, not a large value in `latency_ms`, because an event belongs in a column of its own. The speed term counts a correct answer with `timeouts > 0` as the slowest there is. A timeout that follows a letter which failed to play is not counted: that wait was the voice's failure.

**NULL in `latency_ms` still means one thing**, the answer was not timed from a first hearing of the letter: no clock; the press came while the letter was being spoken again or after it; the press came after returning from PAUSED; the letter failed or was cancelled. A press earlier than `HEARD_MIN_MS` after the letter was sent is not in this list because it writes no row at all ([ADR-027](0027-key-and-accuracy-state-model.md), "A press before the letter could be heard is not an attempt").

**How this was arrived at, the same day.** The first form stored the signed number in `latency_ms` and the length beside it, and the speed term added the two. That session's review found the flaw: an answer could then only be timed once some letter had run to its end in the session, so a child who answers every letter early, the fast listener the early-press question is about, produced whole sessions of untimed rows. The developer then chose the plain time from the sending as the measure and the signed number as a separate column.

**A length for every letter before its first prompt** is the piece still missing: a profile's very first presses, and a child who never lets any letter finish, have no `after_letter_ms`. The developer's answer is the introduction, which is the one time every letter is always spoken in full; it is planned as [alpha-plan](../alpha-plan.md) #12l.

**No migration, as on 2026-10-04 for `ramp_up_phases`.** A database without `after_letter_ms` is refused when it is opened. Its `latency_ms` values were counted from the end of the letter and floored at zero, and nothing in the row says which meaning a value has.

**This makes explicit what `key_attempts` already was:** an append-only event log with a windowed trim. What is added is a **read** that returns the window's rows in order; every query before this one wanted aggregates, and a streak or a run-with-a-budget cannot be computed from aggregates. That read takes an optional row limit, because a bar knows how many rows it can possibly need and pulling two hundred to decide a ten-long streak is work done on every keypress.

**The window is ordered by `rowid`, not by `attempted_at`** *(2026-09-29.)* Both the ordered read and the trim order by insertion. A timestamp is not an ordering: a clock that steps backwards makes a later answer sort earlier, and then the derived ramp-up reads a child's answers in an order they never typed them in — measured, it can declare a ramp-up complete off a stretch that was never the last thirty answers. The trim was worse: with rows stamped ahead of the clock (a first boot in the wrong zone, a dead CMOS battery), every newly written row was the lexicographic oldest, so the trim deleted the row just written and the window froze. Insertion order is what every consumer actually means by "the child's answers, in order".

**Migration is two `ALTER TABLE ... ADD COLUMN` statements** on `key_attempts`, both nullable, plus the two new tables. An existing profile keeps every row it has and has no latency or predecessor history for attempts recorded before the change — which is correct, because it does not. **There is no backfill of `introductions`**, and the consequence is stated rather than hidden: the first session after an upgrade has no step to resume, so it introduces a new key as it would have before #12d, once, and is correct from then on. Alpha's databases are development data and disposable; a pilot profile would need a backfill written, and it would have to guess at step boundaries `key_stats` does not record.

#### Deferred to Beta

- `word_stats (profile_id, word, clean_count, attempt_count, last_seen_at)` — per-word performance for Layer 2.
- Visual display columns on `profiles` (added via `ALTER TABLE`): `display_enabled`, `display_text_size`, `display_bg_color`, `display_fg_color`.

`session_key_stats` (previously listed here) is dropped entirely. Its two stated uses — WPM trend reporting and Layer 2 word-length gate — are covered by `sessions` + `word_stats`. The multi-day Known criterion is computed from `key_attempts.attempted_at` timestamps without any per-session breakdown. See ADR-027.

#### Design notes

- All timestamps are local time, no timezone offset (`datetime.now().isoformat(timespec='seconds')`). This is a fully offline, single-device app with no cross-device sync; timezone-aware timestamps would add complexity with no benefit. Session ordering, duration calculation, and parent report display all work correctly with local time.
- A NULL value in any nullable `profiles` column means "fall through to the app-level config" (ADR-025). The persistence layer never writes a default value into the database — it writes NULL and lets the config resolution layer supply the effective value at runtime.
- `key_stats` retains lifetime aggregate counts for gamification displays (total attempts ever, milestone history). It is not the source of truth for Known. `key_attempts` is authoritative for Known — see ADR-027.
- Milestone detection reads `key_attempts`: the key-count rungs need ≥ 90 attempts at ≥ 90% accuracy across ≥ 2 distinct practice days per grapheme, and the Stage 0 anchor rung needs ≥ 25 attempts at ≥ 95% across ≥ 2 days on each of its six keys. *(Since 2026-10-04 the accuracy in both is the lower confidence bound over decayed evidence: [ADR-027](0027-key-and-accuracy-state-model.md), "Known reads decayed evidence against a confidence bound". No schema change for that: the weights are computed from `attempted_at` on read.)* The old "≥ 50 presses from `key_stats`" criterion is superseded by ADR-027. *(Updated 2026-08-23: this line previously read "Bronze milestone detection (all home-row graphemes Known)". Bronze was retired with the positional criterion — see [ADR-027 § Milestone Ladder](0027-key-and-accuracy-state-model.md#milestone-ladder). **No schema change:** the anchor rung fires once on stage completion and stores a row in `milestones` like any other.)*
