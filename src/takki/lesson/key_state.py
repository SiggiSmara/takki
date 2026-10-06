import math
from collections.abc import Callable, Collection, Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum, auto
from statistics import median

from takki import config
from takki.persistence import Attempt, Store, WindowStats

# How cautious the accuracy reading is: one standard error. Known's press floor
# already demands the evidence, so the bound only has to stop a lucky short run
# reading as a confirmed key. A constant in code on the developer's call
# (ADR-024 § Steady-state drill generation).
CONFIDENCE_Z = 1.0
_NO_EVIDENCE = 1e-6


class KeyState(Enum):
    # ADR-027 § Key States. Nothing persists this: Unseen and Active are read
    # off row presence in key_stats, Known is recomputed from the rolling
    # windows on every query so a drop in accuracy or speed un-Knows a key by
    # itself.
    UNSEEN = auto()
    ACTIVE = auto()
    KNOWN = auto()


@dataclass(frozen=True)
class KnownCriterion:
    """ADR-027's three floors as compiled defaults (ADR-025 tier 1)."""

    min_attempts: int = config.KNOWN_MIN_ATTEMPTS
    min_accuracy: float = config.KNOWN_MIN_ACCURACY
    min_distinct_days: int = config.KNOWN_MIN_DISTINCT_DAYS


DEFAULT_CRITERION = KnownCriterion()


@dataclass(frozen=True)
class Evidence:
    """A key's window as Known reads it (ADR-027 § Known reads decayed evidence)."""

    # The dose and the days are counted as they happened. The accuracy is an
    # estimate, and an old estimate is worth less, so `weight` and `correct`
    # are the same presses with each one counting for less the older it is.
    attempts: int
    distinct_days: int
    weight: float
    correct: float


def accuracy_bound(correct: float, attempts: float) -> float:
    """Wilson lower bound on first-press accuracy: how accurate the key surely is."""
    # Decayed weight can be any positive number, however small: rows stamped
    # decades back by a dead clock weigh 1e-170, and squaring that is zero.
    # Less than a millionth of a press is no evidence at all.
    if attempts < _NO_EVIDENCE:
        return 0.0
    z2 = CONFIDENCE_Z**2
    p = correct / attempts
    centre = p + z2 / (2 * attempts)
    spread = CONFIDENCE_Z * math.sqrt(p * (1 - p) / attempts + z2 / (4 * attempts**2))
    return (centre - spread) / (1 + z2 / attempts)


def weigh(
    stats: WindowStats, rows: Sequence[Attempt], now: datetime, half_life_days: float
) -> Evidence:
    """The window's evidence at `now`, each press halved in weight every `half_life_days`."""
    weight = correct = 0.0
    for row in rows:
        # A press stamped ahead of `now` -- the clock was corrected backwards
        # since -- has an age of zero, not a weight above one.
        age_days = (
            max(0.0, (now - datetime.fromisoformat(row.attempted_at)).total_seconds()) / 86400
        )
        worth = 0.5 ** (age_days / half_life_days)
        weight += worth
        correct += worth * row.correct
    return Evidence(stats.attempt_count, stats.distinct_days, weight, correct)


def key_speed(rows: Sequence[Attempt]) -> float | None:
    """Median time to a correct first answer over the key's latest timed presses, or None."""
    # Correct presses only: a guess made without listening is fast and usually
    # wrong, and must not make a key look fast (ADR-027 § A press before the
    # letter could be heard). An answer that sat through a timeout was not
    # timed, and is the slowest answer there is, so it stands in the sample as
    # one no bar can pass. Too few timed answers is no speed at all.
    timed = [math.inf if row.timeouts else row.latency_ms for row in rows if row.correct]
    sample = [ms for ms in timed if ms is not None][-config.SPEED_SAMPLE :]
    return median(sample) if len(sample) >= config.SPEED_MIN_SAMPLE else None


def qualifies(evidence: Evidence, criterion: KnownCriterion = DEFAULT_CRITERION) -> bool:
    """Known's three floors: the dose, the accuracy bound and the practice days."""
    # Everything Known asks except speed. It is also what puts a key in the
    # speed baseline's pool, and it reads no baseline, which is what keeps
    # Known from depending on itself (ADR-027 § Known has a speed term).
    return (
        evidence.attempts >= criterion.min_attempts
        and accuracy_bound(evidence.correct, evidence.weight) >= criterion.min_accuracy
        and evidence.distinct_days >= criterion.min_distinct_days
    )


