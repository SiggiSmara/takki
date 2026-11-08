import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Literal, cast

from takki import config
from takki.persistence import (
    Attempt,
    ChosenBy,
    Introduction,
    KeyStat,
    Landing,
    Level,
    LevelRecord,
    PhaseRecord,
    Profile,
    ReachPress,
    RestKey,
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
    profile_id      INTEGER NOT NULL REFERENCES profiles(id),
    key_char        TEXT    NOT NULL,
    step            INTEGER NOT NULL,
    position        INTEGER NOT NULL,
    introduced_at   TEXT    NOT NULL,
    stable_attempts INTEGER,
    stable_at       TEXT,
    PRIMARY KEY (profile_id, key_char)
);

CREATE TABLE IF NOT EXISTS ramp_up_levels (
    id                INTEGER PRIMARY KEY,
    profile_id        INTEGER NOT NULL REFERENCES profiles(id),
    key_char          TEXT    NOT NULL,
    level             TEXT    NOT NULL CHECK (level IN ('reach', 'choose', 'travel')),
    session_id        INTEGER NOT NULL REFERENCES sessions(id),
    started_presses   INTEGER NOT NULL,
    started_at        TEXT    NOT NULL,
    completed_presses INTEGER,
    completed_at      TEXT,
    UNIQUE (profile_id, key_char, level, session_id)
);

