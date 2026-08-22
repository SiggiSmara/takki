import queue

import pytest

from takki.audio.fallback_tts import FallbackTTS
from takki.audio.tts import TTSEngine
from takki.audio.tts_worker import SpeechFinished, TTSWorker


@pytest.mark.audio
class TestFallbackTTS:
    def test_conforms_to_protocol(self) -> None:
        # Not a module-level check (unlike the fake-backed Protocols): it
        # would construct a real pyttsx3 engine at collection time, breaking
        # import on a machine with no system TTS, even for the default tier.
        engine: TTSEngine = FallbackTTS()
        assert engine is not None

    def test_speak_does_not_raise(self) -> None:
        FallbackTTS().speak("a")

    def test_stop_does_not_raise_when_idle(self) -> None:
        FallbackTTS().stop()

    def test_stop_does_not_raise_after_speak(self) -> None:
        tts = FallbackTTS()
        tts.speak("a")
        tts.stop()

    # No timing assertion on stop() cutting audible playback: on this dev
    # box, pyttsx3's Linux espeak driver synthesizes the full utterance into
    # a buffer and only then plays it back via one blocking `aplay`
    # subprocess call (see FallbackTTS.stop()) -- `aplay` isn't even
    # installed here, and synthesis alone completes in ~10ms regardless of
    # utterance length, so stop() has nothing in-flight to interrupt by the
    # time a test (or a real keypress) could call it. C12's cross-thread
    # stop() timing is validated on SAPI/Windows only.


@pytest.mark.audio
class TestTTSWorkerWithRealEngine:
    def test_speak_completes_and_reaches_outbound_queue(self) -> None:
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(FallbackTTS(), outbound)
        worker.enqueue_speak("a", utterance_id=1)
        worker.run_one()
        finished = outbound.get_nowait()
        assert finished.utterance_id == 1
        assert finished.status == "completed"

    def test_real_thread_start_and_join(self) -> None:
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(FallbackTTS(), outbound)
        worker.start()
        worker.enqueue_speak("a", utterance_id=1)
        finished = outbound.get(timeout=5)
        assert finished == SpeechFinished(utterance_id=1, status="completed")
        worker.enqueue_shutdown()
        worker.join(timeout=5)
