from takki.audio.tts import SpeechOutputError


class FakeTTSEngine:
    def __init__(self, fail_on: set[str] | None = None) -> None:
        self.spoken: list[str] = []
        self.failed: list[str] = []
        # Entered speak() with the cancel flag set and returned without a sound,
        # as SapiTTS.speak() does. The worker still reports these "completed",
        # so this list is the only place a silent utterance shows up.
        self.skipped: list[str] = []
        # Lines that raise instead of speaking, as SAPI does with no audio output.
        self.fail_on: set[str] = fail_on or set()
        self.stopped: int = 0
        self.cancels_cleared: int = 0
        # The flag the real engines keep. A fake without it made a stop() aimed
        # at an utterance that had already finished harmless under test, while
        # on SAPI it silences the next one (alpha-plan #12c (1), RS-22b/c).
        self.cancel_requested = False

    def speak(self, text: str) -> None:
        if self.cancel_requested:
            self.skipped.append(text)
            return
        if text in self.fail_on:
            self.failed.append(text)
            raise SpeechOutputError(f"cannot sound {text!r}")
        self.spoken.append(text)

    def stop(self) -> None:
        self.stopped += 1
        self.cancel_requested = True

    def clear_cancel(self) -> None:
        self.cancels_cleared += 1
        self.cancel_requested = False
