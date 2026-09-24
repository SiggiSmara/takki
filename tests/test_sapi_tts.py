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
from collections.abc import Callable
from typing import Any

import pytest

from takki.audio.tts import SpeechOutputError
from takki.audio.tts_worker import SpeechFinished, TTSWorker

pytestmark = [pytest.mark.audio, pytest.mark.windows_only]

LONG = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen"
# LONG measures ~5.9 s spoken at ADR-003's Rate 0. The bracket matters as much as
# the floor: SapiTTS abandons an utterance after MAX_UTTERANCE_SECONDS (60 s)
# when SAPI never signals completion, and 60 is greater than any floor below --
# so a lower bound alone would report working speech on a machine that said
# nothing at all, which is the failure this whole file exists to catch.
FULL_MIN, FULL_MAX = 3.5, 15.0


def _voice() -> str:
    """The English voice id, or skip. **Call this on the main thread.**

    `pytest.skip()` raises, and raised on a worker thread it kills that thread
    instead of skipping the test -- the test then blocks until its own queue
    timeout and fails with a bare `queue.Empty` naming none of it. That is how a
    `windows-latest` runner reported itself (alpha session 12a-2): failures that
    were correct but arrived minutes late and said nothing. Every case below
    resolves the voice before it spawns anything.
    """
    from takki.platform.windows import WindowsPlatformInterface

    voice = WindowsPlatformInterface().find_voice("en")
    if voice is None:
        pytest.skip("no English SAPI voice installed on this machine")
    return voice


def _spawn(body: Callable[[], Any], *also: "queue.Queue[Any]") -> "queue.Queue[Any]":
    """Run `body` on its own thread; its return value *or its exception* lands in the queue.

    SapiTTS must be constructed on the thread that drives it, so every case here
    needs a worker. Carrying the exception back is what makes a failure legible:
    without it, anything raised inside the worker -- a COM error, a refused
    voice token -- kills that thread silently and the test reports a timeout
    instead of the cause.

    `also` names the other queues a test is waiting on, typically the one the
    worker hands its engine back through. A failure is delivered to every one of
    them, because a worker that dies before it reaches `handle.put(engine)`
    would otherwise leave the main thread blocked on a queue nothing can ever
    arrive in -- trading a silent thread for a two-minute stall, which is how
    this file behaved on a `windows-latest` runner (alpha session 12a-2).
    """
    box: queue.Queue[Any] = queue.Queue()

    def run() -> None:
        try:
            box.put(body())
        except BaseException as error:
            for destination in (box, *also):
                destination.put(error)

    threading.Thread(target=run, daemon=True).start()
    return box


def _result(box: "queue.Queue[Any]", timeout: float = 180.0) -> Any:
    """Pop a worker's result, re-raising whatever it failed with."""
    outcome = box.get(timeout=timeout)
    if isinstance(outcome, BaseException):
        raise outcome
    return outcome


class TestSapiTTSOnItsOwnThread:
    def test_a_long_utterance_is_not_truncated(self) -> None:
        if sys.platform != "win32":
            return
        from takki.audio.sapi_tts import SapiTTS

        voice = _voice()

        def body() -> float:
            engine = SapiTTS(voice)
            engine.speak("warm up")  # so the timed line is not the first
            start = time.monotonic()
            engine.speak(LONG)
            return time.monotonic() - start

        elapsed = _result(_spawn(body))
        # The pyttsx3 path returned in ~0.9-2.1 s here and cut the audio.
        assert FULL_MIN < elapsed < FULL_MAX, (
            f"second utterance returned in {elapsed:.3f}s -- "
            f"{'truncated' if elapsed <= FULL_MIN else 'abandoned; did SAPI ever finish?'}"
        )

    def test_every_utterance_after_the_first_is_full_length(self) -> None:
        if sys.platform != "win32":
            return
        from takki.audio.sapi_tts import SapiTTS

        voice = _voice()

        def body() -> list[float]:
            engine = SapiTTS(voice)
            engine.speak("warm up")
            times: list[float] = []
            for _ in range(3):
                engine.clear_cancel()
                start = time.monotonic()
                engine.speak(LONG)
                times.append(time.monotonic() - start)
            return times

        times = _result(_spawn(body))
        # Three in a row, not just the second: truncation was self-perpetuating,
        # so a fix that only repaired the second utterance would pass a
        # single-utterance check and still fail the child on the third.
        assert all(FULL_MIN < t < FULL_MAX for t in times), times


