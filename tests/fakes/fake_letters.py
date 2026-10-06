import itertools

from takki.audio.tts_worker import EventSink, SpeechFinished, SpeechStatus


class FakeLetterAudioSource:
    def __init__(self, outbound: EventSink | None = None) -> None:
        self.played: list[str] = []
        self.stopped: int = 0
        # Where a letter's finish is reported, as the worker reports the
        # synthetic source's. None reports nothing.
        self._outbound = outbound
        self._outstanding: int | None = None
        # A range no TTSWorker id can reach. In production both come from the
        # worker's single allocator and cannot collide (concurrency-model.md
        # § TTS); a fake counting from 1 would manufacture the collision that
        # fix exists to prevent, and hide it behind a passing test.
        self._ids = itertools.count(1_000_000)

    def play(self, char: str) -> int:
        self.played.append(char)
        self._outstanding = next(self._ids)
        return self._outstanding

    def stop(self) -> None:
        self.stopped += 1
        self.finish("cancelled")

    def finish(self, status: SpeechStatus = "completed") -> None:
        """The letter now sounding ends. Nothing ends it until a test says so."""
        if self._outstanding is not None and self._outbound is not None:
            self._outbound.put(SpeechFinished(self._outstanding, status))
        self._outstanding = None
