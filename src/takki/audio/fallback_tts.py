from pyttsx3.engine import Engine


class FallbackTTS:
    """Blocking TTSEngine over pyttsx3 (SAPI/Windows, espeak-ng/Linux)."""

    def __init__(self) -> None:
        # Must be driven from the TTS worker thread only (concurrency-model.md).
        # Not pyttsx3.init(): it caches one engine in a module-level
        # WeakValueDict, and a second runAndWait() on that cached instance
        # deadlocks the SAPI5 driver. A fresh Engine() avoids it
        # (docs/research/tts-letter-pronunciation.md).
        self._engine = Engine(driverName=None, debug=False)

    def speak(self, text: str) -> None:
        self._engine.say(text)
        self._engine.runAndWait()

    def stop(self) -> None:
        # On Linux, pyttsx3's espeak driver synthesizes the whole utterance
        # into a buffer, THEN plays it back as one blocking `aplay` subprocess
        # once synthesis finishes -- stop()/Cancel() only reaches the
        # (near-instant) synthesis phase, never the audible playback phase.
        # Validated on SAPI only (C12 spike); do not rely on it cutting
        # audible speech on the Linux dev path.
        self._engine.stop()
