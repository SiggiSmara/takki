import queue
import signal
import sqlite3
import time
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path

import pytest

from takki.audio.cues import CueOutputError
from takki.audio.tts import SpeechOutputError
from takki.main import (
    EXIT_LAYOUT_MISMATCH,
    EXIT_NO_AUDIO,
    EXIT_NO_VOICE,
    main,
    resolve_language,
    verify_layout,
)
from takki.persistence.sqlite_store import SqliteStore
from takki.platform.layout import build_de, build_en, build_is, describe_mismatch
from takki.session import InboundEvent
from tests.fakes.fake_focus_source import FakeFocusSource
from tests.fakes.fake_platform import FakePlatformInterface
from tests.fakes.fake_sound_cues import FakeSoundCues
from tests.fakes.scripted_key_stream import ScriptedKeyStream


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


class TestNoAudioOutput:
    """A4c: with no output device, startup stops with EXIT_NO_AUDIO and the remedy, not a traceback."""

    REMEDY = (
        "Check that speakers or headphones are connected and selected as the "
        "Windows sound output, then start Takki again.\n"
    )

    @pytest.fixture
    def platform(self, monkeypatch: pytest.MonkeyPatch) -> FakePlatformInterface:
        platform = FakePlatformInterface()
        monkeypatch.setattr("takki.main.config.LANGUAGE", "en")
        monkeypatch.setattr("takki.main.select_platform_interface", lambda: platform)

        # No window: startup stops before the focus source is used.
        def no_window(inbound: object) -> None:
            return None

        monkeypatch.setattr("takki.main.PygameFocusSource", no_window)
        return platform

    def test_the_mixer_failing_exits_no_audio(
        self,
        platform: FakePlatformInterface,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        def no_device() -> None:
            raise CueOutputError("the sound cues cannot play (no endpoint)")

        monkeypatch.setattr("takki.main.PygameMixerCues", no_device)
        assert main() == EXIT_NO_AUDIO
        assert capsys.readouterr().err == (
            "Takki cannot start: the sound cues cannot play (no endpoint).\n" + self.REMEDY
        )

    def test_the_voice_failing_exits_no_audio(
        self,
        platform: FakePlatformInterface,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        def mute() -> None:
            raise SpeechOutputError("the voice cannot play any sound (no endpoint)")

        monkeypatch.setattr("takki.main.PygameMixerCues", lambda: None)

        def mute_factory(voice_id: str) -> Callable[[], None]:
            return mute

        monkeypatch.setattr(platform, "get_fallback_tts", mute_factory)
        assert main() == EXIT_NO_AUDIO
        assert capsys.readouterr().err == (
            "Takki cannot start: the voice cannot play any sound (no endpoint).\n" + self.REMEDY
        )


class TestStartup:
    """The wiring: `main()` from an empty data directory to its first words and out again."""

    @pytest.fixture
    def signals(self) -> Iterator[None]:
        # main() installs its own handlers, and pytest's must come back.
        kept = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}
        yield
        for number, handler in kept.items():
            signal.signal(number, handler)

    def test_the_wrong_keyboard_stops_before_anything_is_built(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr("takki.main.config.LANGUAGE", "en")
        monkeypatch.setattr(
            "takki.main.select_platform_interface",
            lambda: FakePlatformInterface(layout=build_de()),
        )
        assert main() == EXIT_LAYOUT_MISMATCH
        assert capsys.readouterr().err.startswith("Takki cannot start: ")

    def test_a_language_with_no_voice_stops_before_anything_is_built(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr("takki.main.config.LANGUAGE", None)
        monkeypatch.setattr(
            "takki.main.select_platform_interface",
            lambda: FakePlatformInterface(system_language="is", layout=build_is()),
        )
        assert main() == EXIT_NO_VOICE
        assert capsys.readouterr().err.startswith(
            "Takki cannot start: no text-to-speech voice is installed for 'is'.\n"
        )

    def test_a_cold_start_introduces_the_first_keys_and_ends_cleanly(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, signals: None
    ) -> None:
        # Everything main() builds is real except the four things that need a
        # machine: the window, the mixer, the voice and the keyboard hook.
        platform = FakePlatformInterface()
        engine = platform.get_fallback_tts("fake-en")()
        platform.fallback_voice_ids.clear()
        database = tmp_path / "data" / "takki.sqlite"

        class Window(FakeFocusSource):
            def __init__(self, inbound: queue.Queue[InboundEvent]) -> None:
                super().__init__(inbound)
                self.gain_focus()

        class Keys(ScriptedKeyStream):
            joined = False

            def __init__(self, inbound: queue.Queue[InboundEvent]) -> None:
                super().__init__([], inbound)

            def join(self, timeout: float) -> None:
                Keys.joined = True

        class Frames:
            waits = 0

            def wait(self) -> None:
                # The pair's two scripts are three utterances each. SIGINT is
                # how a session ends, so the handler is under test as well.
                Frames.waits += 1
                time.sleep(0.001)
                if len(engine.spoken) >= 6 or Frames.waits > 5000:
                    signal.raise_signal(signal.SIGINT)

        monkeypatch.setattr("takki.main.config.LANGUAGE", "en")
        monkeypatch.setattr("takki.main.select_platform_interface", lambda: platform)
        monkeypatch.setattr("takki.main.PygameFocusSource", Window)
        monkeypatch.setattr("takki.main.PygameMixerCues", FakeSoundCues)
        monkeypatch.setattr("takki.main.PynputKeyStream", Keys)
        monkeypatch.setattr("takki.main.SleepFrameLimiter", Frames)
        monkeypatch.setattr("takki.main.database_path", lambda: database)
        closed: list[bool] = []
        close = SqliteStore.close

        def recording_close(store: SqliteStore) -> None:
            closed.append(True)
            close(store)

        monkeypatch.setattr(SqliteStore, "close", recording_close)

        assert main() == 0
        assert engine.spoken[:6] == [
            "New letter:",
            "f",
            "Use your left index finger.",
            "New letter:",
            "j",
            "Use your right index finger. Reach three positions to the right from F.",
        ]
        assert platform.fallback_voice_ids == ["fake-en"]
        assert Keys.joined
        # Closed, so the one file is the whole profile (ADR-011): no WAL beside it.
        assert closed == [True]
        assert [path.name for path in database.parent.iterdir()] == ["takki.sqlite"]

        store = SqliteStore(str(database))
        (profile,) = store.list_profiles()
        assert (profile.name, profile.language) == ("dev", "en")
        introduced = [(row.key_char, row.step) for row in store.introductions(profile.id)]
        assert introduced == [("f", 1), ("j", 1)]
        with sqlite3.connect(database) as connection:
            sessions = connection.execute("SELECT ended_at IS NOT NULL FROM sessions").fetchall()
        assert sessions == [(1,)]
