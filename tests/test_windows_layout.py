import ctypes
import ctypes.wintypes
import sys
from collections.abc import Generator
from contextlib import contextmanager

import pytest

from takki.lesson.introducer import anchor_keys
from takki.platform.layout import build_en, build_is, describe_mismatch, key_positions

pytestmark = pytest.mark.windows_only

# KLF_NOTELLSHELL suppresses the shell notification, not the list membership:
# a loaded layout DOES appear in GetKeyboardLayoutList until unloaded, which is
# why `loaded` unloads. It does not reach HKCU\Keyboard Layout\Preload, so
# nothing here survives a logoff even if a test dies mid-way.
KLF_NOTELLSHELL = 0x80

US_QWERTY = "00000409"
GERMAN_QWERTZ = "00000407"
ICELANDIC = "0000040F"
FRENCH_AZERTY = "0000040C"  # the "not installed on the dev laptop" case


def _installed(user32: "ctypes.CDLL") -> list[int]:
    count = user32.GetKeyboardLayoutList(0, None)
    handles = (ctypes.wintypes.HKL * count)()
    user32.GetKeyboardLayoutList(count, handles)
    return list(handles)


def _preload_klids() -> dict[int, str]:
    """langid → the KLID the user really has, from HKCU\\Keyboard Layout\\Preload.

    The authoritative record of the developer's own layouts, and the only way to
    put back the right variant: an HKL does not carry the KLID it was loaded
    from, so reconstructing one from the langid alone would restore plain US
    QWERTY to somebody whose English layout is Dvorak.
    """
    if sys.platform != "win32":
        return {}
    import winreg

    klids: dict[int, str] = {}
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Keyboard Layout\\Preload") as key:
        for index in range(winreg.QueryInfoKey(key)[1]):
            _, klid, _ = winreg.EnumValue(key, index)
            klids[int(str(klid), 16) & 0xFFFF] = str(klid)
    return klids


@contextmanager
def loaded(klid: str) -> Generator[int]:
    """An HKL for `klid`, loaded but never activated, unloaded again after.

    Only unloads what it added. Unloading a layout the developer really has
    installed would remove it from their machine, which a test must not do.
    """
    from takki.platform.windows import user32

    lib = user32()
    before = set(_installed(lib))
    hkl = lib.LoadKeyboardLayoutW(klid, KLF_NOTELLSHELL)
    if not hkl:
        # The errno matters here more than in most assertions: a failure to load
        # is the CI assumption breaking, not a layout being wrong. Guarded
        # because pyright's Linux pass has no ctypes.get_last_error.
        detail = ctypes.get_last_error() if sys.platform == "win32" else 0
        raise AssertionError(f"LoadKeyboardLayoutW({klid}) failed: {detail}")
    try:
        yield hkl
    finally:
        if hkl not in before:
            lib.UnloadKeyboardLayout(ctypes.wintypes.HKL(hkl))
        # Loading a *variant* of a langid the developer already has -- Dvorak or
        # US-International against their en-US -- substitutes for their entry
        # rather than joining it, and unloading the variant then takes the
        # langid away with it. Measured 2026-09-20: a full run of this file left
        # the machine with no US English layout at all, which is exactly what
        # 12b's precondition needs. So restore anything that went missing, by
        # the KLID the user actually had.
        vanished = before - set(_installed(lib))
        if vanished:
            klids = _preload_klids()
            for handle in vanished:
                langid = handle & 0xFFFF
                lib.LoadKeyboardLayoutW(klids.get(langid, f"{langid:08x}"), KLF_NOTELLSHELL)


class TestReadsTheTargetLayouts:
    def test_us_qwerty_is_exactly_build_en(self) -> None:
        from takki.platform.windows import read_layout

        with loaded(US_QWERTY) as hkl:
            layout = read_layout(hkl)
        expected = build_en()
        assert describe_mismatch(expected, layout) is None
        assert key_positions(layout) == key_positions(expected)
        assert set(layout.graphemes) == set(expected.graphemes)
        assert len(layout.keys) == 26

    def test_icelandic_is_exactly_build_is_including_the_composites(self) -> None:
        from takki.platform.windows import read_layout

        with loaded(ICELANDIC) as hkl:
            layout = read_layout(hkl)
        expected = build_is()
        assert describe_mismatch(expected, layout) is None
        assert set(layout.graphemes) == set(expected.graphemes)
        # The dead-key half, asserted field by field rather than by presence:
        # this is the only path in the reader that issues more than one read per
        # key, and the only one that can silently produce a plausible-looking
        # wrong answer.
        for char in ("á", "é", "í", "ó", "ú", "ý"):
            got, want = layout.graphemes[char], expected.graphemes[char]
            assert got == want, f"{char}: {got} != {want}"
        assert layout.keys["dead-acute"] == expected.keys["dead-acute"]

    def test_german_qwertz_swaps_y_and_z_against_us(self) -> None:
        from takki.platform.windows import read_layout

        with loaded(US_QWERTY) as hkl:
            us = read_layout(hkl)
        with loaded(GERMAN_QWERTZ) as hkl:
            de = read_layout(hkl)
        # The discriminator, stated as the swap rather than as two constants --
        # this is the case main.verify_layout exists to catch.
        assert (us.keys["y"].row, us.keys["y"].col) == (de.keys["z"].row, de.keys["z"].col)
        assert (us.keys["z"].row, us.keys["z"].col) == (de.keys["y"].row, de.keys["y"].col)
        assert (de.keys["y"].row, de.keys["y"].col) == (4, 1)
        assert (de.keys["z"].row, de.keys["z"].col) == (2, 6)

    def test_every_target_layout_carries_letters_at_the_six_anchors(self) -> None:
        # ADR-027 § The Anchor Gate names these by position. anchor_keys indexes
        # them unguarded, so a layout without them raises rather than degrading
        # to a five-key Stage 0. Unreachable in Alpha behind verify_layout, but
        # the measurement belongs in the suite rather than in a plan row.
        from takki.platform.windows import read_layout

        for klid in (US_QWERTY, GERMAN_QWERTZ, ICELANDIC):
            with loaded(klid) as hkl:
                layout = read_layout(hkl)
            anchors = anchor_keys(layout)
            assert len(anchors) == 6
            assert all(name in layout.graphemes for name in anchors), (klid, anchors)


