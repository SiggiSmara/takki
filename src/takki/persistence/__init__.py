from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Profile:
    id: int
    name: str
    language: str
    created_at: str
    tts_voice: str | None = None
    tts_rate: float | None = None
    talk_key: str | None = None
    reread_key: str | None = None
    restart_key: str | None = None
    ptt_mode: str | None = None


@dataclass(frozen=True)
class KeyStat:
    # Lifetime counters for one Active key. Never the source of truth for Known
    # -- that is WindowStats over key_attempts (ADR-027).
    attempt_count: int
    correct_count: int
    last_practised_at: str | None


@dataclass(frozen=True)
class WindowStats:
    attempt_count: int
    correct_count: int
    distinct_days: int


class Store(Protocol):
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
    ) -> Profile: ...

    def get_profile(self, profile_id: int) -> Profile | None: ...

    def list_profiles(self) -> list[Profile]: ...

    def start_session(self, profile_id: int, started_at: str | None = None) -> int: ...

    def end_session(self, session_id: int, ended_at: str | None = None) -> None: ...

    def upsert_key_stat(
        self,
        profile_id: int,
        key_char: str,
        correct: bool,
        practised_at: str | None = None,
    ) -> None: ...

    def bump_key_recency(
        self,
        profile_id: int,
        key_char: str,
        practised_at: str | None = None,
    ) -> None: ...

    def append_attempt(
        self,
        profile_id: int,
        key_char: str,
        correct: bool,
        attempted_at: str | None = None,
    ) -> None: ...

    def key_stats(self, profile_id: int) -> dict[str, KeyStat]: ...

    def window_stats(self, profile_id: int, key_char: str) -> WindowStats: ...

    def record_milestone(
        self,
        profile_id: int,
        level: str,
        achieved_at: str | None = None,
    ) -> None: ...

    def achieved_milestones(self, profile_id: int) -> list[str]: ...
