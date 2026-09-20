import ctypes
import ctypes.wintypes
import logging
import subprocess
import sys

from takki.audio.tts import TTSEngine
from takki.platform.layout import Layout

logger = logging.getLogger(__name__)

_SPI_GETSCREENREADER = 0x0046
_LOCALE_NAME_MAX_LENGTH = 85


def primary_subtag(locale_name: str) -> str:
    # Windows locale names are BCP-47: the primary language subtag is always
    # the first "-"-separated component (not "_", which DevStubInterface's
    # $LANG parsing uses). "en-150"'s "150" is a numeric UN region subtag,
    # not a country code -- there is no second component to strip separately,
    # splitting on "-" already isolates the primary subtag.
    #
    # Module level (not nested in a method), like pynput_stream.translate(),
    # so tests can exercise the parsing directly without a live Windows call.
    primary = locale_name.split("-")[0].lower()
    return primary or "en"


def nvda_in_tasklist_output(output: str) -> bool:
    return "nvda.exe" in output.lower()


def _nvda_running() -> bool:
    # CREATE_NO_WINDOW because tasklist.exe is a console-subsystem binary: run
    # from a windowed process (the PyInstaller bundle, Beta) it pops a console
    # that takes the foreground. In an app whose entire input model is gated on
    # holding foreground (ADR-028), a self-inflicted focus thief at startup
    # would read as a pause the child did not cause. Harmless today only
    # because detect_screen_reader() has no consumer yet (roadmap § D).
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq nvda.exe", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=flags,
        )
    except (OSError, subprocess.SubprocessError):
        # SubprocessError, not just OSError -- covers TimeoutExpired if
        # tasklist ever hangs, which is not an OSError subclass.
        return False
    return nvda_in_tasklist_output(result.stdout)


class WindowsPlatformInterface:
    def get_system_language(self) -> str:
        if sys.platform == "win32":
            buf = ctypes.create_unicode_buffer(_LOCALE_NAME_MAX_LENGTH)
            written = ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, _LOCALE_NAME_MAX_LENGTH)
            # Checked rather than discarded, to match detect_screen_reader's
            # handling of SystemParametersInfoW below. primary_subtag() would
            # turn a failure's empty buffer into a plausible-looking "en",
            # which is the wrong answer everywhere except by luck.
            if not written:
                logger.warning("GetUserDefaultLocaleName failed; falling back to 'en'")
            return primary_subtag(buf.value)
        raise NotImplementedError("WindowsPlatformInterface requires Windows")

    def get_layout_positions(self) -> Layout:
        raise NotImplementedError("session 12")

    def get_fallback_tts(self) -> TTSEngine:
        raise NotImplementedError("session 12")

    def detect_screen_reader(self) -> str | None:
        if sys.platform == "win32":
            # NVDA does not set SPI_GETSCREENREADER by default (ADR-026), so
            # identity comes from the process scan; the flag is only used to
            # log the "a reader is active but unrecognised" case, since Alpha
            # has no consumer for any reader but NVDA.
            if _nvda_running():
                return "nvda"
            flag = ctypes.wintypes.BOOL()
            ok = ctypes.windll.user32.SystemParametersInfoW(
                _SPI_GETSCREENREADER, 0, ctypes.byref(flag), 0
            )
            if not ok:
                logger.warning("SystemParametersInfoW(SPI_GETSCREENREADER) failed")
            elif flag.value:
                logger.info(
                    "SPI_GETSCREENREADER reports an active screen reader, "
                    "but no known reader process was found"
                )
            return None
        raise NotImplementedError("WindowsPlatformInterface requires Windows")
