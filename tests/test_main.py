import pytest

from takki.main import resolve_language, resolve_layout
from tests.fakes.fake_platform import FakePlatformInterface


class TestResolveLanguage:
    def test_no_override_uses_platform(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TAKKI_LANG", raising=False)
        assert resolve_language(FakePlatformInterface(system_language="de")) == "de"

    def test_override_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAKKI_LANG", "en")
        assert resolve_language(FakePlatformInterface(system_language="de")) == "en"

    def test_empty_override_falls_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAKKI_LANG", "")
        assert resolve_language(FakePlatformInterface(system_language="de")) == "de"


class TestResolveLayout:
    def test_no_override_uses_platform(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TAKKI_LAYOUT", raising=False)
        platform = FakePlatformInterface()
        assert resolve_layout(platform) is platform.get_layout_positions()

    def test_override_en(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAKKI_LAYOUT", "en")
        assert resolve_layout(FakePlatformInterface()).lang == "en"

    def test_override_de(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAKKI_LAYOUT", "de")
        assert resolve_layout(FakePlatformInterface()).lang == "de"

    def test_override_is(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAKKI_LAYOUT", "is")
        assert resolve_layout(FakePlatformInterface()).lang == "is"

    def test_empty_override_falls_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Consistent with resolve_language: an empty value is "no override",
        # not an invalid one -- a launcher that does TAKKI_LAYOUT=${X:-} must
        # not crash on startup.
        monkeypatch.setenv("TAKKI_LAYOUT", "")
        platform = FakePlatformInterface()
        assert resolve_layout(platform) is platform.get_layout_positions()

    def test_unknown_override_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAKKI_LAYOUT", "fr")
        with pytest.raises(ValueError, match="TAKKI_LAYOUT"):
            resolve_layout(FakePlatformInterface())
