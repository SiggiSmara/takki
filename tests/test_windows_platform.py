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
                assert found is None or found.startswith(
                    ("HKEY_LOCAL_MACHINE", "HKEY_CURRENT_USER")
                )

    def test_an_unteachable_language_has_no_voice(self) -> None:
        if sys.platform == "win32":
            from takki.platform.windows import WindowsPlatformInterface

            assert WindowsPlatformInterface().find_voice("zz") is None


class TestVoiceTokenCategories:
    """The OneCore gap: Windows 11's "Manage voices" -- the remedy main.py
    prints on EXIT_NO_VOICE -- installs into Speech_OneCore, so reading only
    the SAPI5 key made the printed remedy useless (alpha session 12a-2)."""

    def test_every_category_windows_uses_is_read(self) -> None:
        from takki.platform.windows import VOICE_TOKEN_KEYS

        assert VOICE_TOKEN_KEYS == (
            ("HKEY_LOCAL_MACHINE", r"SOFTWARE\Microsoft\Speech\Voices\Tokens"),
            ("HKEY_CURRENT_USER", r"SOFTWARE\Microsoft\Speech\Voices\Tokens"),
            ("HKEY_LOCAL_MACHINE", r"SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens"),
            ("HKEY_CURRENT_USER", r"SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens"),
        )

    def test_an_id_names_the_hive_it_came_from(self) -> None:
        # SpObjectToken.SetId takes the full path, so the prefix has to match
        # the hive the token was enumerated under, not a hard-coded HKLM.
        if sys.platform == "win32":
            from takki.platform.windows import VOICE_TOKEN_KEYS, installed_voices

            for voice_id in installed_voices().values():
                hive, _, rest = voice_id.partition("\\")
                assert any(
                    hive == known_hive and rest.startswith(subkey)
                    for known_hive, subkey in VOICE_TOKEN_KEYS
                ), voice_id

    def test_onecore_voices_are_discovered_when_present(self) -> None:
        # Not asserting a count: a runner's installed voices are machine state.
        # What is asserted is that if Windows has a OneCore category at all, its
        # languages are candidates -- reading only SAPI5 could never satisfy it.
        if sys.platform == "win32":
            import winreg

            from takki.platform.windows import installed_voices, language_for_lcid

            try:
                tokens = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens",
                )
            except OSError:
                pytest.skip("this machine has no OneCore voice category")
            onecore_languages: set[str] = set()
            for index in range(winreg.QueryInfoKey(tokens)[0]):
                name = winreg.EnumKey(tokens, index)
                try:
                    attributes = winreg.OpenKey(tokens, name + r"\Attributes")
                    language, _ = winreg.QueryValueEx(attributes, "Language")
                except OSError:
                    continue
                code = language_for_lcid(str(language))
                if code is not None:
                    onecore_languages.add(code)
            assert onecore_languages <= set(installed_voices())
