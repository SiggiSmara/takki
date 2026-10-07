from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime

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


def _now() -> str:
    # UTC, as SqliteStore writes (ADR-011 § Timestamps are UTC).
    return datetime.now(UTC).isoformat(timespec="seconds")


def _stamp(given: str | None) -> str:
    return _now() if given is None else utc_stamp(given)


def _local_day(stamp: str) -> str:
    """The local calendar day of a UTC stamp — SQLite's `date(x, 'localtime')`."""
    # A practice day is the child's day, not UTC's (ADR-027 § Known). Parity
    # with the real store matters here, since `distinct_days` gates Known.
    return datetime.fromisoformat(stamp).astimezone().date().isoformat()


class FakeStore:
    def __init__(
        self,
        *,
        window_cap: int = config.ATTEMPT_WINDOW,
        length_cap: int = config.LETTER_LENGTH_SAMPLE,
    ) -> None:
        self._profiles: dict[int, Profile] = {}
        self._next_profile_id = 1
        self._sessions: dict[int, tuple[int, str, str | None]] = {}
        self._next_session_id = 1
        self._key_stats: dict[tuple[int, str], tuple[int, int, str | None]] = {}
        self._introductions: dict[tuple[int, str], Introduction] = {}
        self._phases: dict[tuple[int, str, str], PhaseRecord] = {}
        self._key_attempts: dict[tuple[int, str], list[Attempt]] = {}
        self._milestones: dict[tuple[int, str], str] = {}
        self._letter_lengths: dict[tuple[int, str, str, float], list[int]] = {}
        self._cap = window_cap
        self._length_cap = length_cap

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
        profile = Profile(
            id=self._next_profile_id,
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
        self._profiles[self._next_profile_id] = profile
        self._next_profile_id += 1
        return profile

    def get_profile(self, profile_id: int) -> Profile | None:
        return self._profiles.get(profile_id)

    def list_profiles(self) -> list[Profile]:
        return list(self._profiles.values())

    def start_session(self, profile_id: int, started_at: str | None = None) -> int:
        ts = _stamp(started_at)
        session_id = self._next_session_id
        self._sessions[session_id] = (profile_id, ts, None)
        self._next_session_id += 1
        return session_id

    def end_session(self, session_id: int, ended_at: str | None = None) -> None:
        ts = _stamp(ended_at)
        pid, started_at, _ = self._sessions[session_id]
        self._sessions[session_id] = (pid, started_at, ts)

    def sessions(self) -> list[tuple[int, str, str | None]]:
        """Every session row, in id order. Not on the Store Protocol -- session
        logging has no reader yet, so this exists for tests only."""
        return [self._sessions[key] for key in sorted(self._sessions)]

    def upsert_key_stat(
        self,
        profile_id: int,
        key_char: str,
        correct: bool,
        practised_at: str | None = None,
    ) -> None:
        ts = _stamp(practised_at)
        key = (profile_id, key_char)
        if key in self._key_stats:
            ac, cc, _ = self._key_stats[key]
            self._key_stats[key] = (ac + 1, cc + (int(correct)), ts)
        else:
            self._key_stats[key] = (1, int(correct), ts)

    def bump_key_recency(
        self,
        profile_id: int,
        key_char: str,
        practised_at: str | None = None,
    ) -> None:
        ts = _stamp(practised_at)
        key = (profile_id, key_char)
        if key in self._key_stats:
            ac, cc, _ = self._key_stats[key]
            self._key_stats[key] = (ac, cc, ts)

    def mark_introduced(
        self,
        profile_id: int,
        key_chars: Sequence[str],
        introduced_at: str | None = None,
    ) -> int:
        ts = _stamp(introduced_at)
        steps = [i.step for (pid, _), i in self._introductions.items() if pid == profile_id]
        step = max(steps, default=0) + 1
        for position, key_char in enumerate(key_chars):
            # First introduction wins, as SqliteStore's INSERT OR IGNORE does.
            self._introductions.setdefault(
                (profile_id, key_char),
                Introduction(key_char=key_char, step=step, position=position, introduced_at=ts),
            )
        return step

    def begin_phase(
        self,
        profile_id: int,
        key_char: str,
        phase: str,
        attempts_at: int,
        started_at: str | None = None,
    ) -> None:
        _stamp(started_at)  # Checked as the real store checks it; the fake has no reader for it.
        self._phases.setdefault((profile_id, key_char, phase), PhaseRecord(attempts_at))

    def record_phase(
        self,
        profile_id: int,
        key_char: str,
        phase: str,
        attempts_at: int,
        completed_at: str | None = None,
    ) -> None:
        _stamp(completed_at)
        record = self._phases.get((profile_id, key_char, phase))
        if record is None:
            raise ValueError(f"phase {phase!r} of {key_char!r} was never begun")
        if record.completed_attempts is None:
            self._phases[(profile_id, key_char, phase)] = replace(
                record, completed_attempts=attempts_at
            )

    def phase_records(self, profile_id: int, key_char: str) -> dict[str, PhaseRecord]:
        return {
            phase: record
            for (pid, name, phase), record in self._phases.items()
            if pid == profile_id and name == key_char
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
        key = (profile_id, key_char)
        if key not in self._key_attempts:
            self._key_attempts[key] = []
        attempts = self._key_attempts[key]
        attempts.append(
            Attempt(
                correct=correct,
                attempted_at=ts,
                latency_ms=latency_ms,
                prev_char=prev_char,
                after_letter_ms=after_letter_ms,
                timeouts=timeouts,
            )
        )
        if len(attempts) > self._cap:
            # Insertion order, which is what SqliteStore's ORDER BY rowid ASC
            # evicts. Evicting by timestamp would drop the row just written
            # whenever the clock has moved backwards.
            del attempts[0]

    def key_stats(self, profile_id: int) -> dict[str, KeyStat]:
        return {
            key_char: KeyStat(attempt_count=ac, correct_count=cc, last_practised_at=ts)
            for (pid, key_char), (ac, cc, ts) in self._key_stats.items()
            if pid == profile_id
        }

    def introductions(self, profile_id: int) -> list[Introduction]:
        return sorted(
            (i for (pid, _), i in self._introductions.items() if pid == profile_id),
            key=lambda i: (i.step, i.position),
        )

    def window_stats(self, profile_id: int, key_char: str) -> WindowStats:
        attempts = self._key_attempts.get((profile_id, key_char), [])
        return WindowStats(
            attempt_count=len(attempts),
            correct_count=sum(int(a.correct) for a in attempts),
            distinct_days=len({_local_day(a.attempted_at) for a in attempts}),
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
        # Stamped once and checked before either write, so a refused stamp
        # leaves nothing behind, as SqliteStore's one transaction does.
        ts = _stamp(attempted_at)
        self.upsert_key_stat(profile_id, key_char, correct, ts)
        self.append_attempt(
            profile_id, key_char, correct, ts, latency_ms, prev_char, after_letter_ms, timeouts
        )

    def window_attempts(
        self, profile_id: int, key_char: str, limit: int | None = None
    ) -> list[Attempt]:
        # Insertion order, untouched: SqliteStore orders by rowid alone, so the
        # list as appended *is* the answer. Sorting by timestamp here is what
        # made the fake agree with a real store that was itself wrong.
        attempts = self._key_attempts.get((profile_id, key_char), [])
        # Not `attempts[-limit:]`: at zero that is the whole list, and the real
        # store's `LIMIT 0` is no rows.
        return list(attempts if limit is None else attempts[max(len(attempts) - limit, 0) :])

    def append_letter_lengths(
        self,
        profile_id: int,
        voice: str,
        rate: float,
        lengths: Sequence[tuple[str, int]],
        recorded_at: str | None = None,
    ) -> None:
        _stamp(recorded_at)
        for key_char, ms in lengths:
            kept = self._letter_lengths.setdefault((profile_id, key_char, voice, rate), [])
            kept.append(ms)
            del kept[: -self._length_cap]

    def letter_lengths(self, profile_id: int, key_char: str, voice: str, rate: float) -> list[int]:
        return list(self._letter_lengths.get((profile_id, key_char, voice, rate), []))

    def record_milestone(
        self,
        profile_id: int,
        level: str,
        achieved_at: str | None = None,
    ) -> None:
        ts = _stamp(achieved_at)
        key = (profile_id, level)
        if key not in self._milestones:
            self._milestones[key] = ts

    def achieved_milestones(self, profile_id: int) -> list[str]:
        return [
            level
            for (pid, level), _ in sorted(self._milestones.items(), key=lambda x: x[1])
            if pid == profile_id
        ]
