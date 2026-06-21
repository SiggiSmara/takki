class FakeTTSEngine:
    def __init__(self) -> None:
        self.spoken: list[str] = []
        self.stopped: int = 0

    def speak(self, text: str) -> None:
        self.spoken.append(text)

    def stop(self) -> None:
        self.stopped += 1
