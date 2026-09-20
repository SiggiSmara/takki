import subprocess
import sys
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.windows_only


def test_get_system_language_returns_lowercase_primary_subtag() -> None:
    if sys.platform == "win32":
        from takki.platform.windows import WindowsPlatformInterface

        lang = WindowsPlatformInterface().get_system_language()
        assert lang == lang.lower()
        assert "-" not in lang
        assert lang != ""


def test_detect_screen_reader_returns_str_or_none() -> None:
    if sys.platform == "win32":
        from takki.platform.windows import WindowsPlatformInterface

        result = WindowsPlatformInterface().detect_screen_reader()
        assert result is None or isinstance(result, str)


def test_detect_screen_reader_survives_a_hung_tasklist() -> None:
    # tasklist's TimeoutExpired is a SubprocessError, not an OSError -- a
    # narrower except clause here would let it crash startup instead of
    # degrading to "no screen reader detected".
    if sys.platform == "win32":
        from takki.platform.windows import WindowsPlatformInterface

        with patch(
            "subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="tasklist", timeout=5)
        ):
            assert WindowsPlatformInterface().detect_screen_reader() is None


class TestLanguageForLcid:
    """ADR-003: SAPI records a voice's language as a hex LCID."""

    @pytest.mark.parametrize(
        ("lcid", "expected"),
        [("409", "en"), ("809", "en"), ("407", "de"), ("40F", "is"), ("40f", "is")],
    )
    def test_regional_variants_collapse_to_the_primary_language(
        self, lcid: str, expected: str
    ) -> None:
        # 0x409 en-US and 0x809 en-GB are both "en": the primary language is
        # the low 10 bits, and Takki's curriculum is per-language, not
        # per-region.
        if sys.platform == "win32":
            from takki.platform.windows import language_for_lcid

            assert language_for_lcid(lcid) == expected

    def test_a_multi_language_voice_takes_its_first_lcid(self) -> None:
        if sys.platform == "win32":
            from takki.platform.windows import language_for_lcid

            assert language_for_lcid("409;9") == "en"

    def test_unteachable_and_malformed_values_are_not_candidates(self) -> None:
        # French is a real LCID Takki has no curriculum for; the other two are
        # third-party registry data, so they return None rather than raising.
        if sys.platform == "win32":
            from takki.platform.windows import language_for_lcid

            assert language_for_lcid("40C") is None
            assert language_for_lcid("") is None
            assert language_for_lcid("not-hex") is None


class TestFindVoice:
    def test_find_voice_returns_an_id_or_none(self) -> None:
        if sys.platform == "win32":
            from takki.platform.windows import WindowsPlatformInterface

            # Whatever this machine has, the contract holds: a usable id or a
            # clean None. Not asserting a specific voice -- that is machine
            # state, and the runner's installed voices are not ours to fix.
            for language in ("en", "de", "is"):
                found = WindowsPlatformInterface().find_voice(language)
                assert found is None or found.startswith("HKEY_LOCAL_MACHINE")

    def test_an_unteachable_language_has_no_voice(self) -> None:
        if sys.platform == "win32":
            from takki.platform.windows import WindowsPlatformInterface

            assert WindowsPlatformInterface().find_voice("zz") is None
