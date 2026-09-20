import sys
from typing import Protocol

from takki.audio.tts import TTSEngine
from takki.platform.dev_stub import DevStubInterface
from takki.platform.layout import Layout


class PlatformInterface(Protocol):
    def get_system_language(self) -> str: ...

    def find_voice(self, language: str) -> str | None:
        """The TTS voice id for this language, or None when none is installed.

        The fifth function, added 2026-09-20 (ADR-026). It answers a question
        about the *platform* -- what can this machine speak -- rather than
        handing back an object, and it has to answer during startup before any
        audio object exists, because a missing voice is a graceful stop and
        not something to discover mid-lesson.
        """
        ...

    def get_layout_positions(self) -> Layout: ...

    def get_fallback_tts(self) -> TTSEngine: ...

    def detect_screen_reader(self) -> str | None: ...


def select_platform_interface() -> PlatformInterface:
    if sys.platform == "win32":
        from takki.platform.windows import WindowsPlatformInterface

        return WindowsPlatformInterface()
    return DevStubInterface()
