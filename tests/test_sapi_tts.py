"""The real SAPI engine. Windows only, and every case needs a real voice.

These are the tests no fake could have stood in for: thread affinity, and the
truncation that survived eleven green sessions because Alpha's commonest
utterance is a single letter and letters are shorter than the cutoff
(concurrency-model.md § SAPI speaks only the first utterance in full).
"""

import queue
import sys
import threading
import time

import pytest

from takki.audio.tts_worker import SpeechFinished, TTSWorker

pytestmark = [pytest.mark.audio, pytest.mark.windows_only]

# ADR-023's introduction script is ~4.2 s. Anything past ~0.9 s would have been
# truncated by the pyttsx3 path, so the assertions below are about length.
LONG = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen"


def _voice() -> str:
    from takki.platform.windows import WindowsPlatformInterface

    voice = WindowsPlatformInterface().find_voice("en")
    if voice is None:
        pytest.skip("no English SAPI voice installed on this machine")
    return voice


class TestSapiTTSOnItsOwnThread:
    def test_a_long_utterance_is_not_truncated(self) -> None:
        if sys.platform != "win32":
            return
        from takki.audio.sapi_tts import SapiTTS

        result: queue.Queue[float] = queue.Queue()

        def worker() -> None:
            engine = SapiTTS(_voice())
            engine.speak("warm up")  # so the timed line is not the first
            start = time.monotonic()
            engine.speak(LONG)
            result.put(time.monotonic() - start)

        threading.Thread(target=worker, daemon=True).start()
        elapsed = result.get(timeout=120)
        # The pyttsx3 path returned in ~0.9-2.1 s here and cut the audio.
        assert elapsed > 3.5, f"second utterance returned in {elapsed:.3f}s -- truncated"

    def test_every_utterance_after_the_first_is_full_length(self) -> None:
        if sys.platform != "win32":
            return
        from takki.audio.sapi_tts import SapiTTS

        result: queue.Queue[list[float]] = queue.Queue()

        def worker() -> None:
            engine = SapiTTS(_voice())
            engine.speak("warm up")
            times: list[float] = []
            for _ in range(3):
                engine.clear_cancel()
                start = time.monotonic()
                engine.speak(LONG)
                times.append(time.monotonic() - start)
            result.put(times)

        threading.Thread(target=worker, daemon=True).start()
        times = result.get(timeout=180)
        # Three in a row, not just the second: truncation was self-perpetuating,
        # so a fix that only repaired the second utterance would pass a
        # single-utterance check and still fail the child on the third.
        assert all(t > 3.5 for t in times), times


class TestSapiTTSCancellation:
    def test_stop_cuts_the_utterance(self) -> None:
        if sys.platform != "win32":
            return
        from takki.audio.sapi_tts import SapiTTS

        handle: queue.Queue[SapiTTS] = queue.Queue()
        result: queue.Queue[float] = queue.Queue()

        def worker() -> None:
            engine = SapiTTS(_voice())
            engine.speak("warm up")
            handle.put(engine)
            start = time.monotonic()
            engine.speak(LONG)
            result.put(time.monotonic() - start)

        threading.Thread(target=worker, daemon=True).start()
        engine = handle.get(timeout=120)
        time.sleep(1.0)
        engine.stop()
        elapsed = result.get(timeout=60)
        assert elapsed < 2.5, f"a {LONG.count(' ') + 1}-word line ran {elapsed:.3f}s after stop()"

    def test_stop_does_not_block_the_calling_thread(self) -> None:
        # concurrency-model.md rule 4: a cross-thread call must have its cost on
        # the *calling* thread measured. Under pyttsx3 this held the main thread
        # ~1.17 s -- roughly 70 ticks at TICK_HZ 60, on the keypress hot path.
        # SapiTTS.stop() makes no COM call at all, so the bar is microseconds.
        if sys.platform != "win32":
            return
        from takki.audio.sapi_tts import SapiTTS

        handle: queue.Queue[SapiTTS] = queue.Queue()
        done: queue.Queue[bool] = queue.Queue()

        def worker() -> None:
            engine = SapiTTS(_voice())
            engine.speak("warm up")
            handle.put(engine)
            engine.speak(LONG)
            done.put(True)

        threading.Thread(target=worker, daemon=True).start()
        engine = handle.get(timeout=120)
        time.sleep(1.0)
        start = time.monotonic()
        engine.stop()
        blocked = time.monotonic() - start
        done.get(timeout=60)
        assert blocked < 0.05, f"stop() held the caller {blocked * 1000:.1f} ms"

    def test_the_utterance_after_a_cancelled_one_speaks_in_full(self) -> None:
        if sys.platform != "win32":
            return
        from takki.audio.sapi_tts import SapiTTS

        handle: queue.Queue[SapiTTS] = queue.Queue()
        result: queue.Queue[list[float]] = queue.Queue()
        go = threading.Event()

        def worker() -> None:
            engine = SapiTTS(_voice())
            engine.speak("warm up")
            handle.put(engine)
            times: list[float] = []
            start = time.monotonic()
            engine.speak(LONG)
            times.append(time.monotonic() - start)
            go.wait(30)
            # What TTSWorker.run_one() does before each dequeue. The engine
            # deliberately does not clear its own flag -- see
            # TTSEngine.clear_cancel() -- so a caller driving it by hand has to
            # do the worker's job, and this test is that caller.
            engine.clear_cancel()
            start = time.monotonic()
            engine.speak(LONG)
            times.append(time.monotonic() - start)
            result.put(times)

        threading.Thread(target=worker, daemon=True).start()
        engine = handle.get(timeout=120)
        time.sleep(1.0)
        engine.stop()
        go.set()
        cancelled, after = result.get(timeout=180)
        assert cancelled < 2.5, cancelled
        # A cancel must not leave the engine unable to speak the next thing --
        # the failure mode a purge-based cancel invites.
        assert after > 3.5, after


class TestTTSWorkerWithSapi:
    def test_the_worker_builds_and_drives_its_own_engine(self) -> None:
        # The whole point of the factory: main() never touches the engine, and
        # an engine built anywhere but here never returns from its first
        # utterance (concurrency-model.md § The engine belongs to the thread
        # that creates it). This is the test that failed before the fix.
        if sys.platform != "win32":
            return
        from takki.audio.sapi_tts import SapiTTS

        voice = _voice()
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(lambda: SapiTTS(voice), outbound)
        worker.start()
        first = worker.enqueue_speak("a")
        second = worker.enqueue_speak("b")
        assert outbound.get(timeout=60) == SpeechFinished(first, "completed")
        assert outbound.get(timeout=60) == SpeechFinished(second, "completed")
        worker.enqueue_shutdown()
        worker.join(timeout=10)

    def test_a_stop_from_the_main_thread_cancels_the_in_flight_utterance(self) -> None:
        if sys.platform != "win32":
            return
        from takki.audio.sapi_tts import SapiTTS

        voice = _voice()
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(lambda: SapiTTS(voice), outbound)
        worker.start()
        warm = worker.enqueue_speak("warm up")
        assert outbound.get(timeout=120).utterance_id == warm
        utterance_id = worker.enqueue_speak(LONG)
        time.sleep(1.0)
        worker.stop()
        finished = outbound.get(timeout=60)
        assert finished == SpeechFinished(utterance_id, "cancelled")
        worker.enqueue_shutdown()
        worker.join(timeout=10)
