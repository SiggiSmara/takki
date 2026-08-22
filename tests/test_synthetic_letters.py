import queue

from takki.audio.letters import LetterAudioSource
from takki.audio.synthetic_letters import SyntheticLetterAudioSource
from takki.audio.tts_worker import SpeechFinished, TTSWorker
from tests.fakes.fake_tts import FakeTTSEngine

# Static structural conformance — pyright fails if the impl drifts from the Protocol.
_conforms: LetterAudioSource = SyntheticLetterAudioSource(
    TTSWorker(FakeTTSEngine(), queue.Queue[SpeechFinished]())
)


class TestSyntheticLetterAudioSource:
    def test_play_enqueues_the_letter_on_the_worker(self) -> None:
        engine = FakeTTSEngine()
        worker = TTSWorker(engine, queue.Queue[SpeechFinished]())
        source = SyntheticLetterAudioSource(worker)
        source.play("a")
        worker.run_one()
        assert engine.spoken == ["a"]

    def test_play_does_not_block(self) -> None:
        # No engine.speak() happens until something drains the worker's queue.
        engine = FakeTTSEngine()
        worker = TTSWorker(engine, queue.Queue[SpeechFinished]())
        source = SyntheticLetterAudioSource(worker)
        source.play("a")
        assert engine.spoken == []

    def test_each_letter_gets_a_distinct_utterance_id(self) -> None:
        engine = FakeTTSEngine()
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(engine, outbound)
        source = SyntheticLetterAudioSource(worker)
        source.play("a")
        source.play("b")
        worker.run_one()
        worker.run_one()
        first = outbound.get_nowait().utterance_id
        second = outbound.get_nowait().utterance_id
        assert first != second

    def test_stop_delegates_to_worker_stop(self) -> None:
        engine = FakeTTSEngine()
        worker = TTSWorker(engine, queue.Queue[SpeechFinished]())
        source = SyntheticLetterAudioSource(worker)
        source.stop()
        assert engine.stopped == 1
