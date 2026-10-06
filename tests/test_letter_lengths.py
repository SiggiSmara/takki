from takki import config
from takki.lesson.letter_lengths import LetterLengths
from tests.fakes.fake_store import FakeStore

VOICE = "voice"


def build(store: FakeStore | None = None, voice: str = VOICE, rate: float = config.TTS_RATE):
    store = store or FakeStore()
    profiles = store.list_profiles()
    profile = profiles[0] if profiles else store.create_profile("Alice")
    return LetterLengths(store, profile.id, voice, rate), store, profile.id


class TestUsualLength:
    def test_a_letter_with_no_full_playback_has_no_length(self) -> None:
        lengths, _, _ = build()
        lengths.record("j", 500)
        assert lengths.usual("f") is None

    def test_it_is_the_median_over_the_letters_full_playbacks(self) -> None:
        lengths, _, _ = build()
        for ms in (400, 900, 500):
            lengths.record("f", ms)
        assert lengths.usual("f") == 500

    def test_a_zero_length_is_a_length(self) -> None:
        # What a fake clock that nobody advanced measures. The loop asks
        # "is there one", and zero must not read as no.
        lengths, _, _ = build()
        lengths.record("f", 0)
        assert lengths.usual("f") == 0

    def test_only_the_latest_sample_counts(self) -> None:
        lengths, _, _ = build()
        for ms in [100] * config.LETTER_LENGTH_SAMPLE + [900] * config.LETTER_LENGTH_SAMPLE:
            lengths.record("f", ms)
        assert lengths.usual("f") == 900


class TestAcrossSessions:
    def test_an_earlier_sessions_playbacks_count_with_todays(self) -> None:
        # The case alpha-plan #12l is for: a letter introduced on another day
        # and answered early ever since has a length on its first press today.
        first, store, _ = build()
        first.record("f", 400)
        first.record("f", 500)
        first.flush()
        second, _, _ = build(store)
        assert second.usual("f") == 450
        second.record("f", 900)
        assert second.usual("f") == 500

    def test_nothing_is_stored_until_the_flush_and_nothing_twice(self) -> None:
        lengths, store, profile_id = build()
        lengths.record("f", 400)
        assert store.letter_lengths(profile_id, "f", VOICE, config.TTS_RATE) == []
        lengths.flush()
        lengths.flush()
        assert store.letter_lengths(profile_id, "f", VOICE, config.TTS_RATE) == [400]

    def test_another_voice_starts_with_no_lengths(self) -> None:
        first, store, _ = build()
        first.record("f", 400)
        first.flush()
        assert build(store, voice="other")[0].usual("f") is None

    def test_another_rate_starts_with_no_lengths(self) -> None:
        first, store, _ = build()
        first.record("f", 400)
        first.flush()
        assert build(store, rate=1.2)[0].usual("f") is None

    def test_the_first_voice_keeps_its_lengths_for_a_return_to_it(self) -> None:
        first, store, _ = build()
        first.record("f", 400)
        first.flush()
        other, _, _ = build(store, voice="other")
        other.record("f", 900)
        other.flush()
        assert build(store)[0].usual("f") == 400

    def test_the_store_is_read_once_per_letter(self) -> None:
        reads: list[str] = []

        class CountingStore(FakeStore):
            def letter_lengths(
                self, profile_id: int, key_char: str, voice: str, rate: float
            ) -> list[int]:
                reads.append(key_char)
                return super().letter_lengths(profile_id, key_char, voice, rate)

        lengths, _, _ = build(CountingStore())
        for letter in ("f", "j", "f"):
            lengths.usual(letter)
            lengths.record(letter, 400)
        assert reads == ["f", "j"]
