from typing import Protocol


class SpeechOutputError(Exception):
    """The engine has a voice but cannot make sound -- no usable audio output."""


class TTSEngine(Protocol):
    def speak(self, text: str) -> None:
        """Block until spoken or cancelled. May raise; the worker survives it."""
        ...

    def stop(self) -> None: ...

    def clear_cancel(self) -> None:
        """Forget any cancel request. Called by the worker after it dequeues, before its threshold check.

        Three methods rather than two because a cancel has to be aimed, and
        only the worker can aim it. If the engine cleared its own flag when
        `speak()` began, a `stop()` landing between the worker's decision to
        speak and that clear would be lost and the utterance would play in full
        while being reported cancelled (alpha session 12a-2). Clearing before
        the blocking dequeue was the first answer, and it let a `stop()` aimed
        at an utterance that had already ended silence the next one (alpha-plan
        #12c (1)). The worker clears after the dequeue and then re-checks its
        id threshold, which `stop()` raises before it calls this engine's.
        """
        ...
