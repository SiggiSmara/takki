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

**Profile portability:** the SQLite file *is* the profile data. It lives at `%APPDATA%\Takki\takki.sqlite` on Windows (located via `platformdirs` — see ADR-025). To move a child's progress to another computer, copy that file to the same location on the destination machine. No export/import flow is provided in v1 — the file is the export format. Parents are reminded of this in the parent/teacher summary (ADR-014).

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

CREATE TABLE milestones (
    profile_id  INTEGER NOT NULL REFERENCES profiles(id),
    level       TEXT    NOT NULL,   -- "bronze", "silver", "gold", "platinum", "diamond"
    achieved_at TEXT    NOT NULL,
    PRIMARY KEY (profile_id, level)
);

CREATE TABLE key_attempts (
    profile_id   INTEGER NOT NULL REFERENCES profiles(id),
    key_char     TEXT    NOT NULL,
    attempted_at TEXT    NOT NULL,  -- local time, ISO-8601
    correct      INTEGER NOT NULL   -- 1 = first keystroke correct, 0 = wrong
);
```

The `key_attempts` table is a rolling window: at most 200 rows per (profile_id, key_char). The persistence layer deletes the oldest row on each INSERT when the cap is exceeded. This table is authoritative for the Known criterion — see ADR-027.

#### Deferred to Beta

- `word_stats (profile_id, word, clean_count, attempt_count, last_seen_at)` — per-word performance for Layer 2.
- Visual display columns on `profiles` (added via `ALTER TABLE`): `display_enabled`, `display_text_size`, `display_bg_color`, `display_fg_color`.

`session_key_stats` (previously listed here) is dropped entirely. Its two stated uses — WPM trend reporting and Layer 2 word-length gate — are covered by `sessions` + `word_stats`. The multi-day Known criterion is computed from `key_attempts.attempted_at` timestamps without any per-session breakdown. See ADR-027.

#### Design notes

- All timestamps are local time, no timezone offset (`datetime.now().isoformat(timespec='seconds')`). This is a fully offline, single-device app with no cross-device sync; timezone-aware timestamps would add complexity with no benefit. Session ordering, duration calculation, and parent report display all work correctly with local time.
- A NULL value in any nullable `profiles` column means "fall through to the app-level config" (ADR-025). The persistence layer never writes a default value into the database — it writes NULL and lets the config resolution layer supply the effective value at runtime.
- `key_stats` retains lifetime aggregate counts for gamification displays (total attempts ever, milestone history). It is not the source of truth for Known. `key_attempts` is authoritative for Known — see ADR-027.
- Bronze milestone detection (all home-row graphemes Known) requires ≥ 90 attempts at ≥ 90% accuracy across ≥ 2 distinct practice days, per `key_attempts`. The old "≥ 50 presses from `key_stats`" criterion is superseded by ADR-027.
