import queue

from takki.audio.synthetic_letters import SyntheticLetterAudioSource
from takki.audio.tts_worker import SpeechFinished, TTSWorker
from takki.speech import Speaker
from tests.fakes.fake_letters import FakeLetterAudioSource
from tests.fakes.fake_tts import FakeTTSEngine
from tests.fakes.waiting_queue import WaitingCommandQueue, install

Built = tuple[
    Speaker, TTSWorker, FakeTTSEngine, FakeLetterAudioSource, "queue.Queue[SpeechFinished]"
]


def build() -> Built:
    engine = FakeTTSEngine()
    outbound: queue.Queue[SpeechFinished] = queue.Queue()
    worker = TTSWorker(lambda: engine, outbound)
    letters = FakeLetterAudioSource()
    return Speaker(worker, letters), worker, engine, letters, outbound


def drain(worker: TTSWorker) -> None:
    while not worker.idle:
        worker.run_one()


class TestSequencing:
    def test_only_the_first_utterance_is_enqueued(self) -> None:
        speaker, worker, engine, _, _ = build()
        speaker.say("one", "two", "three")
        drain(worker)
        # The core holds the remainder; the worker's queue never carries a
        # backlog (ADR-012 § TTS utterance sequencing).
        assert engine.spoken == ["one"]

    def test_each_completion_releases_exactly_the_next_one(self) -> None:
        speaker, worker, engine, _, outbound = build()
        speaker.say("one", "two", "three")
        for _ in range(3):
            drain(worker)
            speaker.on_finished(outbound.get_nowait())
        assert engine.spoken == ["one", "two", "three"]
        assert speaker.busy is False

    def test_busy_until_the_last_utterance_finishes(self) -> None:
        speaker, worker, _, _, outbound = build()
        speaker.say("one", "two")
        states = []
        for _ in range(2):
            drain(worker)
            states.append(speaker.busy)
            speaker.on_finished(outbound.get_nowait())
        assert states == [True, True]
        assert speaker.busy is False

    def test_a_letter_does_not_make_the_speaker_busy(self) -> None:
        speaker, _, _, letters, _ = build()
        speaker.letter("f")
        assert letters.played == ["f"]
        assert speaker.busy is False


class TestSupersededUtterances:
    def test_an_unknown_id_is_dropped(self) -> None:
        speaker, worker, _, _, outbound = build()
        speaker.say("one", "two")
        drain(worker)
        assert speaker.on_finished(SpeechFinished(9999, "completed")) is False
        # The sequence did not advance: "two" is still pending, not spoken.
        assert speaker.busy is True
        speaker.on_finished(outbound.get_nowait())
        drain(worker)

    def test_a_cancelled_utterance_racing_its_own_completion_does_not_advance(self) -> None:
        # The concrete case ADR-012 § Utterance ids exists to prevent: stop()
        # is issued, the worker had already finished naturally, and the stale
        # SpeechFinished is still in the queue when the next sequence starts.
        speaker, worker, engine, _, outbound = build()
        speaker.say("prompt")
        drain(worker)
        stale = outbound.get_nowait()
        speaker.interrupt()
        speaker.say("next")
        drain(worker)
        assert speaker.on_finished(stale) is False
        assert speaker.busy is True
        assert engine.spoken == ["prompt", "next"]


