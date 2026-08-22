import pytest

from takki.audio.cues import SoundCuePlayer
from takki.audio.pygame_cues import CLASS_CHANNEL, CUE_CLASS, PygameMixerCues
from tests.fakes.fake_sound_cues import FakeSoundCues

# Static structural conformance — pyright fails if either impl drifts from the Protocol.
_conforms_fake: SoundCuePlayer = FakeSoundCues()


class TestFakeSoundCues:
    def test_play_records_linear_sequence(self) -> None:
        cues = FakeSoundCues()
        cues.play("correct")
        cues.play("chirp_on")
        cues.play("error")
        assert cues.played == ["correct", "chirp_on", "error"]

    def test_initial_state(self) -> None:
        assert FakeSoundCues().played == []

    def test_replacement_within_a_class_is_visible_as_two_entries(self) -> None:
        # The fake records every call -- per-class replacement is a pygame
        # Channel behaviour, asserted against the real PygameMixerCues below.
        cues = FakeSoundCues()
        cues.play("correct")
        cues.play("error")
        assert cues.played == ["correct", "error"]


class TestCueClassMap:
    def test_all_five_cues_have_a_class(self) -> None:
        assert set(CUE_CLASS) == {"correct", "error", "boundary", "chirp_on", "chirp_off"}

    def test_keypress_cues_share_a_class(self) -> None:
        assert CUE_CLASS["correct"] == CUE_CLASS["error"] == CUE_CLASS["boundary"]

    def test_ptt_cues_share_a_class(self) -> None:
        assert CUE_CLASS["chirp_on"] == CUE_CLASS["chirp_off"]

    def test_keypress_and_ptt_are_different_classes(self) -> None:
        assert CUE_CLASS["correct"] != CUE_CLASS["chirp_on"]

    def test_every_class_has_a_reserved_channel(self) -> None:
        assert set(CUE_CLASS.values()) <= set(CLASS_CHANNEL)

    def test_channels_are_distinct(self) -> None:
        assert len(set(CLASS_CHANNEL.values())) == len(CLASS_CHANNEL)


@pytest.mark.audio
class TestPygameMixerCues:
    def test_conforms_to_protocol(self) -> None:
        cues: SoundCuePlayer = PygameMixerCues()
        assert cues is not None

    def test_play_each_cue_does_not_raise(self) -> None:
        cues = PygameMixerCues()
        for name in CUE_CLASS:
            cues.play(name)

    def test_newest_wins_within_a_class(self) -> None:
        import pygame

        cues = PygameMixerCues()
        cues.play("correct")
        first_sound = pygame.mixer.Channel(0).get_sound()
        cues.play("error")
        second_sound = pygame.mixer.Channel(0).get_sound()
        assert first_sound is not second_sound

    def test_classes_use_different_channels(self) -> None:
        import pygame

        cues = PygameMixerCues()
        cues.play("correct")
        cues.play("chirp_on")
        assert pygame.mixer.Channel(0).get_sound() is not pygame.mixer.Channel(1).get_sound()
