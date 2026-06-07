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
```

#### Deferred to Beta

- `session_key_stats (session_id, profile_id, key_char, attempts, correct_count)` — per-session breakdown needed for WPM trend reporting (ADR-014) and Layer 2 word-length advancement gate.
- `word_stats (profile_id, word, clean_count, attempt_count, last_seen_at)` — per-word performance for Layer 2.
- Visual display columns on `profiles` (added via `ALTER TABLE`): `display_enabled`, `display_text_size`, `display_bg_color`, `display_fg_color`.

#### Design notes

- All timestamps are local time, no timezone offset (`datetime.now().isoformat(timespec='seconds')`). This is a fully offline, single-device app with no cross-device sync; timezone-aware timestamps would add complexity with no benefit. Session ordering, duration calculation, and parent report display all work correctly with local time.
- A NULL value in any nullable `profiles` column means "fall through to the app-level config" (ADR-025). The persistence layer never writes a default value into the database — it writes NULL and lets the config resolution layer supply the effective value at runtime.
- `key_stats` uses aggregate counts rather than a per-session breakdown for Alpha. Bronze milestone detection (home row keys at ≥ 90% over ≥ 50 presses) is computable from `correct_count / attempt_count` directly.
