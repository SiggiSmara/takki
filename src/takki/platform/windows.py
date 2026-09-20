import ctypes
import ctypes.wintypes
import logging
import subprocess
import sys
import unicodedata

from takki.audio.tts import TTSEngine
from takki.platform.layout import Grapheme, Layout, PhysicalKey

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


# --- keyboard layout ---------------------------------------------------------

_MAPVK_VSC_TO_VK_EX = 3
_SPACE_SCAN_CODE = 0x39
# wFlags bit 2, "do not change keyboard state" (Windows 10 1607+). Without it a
# dead key leaves a pending composition in the kernel that silently prefixes the
# *next* read: measured on Icelandic, reading the acute at 0x28 and then `a`
# returns 'a-acute', not 'a'. The flag stops a read from creating that state; it
# does not let a read consume state already pending, which is what _flush is for.
_NO_KERNEL_STATE_CHANGE = 0x4

# Set-1 scan codes are positional -- they name the physical key, not the
# character on it -- so this table is a property of the keyboard rather than of
# any layout, and it is the half Windows will not report: no API returns a row
# or a column. It must agree with build_en/build_de/build_is exactly, because
# COL_TO_FINGER is a pure function of `col`; an off-by-one here reassigns
# fingers and re-pairs Phase 1's symmetric slots rather than merely moving a
# letter. Pinned against all three tables by tests/test_windows_layout.py.
#
# 0x56, the extra key ISO keyboards carry left of Z, deliberately has no slot:
# it is the angle-bracket key on German and Icelandic and phantoms as backslash
# on US, and no layout in the target set puts a letter there. One that did would
# read as a missing letter and stop startup, which is the loud failure.
SCAN_CODE_GRID: dict[int, tuple[int, int]] = {
    **{sc: (1, col) for col, sc in enumerate(range(0x02, 0x0E), start=1)},
    **{sc: (2, col) for col, sc in enumerate(range(0x10, 0x1C), start=1)},
    **{sc: (3, col) for col, sc in enumerate(range(0x1E, 0x29), start=1)},
    0x2B: (3, 12),
    **{sc: (4, col) for col, sc in enumerate(range(0x2C, 0x36), start=1)},
}

_user32_cache: "ctypes.CDLL | None" = None


def user32() -> "ctypes.CDLL":
    # Lazy and cached rather than module level: tests/test_platform.py imports
    # this module on Linux, where ctypes.WinDLL does not exist. Same early-raise
    # narrowing as _installed_voices() uses, for the same pyright reason.
    if sys.platform != "win32":
        raise NotImplementedError("WindowsPlatformInterface requires Windows")
    global _user32_cache
    if _user32_cache is None:
        lib = ctypes.WinDLL("user32", use_last_error=True)
        # Handle-returning: left at the default c_int they sign-extend any HKL
        # whose high word exceeds 0x7fff into a negative number.
        lib.GetKeyboardLayout.restype = ctypes.wintypes.HKL
        lib.LoadKeyboardLayoutW.restype = ctypes.wintypes.HKL
        lib.MapVirtualKeyExW.restype = ctypes.wintypes.UINT
        # argtypes matter as much as restype, and for the same reason at the
        # other end: an HKL passed to a function with no argtypes is marshalled
        # as a C int, and the variant layouts have handles that do not fit one.
        # US-International (KLID 00020409) reports 0xfffffffff0010409 -- without
        # this, get_layout_positions() raises OverflowError as main()'s third
        # statement for anyone not on a plain en-US/de-DE/is-IS layout.
        lib.MapVirtualKeyExW.argtypes = [
            ctypes.wintypes.UINT,
            ctypes.wintypes.UINT,
            ctypes.wintypes.HKL,
        ]
        lib.ToUnicodeEx.restype = ctypes.c_int
        lib.ToUnicodeEx.argtypes = [
            ctypes.wintypes.UINT,
            ctypes.wintypes.UINT,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.wintypes.LPWSTR,
            ctypes.c_int,
            ctypes.wintypes.UINT,
            ctypes.wintypes.HKL,
        ]
        _user32_cache = lib
    return _user32_cache


def to_unicode(hkl: int, scan_code: int, flags: int = 0) -> tuple[int, str]:
    """(count, characters) for one physical key with no modifiers held.

    Negative count is a dead key, 0 no translation, 1 the ordinary case.
    """
    lib = user32()
    virtual_key = lib.MapVirtualKeyExW(scan_code, _MAPVK_VSC_TO_VK_EX, hkl)
    if not virtual_key:
        return 0, ""
    state = (ctypes.c_ubyte * 256)()
    buffer = ctypes.create_unicode_buffer(8)
    count = lib.ToUnicodeEx(virtual_key, scan_code, state, buffer, len(buffer), flags, hkl)
    return count, "".join(buffer[: max(count, 0)])


