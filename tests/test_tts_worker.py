import queue

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


class TestTTSWorkerRunOne:
    def test_speak_reaches_engine(self) -> None:
        engine = FakeTTSEngine()
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(engine, outbound)
        worker.enqueue_speak("hello")
        worker.run_one()
        assert engine.spoken == ["hello"]

    def test_natural_completion_posts_completed(self) -> None:
        engine = FakeTTSEngine()
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(engine, outbound)
        utterance_id = worker.enqueue_speak("hello")
        worker.run_one()
        finished = outbound.get_nowait()
        assert finished == SpeechFinished(utterance_id=utterance_id, status="completed")

    def test_cancel_mid_speak_posts_cancelled(self) -> None:
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        stopper = _StopMidSpeakEngine()
        worker = TTSWorker(stopper, outbound)
        stopper.worker = worker
        utterance_id = worker.enqueue_speak("interrupt me")
        worker.run_one()
        finished = outbound.get_nowait()
        assert finished == SpeechFinished(utterance_id=utterance_id, status="cancelled")

    def test_utterance_ids_are_echoed_in_order(self) -> None:
        engine = FakeTTSEngine()
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(engine, outbound)
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
        worker = TTSWorker(FakeTTSEngine(), outbound)
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
        worker = TTSWorker(engine, outbound)
        worker.stop()
        worker.enqueue_speak("hello")
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
        worker.enqueue_speak("hi")
        assert worker.run_one() is True


class TestTTSWorkerStop:
    def test_stop_calls_engine_stop(self) -> None:
        engine = FakeTTSEngine()
        worker = TTSWorker(engine, queue.Queue[SpeechFinished]())
        worker.stop()
        assert engine.stopped == 1


def test_speak_and_shutdown_are_commands() -> None:
    assert isinstance(Speak("x", 1), Speak)
    assert isinstance(Shutdown(), Shutdown)


def test_fake_tts_engine_conforms_to_protocol() -> None:
    engine: TTSEngine = FakeTTSEngine()
    assert engine is not None
