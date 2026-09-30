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
    profile_id   INTEGER NOT NULL REFERENCES profiles(id),
    key_char     TEXT    NOT NULL,
    phase        TEXT    NOT NULL,   -- "A", "B", "C" (ADR-024's ramp-up)
    attempts_at  INTEGER NOT NULL,   -- key_stats.attempt_count when it was passed
    completed_at TEXT    NOT NULL,   -- UTC, ISO-8601
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
    latency_ms   INTEGER,           -- prompt to first press; NULL = unmeasured
    prev_char    TEXT               -- the preceding prompt; NULL = first of a block
);
```

### Timestamps are UTC

*(Added 2026-09-30, alpha-plan #12d.)* Every timestamp in this schema is **UTC**, ISO-8601. Local time is a presentation concern: reports and any spoken or displayed date convert on the way out.

Two things forced it. Naive local strings are not an ordering — an hour repeats every autumn — and this schema is now read positionally by the derived ramp-up and trimmed by the same key, so an ordering that goes backwards is a correctness problem rather than a cosmetic one. And "the same instant" has to survive a machine moving timezone, which a child's laptop does.

**The one place local time is still the meaning is a practice *day*.** ADR-027's Known criterion counts distinct practice days, and that is the child's day at the keyboard, not UTC's — an evening session either side of midnight UTC is one day. So `window_stats` groups by `date(attempted_at, 'localtime')`, and the fake mirrors it by converting rather than by slicing the string. Getting that wrong would move a Known gate by a day for anyone east or west of Greenwich.

Rows written before this rule are naive local. They are not migrated: Alpha data is disposable, and a converted timestamp would be a guess at the offset in force when it was written.

The `key_attempts` table is a rolling window: at most 200 rows per (profile_id, key_char). The persistence layer deletes the oldest row on each INSERT when the cap is exceeded. This table is authoritative for the Known criterion — see ADR-027.

**`latency_ms`, `prev_char` and the `introductions` table** *(added 2026-09-29, alpha-plan #12d, for [ADR-024 § Ramp-up variability, derived exit bars, and the "I know this one" probe](0024-drill-content-and-lesson-granularity.md).)* Two columns and one table, all for one reason: the ramp-up's exit bars stop being session-local state and become queries over what is already stored, which is what makes a ramp-up survive the app closing. What each buys, since none is speculative:

- **`latency_ms`** is the only signal that separates retrieval from anticipation. Correctness cannot: a child following a predictable cycle presses the right key without hearing the prompt. It is read as a **median ratio against the child's own baseline over their Known keys**, never as an absolute figure — an absolute threshold would encode a sighted adult's reaction time. NULL where no prompt time was available, and a NULL never fails a bar.
- **`prev_char`** makes "correct when the next prompt could not be predicted" derivable after a restart rather than only inside the session that generated it. It is also what lets a later reader check ADR-024's anchor invariant against the stored history instead of trusting the generator.
- **`introductions`** answers *which step is current*, which nothing could answer before: Active is row presence in `key_stats`, and insertion order was recoverable only from an implicit `rowid`. The **`step` ordinal** is what groups a step's members and orders the steps — deliberately not the timestamp. A timestamp cannot do either job: two steps introduced inside one clock tick read as one step of four members, and `max()` over clock strings picks the wrong step for good whenever the clock has stepped backwards, at which point the genuinely current step can never be resumed again. **UTC removes the seasonal case and not the general one:** there is no fall-back hour in UTC, but `datetime.now(UTC)` reads the system clock, which is not monotonic — an NTP correction, a manual fix, or a boot with a dead CMOS battery all step it back. An ordinal is not a clock and needs none of this to be true. `position` keeps the member order ADR-023 defines, since the drill generator reads `members[0]` as the left-hand member.

- **`ramp_up_phases`** records that a member has **passed** a phase of ADR-024's ramp-up, write-once. See ADR-024 § A phase completion is an event for why this is stored rather than re-derived; the short version is that `key_attempts` is a window built to forget, so a phase read off it un-passes itself when the window rolls, and the curriculum can lock. `attempts_at` is the key's lifetime `key_stats.attempt_count` at that moment, which is what bounds the next phase's evidence without depending on rows that may since have been evicted.

  **It is its own table rather than an `introduced_at` column on `key_stats`, and that is not a filing preference.** A `key_stats` row *is* Active ([ADR-027](0027-key-and-accuracy-state-model.md) § Key States), so stamping the introduction there would make a key Active before the child had answered a single prompt on it. The introducer reads Active as "already had", so the step would never be offered again and its script — which [ADR-023](0023-key-introduction-protocol.md) § What the introducer remembers calls that letter's only teaching moment — would be silently spent on a child who heard it once and typed nothing. That case is not hypothetical: it is in the #12b-2 log, where `u` was introduced, never answered, and correctly introduced again next session. Keeping introductions separate leaves Active, the milestone denominators, the Layer-2 unlock and ADR-010's gate exactly as they were.

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
- Milestone detection reads `key_attempts`: the key-count rungs need ≥ 90 attempts at ≥ 90% accuracy across ≥ 2 distinct practice days per grapheme, and the Stage 0 anchor rung needs ≥ 25 attempts at ≥ 95% across ≥ 2 days on each of its six keys. The old "≥ 50 presses from `key_stats`" criterion is superseded by ADR-027. *(Updated 2026-08-23: this line previously read "Bronze milestone detection (all home-row graphemes Known)". Bronze was retired with the positional criterion — see [ADR-027 § Milestone Ladder](0027-key-and-accuracy-state-model.md#milestone-ladder). **No schema change:** the anchor rung fires once on stage completion and stores a row in `milestones` like any other.)*
