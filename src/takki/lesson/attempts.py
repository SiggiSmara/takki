from collections.abc import Callable
from enum import Enum, auto

from takki.clock import Clock
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
        clock: Clock | None = None,
    ) -> None:
        self._store = store
        self._profile_id = profile_id
        # Monotonic, for ADR-011's latency_ms. Separate from `now` above, which
        # is wall-clock and only stamps rows. None measures nothing and writes
        # NULL, which every bar treats as unmeasured.
        self._clock = clock
        self._prompted_at: float | None = None
        # The previous *counted* prompt, ADR-011's prev_char. Retries and
        # ignored presses do not move it: it names the prompt before this one,
        # not the last key the child happened to hit.
        self._previous: str | None = None
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
        # Not stamped here: `mark_audible` does it, when the prompt has actually
        # been spoken. Stamping at latch would fold the letter's own synthesis
        # and playback into every measurement, and letter names differ in length
        # ("double-you" against "E"), so the bias would be per-key.
        self._prompted_at = None

    def mark_audible(self) -> None:
        """The open prompt has finished sounding: time the answer from here.

        Called for every route that speaks or re-speaks a prompt -- the first
        issue, the auto-advance timeout, an auto-rejected keypress, the re-read
        key, and the return from PAUSED -- so a re-spoken prompt is timed from
        the version the child actually heard. That is also why no measurement
        needs discarding for being too slow: the only long gaps left are ones
        where nothing was re-spoken.
        """
        if self._clock is not None:
            self._prompted_at = self._clock.monotonic()

    def mark_inaudible(self) -> None:
        """The prompt is being re-spoken, or the child has left: time nothing from the old version."""
        self._prompted_at = None

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
            self._store.append_attempt(
                self._profile_id,
                target,
                correct,
                ts,
                latency_ms=self._latency_ms(),
                prev_char=self._previous,
            )
            self._previous = target
        if correct:
            self._target = None
        return PressOutcome.CORRECT if correct else PressOutcome.WRONG

    def _latency_ms(self) -> int | None:
        """End of the spoken prompt to the first press, or None if unmeasured.

        NULL means exactly one thing -- no clock, or the prompt never became
        audible -- so ADR-011's "a NULL never fails a bar" cannot quietly excuse
        a slow answer. A genuinely slow child is *recorded* as slow, which is
        the child Phase C's speed term exists to notice: a rule that dropped
        anything over the timeout produced an all-NULL window for exactly them.
        """
        if self._clock is None or self._prompted_at is None:
            return None
        return max(0, int((self._clock.monotonic() - self._prompted_at) * 1000))