class TestTheCiAssumptions:
    def test_a_layout_this_machine_does_not_have_can_still_be_read(self) -> None:
        """The assumption the CI strategy rests on (alpha-plan #12a-1).

        If this fails, the layout tests only ever run on a machine that happens
        to have en/de/is installed, and `windows-latest` tests nothing.
        """
        from takki.platform.windows import read_layout

        with loaded(FRENCH_AZERTY) as hkl:
            layout = read_layout(hkl)
        assert layout.lang == "fr"
        # AZERTY, read rather than assumed: `a` sits where QWERTY puts `q`.
        assert (layout.keys["a"].row, layout.keys["a"].col) == (2, 1)
        assert (layout.keys["q"].row, layout.keys["q"].col) == (3, 1)

    @pytest.mark.parametrize(
        "klid,name", [("00020409", "US-International"), ("00010409", "Dvorak")]
    )
    def test_a_variant_layout_with_a_64_bit_handle_is_read_not_crashed_on(
        self, klid: str, name: str
    ) -> None:
        """Variant KLIDs get handles that do not fit a C int.

        US-International reports HKL 0xfffffffff0010409. Without argtypes on the
        HKL parameter, ctypes marshals it as an int and get_layout_positions()
        raises OverflowError as main()'s third statement -- for a layout a real
        US keyboard is very likely to carry. Found by review, 2026-09-20.
        """
        from takki.platform.windows import read_layout

        with loaded(klid) as hkl:
            layout = read_layout(hkl)
        assert layout.lang == "en", name
        # Both are English keyboards and both are refused: identity says `en`,
        # positions say no. Which is the split describe_mismatch exists for.
        assert describe_mismatch(build_en(), layout) is not None, name

    def test_reading_a_layout_does_not_activate_it(self) -> None:
        from takki.platform.windows import read_layout, user32

        lib = user32()
        before = lib.GetKeyboardLayout(0)
        for klid in (US_QWERTY, GERMAN_QWERTZ, ICELANDIC, FRENCH_AZERTY):
            with loaded(klid) as hkl:
                read_layout(hkl)
        assert lib.GetKeyboardLayout(0) == before


class TestDeadKeyState:
    def test_reading_the_same_layout_twice_gives_the_same_answer(self) -> None:
        # The reader arms Icelandic's dead acute 30 times to enumerate the
        # composites. If any of that state escaped, the second read would differ
        # -- letters would come back accented.
        from takki.platform.windows import read_layout

        with loaded(ICELANDIC) as hkl:
            first = read_layout(hkl)
            second = read_layout(hkl)
        assert key_positions(first) == key_positions(second)
        assert first.graphemes == second.graphemes

    def test_a_dead_key_armed_before_the_read_does_not_corrupt_it(self) -> None:
        """Pending composition state outlives the call that made it.

        Measured 2026-09-20: reading Icelandic's acute and then `a` returns the
        accented form. The state is the layout's, not this process's, so the
        reader cannot assume a clean one -- it flushes first. Without that flush
        every letter of the sweep comes back wrong.
        """
        from takki.platform.windows import read_layout, to_unicode

        with loaded(ICELANDIC) as hkl:
            count, _ = to_unicode(hkl, 0x28)  # the acute, unflagged: arms it
            assert count < 0, "0x28 is expected to be a dead key on Icelandic"
            layout = read_layout(hkl)
        assert describe_mismatch(build_is(), layout) is None


class TestLanguageComesFromTheKeyboard:
    def test_lang_is_the_layouts_not_the_system_locale(self) -> None:
        # The laptop reports locale en-150 with a German layout active, so these
        # two sources disagree on the machine this was written on. Sourcing lang
        # from the locale would make describe_mismatch print a position diff
        # instead of naming the language (ADR-025 § Language and layout agree).
        from takki.platform.windows import read_layout

        for klid, expected in (
            (US_QWERTY, "en"),
            (GERMAN_QWERTZ, "de"),
            (ICELANDIC, "is"),
            (FRENCH_AZERTY, "fr"),
        ):
            with loaded(klid) as hkl:
                assert read_layout(hkl).lang == expected

    def test_a_uk_keyboard_teaches_the_english_curriculum(self) -> None:
        """0x0809 is not 0x0409, and it must pass anyway.

        Takki teaches letters and nothing else, and UK QWERTY differs from US
        only outside that set -- which is why describe_mismatch compares
        positions and never layout identity.
        """
        from takki.platform.windows import read_layout

        with loaded("00000809") as hkl:
            layout = read_layout(hkl)
        assert layout.lang == "en"
        assert describe_mismatch(build_en(), layout) is None


class TestNonLatinLayoutsAreRefusedNotMisread:
    @pytest.mark.parametrize("klid,lang", [("00000419", "ru"), ("00000408", "el")])
    def test_an_alphabet_takki_has_no_table_for_stops_startup(self, klid: str, lang: str) -> None:
        # The other ~197 layouts need no right answer, only a clean refusal.
        from takki.platform.windows import read_layout

        with loaded(klid) as hkl:
            layout = read_layout(hkl)
        assert layout.lang == lang
        mismatch = describe_mismatch(build_en(), layout)
        assert mismatch is not None
        assert lang in mismatch
