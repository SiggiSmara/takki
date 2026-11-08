from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, Protocol


def utc_stamp(value: str) -> str:
    """`value` unchanged if it is a UTC instant as the store writes it; ValueError otherwise."""
    # The store's data contract, enforced on the way in and on the way out. A
    # bare stamp is not rejected by SQLite: `date(x, 'localtime')` reads it as
    # UTC, so a local time written by mistake would move a practice day
    # silently.
    parsed = datetime.fromisoformat(value)
    # One spelling only -- whole seconds and `+00:00`, what `_now()` writes --
    # because `milestones` is ordered by this text, and `Z` or a fraction of a
    # second sorts differently from the same instant written the other way.
    if parsed.utcoffset() != timedelta(0) or value != parsed.isoformat(timespec="seconds"):
        raise ValueError(f"timestamp is not UTC in the stored form: {value!r}")
    return value


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
    # Every local day the key was ever practised, not only the window's
    # (ADR-011 `practice_days`): 200 presses in one day must not evict the
    # key's earlier days (review of 2026-10-06, E4).
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
    # `latency_ms` runs from the letter being sent. `after_letter_ms` is the
    # same press counted from the letter's usual end, so it is negative for an
    # answer given while the letter was still sounding, and NULL while no
    # length is known for the letter. Their difference is that length.
    latency_ms: int | None = None
    prev_char: str | None = None
    after_letter_ms: int | None = None
    timeouts: int = 0


@dataclass(frozen=True)
class PhaseRecord:
    """One phase of one key's ramp-up, as lifetime attempt counts at its start and its pass (ADR-011)."""

    started_attempts: int
    completed_attempts: int | None = None


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
    # ADR-024's one bar, met once and never taken back: the lifetime attempt
    # count and the time. None while the letter's ramp-up runs.
    stable_attempts: int | None = None
    stable_at: str | None = None


# ADR-024's ladder, by name. A level a letter does not take has no record.
Level = Literal["reach", "choose", "travel"]


@dataclass(frozen=True)
class LevelRecord:
    """One run of one level of a letter's ramp-up (ADR-011 `ramp_up_levels`)."""

    level: Level
    # A run per session, because Reach starts again after a restart (ADR-024).
    session_id: int
    # The presses the level reads: Reach presses at Reach, counted attempts
    # (`key_stats`) at Choose and Travel. Lifetime counts, so none is evicted.
    started_presses: int
    started_at: str
    completed_presses: int | None = None
    completed_at: str | None = None


@dataclass(frozen=True)
class ReachPress:
    """A first press on a letter at Reach: predictable, so never an attempt (ADR-024)."""

    correct: bool
    pressed_at: str


@dataclass(frozen=True)
class Landing:
    """One press of the keyboard alignment, by position and never by character (ADR-033)."""

    session_id: int
    round: int
    finger: str
    row: int
    col: int
    # Whether that hand's bump press in this round was on the bump.
    validated: bool
    landed_at: str


# "bump" is an index finger's: the one rest key the child does not choose.
ChosenBy = Literal["landings", "answer", "bump"]


@dataclass(frozen=True)
class RestKey:
    """One finger's rest key, current or replaced (ADR-033 § What must be recorded)."""

    finger: str
    row: int
    col: int
    chosen_by: ChosenBy
    chosen_at: str
    ready_at: str | None = None
    passed_at: str | None = None
    replaced_at: str | None = None


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
        after_letter_ms: int | None = None,
        timeouts: int = 0,
    ) -> None: ...

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
        """`upsert_key_stat` and `append_attempt` for one counted attempt, written together."""
        # A ramp-up phase's evidence is the rows since the lifetime count at
        # its start (ADR-011), so a count without its row shifts that evidence
        # by one for good.
        ...

    def mark_introduced(
        self,
        profile_id: int,
        key_chars: Sequence[str],
        introduced_at: str | None = None,
    ) -> int: ...

    def begin_phase(
        self,
        profile_id: int,
        key_char: str,
        phase: str,
        attempts_at: int,
        started_at: str | None = None,
    ) -> None: ...

    def record_phase(
        self,
        profile_id: int,
        key_char: str,
        phase: str,
        attempts_at: int,
        completed_at: str | None = None,
    ) -> None: ...

    def phase_records(self, profile_id: int, key_char: str) -> dict[str, PhaseRecord]: ...

    def introductions(self, profile_id: int) -> list[Introduction]: ...

    def record_stable(
        self,
        profile_id: int,
        key_char: str,
        attempts: int,
        stable_at: str | None = None,
    ) -> None:
        """The letter met ADR-024's one bar. Write-once; refused for a letter never introduced."""
        ...

    def begin_level(
        self,
        profile_id: int,
        key_char: str,
        level: Level,
        session_id: int,
        presses: int,
        started_at: str | None = None,
    ) -> None:
        """The step reached `level` in this session, which must be this profile's. Write-once."""
        ...

    def complete_level(
        self,
        profile_id: int,
        key_char: str,
        level: Level,
        session_id: int,
        presses: int,
        completed_at: str | None = None,
    ) -> None:
        """The letter met `level`'s rule in that session's run. Write-once; refused if never begun."""
        ...

    def level_records(self, profile_id: int, key_char: str) -> list[LevelRecord]:
        """Every run of every level of this letter, in the order begun."""
        ...

    def append_reach_press(
        self,
        profile_id: int,
        key_char: str,
        correct: bool,
        pressed_at: str | None = None,
    ) -> None: ...

    def reach_presses(self, profile_id: int, key_char: str) -> list[ReachPress]:
        """This letter's Reach presses, oldest first. Never trimmed."""
        ...

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
    ) -> None: ...

    def landings(self, profile_id: int) -> list[Landing]:
        """Every landing, in the order pressed."""
        ...

    def choose_rest_key(
        self,
        profile_id: int,
        finger: str,
        row: int,
        col: int,
        chosen_by: ChosenBy,
        chosen_at: str | None = None,
    ) -> None:
        """The finger's rest key is this cell. A different cell replaces the current key, which is kept."""
        ...

    def mark_rest_key_ready(
        self, profile_id: int, finger: str, ready_at: str | None = None
    ) -> None:
        """The finger's current rest key became ready. Write-once; refused if it has none."""
        ...

    def mark_rest_key_passed(
        self, profile_id: int, finger: str, passed_at: str | None = None
    ) -> None:
        """The finger's current rest key passed its session-start test. Write-once; refused if it has none."""
        ...

    def rest_keys(self, profile_id: int) -> list[RestKey]:
        """Every rest key the profile has had, replaced ones included, in the order chosen."""
        ...

    def key_stats(self, profile_id: int) -> dict[str, KeyStat]: ...

    def window_stats(self, profile_id: int, key_char: str) -> WindowStats:
        """The window's counts, and every practice day of the key (ADR-027's Known query)."""
        ...

    def window_attempts(
        self, profile_id: int, key_char: str, limit: int | None = None
    ) -> list[Attempt]: ...

    def append_letter_lengths(
        self,
        profile_id: int,
        voice: str,
        rate: float,
        lengths: Sequence[tuple[str, int]],
        recorded_at: str | None = None,
    ) -> None: ...

    def letter_lengths(self, profile_id: int, key_char: str, voice: str, rate: float) -> list[int]:
        """This letter's stored lengths under one voice and rate, oldest first (ADR-011)."""
        ...

    def record_milestone(
        self,
        profile_id: int,
        level: str,
        achieved_at: str | None = None,
    ) -> None: ...

    def achieved_milestones(self, profile_id: int) -> list[str]: ...
