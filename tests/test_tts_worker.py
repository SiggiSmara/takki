import queue

import pytest

from takki.audio.synthetic_letters import SyntheticLetterAudioSource
from takki.audio.tts import TTSEngine
from takki.audio.tts_worker import Shutdown, Speak, SpeechFinished, TTSWorker
from takki.display.focus import FocusEvent, FocusLost
from takki.events import Quit
from takki.focus_model import FocusModel
from takki.speech import Speaker
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_focus_source import FakeFocusSource
from tests.fakes.fake_tts import FakeTTSEngine


class _StopMidSpeakEngine:
    """A TTSEngine whose speak() simulates a cross-thread stop() arriving
    while the (real) engine would still be blocked in runAndWait(). `worker`
    is set after construction to break the construction-order cycle (the
    worker needs the engine, this engine needs the worker)."""

    def __init__(self) -> None:
        self.worker: TTSWorker | None = None
        self.spoken: list[str] = []

    def speak(self, text: str) -> None:
        self.spoken.append(text)
        assert self.worker is not None
        self.worker.stop()

    def stop(self) -> None:
        pass

    def clear_cancel(self) -> None:
        pass


class TestTTSWorkerRunOne:
    def test_speak_reaches_engine(self) -> None:
        engine = FakeTTSEngine()
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(lambda: engine, outbound)
        worker.enqueue_speak("hello")
        worker.run_one()
        assert engine.spoken == ["hello"]

    def test_natural_completion_posts_completed(self) -> None:
        engine = FakeTTSEngine()
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(lambda: engine, outbound)
        utterance_id = worker.enqueue_speak("hello")
        worker.run_one()
        finished = outbound.get_nowait()
        assert finished == SpeechFinished(utterance_id=utterance_id, status="completed")

    def test_cancel_mid_speak_posts_cancelled(self) -> None:
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        stopper = _StopMidSpeakEngine()
        worker = TTSWorker(lambda: stopper, outbound)
        stopper.worker = worker
        utterance_id = worker.enqueue_speak("interrupt me")
        worker.run_one()
        finished = outbound.get_nowait()
        assert finished == SpeechFinished(utterance_id=utterance_id, status="cancelled")

    def test_utterance_ids_are_echoed_in_order(self) -> None:
        engine = FakeTTSEngine()
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(lambda: engine, outbound)
        first = worker.enqueue_speak("a")
        second = worker.enqueue_speak("b")
        worker.run_one()
        worker.run_one()
        assert [first, second] == [1, 2]
        assert outbound.get_nowait().utterance_id == first
        assert outbound.get_nowait().utterance_id == second

    def test_the_worker_is_the_only_allocator(self) -> None:
        # concurrency-model.md § TTS: every speaking component used to mint its
        # own ids from 0. Two components on one worker must not collide.
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(FakeTTSEngine, outbound)
        letters = SyntheticLetterAudioSource(worker)
        focus_events: queue.Queue[FocusEvent | Quit] = queue.Queue()
        focus = FocusModel(FakeFocusSource(focus_events), Speaker(worker, letters), FakeClock())
        letters.play("a")
        focus.handle(FocusLost())
        letters.play("b")
        for _ in range(3):
            worker.run_one()
        ids = [outbound.get_nowait().utterance_id for _ in range(3)]
        assert ids == [1, 2, 3]

    def test_stale_cancel_flag_does_not_leak_into_next_utterance(self) -> None:
        # stop() called while idle (nothing playing) must not mark the next
        # Speak as cancelled.
        engine = FakeTTSEngine()
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(lambda: engine, outbound)
        worker.stop()
        worker.enqueue_speak("hello")
        worker.run_one()
        assert outbound.get_nowait().status == "completed"

    def test_a_stop_between_enqueue_and_dequeue_is_not_spoken(self) -> None:
        # The handed-over utterance. run_one() used to clear the cancel flag
        # after the get(), so a stop() landing while the command sat in the
        # queue was discarded and the utterance played in full -- the opposite
        # of what concurrency-model.md § TTS promises (alpha session 12a-2).
        engine = FakeTTSEngine()
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(lambda: engine, outbound)
        utterance_id = worker.enqueue_speak("cancel me")
        worker.stop()
        assert worker.run_one() is True
        assert engine.spoken == []
        assert outbound.get_nowait() == SpeechFinished(utterance_id, "cancelled")
        assert outbound.empty()

    def test_a_stop_cancels_every_utterance_already_enqueued(self) -> None:
        engine = FakeTTSEngine()
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(lambda: engine, outbound)
        first = worker.enqueue_speak("one")
        second = worker.enqueue_speak("two")
        worker.stop()
        for _ in range(2):
            worker.run_one()
        assert engine.spoken == []
        assert [outbound.get_nowait() for _ in range(2)] == [
            SpeechFinished(first, "cancelled"),
            SpeechFinished(second, "cancelled"),
        ]

    def test_an_utterance_enqueued_after_a_stop_is_spoken(self) -> None:
        engine = FakeTTSEngine()
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(lambda: engine, outbound)
        cancelled = worker.enqueue_speak("cancel me")
        worker.stop()
        spoken = worker.enqueue_speak("say me")
        for _ in range(2):
            worker.run_one()
        assert engine.spoken == ["say me"]
        assert [outbound.get_nowait() for _ in range(2)] == [
            SpeechFinished(cancelled, "cancelled"),
            SpeechFinished(spoken, "completed"),
        ]

    def test_shutdown_returns_false_without_speaking(self) -> None:
        engine = FakeTTSEngine()
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(lambda: engine, outbound)
        worker.enqueue_shutdown()
        assert worker.run_one() is False
        assert engine.spoken == []

    def test_run_one_returns_true_after_speak(self) -> None:
        engine = FakeTTSEngine()
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(lambda: engine, outbound)
        worker.enqueue_speak("hi")
        assert worker.run_one() is True


