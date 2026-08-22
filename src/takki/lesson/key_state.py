from dataclasses import dataclass
from enum import Enum, auto

from takki import config
from takki.persistence import Store, WindowStats


class KeyState(Enum):
    # ADR-027 § Key States. Nothing persists this: Unseen and Active are read
    # off row presence in key_stats, Known is recomputed from the rolling
    # window on every query so an accuracy drop un-Knows a key by itself.
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


def is_known(stats: WindowStats, criterion: KnownCriterion = DEFAULT_CRITERION) -> bool:
    # The attempt floor is evaluated first on purpose: with min_attempts >= 1
    # -- ADR-027's is 90 -- it is what makes the division below safe on a key
    # with no attempts yet.
    return (
        stats.attempt_count >= criterion.min_attempts
        and stats.correct_count / stats.attempt_count >= criterion.min_accuracy
        and stats.distinct_days >= criterion.min_distinct_days
    )


class KeyStates:
    """Key states for one profile, derived from the store on every call (ADR-027)."""

    def __init__(
        self,
        store: Store,
        profile_id: int,
        criterion: KnownCriterion = DEFAULT_CRITERION,
    ) -> None:
        self._store = store
        self._profile_id = profile_id
        self._criterion = criterion

    def state(self, key_char: str) -> KeyState:
        if key_char not in self._store.key_stats(self._profile_id):
            return KeyState.UNSEEN
        return KeyState.KNOWN if self._known(key_char) else KeyState.ACTIVE

    def active_keys(self) -> set[str]:
        # Every key with a row, Known ones included -- ADR-027's Active is row
        # presence. Only state() draws the ACTIVE/KNOWN line.
        return set(self._store.key_stats(self._profile_id))

    def known_keys(self) -> set[str]:
        return {c for c in self.active_keys() if self._known(c)}

    def _known(self, key_char: str) -> bool:
        return is_known(self._store.window_stats(self._profile_id, key_char), self._criterion)
