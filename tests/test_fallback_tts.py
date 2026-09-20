import queue
import sys

import pytest

from takki.audio.fallback_tts import FallbackTTS
from takki.audio.tts import TTSEngine
from takki.audio.tts_worker import SpeechFinished, TTSWorker

# FallbackTTS is the Linux dev path and nothing else (ADR-003): Windows drives
# SAPI through SapiTTS, covered by tests/test_sapi_tts.py. Running these on
# Windows exercises a path Takki does not ship -- and it hangs rather than
# failing, which is worse than useless in CI. Demonstrated on a
# `windows-latest` runner (alpha session 12a-2): pyttsx3's engine constructed
# fine and then `runAndWait()` never returned, because with no usable audio
# endpoint SAPI accepts the text and never fires the completion event its loop
# is polling for. The run had to be cancelled by hand at 8.5 minutes.
pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="FallbackTTS is the Linux dev path; Windows uses SapiTTS (ADR-003)",
)


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
        worker = TTSWorker(FallbackTTS, outbound)
        utterance_id = worker.enqueue_speak("a")
        worker.run_one()
        finished = outbound.get_nowait()
        assert finished.utterance_id == utterance_id
        assert finished.status == "completed"

    def test_real_thread_start_and_join(self) -> None:
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(FallbackTTS, outbound)
        worker.start()
        utterance_id = worker.enqueue_speak("a")
        finished = outbound.get(timeout=5)
        assert finished == SpeechFinished(utterance_id=utterance_id, status="completed")
        worker.enqueue_shutdown()
        worker.join(timeout=5)
