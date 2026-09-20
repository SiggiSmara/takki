from pyttsx3.engine import Engine


class FallbackTTS:
    """Blocking TTSEngine over pyttsx3. The Linux dev path only (ADR-019).

    Do not put this back on Windows. pyttsx3's SAPI driver truncates every
    utterance after the first, because it leaves its own `DriverProxy._busy`
    False when `runAndWait()` returns and then purges the utterance it has just
    started -- proof in `spikes/tts_thread_truncation_spike.py busy`. It also
    rejects OneCore voice ids and swallows the ValueError, so a verified voice
    silently does not apply. Windows uses `takki.audio.sapi_tts.SapiTTS`
    instead (alpha session 12a-2; ADR-003).

    It is worth knowing that all of that *is* repairable here, and was made to
    work before being rejected: `proxy.setBusy(True)` after each runAndWait(),
    a ~250ms message pump before it to absorb the purge's own EndStream, and
    the voice token assigned onto `proxy._driver._tts.Voice`. It was refused
    because those three depend on undocumented internals and what they prevent
    is silence -- a version bump could reintroduce it without raising, and no
    test tier would hear. Run `spikes/tts_thread_truncation_spike.py repaired`
    before reopening the question; ADR-003 has the argument.
    """

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

    def clear_cancel(self) -> None:
        # pyttsx3 holds no cancel flag of its own -- stop() reaches the driver
        # directly -- so there is nothing to forget.
        pass
