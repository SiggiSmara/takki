class FakeSoundCues:
    def __init__(self) -> None:
        self.played: list[str] = []

    def play(self, cue: str) -> None:
        self.played.append(cue)
