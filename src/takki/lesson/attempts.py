from collections.abc import Callable
from enum import Enum, auto

from takki import config
from takki.clock import Clock
from takki.lesson.letter_lengths import LetterLengths
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
        heard_min_ms: int = config.HEARD_MIN_MS,
        lengths: LetterLengths | None = None,
    ) -> None:
        self._store = store
        self._profile_id = profile_id
        # Monotonic, for ADR-011's latency_ms. Separate from `now` above, which
        # is wall-clock and only stamps rows. None measures nothing, writes
        # NULL, which every bar treats as unmeasured, and applies no floor.
        self._clock = clock
        self._heard_min_ms = heard_min_ms
        # When the open prompt's letter was first sent to be spoken. The floor
        # is counted from here whatever is re-spoken afterwards.
        self._sent_at: float | None = None
        # Whether the answer is still an answer to that first hearing.
        self._timed = False
        # Whether a press cuts the letter now sounding (ADR-012).
        self._cuttable = True
        # Each letter's usual length, for ADR-011's `after_letter_ms`. None
        # leaves that column NULL.
        self._lengths = lengths
        self._timeouts = 0
        # The letter now out failed, or the child has left: it was not heard.
        self._unheard = False
        # The previous prompt, ADR-011's prev_char. Retries and ignored presses
        # do not move it: it names the prompt before this one, not the last key
        # the child happened to hit.
        self._previous: str | None = None
        # Wall-clock UTC in the store's form (ADR-011) -- a separate concern
        # from Clock, which is monotonic and only answers deadlines. None
        # leaves the timestamp to the store.
        self._now = now
        self._target: str | None = None
        self._counted = False

    @property
    def counted(self) -> bool:
        """Whether the prompt last opened has had its one attempt written."""
        return self._counted

    def start_prompt(self, target: str) -> None:
        # Once per prompt, and only for a new one. A timeout re-issue re-speaks
        # the same prompt and must not call this: it counts nothing, and
        # re-latching would let the child's second keystroke be counted as
        # another first attempt (ADR-027 § Timeouts).
        self._target = target
        self._counted = False
        self._sent_at = None
        self._timed = False
        self._timeouts = 0
        self._unheard = False
        if self._lengths is not None:
            # The letter's stored lengths are read on the first ask. Asked here
            # and not only in `press`: the caller plays the cue right after a
            # press, and a store read ahead of it is audible delay.
            self._lengths.usual(target)

    def letter_sent(self, *, cuttable: bool = True) -> None:
        """The open prompt's letter has been sent to be spoken, for the first time or again."""
        if self._clock is None or self._target is None:
            return
        self._cuttable = cuttable
        self._unheard = False
        # Only the first hearing is timed: a child answering a re-spoken letter
        # has had the whole wait before it to find the key (ADR-011).
        self._timed = self._sent_at is None
        if self._sent_at is None:
            self._sent_at = self._clock.monotonic()

    def mark_inaudible(self) -> None:
        """The letter failed, or the child has left: the answer is not timed from it."""
        self._timed = False
        self._unheard = True

    def timed_out(self) -> None:
        """The prompt went unanswered for the whole timeout (ADR-011's `timeouts`)."""
        # A timeout is counted as the slowest answer there is, so it has to be
        # the child who was slow. One that follows a letter nobody heard is
        # the voice's failure and is not counted.
        if not self._unheard:
            self._timeouts += 1

    def press(self, char: str, *, repeat: bool = False) -> PressOutcome:
        if self._target is None:
            return PressOutcome.IGNORED
        if repeat:
            # ADR-027 § Held keys: a press that repeats a key still physically
            # down is the same actuation continuing, not a new attempt. It
            # writes nothing at all -- not even recency.
            return PressOutcome.IGNORED
        target = self._target
        correct = char == target
        elapsed_ms = self._elapsed_ms()
        if not self._counted and elapsed_ms is not None and elapsed_ms < self._heard_min_ms:
            # ADR-027 § A press before the letter could be heard is not an
            # attempt. It writes nothing, and to the child it is an ordinary
            # press: the caller plays the cue and moves on or re-speaks. After a
            # wrong one the prompt is still open and uncounted.
            if correct:
                self._target = None
                # The next row's predecessor is what the child was given,
                # whether or not it left a row of its own.
                self._previous = target
            elif self._cuttable:
                # The press cut the letter before it could sound (ADR-012), so
                # the child has heard nothing yet. The letter the caller sends
                # next is the first one they can hear: the floor and the
                # timing both start again from it. A letter that cannot be cut
                # runs on and is heard, so the one sent after it is a letter
                # spoken again, and the answer to that is not timed (ADR-011).
                self._sent_at = None
            return PressOutcome.CORRECT if correct else PressOutcome.WRONG
        ts = self._now() if self._now is not None else None
        if self._counted:
            # The prompt's outcome is already decided; every keystroke until
            # the correct character arrives is engagement and nothing more.
            self._store.bump_key_recency(self._profile_id, target, ts)
        else:
            self._counted = True
            latency_ms = elapsed_ms if self._timed else None
            # Read at the press and not when the prompt opened: a letter that
            # ran to its end before this press has been measured since.
            length = (
                None if latency_ms is None or self._lengths is None else self._lengths.usual(target)
            )
            self._store.upsert_key_stat(self._profile_id, target, correct, ts)
            self._store.append_attempt(
                self._profile_id,
                target,
                correct,
                ts,
                latency_ms=latency_ms,
                prev_char=self._previous,
                after_letter_ms=(
                    None if latency_ms is None or length is None else latency_ms - length
                ),
                timeouts=self._timeouts,
            )
            self._previous = target
        if correct:
            self._target = None
        return PressOutcome.CORRECT if correct else PressOutcome.WRONG

    def _elapsed_ms(self) -> int | None:
        """The first sending of the open prompt's letter to now, or None with no clock or letter."""
        if self._clock is None or self._sent_at is None:
            return None
        return _ms(self._clock.monotonic() - self._sent_at)


def _ms(seconds: float) -> int:
    return round(seconds * 1000)
