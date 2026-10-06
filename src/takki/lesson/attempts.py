from collections.abc import Callable
from enum import Enum, auto
from statistics import median

from takki import config
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
        heard_min_ms: int = config.HEARD_MIN_MS,
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
        # The letter now sounding and when it was sent, for its length.
        self._playing: tuple[str, float] | None = None
        # How long each letter took from being sent to finishing, over the
        # playbacks that ran to the end in this session. A length belongs to a
        # voice and a rate, so it is not carried between sessions.
        self._lengths: dict[str, list[int]] = {}
        # What the store's rows say each letter took, read once per letter.
        self._stored: dict[str, int | None] = {}
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
        self._playing = None
        self._timeouts = 0
        self._unheard = False
        if self._clock is not None and target not in self._stored:
            # Read here and not in `press`: the caller plays the cue right
            # after a press, and a window read ahead of it is audible delay.
            self._stored[target] = next(
                (
                    row.latency_ms - row.after_letter_ms
                    for row in reversed(
                        self._store.window_attempts(
                            self._profile_id, target, limit=config.SPEED_SAMPLE
                        )
                    )
                    if row.latency_ms is not None and row.after_letter_ms is not None
                ),
                None,
            )

    def letter_sent(self) -> None:
        """The open prompt's letter has been sent to be spoken, for the first time or again."""
        if self._clock is None or self._target is None:
            return
        now = self._clock.monotonic()
        self._playing = (self._target, now)
        self._unheard = False
        # Only the first hearing is timed: a child answering a re-spoken letter
        # has had the whole wait before it to find the key (ADR-011).
        self._timed = self._sent_at is None
        if self._sent_at is None:
            self._sent_at = now

    def letter_finished(self) -> None:
        """The letter ran to its end: one more measurement of how long it takes."""
        if self._clock is None or self._playing is None:
            return
        letter, sent_at = self._playing
        self._playing = None
        self._lengths.setdefault(letter, []).append(_ms(self._clock.monotonic() - sent_at))

    def mark_inaudible(self) -> None:
        """The letter failed, or the child has left: the answer is not timed from it."""
        self._timed = False
        self._playing = None
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
            else:
                # The press cut the letter before it could sound (ADR-012), so
                # the child has heard nothing yet. The letter the caller sends
                # next is the first one they can hear: the floor and the
                # timing both start again from it.
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
            length = None if latency_ms is None else self._usual_length(target)
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

    def _usual_length(self, letter: str) -> int | None:
        """How long this letter takes to say, for ADR-011's `after_letter_ms`, or None if unknown."""
        # Anything measured in this session comes first, because a length
        # belongs to a voice and a rate: the letter's own playbacks, and for a
        # letter that never runs to its end (a press cuts it, ADR-012) the
        # median over the letters that did. What the letter's stored rows say
        # is only for a session that has measured nothing yet. A stored length
        # may be another voice's, or itself borrowed, and used ahead of today's
        # measurements it would be written back and never corrected.
        own = self._lengths.get(letter)
        if own:
            return round(median(own))
        if self._lengths:
            return round(median(median(lengths) for lengths in self._lengths.values()))
        return self._stored.get(letter)


def _ms(seconds: float) -> int:
    return round(seconds * 1000)
