from takki.audio.tts_worker import TTSWorker


class SyntheticLetterAudioSource:
    """LetterAudioSource floor (ADR-003): runtime TTS speaks the letter name."""

    def __init__(self, worker: TTSWorker) -> None:
        # Never empty -- espeak-ng/SAPI cover every letter of every target
        # language. Personal and Base (Beta) slot in above this as separate
        # LetterAudioSource implementations without reshaping this seam.
        self._worker = worker

    def play(self, char: str) -> int:
        return self._worker.enqueue_speak(char)

    def stop(self) -> None:
        self._worker.stop()