class KeyStates:
    """Key states for one profile, derived from the store on every call (ADR-027)."""

    def __init__(
        self,
        store: Store,
        profile_id: int,
        criterion: KnownCriterion = DEFAULT_CRITERION,
        now: Callable[[], str] | None = None,
        bump_keys: Collection[str] = (),
        half_life_days: float = config.EVIDENCE_HALF_LIFE_DAYS,
        max_latency_ratio: float = config.KNOWN_MAX_LATENCY_RATIO,
    ) -> None:
        self._store = store
        self._profile_id = profile_id
        self._criterion = criterion
        # How evidence is read, not a bar a key is held to: the same weighed
        # evidence is judged against Known's criterion and the anchor rung's.
        self._half_life_days = half_life_days
        self._max_latency_ratio = max_latency_ratio
        # The two keys with a bump, `f` and `j` on every layout Takki has. They
        # are in the speed baseline from their first presses and have no speed
        # term of their own: something has to be the root of the comparison.
        self._bump_keys = frozenset(bump_keys)
        self._held: dict[str, tuple[Evidence, float | None]] | None = None
        # Wall-clock UTC in the store's form, as `AttemptCounter` takes it.
        # Evidence ages against this; None reads the system clock.
        self._now = now

    @contextmanager
    def held(self) -> Generator[None]:
        """Read each key's window once for everything asked inside the block."""
        # A block boundary asks for the Known set, the slow keys and every
        # key's evidence, and each of those reads every Active key's window:
        # about 95 ms a pass on a full profile (measured 2026-10-04), between
        # the child's last press and the next letter. Nothing may write an
        # attempt inside, or it is not seen until the block is left.
        if self._held is not None:
            yield
            return
        self._held = {}
        try:
            yield
        finally:
            self._held = None

    def state(self, key_char: str) -> KeyState:
        if key_char not in self._store.key_stats(self._profile_id):
            return KeyState.UNSEEN
        return KeyState.KNOWN if key_char in self.known_keys() else KeyState.ACTIVE

    def active_keys(self) -> set[str]:
        # Every key with a row, Known ones included -- ADR-027's Active is row
        # presence. Only state() draws the ACTIVE/KNOWN line.
        return set(self._store.key_stats(self._profile_id))

    def evidence(self, key_char: str) -> Evidence:
        return self._read(key_char)[0]

    def window_attempts(self, key_char: str) -> list[Attempt]:
        # The window's rows in order, for ADR-024's derived ramp-up bars: a
        # streak and a run-with-a-budget cannot be computed from aggregates.
        return self._store.window_attempts(self._profile_id, key_char)

    def known_keys(self) -> set[str]:
        survey = self._survey()
        return {
            name
            for name, (evidence, _) in survey.items()
            if qualifies(evidence, self._criterion) and not self._slow(name, survey)
        }

    def slow_keys(self) -> set[str]:
        """The keys that meet every floor and are kept from Known by speed alone."""
        survey = self._survey()
        return {
            name
            for name, (evidence, _) in survey.items()
            if qualifies(evidence, self._criterion) and self._slow(name, survey)
        }

    def speed_baseline(self, key_char: str) -> float | None:
        """What this key's speed is judged against, or None when there is nothing to judge by."""
        return self._baseline(key_char, self._survey())

    def _read(self, key_char: str) -> tuple[Evidence, float | None]:
        if self._held is None:
            return self._read_store(key_char)
        if key_char not in self._held:
            self._held[key_char] = self._read_store(key_char)
        return self._held[key_char]

    def _read_store(self, key_char: str) -> tuple[Evidence, float | None]:
        now = datetime.now(UTC) if self._now is None else datetime.fromisoformat(self._now())
        rows = self._store.window_attempts(self._profile_id, key_char)
        stats = self._store.window_stats(self._profile_id, key_char)
        return weigh(stats, rows, now, self._half_life_days), key_speed(rows)

    def _survey(self) -> dict[str, tuple[Evidence, float | None]]:
        # Every Active key's evidence and speed in one pass. A key's speed is
        # judged against the others', so one key cannot be read alone.
        return {name: self._read(name) for name in sorted(self.active_keys())}

    def _baseline(
        self, key_char: str, survey: dict[str, tuple[Evidence, float | None]]
    ) -> float | None:
        # ADR-027 § Known has a speed term: the median over the bump keys and
        # every *other* key that meets the floors, each counted once by its own
        # median. Whether those keys pass their own speed test is not asked;
        # asking would make Known depend on Known.
        if key_char in self._bump_keys:
            return None
        pool = [
            speed
            for name, (evidence, speed) in survey.items()
            if name != key_char
            and speed is not None
            and (name in self._bump_keys or qualifies(evidence, self._criterion))
        ]
        return median(pool) if pool else None

    def _slow(self, key_char: str, survey: dict[str, tuple[Evidence, float | None]]) -> bool:
        speed = survey[key_char][1]
        baseline = self._baseline(key_char, survey)
        # No baseline or no speed, no term: a measurement that cannot be made
        # must not hold a key back (the rule Phase C already had).
        if speed is None or baseline is None:
            return False
        return speed > self._max_latency_ratio * baseline