class TestInterrupt:
    def test_interruptible_sequence_loses_its_remainder(self) -> None:
        speaker, worker, engine, _, _ = build()
        speaker.say("one", "two", "three")
        drain(worker)
        speaker.interrupt()
        drain(worker)
        assert engine.spoken == ["one"]
        assert engine.stopped == 1
        assert speaker.busy is False

    def test_a_non_interruptible_sequence_survives_intact(self) -> None:
        speaker, worker, engine, _, outbound = build()
        speaker.say("rung one", "rung two", interruptible=False)
        drain(worker)
        speaker.interrupt()
        assert engine.stopped == 0
        for _ in range(2):
            drain(worker)
            speaker.on_finished(outbound.get_nowait())
        assert engine.spoken == ["rung one", "rung two"]

    def test_dropping_stops_at_the_first_non_interruptible_utterance(self) -> None:
        speaker, worker, engine, _, _ = build()
        speaker.say("prompt")
        speaker.say("rung", interruptible=False)
        drain(worker)
        speaker.interrupt()
        drain(worker)
        assert engine.spoken == ["prompt", "rung"]

    def test_a_non_interruptible_utterance_survives_an_outstanding_letter(self) -> None:
        # interrupt() used to call _letters.stop() before the non-interruptible
        # guard, and for Alpha's SyntheticLetterAudioSource that call *is*
        # TTSWorker.stop() -- so a milestone announcement was cut whenever a
        # letter was still outstanding (alpha session 12a-2).
        engine = FakeTTSEngine()
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(lambda: engine, outbound)
        letters = SyntheticLetterAudioSource(worker)
        speaker = Speaker(worker, letters)
        speaker.say("rung one", "rung two", interruptible=False)
        speaker.letter("f")
        drain(worker)
        speaker.interrupt()
        assert engine.stopped == 0
        for _ in range(2):
            drain(worker)
            speaker.on_finished(outbound.get_nowait())
        assert engine.spoken == ["rung one", "f", "rung two"]

    def test_a_non_interruptible_utterance_leaves_the_letter_alone(self) -> None:
        speaker, _, engine, letters, _ = build()
        speaker.say("rung", interruptible=False)
        speaker.letter("f")
        speaker.interrupt()
        assert (letters.played, letters.stopped, engine.stopped) == (["f"], 0, 0)

    def test_a_playing_letter_is_stopped_once(self) -> None:
        speaker, _, _, letters, _ = build()
        speaker.letter("f")
        speaker.interrupt()
        speaker.interrupt()
        assert letters.stopped == 1

    def test_a_letter_that_already_finished_is_not_stopped(self) -> None:
        # Through the real synthetic source, so the letter's completion comes
        # back as a SpeechFinished carrying the id play() handed out.
        engine = FakeTTSEngine()
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(lambda: engine, outbound)
        speaker = Speaker(worker, SyntheticLetterAudioSource(worker))
        speaker.letter("f")
        drain(worker)
        assert speaker.on_finished(outbound.get_nowait()) is False
        speaker.interrupt()
        assert engine.stopped == 0

    def test_a_completed_letter_is_reported_as_finished(self) -> None:
        speaker, _, _, _, _ = build()
        speaker.letter("f")
        assert speaker.on_finished(SpeechFinished(1_000_000, "completed")) is False
        assert speaker.letter_finished is True

    def test_a_letter_that_failed_is_not_reported_as_finished(self) -> None:
        # The child did not hear it, so nothing may be timed from it
        # (alpha-plan #12j, O4). Through the real worker, which is what turns
        # an engine that raises into a "failed" status.
        engine = FakeTTSEngine(fail_on={"f"})
        outbound: queue.Queue[SpeechFinished] = queue.Queue()
        worker = TTSWorker(lambda: engine, outbound)
        speaker = Speaker(worker, SyntheticLetterAudioSource(worker))
        speaker.letter("f")
        drain(worker)
        event = outbound.get_nowait()
        assert event.status == "failed"
        assert speaker.on_finished(event) is False
        assert speaker.letter_finished is False
        # No longer outstanding either: there is nothing left to stop.
        speaker.interrupt()
        assert engine.stopped == 0

    def test_a_cancelled_letter_is_not_reported_as_finished(self) -> None:
        speaker, _, _, _, _ = build()
        speaker.letter("f")
        assert speaker.on_finished(SpeechFinished(1_000_000, "cancelled")) is False
        assert speaker.letter_finished is False

    def test_a_second_letter_supersedes_an_outstanding_one(self) -> None:
        # The worker serialises utterances, so a letter queued behind an
        # unfinished one plays after it -- over the cue and the next prompt.
        speaker, _, _, letters, _ = build()
        speaker.letter("f")
        speaker.letter("j")
        assert (letters.played, letters.stopped) == (["f", "j"], 1)

    def test_interrupt_with_nothing_audible_stops_nothing(self) -> None:
        speaker, _, engine, letters, _ = build()
        speaker.interrupt()
        assert engine.stopped == 0
        assert letters.stopped == 0


class TestLateStop:
    """alpha-plan #12c (1), from the Speaker's side: every path that stops an
    utterance which has already ended -- its SpeechFinished not yet delivered
    here -- and then queues another. The worker has cleared the flag and is
    waiting for that next utterance, which the late stop must not silence.
    Only the first path was observed on hardware (RS-22b/c); the rest follow
    from the same code.
    """

    def test_the_answer_key_does_not_silence_the_next_prompt(self) -> None:
        # SessionLoop._on_character: interrupt(), then the next prompt's letter.
        speaker, engine, commands, worker = self.letter_spoken("f")

        def answer() -> None:
            speaker.interrupt()
            speaker.letter("j")

        commands.while_waiting = answer
        worker.run_one()
        assert (engine.spoken, engine.skipped) == (["f", "j"], [])

    def test_the_re_read_is_not_itself_silenced(self) -> None:
        # Escape tapped as the letter ends: letter() stops the outstanding one
        # and plays it again. The recovery key must not be the thing that fails.
        speaker, engine, commands, worker = self.letter_spoken("f")
        commands.while_waiting = lambda: speaker.letter("f")
        worker.run_one()
        assert (engine.spoken, engine.skipped) == (["f", "f"], [])

    def test_an_announcement_over_a_finished_letter_is_spoken(self) -> None:
        # A focus change as the letter ends: announce() interrupts, then says.
        speaker, engine, commands, worker = self.letter_spoken("f")
        commands.while_waiting = lambda: speaker.announce("paused")
        worker.run_one()
        assert (engine.spoken, engine.skipped) == (["f", "paused"], [])

    def test_an_announcement_over_a_finished_line_of_a_sequence_is_spoken(self) -> None:
        # The in-flight path (worker.stop(), not the letter source): focus
        # changes as the first line of an introduction script ends.
        engine = FakeTTSEngine()
        worker = TTSWorker(lambda: engine, queue.Queue[SpeechFinished]())
        commands = install(worker)
        speaker = Speaker(worker, SyntheticLetterAudioSource(worker))
        speaker.say("New letter: F.", "Use your left index finger.")
        worker.run_one()
        commands.while_waiting = lambda: speaker.announce("paused")
        worker.run_one()
        assert (engine.spoken, engine.skipped) == (["New letter: F.", "paused"], [])

    def letter_spoken(
        self, char: str
    ) -> tuple[Speaker, FakeTTSEngine, WaitingCommandQueue, TTSWorker]:
        """A letter the worker has finished speaking, its SpeechFinished undelivered."""
        engine = FakeTTSEngine()
        worker = TTSWorker(lambda: engine, queue.Queue[SpeechFinished]())
        commands = install(worker)
        speaker = Speaker(worker, SyntheticLetterAudioSource(worker))
        speaker.letter(char)
        worker.run_one()
        return speaker, engine, commands, worker
