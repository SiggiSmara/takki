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
    introduced_at     TEXT,         -- when the step carrying this key was spoken;
                                    -- one value shared by both members of a pair
    PRIMARY KEY (profile_id, key_char)
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

The `key_attempts` table is a rolling window: at most 200 rows per (profile_id, key_char). The persistence layer deletes the oldest row on each INSERT when the cap is exceeded. This table is authoritative for the Known criterion — see ADR-027.

**`latency_ms`, `prev_char` and `introduced_at`** *(added 2026-09-29, alpha-plan #12d, for [ADR-024 § Ramp-up variability, derived exit bars, and the "I know this one" probe](0024-drill-content-and-lesson-granularity.md).)* The three columns exist for one reason: the ramp-up's exit bars stop being session-local state and become queries over what is already stored, which is what makes a ramp-up survive the app closing. What each buys, since none is speculative:

- **`latency_ms`** is the only signal that separates retrieval from anticipation. Correctness cannot: a child following a predictable cycle presses the right key without hearing the prompt. It is read as a **median ratio against the child's own baseline over their Known keys**, never as an absolute figure — an absolute threshold would encode a sighted adult's reaction time. NULL where no prompt time was available, and a NULL never fails a bar.
- **`prev_char`** makes "correct when the next prompt could not be predicted" derivable after a restart rather than only inside the session that generated it. It is also what lets a later reader check ADR-024's anchor invariant against the stored history instead of trusting the generator.
- **`introduced_at`** on `key_stats` answers *which step is current*, which nothing could answer before: Active is row presence, and insertion order was recoverable only from an implicit `rowid`. Both members of a pair step are written with **one shared timestamp value**, so a pair is recovered by exact equality rather than by proximity — second-resolution timestamps cannot be compared for nearness safely.

**This makes explicit what `key_attempts` already was:** an append-only event log with a windowed trim, ordered by `(attempted_at, rowid)`. No ordering column is added, because the existing trim already relies on that tiebreaker. What is added is a **read** that returns the window's rows in order; every query before this one wanted aggregates, and a streak or a run-with-a-budget cannot be computed from aggregates. Migration is three `ALTER TABLE ... ADD COLUMN` statements, all nullable, so an existing profile keeps every row it has and simply has no latency or predecessor history for attempts recorded before the change — which is correct, because it does not.

#### Deferred to Beta

- `word_stats (profile_id, word, clean_count, attempt_count, last_seen_at)` — per-word performance for Layer 2.
- Visual display columns on `profiles` (added via `ALTER TABLE`): `display_enabled`, `display_text_size`, `display_bg_color`, `display_fg_color`.

`session_key_stats` (previously listed here) is dropped entirely. Its two stated uses — WPM trend reporting and Layer 2 word-length gate — are covered by `sessions` + `word_stats`. The multi-day Known criterion is computed from `key_attempts.attempted_at` timestamps without any per-session breakdown. See ADR-027.

#### Design notes

- All timestamps are local time, no timezone offset (`datetime.now().isoformat(timespec='seconds')`). This is a fully offline, single-device app with no cross-device sync; timezone-aware timestamps would add complexity with no benefit. Session ordering, duration calculation, and parent report display all work correctly with local time.
- A NULL value in any nullable `profiles` column means "fall through to the app-level config" (ADR-025). The persistence layer never writes a default value into the database — it writes NULL and lets the config resolution layer supply the effective value at runtime.
- `key_stats` retains lifetime aggregate counts for gamification displays (total attempts ever, milestone history). It is not the source of truth for Known. `key_attempts` is authoritative for Known — see ADR-027.
- Milestone detection reads `key_attempts`: the key-count rungs need ≥ 90 attempts at ≥ 90% accuracy across ≥ 2 distinct practice days per grapheme, and the Stage 0 anchor rung needs ≥ 25 attempts at ≥ 95% across ≥ 2 days on each of its six keys. The old "≥ 50 presses from `key_stats`" criterion is superseded by ADR-027. *(Updated 2026-08-23: this line previously read "Bronze milestone detection (all home-row graphemes Known)". Bronze was retired with the positional criterion — see [ADR-027 § Milestone Ladder](0027-key-and-accuracy-state-model.md#milestone-ladder). **No schema change:** the anchor rung fires once on stage completion and stores a row in `milestones` like any other.)*
