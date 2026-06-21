from takki.audio.tts import TTSEngine
from takki.platform.layout import Layout


class WindowsPlatformInterface:
    def get_system_language(self) -> str:
        raise NotImplementedError("session 12")

    def get_layout_positions(self) -> Layout:
        raise NotImplementedError("session 12")

    def get_fallback_tts(self) -> TTSEngine:
        raise NotImplementedError("session 12")

    def detect_screen_reader(self) -> str | None:
        raise NotImplementedError("session 12")