CREATE TABLE IF NOT EXISTS reach_presses (
    id         INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    key_char   TEXT    NOT NULL,
    correct    INTEGER NOT NULL,
    pressed_at TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rp_profile_key ON reach_presses (profile_id, key_char);

CREATE TABLE IF NOT EXISTS landings (
    id         INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    round      INTEGER NOT NULL,
    finger     TEXT    NOT NULL,
    key_row    INTEGER NOT NULL,
    key_col    INTEGER NOT NULL,
    validated  INTEGER NOT NULL,
    landed_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_landings_profile ON landings (profile_id);

CREATE TABLE IF NOT EXISTS rest_keys (
    id          INTEGER PRIMARY KEY,
    profile_id  INTEGER NOT NULL REFERENCES profiles(id),
    finger      TEXT    NOT NULL,
    key_row     INTEGER NOT NULL,
    key_col     INTEGER NOT NULL,
    chosen_by   TEXT    NOT NULL CHECK (chosen_by IN ('landings', 'answer', 'bump')),
    chosen_at   TEXT    NOT NULL,
    ready_at    TEXT,
    passed_at   TEXT,
    replaced_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_rest_keys_current
    ON rest_keys (profile_id, finger) WHERE replaced_at IS NULL;

CREATE TABLE IF NOT EXISTS practice_days (
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    key_char   TEXT    NOT NULL,
    day        TEXT    NOT NULL,
    PRIMARY KEY (profile_id, key_char, day)
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

CREATE TABLE IF NOT EXISTS letter_lengths (
    profile_id  INTEGER NOT NULL REFERENCES profiles(id),
    key_char    TEXT    NOT NULL,
    voice       TEXT    NOT NULL,
    rate        REAL    NOT NULL,
    length_ms   INTEGER NOT NULL,
    recorded_at TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ll_profile_key
    ON letter_lengths (profile_id, key_char, voice, rate);
"""


# Raised by a schema change that an older database cannot be opened under.
# 1: alpha-plan #12m session 2. Every database before it reads 0.
_SCHEMA_VERSION = 1


# A record of a letter's ramp-up needs the letter's introduction.
_INTRODUCED = "SELECT 1 FROM introductions WHERE profile_id = ? AND key_char = ?"


def _never_introduced(key_char: str) -> str:
    return f"{key_char!r} was never introduced"


def _now() -> str:
    # UTC. Every timestamp this module writes is UTC, and local time is a
    # presentation concern (ADR-011 § Timestamps are UTC): naive local strings
    # are not an ordering across a DST fall-back, and no wall-clock stamp is one
    # across a clock correction -- UTC included, since the system clock it reads
    # is not monotonic. The derived ramp-up reads this history positionally.
    return datetime.now(UTC).isoformat(timespec="seconds")


def _stamp(given: str | None) -> str:
    return _now() if given is None else utc_stamp(given)


def _utc_or_none(value: object) -> str | None:
    return None if value is None else utc_stamp(cast(str, value))


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
    def __init__(
        self,
        path: str,
        *,
        window_cap: int = config.ATTEMPT_WINDOW,
        length_cap: int = config.LETTER_LENGTH_SAMPLE,
    ) -> None:
        self.conn = sqlite3.connect(path)
        try:
            self._open()
        except BaseException:
            # Refused, not a database, or killed mid-schema: the handle goes,
            # so a file the message says to delete is not held open. The
            # schema was uncommitted, so none of it stays.
            self.conn.close()
            raise
        self._cap = window_cap
        self._length_cap = length_cap

    def _open(self) -> None:
        # Before anything is written, so a refused database is left as found.
        has_tables = self.conn.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone()
        version = cast(int, self.conn.execute("PRAGMA user_version").fetchone()[0])
        if has_tables is not None and version < _SCHEMA_VERSION:
            # ADR-011, alpha-plan #12m session 2: a key's practice days are
            # kept outside the window from now on. An older database has them
            # only in the window, so its keys would lose days they had. Every
            # database an earlier refusal (#12j's phase table, #12f's latency)
            # was for is older still, so this one check covers them.
            raise RuntimeError(
                f"this Takki database has schema version {version}, older than this Takki's "
                f"{_SCHEMA_VERSION}, and cannot be used; delete it"
            )
        if version > _SCHEMA_VERSION:
            # Opened, it would be stamped back down and then refused by the
            # newer Takki that wrote it.
            raise RuntimeError(
                f"this Takki database has schema version {version}, newer than this Takki's "
                f"{_SCHEMA_VERSION}, and cannot be used"
            )
        # The engine writes key_attempts per keystroke mid-drill; WAL +
        # synchronous=NORMAL avoids an fsync stall on every keypress.
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self.conn.execute("PRAGMA foreign_keys = ON")
        if version == _SCHEMA_VERSION:
            # Creates only a table that is missing, so an open of a current
            # database takes no write lock while another connection writes.
            self.conn.executescript(_SCHEMA)
            return
        # A new database: one transaction, with its version, so a first launch
        # killed part-way leaves no tables rather than some, which the check
        # above would refuse. IMMEDIATE so a second launch at the same moment
        # waits for the first instead of failing on its lock.
        self.conn.executescript(
            f"BEGIN IMMEDIATE;\n{_SCHEMA}\nPRAGMA user_version = {_SCHEMA_VERSION};\nCOMMIT;"
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

    def close(self) -> None:
        # The last connection closing is what folds the WAL back into the one
        # file ADR-011 calls the profile.
        self.conn.close()

    def upsert_key_stat(
        self,
        profile_id: int,
        key_char: str,
        correct: bool,
        practised_at: str | None = None,
    ) -> None:
        self._upsert_key_stat(profile_id, key_char, correct, _stamp(practised_at))
        self.conn.commit()

    def _upsert_key_stat(self, profile_id: int, key_char: str, correct: bool, ts: str) -> None:
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
        # A completion with no start has no evidence it could have been read
        # from, so it is a caller's mistake and not a row to invent.
        key = (profile_id, key_char, phase)
        self._write_once(
            """
            UPDATE ramp_up_phases SET completed_attempts = ?, completed_at = ?
            WHERE profile_id = ? AND key_char = ? AND phase = ?
              AND completed_attempts IS NULL
            """,
            (attempts_at, _stamp(completed_at), *key),
            "SELECT 1 FROM ramp_up_phases WHERE profile_id = ? AND key_char = ? AND phase = ?",
            key,
            f"phase {phase!r} of {key_char!r} was never begun",
        )

    def phase_records(self, profile_id: int, key_char: str) -> dict[str, PhaseRecord]:
        rows = self.conn.execute(
            """
            SELECT phase, started_attempts, completed_attempts FROM ramp_up_phases
            WHERE profile_id = ? AND key_char = ?
            ORDER BY phase
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
        # The row and its practice day, both or neither.
        with self.conn:
            self._append_attempt(
                profile_id, key_char, correct, ts, latency_ms, prev_char, after_letter_ms, timeouts
            )

    def count_attempt(
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
        # One transaction: both are committed or neither is.
        with self.conn:
            self._upsert_key_stat(profile_id, key_char, correct, ts)
            self._append_attempt(
                profile_id, key_char, correct, ts, latency_ms, prev_char, after_letter_ms, timeouts
            )

    def _append_attempt(
        self,
        profile_id: int,
        key_char: str,
        correct: bool,
        ts: str,
        latency_ms: int | None,
        prev_char: str | None,
        after_letter_ms: int | None,
        timeouts: int,
    ) -> None:
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
        # The child's local day, fixed when the press is written: the trim
        # below must not take it away (ADR-011 `practice_days`).
        self.conn.execute(
            """
            INSERT INTO practice_days (profile_id, key_char, day)
            VALUES (?, ?, date(?, 'localtime'))
            ON CONFLICT (profile_id, key_char, day) DO NOTHING
            """,
            (profile_id, key_char, ts),
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

    def key_stats(self, profile_id: int) -> dict[str, KeyStat]:
        rows = self.conn.execute(
            """
            SELECT key_char, attempt_count, correct_count, last_practised_at
            FROM key_stats
            WHERE profile_id = ?
            ORDER BY key_char
            """,
            (profile_id,),
        ).fetchall()
        return {
            cast(str, r[0]): KeyStat(
                attempt_count=cast(int, r[1]),
                correct_count=cast(int, r[2]),
                last_practised_at=_utc_or_none(r[3]),
            )
            for r in rows
        }

    def introductions(self, profile_id: int) -> list[Introduction]:
        rows = self.conn.execute(
            """
            SELECT key_char, step, position, introduced_at, stable_attempts, stable_at
            FROM introductions
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
                stable_attempts=cast(int | None, r[4]),
                stable_at=_utc_or_none(r[5]),
            )
            for r in rows
        ]

    def record_stable(
        self,
        profile_id: int,
        key_char: str,
        attempts: int,
        stable_at: str | None = None,
    ) -> None:
        key = (profile_id, key_char)
        self._write_once(
            """
            UPDATE introductions SET stable_attempts = ?, stable_at = ?
            WHERE profile_id = ? AND key_char = ? AND stable_at IS NULL
            """,
            (attempts, _stamp(stable_at), *key),
            _INTRODUCED,
            key,
            _never_introduced(key_char),
        )

    def _write_once(
        self,
        update: str,
        params: tuple[object, ...],
        exists: str,
        key: tuple[object, ...],
        refusal: str,
    ) -> None:
        """Write an event's column once: again is no change, and with no row to go in is refused."""
        # `with`: the UPDATE opens a transaction, and on any error, the refusal
        # included, it is rolled back so that its lock does not outlive it.
        with self.conn:
            if self.conn.execute(update, params).rowcount == 0 and not self._exists(exists, key):
                raise ValueError(refusal)

    def _check_introduced(self, profile_id: int, key_char: str) -> None:
        if not self._exists(_INTRODUCED, (profile_id, key_char)):
            raise ValueError(_never_introduced(key_char))

    def _exists(self, sql: str, params: tuple[object, ...]) -> bool:
        return self.conn.execute(sql, params).fetchone() is not None

    def _check_session(self, profile_id: int, session_id: int) -> None:
        # The foreign key only asks that the session exists. The `rest` rung
        # reads a profile's sessions, so another child's would be counted.
        if not self._exists(
            "SELECT 1 FROM sessions WHERE id = ? AND profile_id = ?", (session_id, profile_id)
        ):
            raise ValueError(f"session {session_id} is not profile {profile_id}'s")

    def begin_level(
        self,
        profile_id: int,
        key_char: str,
        level: Level,
        session_id: int,
        presses: int,
        started_at: str | None = None,
    ) -> None:
        ts = _stamp(started_at)
        self._check_session(profile_id, session_id)
        self._check_introduced(profile_id, key_char)
        # `with`: a refused INSERT (the level's CHECK) rolls back, and no lock stays.
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO ramp_up_levels
                    (profile_id, key_char, level, session_id, started_presses, started_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (profile_id, key_char, level, session_id) DO NOTHING
                """,
                (profile_id, key_char, level, session_id, presses, ts),
            )

    def complete_level(
        self,
        profile_id: int,
        key_char: str,
        level: Level,
        session_id: int,
        presses: int,
        completed_at: str | None = None,
    ) -> None:
        key = (profile_id, key_char, level, session_id)
        self._write_once(
            """
            UPDATE ramp_up_levels SET completed_presses = ?, completed_at = ?
            WHERE profile_id = ? AND key_char = ? AND level = ? AND session_id = ?
              AND completed_presses IS NULL
            """,
            (presses, _stamp(completed_at), *key),
            """
            SELECT 1 FROM ramp_up_levels
            WHERE profile_id = ? AND key_char = ? AND level = ? AND session_id = ?
            """,
            key,
            f"level {level!r} of {key_char!r} was never begun in that session",
        )

    def level_records(self, profile_id: int, key_char: str) -> list[LevelRecord]:
        rows = self.conn.execute(
            """
            SELECT level, session_id, started_presses, started_at, completed_presses, completed_at
            FROM ramp_up_levels
            WHERE profile_id = ? AND key_char = ?
            ORDER BY id
            """,
            (profile_id, key_char),
        ).fetchall()
        return [
            LevelRecord(
                level=cast(Level, r[0]),
                session_id=cast(int, r[1]),
                started_presses=cast(int, r[2]),
                started_at=utc_stamp(cast(str, r[3])),
                completed_presses=cast(int | None, r[4]),
                completed_at=_utc_or_none(r[5]),
            )
            for r in rows
        ]

    def append_reach_press(
        self,
        profile_id: int,
        key_char: str,
        correct: bool,
        pressed_at: str | None = None,
    ) -> None:
        ts = _stamp(pressed_at)
        self._check_introduced(profile_id, key_char)
        with self.conn:
            self.conn.execute(
                "INSERT INTO reach_presses (profile_id, key_char, correct, pressed_at)"
                " VALUES (?, ?, ?, ?)",
                (profile_id, key_char, int(correct), ts),
            )

    def reach_presses(self, profile_id: int, key_char: str) -> list[ReachPress]:
        rows = self.conn.execute(
            """
            SELECT correct, pressed_at FROM reach_presses
            WHERE profile_id = ? AND key_char = ?
            ORDER BY id
            """,
            (profile_id, key_char),
        ).fetchall()
        return [ReachPress(bool(r[0]), utc_stamp(cast(str, r[1]))) for r in rows]

    def record_landing(
        self,
        profile_id: int,
        session_id: int,
        round: int,
        finger: str,
        row: int,
        col: int,
        validated: bool,
        landed_at: str | None = None,
    ) -> None:
        ts = _stamp(landed_at)
        self._check_session(profile_id, session_id)
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO landings
                    (profile_id, session_id, round, finger, key_row, key_col, validated, landed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (profile_id, session_id, round, finger, row, col, int(validated), ts),
            )

    def landings(self, profile_id: int) -> list[Landing]:
        rows = self.conn.execute(
            """
            SELECT session_id, round, finger, key_row, key_col, validated, landed_at
            FROM landings
            WHERE profile_id = ?
            ORDER BY id
            """,
            (profile_id,),
        ).fetchall()
        return [
            Landing(
                session_id=cast(int, r[0]),
                round=cast(int, r[1]),
                finger=cast(str, r[2]),
                row=cast(int, r[3]),
                col=cast(int, r[4]),
                validated=bool(r[5]),
                landed_at=utc_stamp(cast(str, r[6])),
            )
            for r in rows
        ]

    def choose_rest_key(
        self,
        profile_id: int,
        finger: str,
        row: int,
        col: int,
        chosen_by: ChosenBy,
        chosen_at: str | None = None,
    ) -> None:
        ts = _stamp(chosen_at)
        current = self.conn.execute(
            """
            SELECT key_row, key_col FROM rest_keys
            WHERE profile_id = ? AND finger = ? AND replaced_at IS NULL
            """,
            (profile_id, finger),
        ).fetchone()
        if current is not None and tuple(current) == (row, col):
            # The same key chosen again is no change, and its ready and passed
            # events stand (ADR-033: a changed key starts afresh, a kept one does not).
            return
        # One transaction: a finger never has two current keys, or none between them.
        with self.conn:
            self.conn.execute(
                """
                UPDATE rest_keys SET replaced_at = ?
                WHERE profile_id = ? AND finger = ? AND replaced_at IS NULL
                """,
                (ts, profile_id, finger),
            )
            self.conn.execute(
                """
                INSERT INTO rest_keys (profile_id, finger, key_row, key_col, chosen_by, chosen_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (profile_id, finger, row, col, chosen_by, ts),
            )

    def mark_rest_key_ready(
        self, profile_id: int, finger: str, ready_at: str | None = None
    ) -> None:
        self._mark_rest_key(profile_id, finger, "ready_at", _stamp(ready_at))

    def mark_rest_key_passed(
        self, profile_id: int, finger: str, passed_at: str | None = None
    ) -> None:
        self._mark_rest_key(profile_id, finger, "passed_at", _stamp(passed_at))

    def _mark_rest_key(
        self, profile_id: int, finger: str, column: Literal["ready_at", "passed_at"], ts: str
    ) -> None:
        self._write_once(
            f"""
            UPDATE rest_keys SET {column} = ?
            WHERE profile_id = ? AND finger = ? AND replaced_at IS NULL AND {column} IS NULL
            """,
            (ts, profile_id, finger),
            "SELECT 1 FROM rest_keys WHERE profile_id = ? AND finger = ? AND replaced_at IS NULL",
            (profile_id, finger),
            f"finger {finger!r} has no rest key",
        )

    def rest_keys(self, profile_id: int) -> list[RestKey]:
        rows = self.conn.execute(
            """
            SELECT finger, key_row, key_col, chosen_by, chosen_at, ready_at, passed_at, replaced_at
            FROM rest_keys
            WHERE profile_id = ?
            ORDER BY id
            """,
            (profile_id,),
        ).fetchall()
        return [
            RestKey(
                finger=cast(str, r[0]),
                row=cast(int, r[1]),
                col=cast(int, r[2]),
                chosen_by=cast(ChosenBy, r[3]),
                chosen_at=utc_stamp(cast(str, r[4])),
                ready_at=_utc_or_none(r[5]),
                passed_at=_utc_or_none(r[6]),
                replaced_at=_utc_or_none(r[7]),
            )
            for r in rows
        ]

    def window_stats(self, profile_id: int, key_char: str) -> WindowStats:
        row = self.conn.execute(
            """
            SELECT
                COUNT(*)     AS attempt_count,
                SUM(correct) AS correct_count,
                (SELECT COUNT(*) FROM practice_days
                 WHERE profile_id = :profile AND key_char = :key) AS distinct_days
            FROM key_attempts
            WHERE profile_id = :profile AND key_char = :key
            """,
            {"profile": profile_id, "key": key_char},
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

    def append_letter_lengths(
        self,
        profile_id: int,
        voice: str,
        rate: float,
        lengths: Sequence[tuple[str, int]],
        recorded_at: str | None = None,
    ) -> None:
        ts = _stamp(recorded_at)
        self.conn.executemany(
            """
            INSERT INTO letter_lengths (profile_id, key_char, voice, rate, length_ms, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [(profile_id, key_char, voice, rate, ms, ts) for key_char, ms in lengths],
        )
        for key_char in {key_char for key_char, _ in lengths}:
            self.conn.execute(
                """
                DELETE FROM letter_lengths
                WHERE profile_id = ? AND key_char = ? AND voice = ? AND rate = ?
                  AND rowid NOT IN (
                    SELECT rowid FROM letter_lengths
                    WHERE profile_id = ? AND key_char = ? AND voice = ? AND rate = ?
                    ORDER BY rowid DESC
                    LIMIT ?
                )
                """,
                (profile_id, key_char, voice, rate) * 2 + (self._length_cap,),
            )
        self.conn.commit()

    def letter_lengths(self, profile_id: int, key_char: str, voice: str, rate: float) -> list[int]:
        rows = self.conn.execute(
            """
            SELECT length_ms FROM letter_lengths
            WHERE profile_id = ? AND key_char = ? AND voice = ? AND rate = ?
            ORDER BY rowid ASC
            """,
            (profile_id, key_char, voice, rate),
        ).fetchall()
        return [cast(int, r[0]) for r in rows]

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
        # Rungs fired at one block boundary share a stamp; `rowid` keeps
        # those in the order they were earned.
        rows = self.conn.execute(
            "SELECT level FROM milestones WHERE profile_id = ? ORDER BY achieved_at, rowid",
            (profile_id,),
        ).fetchall()
        return [cast(str, r[0]) for r in rows]
