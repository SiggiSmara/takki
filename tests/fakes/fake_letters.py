class FakeLetterAudioSource:
    def __init__(self) -> None:
        self.played: list[str] = []
        self.stopped: int = 0

    def play(self, char: str) -> None:
        self.played.append(char)

    def stop(self) -> None:
        self.stopped += 1
