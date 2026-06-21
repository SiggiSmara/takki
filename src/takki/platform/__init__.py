import sys
from typing import Protocol

from takki.audio.tts import TTSEngine
from takki.platform.dev_stub import DevStubInterface
from takki.platform.layout import Layout


class PlatformInterface(Protocol):
    def get_system_language(self) -> str: ...

    def get_layout_positions(self) -> Layout: ...

    def get_fallback_tts(self) -> TTSEngine: ...

    def detect_screen_reader(self) -> str | None: ...


def select_platform_interface() -> PlatformInterface:
    if sys.platform == "win32":
        from takki.platform.windows import WindowsPlatformInterface

        return WindowsPlatformInterface()
    return DevStubInterface()
