from collections.abc import Callable
from enum import Enum, auto

from takki.persistence import Store


class PressOutcome(Enum):
    CORRECT = auto()
    WRONG = auto()
    # Counted for nothing and fed back to no one: an OS auto-repeat of a key
    # that never came up, or a keystroke with no prompt to answer.
    IGNORED = auto()


class AttemptCounter:
    """ADR-027 § First-Attempt Counting Semantics: one attempt per prompt, decided by the first press."""

    def __init__(
        self,
        store: Store,
        profile_id: int,
        now: Callable[[], str] | None = None,
    ) -> None:
        self._store = store
        self._profile_id = profile_id
        # Wall-clock ISO-8601 local time, the ADR-011 convention -- a separate
        # concern from Clock, which is monotonic and only answers deadlines.
        # None leaves the timestamp to the store.
        self._now = now
        self._target: str | None = None
        self._counted = False

    def start_prompt(self, target: str) -> None:
        # Once per prompt, and only for a new one. A timeout re-issue re-speaks
        # the same prompt and must not call this: it counts nothing, and
        # re-latching would let the child's second keystroke be counted as
        # another first attempt (ADR-027 § Timeouts).
        self._target = target
        self._counted = False

    def press(self, char: str, *, repeat: bool = False) -> PressOutcome:
        if self._target is None:
            return PressOutcome.IGNORED
        if repeat:
            # ADR-027 § Held keys: a press that repeats a key still physically
            # down is the same actuation continuing, not a new attempt. It
            # writes nothing at all -- not even recency.
            return PressOutcome.IGNORED
        ts = self._now() if self._now is not None else None
        target = self._target
        correct = char == target
        if self._counted:
            # The prompt's outcome is already decided; every keystroke until
            # the correct character arrives is engagement and nothing more.
            self._store.bump_key_recency(self._profile_id, target, ts)
        else:
            self._counted = True
            self._store.upsert_key_stat(self._profile_id, target, correct, ts)
            self._store.append_attempt(self._profile_id, target, correct, ts)
        if correct:
            self._target = None
        return PressOutcome.CORRECT if correct else PressOutcome.WRONG
