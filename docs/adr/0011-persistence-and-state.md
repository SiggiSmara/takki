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

Each child has a named profile selected at startup (spoken menu). Multiple children can share one installation. Each profile stores:
- Visual display settings (on/off, text size, background color, foreground color, cursor style) — see ADR-016
- Voice settings (`tts_rate`, `tts_voice`, `language` override) — see ADR-003

**Profile portability:** the SQLite file *is* the profile data. It lives at `%APPDATA%\Takki\takki.sqlite` on Windows (the cross-platform location is the standard per-user application data folder reported by the platform interface). To move a child's progress to another computer, copy that file to the same location on the destination machine and rename if necessary to avoid colliding with an existing profile. No export/import flow is provided in v1 — the file is the export format. Parents are reminded of this in the parent/teacher summary (ADR-014).
