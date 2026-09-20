import itertools


class FakeLetterAudioSource:
    def __init__(self) -> None:
        self.played: list[str] = []
        self.stopped: int = 0
        # A range no TTSWorker id can reach. In production both come from the
        # worker's single allocator and cannot collide (concurrency-model.md
        # § TTS); a fake counting from 1 would manufacture the collision that
        # fix exists to prevent, and hide it behind a passing test.
        self._ids = itertools.count(1_000_000)

    def play(self, char: str) -> int:
        self.played.append(char)
        return next(self._ids)

    def stop(self) -> None:
        self.stopped += 1
