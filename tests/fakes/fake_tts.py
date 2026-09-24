from takki.audio.tts import SpeechOutputError


class FakeTTSEngine:
    def __init__(self, fail_on: set[str] | None = None) -> None:
        self.spoken: list[str] = []
        self.failed: list[str] = []
        # Lines that raise instead of speaking, as SAPI does with no audio output.
        self.fail_on: set[str] = fail_on or set()
        self.stopped: int = 0
        self.cancels_cleared: int = 0

    def speak(self, text: str) -> None:
        if text in self.fail_on:
            self.failed.append(text)
            raise SpeechOutputError(f"cannot sound {text!r}")
        self.spoken.append(text)

    def stop(self) -> None:
        self.stopped += 1

    def clear_cancel(self) -> None:
        self.cancels_cleared += 1
