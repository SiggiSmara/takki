from collections.abc import Callable

from takki.platform.layout import Layout, build_en
from tests.fakes.fake_tts import FakeTTSEngine


class FakePlatformInterface:
    def __init__(
        self,
        system_language: str = "en",
        layout: Layout | None = None,
        screen_reader: str | None = None,
        voices: dict[str, str] | None = None,
    ) -> None:
        self._language = system_language
        self._layout = layout if layout is not None else build_en()
        self._screen_reader = screen_reader
        self._voices = voices if voices is not None else {"en": "fake-en", "de": "fake-de"}
        self._tts = FakeTTSEngine()
        # Every voice id get_fallback_tts() was asked to build with, so a test
        # can assert the verified id actually reached the engine (ADR-003).
        self.fallback_voice_ids: list[str] = []

    def get_system_language(self) -> str:
        return self._language

    def get_layout_positions(self) -> Layout:
        return self._layout

    def find_voice(self, language: str) -> str | None:
        return self._voices.get(language)

    def get_fallback_tts(self, voice_id: str) -> Callable[[], FakeTTSEngine]:
        self.fallback_voice_ids.append(voice_id)
        return lambda: self._tts

    def detect_screen_reader(self) -> str | None:
        return self._screen_reader