def _flush(hkl: int) -> None:
    """Consume any dead-key composition left pending for this layout.

    Deliberately unflagged: a flagged read cannot consume pending state, so a
    contaminated layout stays contaminated for every read that follows. Space
    composes with any pending dead key and clears it. The state outlives the
    call that created it and is not ours to assume clean.
    """
    for _ in range(8):
        if to_unicode(hkl, _SPACE_SCAN_CODE)[0] >= 0:
            return


def dead_key_name(standalone: str) -> str:
    """A dead key's name, from the character it produces when followed by space.

    Unicode names these "ACUTE ACCENT", "DIAERESIS", "CIRCUMFLEX ACCENT"; the
    first word is the diacritic, which is the spelling build_is already uses
    ("dead-acute"). Derived rather than tabulated so a diacritic nobody has
    measured still gets a stable name instead of a guess.
    """
    if not standalone:
        return "dead-unknown"
    try:
        return "dead-" + unicodedata.name(standalone).split()[0].lower()
    except ValueError:
        return f"dead-u{ord(standalone):04x}"


def language_for_hkl(hkl: int) -> str:
    """The keyboard's own language, which is not the system locale.

    ADR-025 § Language and layout must agree needs the two comparable: this
    laptop reports locale en-150 while the active layout is German, and taking
    both from the locale would have describe_mismatch print a bare position diff
    instead of naming the language. The low word of an HKL is the langid, and
    LCIDToLocaleName turns it into a BCP-47 name primary_subtag already reduces
    -- correct for every layout Windows ships, not only the three Alpha tables.
    """
    if sys.platform != "win32":
        raise NotImplementedError("WindowsPlatformInterface requires Windows")
    buffer = ctypes.create_unicode_buffer(_LOCALE_NAME_MAX_LENGTH)
    written = ctypes.windll.kernel32.LCIDToLocaleName(
        hkl & 0xFFFF, buffer, _LOCALE_NAME_MAX_LENGTH, 0
    )
    if not written:
        # Not primary_subtag(""), which would answer "en" -- a confident wrong
        # answer here reads as "this is an English keyboard" and would let an
        # unknown layout teach the English curriculum. The marker cannot match
        # any curriculum language, so verify_layout stops and names it.
        logger.warning("LCIDToLocaleName failed for langid 0x%04x", hkl & 0xFFFF)
        return f"langid-{hkl & 0xFFFF:04x}"
    return primary_subtag(buffer.value)


def read_layout(hkl: int) -> Layout:
    """What `hkl` actually is, read from Windows rather than assumed.

    Takes the HKL instead of reading the active layout so a test can point it at
    a layout it loaded but never activated -- LoadKeyboardLayout and ToUnicodeEx
    both accept one. That is what lets en/de/is be asserted on a runner that has
    none of them installed.

    It reports; it does not judge. Nothing here knows which language was
    configured, so a German keyboard is described truthfully and
    main.verify_layout decides whether that can teach the configured curriculum.
    A reader that knew the answer could give it.
    """
    _flush(hkl)
    keys: dict[str, PhysicalKey] = {}
    graphemes: dict[str, Grapheme] = {}
    letter_scan_codes: dict[str, int] = {}
    dead_scan_codes: list[int] = []

    for scan_code, (row, col) in SCAN_CODE_GRID.items():
        count, chars = to_unicode(hkl, scan_code, _NO_KERNEL_STATE_CHANGE)
        if count < 0:
            dead_scan_codes.append(scan_code)
        elif count == 1 and chars.isalpha():
            # isalpha, not an ASCII range: a Cyrillic or Greek layout must be
            # reported truthfully so describe_mismatch can refuse it by name,
            # and a future language pack needs its own alphabet to survive here.
            letter = chars.lower()
            keys[letter] = PhysicalKey(letter, row, col)
            graphemes[letter] = Grapheme(letter, "direct", (letter,), 1)
            letter_scan_codes[letter] = scan_code

    for scan_code in dead_scan_codes:
        row, col = SCAN_CODE_GRID[scan_code]
        _flush(hkl)
        to_unicode(hkl, scan_code)  # arm it -- unflagged, because this must set state
        _, standalone = to_unicode(hkl, _SPACE_SCAN_CODE)
        name = dead_key_name(standalone)
        keys[name] = PhysicalKey(name, row, col)
        for base, base_scan_code in letter_scan_codes.items():
            _flush(hkl)
            if to_unicode(hkl, scan_code)[0] >= 0:
                continue
            count, composed = to_unicode(hkl, base_scan_code)
            if count == 1 and composed.isalpha() and composed.lower() != base:
                composed = composed.lower()
                graphemes[composed] = Grapheme(
                    composed, "dead-key", (name, base), 2, base=base, dead_key=name
                )
    _flush(hkl)
    return Layout(lang=language_for_hkl(hkl), keys=keys, graphemes=graphemes)


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
        # ADR-006 makes Windows authoritative, so this reads the active layout
        # and never substitutes one of its own. GetKeyboardLayout(0) is the
        # *calling thread's* layout -- right here only because the main thread
        # owns the window that anchors keyboard focus (ADR-028) and is the
        # thread the lesson runs on.
        return read_layout(user32().GetKeyboardLayout(0))

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
