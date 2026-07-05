from takki.audio.letters import LetterAudioSource
from tests.fakes.fake_letters import FakeLetterAudioSource

# Static structural conformance — pyright fails if the fake drifts from the Protocol.
_conforms: LetterAudioSource = FakeLetterAudioSource()


class TestFakeLetterAudioSource:
    def test_play_records_char(self) -> None:
        src = FakeLetterAudioSource()
        src.play("a")
        src.play("ä")
        assert src.played == ["a", "ä"]

    def test_stop_increments_counter(self) -> None:
        src = FakeLetterAudioSource()
        src.stop()
        src.stop()
        assert src.stopped == 2

    def test_initial_state(self) -> None:
        src = FakeLetterAudioSource()
        assert src.played == []
        assert src.stopped == 0
