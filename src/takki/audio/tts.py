from typing import Protocol


class TTSEngine(Protocol):
    def speak(self, text: str) -> None: ...

    def stop(self) -> None: ...
