from collections.abc import Sequence
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


@dataclass(frozen=True)
class Attempt:
    """One row of the rolling window, in insertion order (ADR-011).

    The aggregate `WindowStats` cannot answer a streak or a run-with-a-budget,
    which is what ADR-024's derived ramp-up bars are. `attempted_at` is UTC and
    is *not* what orders these rows -- see `window_attempts`.
    """

    correct: bool
    attempted_at: str
    latency_ms: int | None = None
    prev_char: str | None = None


@dataclass(frozen=True)
class Introduction:
    """One grapheme's introduction, and the step it belonged to (ADR-011).

    `step` is a per-profile ordinal, not a timestamp: it both groups a step's
    members and orders the steps, exactly and without a clock. `position` keeps
    the step's own member order, which ADR-023 defines as left-hand member
    first and which the drill generator reads off `members[0]`.
    """

    key_char: str
    step: int
    position: int
    introduced_at: str


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
        latency_ms: int | None = None,
        prev_char: str | None = None,
    ) -> None: ...

    def mark_introduced(
        self,
        profile_id: int,
        key_chars: Sequence[str],
        introduced_at: str | None = None,
    ) -> int: ...

    def record_phase(
        self,
        profile_id: int,
        key_char: str,
        phase: str,
        attempts_at: int,
        completed_at: str | None = None,
    ) -> None: ...

    def completed_phases(self, profile_id: int, key_char: str) -> dict[str, int]: ...

    def introductions(self, profile_id: int) -> list[Introduction]: ...

    def key_stats(self, profile_id: int) -> dict[str, KeyStat]: ...

    def window_stats(self, profile_id: int, key_char: str) -> WindowStats: ...

    def window_attempts(
        self, profile_id: int, key_char: str, limit: int | None = None
    ) -> list[Attempt]: ...

    def record_milestone(
        self,
        profile_id: int,
        level: str,
        achieved_at: str | None = None,
    ) -> None: ...

    def achieved_milestones(self, profile_id: int) -> list[str]: ...
