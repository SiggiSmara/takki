import locale
import logging
import os

from takki.audio.fallback_tts import FallbackTTS
from takki.audio.tts import TTSEngine
from takki.platform.layout import Layout, build_en

logger = logging.getLogger(__name__)


class DevStubInterface:
    def __init__(self) -> None:
        logger.warning(
            "DevStubInterface active — platform detection is stubbed. Not suitable for production."
        )

    def get_system_language(self) -> str:
        lang_env = os.environ.get("LANG", "")
        if lang_env:
            primary = lang_env.split("_")[0].split(".")[0].lower()
            if primary and primary not in ("c", "posix"):
                return primary
        loc = locale.getlocale()[0]
        if loc:
            primary = loc.split("_")[0].lower()
            if primary and primary not in ("c", "posix"):
                return primary
        return "en"

    def get_layout_positions(self) -> Layout:
        return build_en()

    def get_fallback_tts(self) -> TTSEngine:
        return FallbackTTS()

    def detect_screen_reader(self) -> str | None:
        return None
