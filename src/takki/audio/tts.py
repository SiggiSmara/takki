from typing import Protocol


class SpeechOutputError(Exception):
    """The engine has a voice but cannot make sound -- no usable audio output."""


class TTSEngine(Protocol):
    def speak(self, text: str) -> None:
        """Block until spoken or cancelled. May raise; the worker survives it."""
        ...

    def stop(self) -> None: ...

    def clear_cancel(self) -> None:
        """Forget any cancel request. Called by the worker before it dequeues.

        Three methods rather than two because a cancel has to be aimed. If the
        engine cleared its own flag when `speak()` began, a `stop()` landing
        between the worker's decision to speak and that clear would be lost and
        the utterance would play in full while being reported cancelled -- the
        same failure class as the queued-utterance defect, one layer down
        (alpha session 12a-2). Clearing *before* the blocking dequeue means
        every cancel from that moment on belongs to the utterance about to be
        spoken, and nothing can clear it out from under it.
        """
        ...
