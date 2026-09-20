"""ADR-012 § TTS utterance sequencing and cancellation — the core's half.

The worker owns the engine and speaks one utterance at a time; this owns the
*remainder* of a multi-utterance prompt as ordinary main-thread state, enqueues
the next only when its `SpeechFinished` arrives, and decides what a keypress
cancels. Nothing here blocks and nothing here is shared across threads.
"""

from collections import deque
from dataclasses import dataclass

from takki.audio.letters import LetterAudioSource
from takki.audio.tts_worker import SpeechFinished, TTSWorker


@dataclass(frozen=True)
class _Utterance:
    text: str
    interruptible: bool


class Speaker:
    def __init__(self, worker: TTSWorker, letters: LetterAudioSource) -> None:
        self._worker = worker
        self._letters = letters
        self._pending: deque[_Utterance] = deque()
        self._in_flight: int | None = None
        self._in_flight_interruptible = True
        # The letter still outstanding, if any. Tracked by id rather than as a
        # bare "a letter was played" flag so that superseding one is precise: a
        # letter that has already finished is not stopped again, and a second
        # letter is never queued behind an unfinished first, where the worker
        # would play it after the cue and over the next prompt.
        self._letter_id: int | None = None

    @property
    def busy(self) -> bool:
        return self._in_flight is not None or bool(self._pending)

    def say(self, *texts: str, interruptible: bool = True) -> None:
        """Queue a sequence, one utterance at a time (ADR-012)."""
        self._pending.extend(_Utterance(text, interruptible) for text in texts)
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
        # Letters deliberately do not make the speaker `busy`: the child answers
        # while the letter is still sounding, and holding the next prompt until
        # it finished would reopen the window where a typed-ahead keystroke
        # lands on no prompt at all.
        if self._letter_id is not None:
            self._letters.stop()
        self._letter_id = self._letters.play(char)

    def on_finished(self, event: SpeechFinished) -> bool:
        """True when this was the utterance in flight; False for anything else.

        Everything else is a superseded utterance whose cancel raced its own
        completion, or a letter, which is tracked but never sequenced. Both must be
        dropped, or the stale event advances a sequence it was never part of
        and skips an utterance nobody heard (ADR-012 § Utterance ids).
        """
        if event.utterance_id == self._letter_id:
            self._letter_id = None
            return False
        if event.utterance_id != self._in_flight:
            return False
        self._in_flight = None
        self._pump()
        return True

    def interrupt(self) -> None:
        """ADR-012 § TTS interrupt on keypress: stop what is audible, drop the rest.

        A non-interruptible utterance -- a milestone announcement -- runs to
        completion, and so does everything queued behind it: the tail is part
        of the same unit. Dropping stops at the first one for that reason, so
        the rule reads the same whatever order the caller queued things in.
        """
        if self._letter_id is not None:
            self._letters.stop()
            # Cleared without waiting for the cancellation to come back: the
            # stop has been asked for, and the stale SpeechFinished that
            # follows is dropped by id like any other superseded utterance.
            self._letter_id = None
        if self._in_flight is not None:
            if not self._in_flight_interruptible:
                return
            self._worker.stop()
            self._in_flight = None
        while self._pending and self._pending[0].interruptible:
            self._pending.popleft()
        self._pump()

    def _pump(self) -> None:
        if self._in_flight is not None or not self._pending:
            return
        utterance = self._pending.popleft()
        self._in_flight_interruptible = utterance.interruptible
        self._in_flight = self._worker.enqueue_speak(utterance.text)
