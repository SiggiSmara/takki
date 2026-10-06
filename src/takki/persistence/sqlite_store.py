import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast

from takki import config
from takki.persistence import (
    Attempt,
    Introduction,
    KeyStat,
    PhaseRecord,
    Profile,
    WindowStats,
    utc_stamp,
)

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

CREATE TABLE IF NOT EXISTS introductions (
    profile_id    INTEGER NOT NULL REFERENCES profiles(id),
    key_char      TEXT    NOT NULL,
    step          INTEGER NOT NULL,
    position      INTEGER NOT NULL,
    introduced_at TEXT    NOT NULL,
    PRIMARY KEY (profile_id, key_char)
);

CREATE TABLE IF NOT EXISTS ramp_up_phases (
    profile_id         INTEGER NOT NULL REFERENCES profiles(id),
    key_char           TEXT    NOT NULL,
    phase              TEXT    NOT NULL,
    started_attempts   INTEGER NOT NULL,
    started_at         TEXT    NOT NULL,
    completed_attempts INTEGER,
    completed_at       TEXT,
    PRIMARY KEY (profile_id, key_char, phase)
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
    correct      INTEGER NOT NULL,
    latency_ms   INTEGER,
    prev_char    TEXT,
    after_letter_ms    INTEGER,
    timeouts     INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_ka_profile_key
    ON key_attempts (profile_id, key_char, attempted_at, correct);
"""


def _now() -> str:
    # UTC. Every timestamp this module writes is UTC, and local time is a
    # presentation concern (ADR-011 § Timestamps are UTC): naive local strings
    # are not an ordering across a DST fall-back, and no wall-clock stamp is one
    # across a clock correction -- UTC included, since the system clock it reads
    # is not monotonic. The derived ramp-up reads this history positionally.
    return datetime.now(UTC).isoformat(timespec="seconds")


def _stamp(given: str | None) -> str:
    return _now() if given is None else utc_stamp(given)


def _row_to_profile(row: tuple[Any, ...]) -> Profile:
    return Profile(
        id=cast(int, row[0]),
        name=cast(str, row[1]),
        language=cast(str, row[2]),
        created_at=utc_stamp(cast(str, row[3])),
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
    def __init__(self, path: str, *, window_cap: int = config.ATTEMPT_WINDOW) -> None:
        self.conn = sqlite3.connect(path)
        # The engine writes key_attempts per keystroke mid-drill; WAL +
        # synchronous=NORMAL avoids an fsync stall on every keypress.
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(_SCHEMA)
        self._migrate()
        self._cap = window_cap

    def _migrate(self) -> None:
        phase_columns = {
            cast(str, row[1])
            for row in self.conn.execute("PRAGMA table_info(ramp_up_phases)").fetchall()
        }
        if "started_attempts" not in phase_columns:
            # ADR-011, 2026-10-04: the table changed shape and old rows cannot
            # say where a phase began. Said here, or it surfaces as a missing
            # column at the first phase read, mid-session.
            raise RuntimeError(
                "this Takki database was written before 2026-10-04 and cannot be used; delete it"
            )
        attempt_columns = {
            cast(str, row[1])
            for row in self.conn.execute("PRAGMA table_info(key_attempts)").fetchall()
        }
        if "after_letter_ms" not in attempt_columns:
            # ADR-011, alpha-plan #12f: `latency_ms` changed meaning (it now
            # runs from the letter being sent, not from its end) and an old
            # row cannot say which meaning its value has.
            raise RuntimeError(
                "this Takki database was written before alpha-plan #12f and cannot be used; "
                "delete it"
            )

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
        ts = _stamp(created_at)
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
        ts = _stamp(started_at)
        cur = self.conn.execute(
            "INSERT INTO sessions (profile_id, started_at) VALUES (?, ?)",
            (profile_id, ts),
        )
        self.conn.commit()
        return cast(int, cur.lastrowid)

    def end_session(self, session_id: int, ended_at: str | None = None) -> None:
        ts = _stamp(ended_at)
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
        ts = _stamp(practised_at)
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
        ts = _stamp(practised_at)
        self.conn.execute(
            "UPDATE key_stats SET last_practised_at = ? WHERE profile_id = ? AND key_char = ?",
            (ts, profile_id, key_char),
        )
        self.conn.commit()

    def mark_introduced(
        self,
        profile_id: int,
        key_chars: Sequence[str],
        introduced_at: str | None = None,
    ) -> int:
        # The step ordinal is what groups and orders steps -- not the timestamp,
        # which no longer carries identity (ADR-011 § The step ordinal). A member
        # already introduced keeps the step it had: re-introducing is not a
        # thing, and moving a key's step would move it under a resumed ramp-up.
        ts = _stamp(introduced_at)
        row = self.conn.execute(
            "SELECT MAX(step) FROM introductions WHERE profile_id = ?", (profile_id,)
        ).fetchone()
        step = cast(int, row[0] or 0) + 1
        for position, key_char in enumerate(key_chars):
            self.conn.execute(
                """
                INSERT OR IGNORE INTO introductions
                    (profile_id, key_char, step, position, introduced_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (profile_id, key_char, step, position, ts),
            )
        self.conn.commit()
        return step

    def begin_phase(
        self,
        profile_id: int,
        key_char: str,
        phase: str,
        attempts_at: int,
        started_at: str | None = None,
    ) -> None:
        # Write-once: the phase's evidence is the key's attempts after this
        # count, and moving it would move the evidence under the child.
        ts = _stamp(started_at)
        self.conn.execute(
            """
            INSERT OR IGNORE INTO ramp_up_phases
                (profile_id, key_char, phase, started_attempts, started_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (profile_id, key_char, phase, attempts_at, ts),
        )
        self.conn.commit()

    def record_phase(
        self,
        profile_id: int,
        key_char: str,
        phase: str,
        attempts_at: int,
        completed_at: str | None = None,
    ) -> None:
        # Write-once: a phase a child has passed stays passed (ADR-024 § A phase
        # completion is an event). `attempts_at` is the key's lifetime attempt
        # count at that moment, which no rolling window can evict.
        ts = _stamp(completed_at)
        cursor = self.conn.execute(
            """
            UPDATE ramp_up_phases SET completed_attempts = ?, completed_at = ?
            WHERE profile_id = ? AND key_char = ? AND phase = ?
              AND completed_attempts IS NULL
            """,
            (attempts_at, ts, profile_id, key_char, phase),
        )
        if cursor.rowcount == 0 and phase not in self.phase_records(profile_id, key_char):
            # A completion with no start has no evidence it could have been
            # read from, so it is a caller's mistake and not a row to invent.
            raise ValueError(f"phase {phase!r} of {key_char!r} was never begun")
        self.conn.commit()

    def phase_records(self, profile_id: int, key_char: str) -> dict[str, PhaseRecord]:
        rows = self.conn.execute(
            """
            SELECT phase, started_attempts, completed_attempts FROM ramp_up_phases
            WHERE profile_id = ? AND key_char = ?
            """,
            (profile_id, key_char),
        ).fetchall()
        return {
            cast(str, r[0]): PhaseRecord(cast(int, r[1]), cast("int | None", r[2])) for r in rows
        }

    def append_attempt(
        self,
        profile_id: int,
        key_char: str,
        correct: bool,
        attempted_at: str | None = None,
        latency_ms: int | None = None,
        prev_char: str | None = None,
        after_letter_ms: int | None = None,
        timeouts: int = 0,
    ) -> None:
        ts = _stamp(attempted_at)
        self.conn.execute(
            """
            INSERT INTO key_attempts
                (profile_id, key_char, correct, attempted_at, latency_ms, prev_char,
                 after_letter_ms, timeouts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile_id,
                key_char,
                int(correct),
                ts,
                latency_ms,
                prev_char,
                after_letter_ms,
                timeouts,
            ),
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
                    ORDER BY rowid ASC
                    LIMIT ?
                )
                """,
                (profile_id, key_char, excess),
            )
        self.conn.commit()

    def key_stats(self, profile_id: int) -> dict[str, KeyStat]:
        rows = self.conn.execute(
            """
            SELECT key_char, attempt_count, correct_count, last_practised_at
            FROM key_stats
            WHERE profile_id = ?
            """,
            (profile_id,),
        ).fetchall()
        return {
            cast(str, r[0]): KeyStat(
                attempt_count=cast(int, r[1]),
                correct_count=cast(int, r[2]),
                last_practised_at=None if r[3] is None else utc_stamp(cast(str, r[3])),
            )
            for r in rows
        }

    def introductions(self, profile_id: int) -> list[Introduction]:
        rows = self.conn.execute(
            """
            SELECT key_char, step, position, introduced_at FROM introductions
            WHERE profile_id = ?
            ORDER BY step ASC, position ASC
            """,
            (profile_id,),
        ).fetchall()
        return [
            Introduction(
                key_char=cast(str, r[0]),
                step=cast(int, r[1]),
                position=cast(int, r[2]),
                introduced_at=utc_stamp(cast(str, r[3])),
            )
            for r in rows
        ]

    def window_stats(self, profile_id: int, key_char: str) -> WindowStats:
        row = self.conn.execute(
            """
            SELECT
                COUNT(*)                             AS attempt_count,
                SUM(correct)                         AS correct_count,
                COUNT(DISTINCT date(attempted_at, 'localtime')) AS distinct_days
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

    def window_attempts(
        self, profile_id: int, key_char: str, limit: int | None = None
    ) -> list[Attempt]:
        """The window in the order the child typed it, oldest first.

        **Ordered by `rowid` alone**, which is insertion order. `attempted_at`
        looks like an ordering and is not one: a clock correction makes a later
        answer sort earlier even in UTC, because the system clock it comes from
        is not monotonic. Every consumer in `takki.lesson.rampup` reads this list
        positionally as the sequence of answers. The trim above evicts by the same key for the same reason.

        `limit` returns only the newest `limit` rows, still oldest-first. The
        derived bars know how many rows they can possibly need, and reading 200
        to decide a 10-long streak is work done on every keypress.
        """
        rows = self.conn.execute(
            """
            SELECT correct, attempted_at, latency_ms, prev_char, after_letter_ms, timeouts FROM (
                SELECT rowid, correct, attempted_at, latency_ms, prev_char, after_letter_ms, timeouts
                FROM key_attempts
                WHERE profile_id = ? AND key_char = ?
                ORDER BY rowid DESC
                LIMIT ?
            ) ORDER BY rowid ASC
            """,
            (profile_id, key_char, self._cap if limit is None else limit),
        ).fetchall()
        return [
            Attempt(
                correct=bool(r[0]),
                attempted_at=utc_stamp(cast(str, r[1])),
                latency_ms=cast(int | None, r[2]),
                prev_char=cast(str | None, r[3]),
                after_letter_ms=cast(int | None, r[4]),
                timeouts=cast(int, r[5]),
            )
            for r in rows
        ]

    def record_milestone(
        self,
        profile_id: int,
        level: str,
        achieved_at: str | None = None,
    ) -> None:
        ts = _stamp(achieved_at)
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
