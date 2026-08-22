from typing import Literal, Protocol

CueName = Literal["correct", "error", "boundary", "chirp_on", "chirp_off"]


class SoundCuePlayer(Protocol):
    def play(self, cue: CueName) -> None: ...
