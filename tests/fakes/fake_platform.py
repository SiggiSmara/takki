from takki.platform.layout import Layout, build_en
from tests.fakes.fake_tts import FakeTTSEngine


class FakePlatformInterface:
    def __init__(
        self,
        system_language: str = "en",
        layout: Layout | None = None,
        screen_reader: str | None = None,
    ) -> None:
        self._language = system_language
        self._layout = layout if layout is not None else build_en()
        self._screen_reader = screen_reader
        self._tts = FakeTTSEngine()

    def get_system_language(self) -> str:
        return self._language

    def get_layout_positions(self) -> Layout:
        return self._layout

    def get_fallback_tts(self) -> FakeTTSEngine:
        return self._tts

    def detect_screen_reader(self) -> str | None:
        return self._screen_reader
