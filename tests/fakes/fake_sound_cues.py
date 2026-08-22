from takki.audio.cues import CueName


class FakeSoundCues:
    def __init__(self) -> None:
        self.played: list[CueName] = []

    def play(self, cue: CueName) -> None:
        self.played.append(cue)
