import sqlite3
from datetime import datetime
from typing import Any, cast

from takki.persistence import Profile, WindowStats

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    language    TEXT    NOT NULL DEFAULT 'en',
    tts_voice   TEXT,
    tts_rate    REAL,
    talk_key    TEXT,
    reread_key  TEXT,
    restart_key TEXT,
    ptt_mode    TEXT,
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY,
    profile_id  INTEGER NOT NULL REFERENCES profiles(id),
    started_at  TEXT    NOT NULL,
    ended_at    TEXT
);

CREATE TABLE IF NOT EXISTS key_stats (
    profile_id        INTEGER NOT NULL REFERENCES profiles(id),
    key_char          TEXT    NOT NULL,
    attempt_count     INTEGER NOT NULL DEFAULT 0,
    correct_count     INTEGER NOT NULL DEFAULT 0,
    last_practised_at TEXT,
    PRIMARY KEY (profile_id, key_char)
);

CREATE TABLE IF NOT EXISTS milestones (
    profile_id  INTEGER NOT NULL REFERENCES profiles(id),
    level       TEXT    NOT NULL,
    achieved_at TEXT    NOT NULL,
    PRIMARY KEY (profile_id, level)
);

CREATE TABLE IF NOT EXISTS key_attempts (
    profile_id   INTEGER NOT NULL REFERENCES profiles(id),
    key_char     TEXT    NOT NULL,
    attempted_at TEXT    NOT NULL,
    correct      INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ka_profile_key
    ON key_attempts (profile_id, key_char, attempted_at, correct);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _row_to_profile(row: tuple[Any, ...]) -> Profile:
    return Profile(
        id=cast(int, row[0]),
        name=cast(str, row[1]),
        language=cast(str, row[2]),
        created_at=cast(str, row[3]),
        tts_voice=cast(str | None, row[4]),
        tts_rate=cast(float | None, row[5]),
        talk_key=cast(str | None, row[6]),
        reread_key=cast(str | None, row[7]),
        restart_key=cast(str | None, row[8]),
        ptt_mode=cast(str | None, row[9]),
    )


_PROFILE_SELECT = """
    SELECT id, name, language, created_at, tts_voice, tts_rate,
           talk_key, reread_key, restart_key, ptt_mode
    FROM profiles
"""


class SqliteStore:
    def __init__(self, path: str, *, window_cap: int = 200) -> None:
        self.conn = sqlite3.connect(path)
        # The engine writes key_attempts per keystroke mid-drill; WAL +
        # synchronous=NORMAL avoids an fsync stall on every keypress.
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(_SCHEMA)
        self._cap = window_cap

    def create_profile(
        self,
        name: str,
        language: str = "en",
        *,
        tts_voice: str | None = None,
        tts_rate: float | None = None,
        talk_key: str | None = None,
        reread_key: str | None = None,
        restart_key: str | None = None,
        ptt_mode: str | None = None,
        created_at: str | None = None,
    ) -> Profile:
        ts = created_at or _now()
        cur = self.conn.execute(
            """
            INSERT INTO profiles
                (name, language, tts_voice, tts_rate, talk_key, reread_key,
                 restart_key, ptt_mode, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (name, language, tts_voice, tts_rate, talk_key, reread_key, restart_key, ptt_mode, ts),
        )
        self.conn.commit()
        return Profile(
            id=cast(int, cur.lastrowid),
            name=name,
            language=language,
            created_at=ts,
            tts_voice=tts_voice,
            tts_rate=tts_rate,
            talk_key=talk_key,
            reread_key=reread_key,
            restart_key=restart_key,
            ptt_mode=ptt_mode,
        )

    def get_profile(self, profile_id: int) -> Profile | None:
        row = self.conn.execute(
            _PROFILE_SELECT + "WHERE id = ?",
            (profile_id,),
        ).fetchone()
        return _row_to_profile(row) if row is not None else None

    def list_profiles(self) -> list[Profile]:
        rows = self.conn.execute(_PROFILE_SELECT + "ORDER BY id").fetchall()
        return [_row_to_profile(r) for r in rows]

    def start_session(self, profile_id: int, started_at: str | None = None) -> int:
        ts = started_at or _now()
        cur = self.conn.execute(
            "INSERT INTO sessions (profile_id, started_at) VALUES (?, ?)",
            (profile_id, ts),
        )
        self.conn.commit()
        return cast(int, cur.lastrowid)

    def end_session(self, session_id: int, ended_at: str | None = None) -> None:
        ts = ended_at or _now()
        self.conn.execute(
            "UPDATE sessions SET ended_at = ? WHERE id = ?",
            (ts, session_id),
        )
        self.conn.commit()

    def upsert_key_stat(
        self,
        profile_id: int,
        key_char: str,
        correct: bool,
        practised_at: str | None = None,
    ) -> None:
        ts = practised_at or _now()
        self.conn.execute(
            """
            INSERT INTO key_stats
                (profile_id, key_char, attempt_count, correct_count, last_practised_at)
            VALUES (?, ?, 1, ?, ?)
            ON CONFLICT(profile_id, key_char) DO UPDATE SET
                attempt_count     = attempt_count + 1,
                correct_count     = correct_count + excluded.correct_count,
                last_practised_at = excluded.last_practised_at
            """,
            (profile_id, key_char, int(correct), ts),
        )
        self.conn.commit()

    def bump_key_recency(
        self,
        profile_id: int,
        key_char: str,
        practised_at: str | None = None,
    ) -> None:
        ts = practised_at or _now()
        self.conn.execute(
            "UPDATE key_stats SET last_practised_at = ? WHERE profile_id = ? AND key_char = ?",
            (ts, profile_id, key_char),
        )
        self.conn.commit()

    def append_attempt(
        self,
        profile_id: int,
        key_char: str,
        correct: bool,
        attempted_at: str | None = None,
    ) -> None:
        ts = attempted_at or _now()
        self.conn.execute(
            "INSERT INTO key_attempts (profile_id, key_char, correct, attempted_at) VALUES (?, ?, ?, ?)",
            (profile_id, key_char, int(correct), ts),
        )
        row = self.conn.execute(
            "SELECT COUNT(*) FROM key_attempts WHERE profile_id = ? AND key_char = ?",
            (profile_id, key_char),
        ).fetchone()
        excess = cast(int, row[0]) - self._cap
        if excess > 0:
            self.conn.execute(
                """
                DELETE FROM key_attempts WHERE rowid IN (
                    SELECT rowid FROM key_attempts
                    WHERE profile_id = ? AND key_char = ?
                    ORDER BY attempted_at ASC, rowid ASC
                    LIMIT ?
                )
                """,
                (profile_id, key_char, excess),
            )
        self.conn.commit()

    def window_stats(self, profile_id: int, key_char: str) -> WindowStats:
        row = self.conn.execute(
            """
            SELECT
                COUNT(*)                             AS attempt_count,
                SUM(correct)                         AS correct_count,
                COUNT(DISTINCT date(attempted_at))   AS distinct_days
            FROM key_attempts
            WHERE profile_id = ? AND key_char = ?
            """,
            (profile_id, key_char),
        ).fetchone()
        return WindowStats(
            attempt_count=cast(int, row[0]),
            correct_count=cast(int, row[1] or 0),
            distinct_days=cast(int, row[2]),
        )

    def record_milestone(
        self,
        profile_id: int,
        level: str,
        achieved_at: str | None = None,
    ) -> None:
        ts = achieved_at or _now()
        self.conn.execute(
            "INSERT OR IGNORE INTO milestones (profile_id, level, achieved_at) VALUES (?, ?, ?)",
            (profile_id, level, ts),
        )
        self.conn.commit()

    def achieved_milestones(self, profile_id: int) -> list[str]:
        rows = self.conn.execute(
            "SELECT level FROM milestones WHERE profile_id = ? ORDER BY achieved_at",
            (profile_id,),
        ).fetchall()
        return [cast(str, r[0]) for r in rows]
