import sys
from unittest.mock import patch

import pytest

from takki.platform import select_platform_interface
from takki.platform.dev_stub import DevStubInterface
from takki.platform.layout import COL_TO_FINGER, Layout, PhysicalKey, build_en
from tests.fakes.fake_platform import FakePlatformInterface
from tests.fakes.fake_tts import FakeTTSEngine


class TestCOLToFinger:
    def test_left_columns(self) -> None:
        assert COL_TO_FINGER[1] == "L-pink"
        assert COL_TO_FINGER[2] == "L-ring"
        assert COL_TO_FINGER[3] == "L-mid"
        assert COL_TO_FINGER[4] == "L-idx"
        assert COL_TO_FINGER[5] == "L-idx"

    def test_right_columns(self) -> None:
        assert COL_TO_FINGER[6] == "R-idx"
        assert COL_TO_FINGER[7] == "R-idx"
        assert COL_TO_FINGER[8] == "R-mid"
        assert COL_TO_FINGER[9] == "R-ring"
        assert COL_TO_FINGER[10] == "R-pink"
        assert COL_TO_FINGER[11] == "R-pink"
        assert COL_TO_FINGER[12] == "R-pink"
        assert COL_TO_FINGER[13] == "R-pink"


class TestPhysicalKey:
    def test_finger_left_index_home(self) -> None:
        assert PhysicalKey("f", 3, 4).finger == "L-idx"

    def test_finger_right_index_home(self) -> None:
        assert PhysicalKey("j", 3, 7).finger == "R-idx"

    def test_finger_left_pinky(self) -> None:
        assert PhysicalKey("a", 3, 1).finger == "L-pink"

    def test_side_left(self) -> None:
        assert PhysicalKey("a", 3, 1).side == "L"
        assert PhysicalKey("g", 3, 5).side == "L"

    def test_side_right(self) -> None:
        assert PhysicalKey("h", 3, 6).side == "R"
        assert PhysicalKey("j", 3, 7).side == "R"

    def test_frozen(self) -> None:
        pk = PhysicalKey("a", 3, 1)
        with pytest.raises(Exception):
            pk.name = "b"  # type: ignore[misc]


class TestLayout:
    def test_build_en_lang(self) -> None:
        assert build_en().lang == "en"

    def test_build_en_has_all_26_letters(self) -> None:
        layout = build_en()
        for ch in "abcdefghijklmnopqrstuvwxyz":
            assert ch in layout.keys, f"missing key '{ch}'"
            assert ch in layout.graphemes, f"missing grapheme '{ch}'"

    def test_home_row_row_3(self) -> None:
        layout = build_en()
        for ch in "asdfghjkl":
            assert layout.keys[ch].row == 3

    def test_top_row_row_2(self) -> None:
        layout = build_en()
        for ch in "qwertyuiop":
            assert layout.keys[ch].row == 2

    def test_bottom_row_row_4(self) -> None:
        layout = build_en()
        for ch in "zxcvbnm":
            assert layout.keys[ch].row == 4

    def test_direct_grapheme_fields(self) -> None:
        g = build_en().graphemes["a"]
        assert g.mechanism == "direct"
        assert g.prereq_keys == ("a",)
        assert g.keystrokes == 1
        assert g.base is None
        assert g.dead_key is None

    def test_layout_type(self) -> None:
        assert isinstance(build_en(), Layout)

    def test_f_key_position(self) -> None:
        pk = build_en().keys["f"]
        assert pk.row == 3 and pk.col == 4 and pk.finger == "L-idx"

    def test_j_key_position(self) -> None:
        pk = build_en().keys["j"]
        assert pk.row == 3 and pk.col == 7 and pk.finger == "R-idx"


class TestDevStubInterface:
    def test_get_layout_positions_returns_en_layout(self) -> None:
        stub = DevStubInterface()
        layout = stub.get_layout_positions()
        assert layout.lang == "en"
        assert "f" in layout.keys and "j" in layout.keys

    def test_detect_screen_reader_is_none(self) -> None:
        assert DevStubInterface().detect_screen_reader() is None

    def test_get_fallback_tts_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError, match="session 4"):
            DevStubInterface().get_fallback_tts()

    def test_get_system_language_from_lang_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LANG", "de_DE.UTF-8")
        assert DevStubInterface().get_system_language() == "de"

    def test_get_system_language_lang_primary_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LANG", "fi")
        assert DevStubInterface().get_system_language() == "fi"

    def test_get_system_language_strips_encoding(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LANG", "en.UTF-8")
        assert DevStubInterface().get_system_language() == "en"

    def test_get_system_language_from_locale_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("LANG", raising=False)
        with patch("locale.getlocale", return_value=("fr_FR", "UTF-8")):
            assert DevStubInterface().get_system_language() == "fr"

    def test_get_system_language_default_en(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LANG", raising=False)
        with patch("locale.getlocale", return_value=(None, None)):
            assert DevStubInterface().get_system_language() == "en"

    def test_get_system_language_c_locale_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LANG", "C")
        with patch("locale.getlocale", return_value=(None, None)):
            assert DevStubInterface().get_system_language() == "en"


class TestFakePlatformInterface:
    def test_default_language(self) -> None:
        assert FakePlatformInterface().get_system_language() == "en"

    def test_default_layout_is_en(self) -> None:
        assert FakePlatformInterface().get_layout_positions().lang == "en"

    def test_default_screen_reader_none(self) -> None:
        assert FakePlatformInterface().detect_screen_reader() is None

    def test_override_language(self) -> None:
        assert FakePlatformInterface(system_language="de").get_system_language() == "de"

    def test_override_layout(self) -> None:
        custom = build_en()
        fake = FakePlatformInterface(layout=custom)
        assert fake.get_layout_positions() is custom

    def test_override_screen_reader(self) -> None:
        assert FakePlatformInterface(screen_reader="nvda").detect_screen_reader() == "nvda"

    def test_get_fallback_tts_returns_fake_tts(self) -> None:
        tts = FakePlatformInterface().get_fallback_tts()
        assert isinstance(tts, FakeTTSEngine)

    def test_get_fallback_tts_returns_same_instance(self) -> None:
        fake = FakePlatformInterface()
        assert fake.get_fallback_tts() is fake.get_fallback_tts()


class TestFakeTTSEngine:
    def test_speak_records_text(self) -> None:
        tts = FakeTTSEngine()
        tts.speak("hello")
        tts.speak("world")
        assert tts.spoken == ["hello", "world"]

    def test_stop_increments_counter(self) -> None:
        tts = FakeTTSEngine()
        tts.stop()
        tts.stop()
        assert tts.stopped == 2

    def test_initial_state(self) -> None:
        tts = FakeTTSEngine()
        assert tts.spoken == []
        assert tts.stopped == 0


class TestSelectPlatformInterface:
    def test_returns_dev_stub_off_win32(self) -> None:
        if sys.platform == "win32":
            pytest.skip("test is for non-win32 platforms")
        iface = select_platform_interface()
        assert isinstance(iface, DevStubInterface)

    def test_returns_windows_interface_on_win32(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from takki.platform.windows import WindowsPlatformInterface

        monkeypatch.setattr(sys, "platform", "win32")
        iface = select_platform_interface()
        assert isinstance(iface, WindowsPlatformInterface)
