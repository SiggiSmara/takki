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


# SAPI voice tokens record their language as a hex LCID; the primary language
# is the low 10 bits, so every regional variant of a language collapses onto
# one entry (0x409 en-US and 0x809 en-GB are both "en"). Only the languages
# Takki teaches are listed -- an unlisted voice is simply not a candidate.
_PRIMARY_LANGID: dict[int, str] = {0x09: "en", 0x07: "de", 0x0F: "is"}

_VOICE_TOKENS = "SOFTWARE\\Microsoft\\Speech\\Voices\\Tokens"
_VOICE_ID_PREFIX = "HKEY_LOCAL_MACHINE\\" + _VOICE_TOKENS


def language_for_lcid(value: str) -> str | None:
    """Map a SAPI token's `Language` attribute to a Takki language code."""
    # Multi-language voices list several LCIDs separated by ";"; the first is
    # the primary one. A malformed value is not a candidate rather than an
    # error -- this is a third-party registry key, not our data.
    head = value.split(";")[0].strip()
    try:
        lcid = int(head, 16)
    except ValueError:
        return None
    return _PRIMARY_LANGID.get(lcid & 0x3FF)


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


def _installed_voices() -> dict[str, str]:
    """Language code → SAPI voice id, read straight from the registry.

    No COM and no pyttsx3 engine, which is the point: the engine can only be
    built on the TTS worker thread (concurrency-model.md § TTS), and this has
    to answer before any thread or audio object exists. The ids it returns are
    exactly the strings `pyttsx3`'s `setProperty("voice", ...)` expects.
    """
    # Early raise rather than the `if sys.platform == "win32":` wrapper the
    # methods below use: it narrows the same way for pyright's Linux pass --
    # `winreg`'s members are all Windows-gated in typeshed -- without indenting
    # the whole body.
    if sys.platform != "win32":
        raise NotImplementedError("WindowsPlatformInterface requires Windows")

    import winreg

    voices: dict[str, str] = {}
    try:
        tokens = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _VOICE_TOKENS)
    except OSError:
        logger.warning("no SAPI voice tokens in the registry")
        return voices
    for index in range(winreg.QueryInfoKey(tokens)[0]):
        name = winreg.EnumKey(tokens, index)
        try:
            attributes = winreg.OpenKey(tokens, name + "\\Attributes")
            language, _ = winreg.QueryValueEx(attributes, "Language")
        except OSError:
            continue
        code = language_for_lcid(str(language))
        # First token wins: David before Zira on a default en-US install.
        # Which of two same-language voices is chosen is a Beta preference
        # (ADR-003 `tts_voice`), not something to decide by registry order.
        if code is not None and code not in voices:
            voices[code] = _VOICE_ID_PREFIX + "\\" + name
    return voices


class WindowsPlatformInterface:
    def find_voice(self, language: str) -> str | None:
        if sys.platform == "win32":
            return _installed_voices().get(language)
        raise NotImplementedError("WindowsPlatformInterface requires Windows")

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