class TestSapiTTSCancellation:
    def test_stop_cuts_the_utterance(self) -> None:
        if sys.platform != "win32":
            return
        from takki.audio.sapi_tts import SapiTTS

        voice = _voice()
        handle: queue.Queue[Any] = queue.Queue()

        def body() -> float:
            engine = SapiTTS(voice)
            engine.speak("warm up")
            handle.put(engine)
            start = time.monotonic()
            engine.speak(LONG)
            return time.monotonic() - start

        box = _spawn(body, handle)
        engine = _result(handle, timeout=120)
        time.sleep(1.0)
        engine.stop()
        elapsed = _result(box)
        assert elapsed < 2.5, f"a {LONG.count(' ') + 1}-word line ran {elapsed:.3f}s after stop()"

    def test_stop_does_not_block_the_calling_thread(self) -> None:
        # concurrency-model.md rule 4: a cross-thread call must have its cost on
        # the *calling* thread measured. Through pyttsx3 the same call held the
        # main thread ~100 ms even after repair, on the keypress hot path.
        # SapiTTS.stop() makes no COM call at all, so the bar is microseconds.
        if sys.platform != "win32":
            return
        from takki.audio.sapi_tts import SapiTTS

        voice = _voice()
        handle: queue.Queue[Any] = queue.Queue()

        def body() -> bool:
            engine = SapiTTS(voice)
            engine.speak("warm up")
            handle.put(engine)
            engine.speak(LONG)
            return True

        box = _spawn(body, handle)
        engine = _result(handle, timeout=120)
        time.sleep(1.0)
        start = time.monotonic()
        engine.stop()
        blocked = time.monotonic() - start
        _result(box)
        assert blocked < 0.05, f"stop() held the caller {blocked * 1000:.1f} ms"

    def test_the_utterance_after_a_cancelled_one_speaks_in_full(self) -> None:
        if sys.platform != "win32":
            return
        from takki.audio.sapi_tts import SapiTTS

        voice = _voice()
        handle: queue.Queue[Any] = queue.Queue()
        go = threading.Event()

        def body() -> tuple[float, float]:
            engine = SapiTTS(voice)
            engine.speak("warm up")
            handle.put(engine)
            start = time.monotonic()
            engine.speak(LONG)
            cancelled = time.monotonic() - start
            go.wait(30)
            # What TTSWorker.run_one() does before each dequeue. The engine
            # deliberately does not clear its own flag -- see
            # TTSEngine.clear_cancel() -- so a caller driving it by hand has to
            # do the worker's job, and this test is that caller.
            engine.clear_cancel()
            start = time.monotonic()
            engine.speak(LONG)
            return cancelled, time.monotonic() - start

        box = _spawn(body, handle)
        engine = _result(handle, timeout=120)
        time.sleep(1.0)
        engine.stop()
        go.set()
        cancelled, after = _result(box)
        assert cancelled < 2.5, cancelled
        # A cancel must not leave the engine unable to speak the next thing --
        # the failure mode a purge-based cancel invites.
        assert FULL_MIN < after < FULL_MAX, after


class TestSapiTTSDoesNotHang:
    def test_an_utterance_that_never_finishes_is_abandoned(self) -> None:
        # The failure a windows-latest runner found (alpha session 12a-2): with
        # no usable audio endpoint SAPI accepts the text and never signals
        # completion, and an unbounded wait hangs the TTS worker forever -- no
        # SpeechFinished, Speaker stays busy, the loop stops issuing prompts,
        # and the app is silently inert. Simulated here by shortening the cap
        # rather than by removing the sound card.
        if sys.platform != "win32":
            return
        import takki.audio.sapi_tts as sapi_tts
        from takki.audio.sapi_tts import SapiTTS

        voice = _voice()
        original = sapi_tts.MAX_UTTERANCE_SECONDS

        def body() -> tuple[float, float]:
            engine = SapiTTS(voice)
            engine.speak("warm up")
            sapi_tts.MAX_UTTERANCE_SECONDS = 0.5
            start = time.monotonic()
            # ~5.9 s of speech, abandoned at ~0.5 s. It raises, so TTSWorker
            # reports "failed" -- returning reported it "completed".
            with pytest.raises(SpeechOutputError):
                engine.speak(LONG)
            abandoned = time.monotonic() - start
            sapi_tts.MAX_UTTERANCE_SECONDS = original
            # The engine has to survive it: the purge on the way out is what
            # leaves it usable, and a cap that bricked the voice would trade a
            # hang for permanent silence.
            engine.clear_cancel()
            start = time.monotonic()
            engine.speak(LONG)
            return abandoned, time.monotonic() - start

        try:
            abandoned, after = _result(_spawn(body))
        finally:
            sapi_tts.MAX_UTTERANCE_SECONDS = original
        assert abandoned < 2.0, f"waited {abandoned:.3f}s past a 0.5s cap"
        assert FULL_MIN < after < FULL_MAX, f"engine unusable after an abandon: {after:.3f}s"


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
