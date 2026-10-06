"""ADR-012 § TTS utterance sequencing and cancellation — the core's half.

The worker owns the engine and speaks one utterance at a time; this owns the
*remainder* of a multi-utterance prompt as ordinary main-thread state, enqueues
the next only when its `SpeechFinished` arrives, and decides what a keypress
cancels. Nothing here blocks and nothing here is shared across threads.
"""

from collections import deque
from dataclasses import dataclass

from takki.audio.letters import LetterAudioSource
from takki.audio.tts_worker import SpeechFinished, SpeechStatus, TTSWorker
from takki.clock import Clock


@dataclass(frozen=True)
class Letter:
    """A letter as one part of a sequence, spoken through the letter source (ADR-012)."""

    char: str


@dataclass(frozen=True)
class FinishedLetter:
    char: str
    status: SpeechStatus
    # From the letter being sent to its finish. A length only when `status`
    # is "completed" (ADR-011 § letter_lengths).
    seconds: float


@dataclass(frozen=True)
class _Part:
    spoken: str | Letter
    interruptible: bool


class Speaker:
    def __init__(self, worker: TTSWorker, letters: LetterAudioSource, clock: Clock) -> None:
        self._worker = worker
        self._letters = letters
        self._clock = clock
        self._pending: deque[_Part] = deque()
        self._in_flight: int | None = None
        self._in_flight_interruptible = True
        # The letter in flight and when it was sent, when the part in flight
        # is a letter.
        self._in_flight_letter: tuple[str, float] | None = None
        # The prompt's letter still outstanding, if any: its id, the letter
        # and when it was sent. Tracked by id rather than as a bare "a letter
        # was played" flag so that superseding one is precise: a letter that
        # has already finished is not stopped again, and a second letter is
        # never queued behind an unfinished first, where the worker would play
        # it after the cue and over the next prompt.
        self._letter: tuple[int, str, float] | None = None
        self._finished_letter: FinishedLetter | None = None

    @property
    def busy(self) -> bool:
        return self._in_flight is not None or bool(self._pending)

    def say(self, *parts: str | Letter, interruptible: bool = True) -> None:
        """Queue a sequence, one utterance at a time (ADR-012)."""
        self._pending.extend(_Part(part, interruptible) for part in parts)
        self._pump()

    def announce(self, text: str) -> None:
        """Say this now, in place of whatever is audible.

        The focus model's channel (ADR-028 § C8): a pause, a resume or an
        Alt+Tab hint is about the state the child is in *now*, so it replaces
        the prompt or the announcement it supersedes rather than queueing
        behind it. Routed through here rather than straight at the worker so
        that one object knows what is audible -- otherwise a bare
        `TTSWorker.stop()` from the gate cancels a core sequence's utterance,
        the core sees a `SpeechFinished` for the id it is holding, and
        *advances* the sequence it meant to clear.
        """
        self.interrupt()
        self.say(text)

    def letter(self, char: str) -> None:
        # A prompt's letter deliberately does not make the speaker `busy`: the
        # child answers while the letter is still sounding, and holding the
        # next prompt until it finished would reopen the window where a
        # typed-ahead keystroke lands on no prompt at all. A letter that has
        # to be heard to its end goes through `say` as a `Letter` instead.
        # Unguarded by `_in_flight_interruptible`, unlike interrupt(): for
        # Alpha's SyntheticLetterAudioSource this stop() is TTSWorker.stop(),
        # so it would cut a non-interruptible utterance the same way
        # interrupt() used to (alpha session 12a-2). Safe only because
        # `_advance` issues no letter while the speaker is busy, which is what
        # keeps a letter and a celebration from ever being outstanding
        # together. Add the guard here too if that gate moves.
        if self._letter is not None:
            self._letters.stop()
        self._letter = (self._letters.play(char), char, self._clock.monotonic())

    def take_finished_letter(self) -> FinishedLetter | None:
        """How a letter's own SpeechFinished came back, on either route; asked once per event.

        A letter that ran to its end is one more measurement of its length, and
        one that did not was not heard, so no answer is timed from it (ADR-011
        § latency_ms).
        """
        letter, self._finished_letter = self._finished_letter, None
        return letter

    def on_finished(self, event: SpeechFinished) -> bool:
        """True when this was the part in flight; False for anything else.

        Everything else is a superseded utterance whose cancel raced its own
        completion, or a prompt's letter, which is tracked but never sequenced.
        Both must be dropped, or the stale event advances a sequence it was
        never part of and skips an utterance nobody heard (ADR-012 § Utterance
        ids).
        """
        if self._letter is not None and event.utterance_id == self._letter[0]:
            self._report(self._letter[1:], event)
            self._letter = None
            return False
        if event.utterance_id != self._in_flight:
            return False
        if self._in_flight_letter is not None:
            self._report(self._in_flight_letter, event)
            self._in_flight_letter = None
        self._in_flight = None
        self._pump()
        return True

    def interrupt(self) -> None:
        """ADR-012 § TTS interrupt on keypress: stop what is audible, drop the rest.

        A non-interruptible utterance -- a milestone announcement, or a letter
        that has no measured length yet -- runs to completion, and so does a
        non-interruptible one queued behind it: the tail is part of the same
        unit. Dropping stops at the first one for that reason, so the rule
        reads the same whatever order the caller queued things in.
        """
        # The guard comes first, before anything is stopped. `_letters.stop()`
        # is `TTSWorker.stop()` for Alpha's SyntheticLetterAudioSource, so
        # stopping a letter here also cut the non-interruptible utterance this
        # is about to decline to cut (alpha session 12a-2).
        if self._in_flight is None or self._in_flight_interruptible:
            self._stop_audible()
        # Also behind an utterance that is left to finish: an announcement
        # waiting there has been superseded by the one about to be queued, and
        # would otherwise be spoken after the state it describes is over.
        while self._pending and self._pending[0].interruptible:
            self._pending.popleft()
        self._pump()

    def _stop_audible(self) -> None:
        if self._letter is not None:
            self._letters.stop()
            # Cleared without waiting for the cancellation to come back: the
            # stop has been asked for, and the stale SpeechFinished that
            # follows is dropped by id like any other superseded utterance.
            self._letter = None
        if self._in_flight is not None:
            # A letter is stopped where it was played: a source with its own
            # audio is not reached by the worker's stop.
            if self._in_flight_letter is not None:
                self._letters.stop()
                self._in_flight_letter = None
            else:
                self._worker.stop()
            self._in_flight = None

    def _report(self, sent: tuple[str, float], event: SpeechFinished) -> None:
        char, sent_at = sent
        self._finished_letter = FinishedLetter(
            char, event.status, self._clock.monotonic() - sent_at
        )

    def _pump(self) -> None:
        if self._in_flight is not None or not self._pending:
            return
        part = self._pending.popleft()
        self._in_flight_interruptible = part.interruptible
        if isinstance(part.spoken, Letter):
            self._in_flight = self._letters.play(part.spoken.char)
            self._in_flight_letter = (part.spoken.char, self._clock.monotonic())
        else:
            self._in_flight = self._worker.enqueue_speak(part.spoken)
