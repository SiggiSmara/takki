import queue

from takki.audio.tts import TTSEngine
from takki.audio.tts_worker import Shutdown, Speak, SpeechFinished, TTSWorker
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


class TestTTSWorkerRunOne:
    def test_speak_reaches_engine(self) -> None:
        engine = FakeTTSEngine()
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(engine, outbound)
        worker.enqueue_speak("hello", utterance_id=1)
        worker.run_one()
        assert engine.spoken == ["hello"]

    def test_natural_completion_posts_completed(self) -> None:
        engine = FakeTTSEngine()
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(engine, outbound)
        worker.enqueue_speak("hello", utterance_id=7)
        worker.run_one()
        finished = outbound.get_nowait()
        assert finished == SpeechFinished(utterance_id=7, status="completed")

    def test_cancel_mid_speak_posts_cancelled(self) -> None:
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        stopper = _StopMidSpeakEngine()
        worker = TTSWorker(stopper, outbound)
        stopper.worker = worker
        worker.enqueue_speak("interrupt me", utterance_id=3)
        worker.run_one()
        finished = outbound.get_nowait()
        assert finished == SpeechFinished(utterance_id=3, status="cancelled")

    def test_utterance_ids_are_echoed_in_order(self) -> None:
        engine = FakeTTSEngine()
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(engine, outbound)
        worker.enqueue_speak("a", utterance_id=1)
        worker.enqueue_speak("b", utterance_id=2)
        worker.run_one()
        worker.run_one()
        assert outbound.get_nowait().utterance_id == 1
        assert outbound.get_nowait().utterance_id == 2

    def test_stale_cancel_flag_does_not_leak_into_next_utterance(self) -> None:
        # stop() called while idle (nothing playing) must not mark the next
        # Speak as cancelled.
        engine = FakeTTSEngine()
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(engine, outbound)
        worker.stop()
        worker.enqueue_speak("hello", utterance_id=1)
        worker.run_one()
        assert outbound.get_nowait().status == "completed"

    def test_shutdown_returns_false_without_speaking(self) -> None:
        engine = FakeTTSEngine()
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(engine, outbound)
        worker.enqueue_shutdown()
        assert worker.run_one() is False
        assert engine.spoken == []

    def test_run_one_returns_true_after_speak(self) -> None:
        engine = FakeTTSEngine()
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(engine, outbound)
        worker.enqueue_speak("hi", utterance_id=1)
        assert worker.run_one() is True


class TestTTSWorkerStop:
    def test_stop_calls_engine_stop(self) -> None:
        engine = FakeTTSEngine()
        worker = TTSWorker(engine, queue.Queue())
        worker.stop()
        assert engine.stopped == 1


def test_speak_and_shutdown_are_commands() -> None:
    assert isinstance(Speak("x", 1), Speak)
    assert isinstance(Shutdown(), Shutdown)


def test_fake_tts_engine_conforms_to_protocol() -> None:
    engine: TTSEngine = FakeTTSEngine()
    assert engine is not None