class TestTTSWorkerCancelAiming:
    def test_the_cancel_flag_is_cleared_before_the_dequeue_not_after(self) -> None:
        # Clearing after the get() would let the engine discard a stop() aimed
        # at the utterance it is about to speak (alpha session 12a-2).
        engine = FakeTTSEngine()
        worker = TTSWorker(lambda: engine, queue.Queue[SpeechFinished]())
        worker.enqueue_speak("a")
        worker.run_one()
        assert engine.cancels_cleared == 1
        worker.enqueue_speak("b")
        worker.run_one()
        assert engine.cancels_cleared == 2

    def test_a_cancelled_utterance_still_clears_before_the_next_dequeue(self) -> None:
        # The skipped utterance must not leave a stale cancel behind, or the
        # next one -- enqueued after the stop -- is silently swallowed too.
        engine = FakeTTSEngine()
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(lambda: engine, outbound)
        worker.enqueue_speak("cancel me")
        worker.stop()
        worker.enqueue_speak("say me")
        worker.run_one()
        worker.run_one()
        assert engine.spoken == ["say me"]
        assert engine.cancels_cleared == 2
        assert [outbound.get_nowait().status for _ in range(2)] == ["cancelled", "completed"]


class TestTTSWorkerSurvivesEngineFailure:
    # SapiTTS.speak() raising used to propagate out of run() and end the
    # worker thread: no SpeechFinished, the Speaker busy forever, a silent app
    # (ADR-019 § Headless audio/video, found by a windows-latest runner).

    def test_a_failed_utterance_is_reported_and_the_next_one_spoken(self) -> None:
        engine = FakeTTSEngine(fail_on={"lost"})
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(lambda: engine, outbound)
        first = worker.enqueue_speak("lost")
        second = worker.enqueue_speak("heard")
        assert worker.run_one() is True
        assert worker.run_one() is True
        assert [outbound.get_nowait() for _ in range(2)] == [
            SpeechFinished(first, "failed"),
            SpeechFinished(second, "completed"),
        ]
        assert outbound.empty()
        assert engine.failed == ["lost"]
        assert engine.spoken == ["heard"]

    def test_a_cancel_outranks_a_failure(self) -> None:
        # The core asked for it to stop; that it also failed changes nothing the
        # core does with the event.
        class StopThenFail(FakeTTSEngine):
            worker: TTSWorker | None = None

            def speak(self, text: str) -> None:
                assert self.worker is not None
                self.worker.stop()
                super().speak(text)

        engine = StopThenFail(fail_on={"x"})
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(lambda: engine, outbound)
        engine.worker = worker
        utterance_id = worker.enqueue_speak("x")
        worker.run_one()
        assert outbound.get_nowait() == SpeechFinished(utterance_id, "cancelled")
        assert outbound.empty()

    def test_the_worker_thread_outlives_a_failure(self) -> None:
        engine = FakeTTSEngine(fail_on={"lost"})
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(lambda: engine, outbound)
        worker.start()
        first = worker.enqueue_speak("lost")
        second = worker.enqueue_speak("heard")
        assert outbound.get(timeout=5) == SpeechFinished(first, "failed")
        assert outbound.get(timeout=5) == SpeechFinished(second, "completed")
        worker.enqueue_shutdown()
        worker.join(timeout=5)
        assert worker._thread is not None and not worker._thread.is_alive()  # pyright: ignore[reportPrivateUsage]
        assert outbound.empty()


