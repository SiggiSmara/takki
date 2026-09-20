from dataclasses import replace

import pytest

from takki.main import (
    EXIT_LAYOUT_MISMATCH,
    EXIT_NO_VOICE,
    resolve_language,
    verify_layout,
)
from takki.platform.layout import build_de, build_en, build_is, describe_mismatch
from tests.fakes.fake_platform import FakePlatformInterface


class TestResolveLanguage:
    def test_falls_back_to_the_platform_locale(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("takki.main.config.LANGUAGE", None)
        assert resolve_language(FakePlatformInterface(system_language="de")) == "de"

    def test_config_wins_over_the_locale(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The multi-layout machine: the locale says one thing, the parent has
        # pinned the curriculum to another.
        monkeypatch.setattr("takki.main.config.LANGUAGE", "en")
        assert resolve_language(FakePlatformInterface(system_language="de")) == "en"


class TestVerifyLayout:
    def test_matching_language_and_layout_pass(self) -> None:
        assert verify_layout("en", build_en()) is None
        assert verify_layout("de", build_de()) is None
        assert verify_layout("is", build_is()) is None

    def test_wrong_keyboard_is_reported(self) -> None:
        mismatch = verify_layout("en", build_de())
        assert mismatch is not None
        assert "en" in mismatch and "de" in mismatch

    def test_an_unteachable_language_is_reported(self) -> None:
        # A locale Alpha has no layout table for -- reported, not crashed on.
        mismatch = verify_layout("fr", build_en())
        assert mismatch is not None
        assert "fr" in mismatch

    def test_mismatch_exit_code_is_not_success(self) -> None:
        assert EXIT_LAYOUT_MISMATCH != 0


class TestDescribeMismatch:
    def test_identical_layouts_match(self) -> None:
        assert describe_mismatch(build_en(), build_en()) is None

    def test_a_relabelled_layout_is_still_caught_by_position(self) -> None:
        # The language tags agree, so only the key positions can give it away.
        # This is the path that matters if #12a-1's reader labels a machine-read
        # layout with the system locale rather than the keyboard's own
        # language -- the check must not depend on getting that label right.
        disguised = replace(build_de(), lang="en")
        mismatch = describe_mismatch(build_en(), disguised)
        assert mismatch is not None
        assert "unexpected" in mismatch or "moved" in mismatch

    def test_y_and_z_swapping_is_a_mismatch(self) -> None:
        # QWERTY vs QWERTZ differ on exactly these two letters, and a swap is
        # the quietest possible corruption: every key still exists.
        swapped = build_en()
        y, z = swapped.keys["y"], swapped.keys["z"]
        swapped.keys["y"] = replace(y, row=z.row, col=z.col)
        swapped.keys["z"] = replace(z, row=y.row, col=y.col)
        mismatch = describe_mismatch(build_en(), swapped)
        assert mismatch is not None
        assert "moved" in mismatch

    def test_extra_letters_are_named(self) -> None:
        relabelled = replace(build_de(), lang="en")
        mismatch = describe_mismatch(build_en(), relabelled)
        assert mismatch is not None
        assert "unexpected" in mismatch


class TestVoiceAvailability:
    """ADR-003 § SAPI fallback voice selection: a missing voice is a graceful stop."""

    def test_a_language_with_a_voice_resolves(self) -> None:
        assert FakePlatformInterface().find_voice("en") == "fake-en"

    def test_a_language_with_no_voice_resolves_to_none(self) -> None:
        # Icelandic on the test laptop: SAPI ships no voice for it, and the
        # letter-pronunciation research records that no Windows one exists.
        assert FakePlatformInterface().find_voice("is") is None

    def test_exit_codes_are_distinct_and_non_zero(self) -> None:
        # A script driving Takki must be able to tell "wrong keyboard" from
        # "no voice" -- the two have different remedies.
        assert EXIT_NO_VOICE != 0
        assert EXIT_NO_VOICE != EXIT_LAYOUT_MISMATCH
