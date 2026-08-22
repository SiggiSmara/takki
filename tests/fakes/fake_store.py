from datetime import datetime

from takki import config
from takki.persistence import KeyStat, Profile, WindowStats


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class FakeStore:
    def __init__(self, *, window_cap: int = config.ATTEMPT_WINDOW) -> None:
        self._profiles: dict[int, Profile] = {}
        self._next_profile_id = 1
        self._sessions: dict[int, tuple[int, str, str | None]] = {}
        self._next_session_id = 1
        self._key_stats: dict[tuple[int, str], tuple[int, int, str | None]] = {}
        self._key_attempts: dict[tuple[int, str], list[tuple[str, int]]] = {}
        self._milestones: dict[tuple[int, str], str] = {}
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
        ts = started_at or _now()
        session_id = self._next_session_id
        self._sessions[session_id] = (profile_id, ts, None)
        self._next_session_id += 1
        return session_id

    def end_session(self, session_id: int, ended_at: str | None = None) -> None:
        ts = ended_at or _now()
        pid, started_at, _ = self._sessions[session_id]
        self._sessions[session_id] = (pid, started_at, ts)

    def upsert_key_stat(
        self,
        profile_id: int,
        key_char: str,
        correct: bool,
        practised_at: str | None = None,
    ) -> None:
        ts = practised_at or _now()
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
        ts = practised_at or _now()
        key = (profile_id, key_char)
        if key in self._key_stats:
            ac, cc, _ = self._key_stats[key]
            self._key_stats[key] = (ac, cc, ts)

    def append_attempt(
        self,
        profile_id: int,
        key_char: str,
        correct: bool,
        attempted_at: str | None = None,
    ) -> None:
        ts = attempted_at or _now()
        key = (profile_id, key_char)
        if key not in self._key_attempts:
            self._key_attempts[key] = []
        attempts = self._key_attempts[key]
        attempts.append((ts, int(correct)))
        if len(attempts) > self._cap:
            # Oldest by timestamp, ties broken by insertion order: what
            # SqliteStore's ORDER BY attempted_at ASC, rowid ASC evicts.
            del attempts[min(range(len(attempts)), key=lambda i: (attempts[i][0], i))]

    def key_stats(self, profile_id: int) -> dict[str, KeyStat]:
        return {
            key_char: KeyStat(attempt_count=ac, correct_count=cc, last_practised_at=ts)
            for (pid, key_char), (ac, cc, ts) in self._key_stats.items()
            if pid == profile_id
        }

    def window_stats(self, profile_id: int, key_char: str) -> WindowStats:
        attempts = self._key_attempts.get((profile_id, key_char), [])
        return WindowStats(
            attempt_count=len(attempts),
            correct_count=sum(c for _, c in attempts),
            distinct_days=len({ts[:10] for ts, _ in attempts}),
        )

    def record_milestone(
        self,
        profile_id: int,
        level: str,
        achieved_at: str | None = None,
    ) -> None:
        ts = achieved_at or _now()
        key = (profile_id, level)
        if key not in self._milestones:
            self._milestones[key] = ts

    def achieved_milestones(self, profile_id: int) -> list[str]:
        return [
            level
            for (pid, level), _ in sorted(self._milestones.items(), key=lambda x: x[1])
            if pid == profile_id
        ]