class TestTTSWorkerStartupFailure:
    def test_a_failing_factory_raises_on_the_caller_not_in_silence(self) -> None:
        # The worker builds the engine, so a failure there kills the thread.
        # Left unreported it is silent: no SpeechFinished ever arrives, the
        # Speaker stays busy and the loop stops issuing prompts, and a blind
        # child gets a running app that says nothing (alpha session 12a-2).
        def factory() -> FakeTTSEngine:
            raise OSError("no voice token")

        worker = TTSWorker(factory, queue.Queue[SpeechFinished]())
        with pytest.raises(OSError, match="no voice token"):
            worker.start()

    def test_start_returns_once_the_engine_exists(self) -> None:
        built: list[FakeTTSEngine] = []

        def factory() -> FakeTTSEngine:
            engine = FakeTTSEngine()
            built.append(engine)
            return engine

        worker = TTSWorker(factory, queue.Queue[SpeechFinished]())
        worker.start()
        # Not "eventually": start() has waited, so the engine is there now.
        assert len(built) == 1
        worker.enqueue_shutdown()
        worker.join(timeout=5)


class TestTTSWorkerEngineOwnership:
    def test_the_engine_is_not_built_until_the_worker_runs(self) -> None:
        # concurrency-model.md § The engine belongs to the thread that creates
        # it: main() must not build it, so constructing a TTSWorker must not
        # call the factory at all.
        built: list[FakeTTSEngine] = []

        def factory() -> FakeTTSEngine:
            engine = FakeTTSEngine()
            built.append(engine)
            return engine

        worker = TTSWorker(factory, queue.Queue[SpeechFinished]())
        assert built == []
        worker.build_engine()
        assert len(built) == 1

    def test_the_engine_is_built_exactly_once(self) -> None:
        built: list[FakeTTSEngine] = []

        def factory() -> FakeTTSEngine:
            engine = FakeTTSEngine()
            built.append(engine)
            return engine

        worker = TTSWorker(factory, queue.Queue[SpeechFinished]())
        worker.enqueue_speak("a")
        worker.enqueue_speak("b")
        worker.run_one()
        worker.run_one()
        assert len(built) == 1
        assert built[0].spoken == ["a", "b"]


class TestTTSWorkerStop:
    def test_stop_before_the_engine_exists_reaches_no_engine(self) -> None:
        # Nothing can be sounding yet, and reaching for the engine here would
        # construct it on the caller's thread -- the failure this session exists
        # to remove. The id threshold still records the cancel.
        built: list[FakeTTSEngine] = []

        def factory() -> FakeTTSEngine:
            engine = FakeTTSEngine()
            built.append(engine)
            return engine

        worker = TTSWorker(factory, queue.Queue[SpeechFinished]())
        worker.stop()
        assert built == []

    def test_stop_calls_engine_stop(self) -> None:
        engine = FakeTTSEngine()
        worker = TTSWorker(lambda: engine, queue.Queue[SpeechFinished]())
        worker.build_engine()
        worker.stop()
        assert engine.stopped == 1


def test_speak_and_shutdown_are_commands() -> None:
    assert isinstance(Speak("x", 1), Speak)
    assert isinstance(Shutdown(), Shutdown)


def test_fake_tts_engine_conforms_to_protocol() -> None:
    engine: TTSEngine = FakeTTSEngine()
    assert engine is not None
