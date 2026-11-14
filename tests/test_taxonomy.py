import pytest

from takki import config
from takki.input.taxonomy import (
    Boundary,
    Character,
    Composing,
    KeyBindings,
    RecoveryKey,
    System,
    TalkKey,
    classify,
)
from takki.input.window_keys import KeyDown, KeyUp, TextTyped

DEFAULTS = KeyBindings()
# SDL scan codes (research/key-capture-source.md).
SC_A, SC_SPACE, SC_F5 = 4, 44, 62


def down(scancode: int) -> KeyDown:
    return KeyDown(scancode, 0)


def text(chars: str, scancode: int | None = SC_A) -> TextTyped:
    return TextTyped(chars, scancode, fresh=True)


class TestBindingDefaults:
    def test_defaults_come_from_config(self) -> None:
        assert DEFAULTS.talk == config.TALK_KEY
        assert DEFAULTS.reread == config.REREAD_KEY
        assert DEFAULTS.restart == config.RESTART_KEY
        assert DEFAULTS.restart_hold_ms == config.RESTART_HOLD_MS

    def test_the_bindings_are_right_ctrl_and_escape(self) -> None:
        assert (DEFAULTS.talk, DEFAULTS.reread, DEFAULTS.restart) == (228, 41, 41)


class TestTaxonomy:
    def test_talk_key(self) -> None:
        assert classify(down(config.TALK_KEY), DEFAULTS) == TalkKey()

    def test_shared_recovery_key_is_bound_to_both_actions(self) -> None:
        assert classify(down(config.REREAD_KEY), DEFAULTS) == RecoveryKey(reread=True, restart=True)

    def test_distinct_recovery_keys_are_classified_separately(self) -> None:
        bindings = KeyBindings(reread=config.REREAD_KEY, restart=SC_F5)
        assert classify(down(config.REREAD_KEY), bindings) == RecoveryKey(
            reread=True, restart=False
        )
        assert classify(down(SC_F5), bindings) == RecoveryKey(reread=False, restart=True)

    def test_printable_text(self) -> None:
        assert classify(text("a"), DEFAULTS) == Character("a")

    def test_composed_grapheme_is_an_ordinary_character(self) -> None:
        # ADR-028: the composite arrives already composed; `á` is as atomic as `a`.
        assert classify(text("\u00e1"), DEFAULTS) == Character("\u00e1")

    def test_non_printable_text_is_composing(self) -> None:
        assert classify(text("\x01"), DEFAULTS) == Composing()

    @pytest.mark.parametrize("scancode", [42, 43, 76, 40, 88])
    def test_boundary_keys(self, scancode: int) -> None:
        # Backspace, Tab, Delete, Enter and the keypad's Enter.
        assert classify(down(scancode), DEFAULTS) == Boundary()

    @pytest.mark.parametrize("scancode", [59, 227, 229, 82, 57, 52, SC_A, SC_SPACE])
    def test_every_other_key_is_system(self, scancode: int) -> None:
        # F2, Left Windows, Right Shift, Up, Caps Lock, the Icelandic dead
        # acute, `a` and the space bar: a key's press says which key it was,
        # and what it typed, if anything, is classified from its text.
        assert classify(down(scancode), DEFAULTS) == System()

    def test_the_space_bar_types_a_space_and_is_system_by_its_key(self) -> None:
        # ADR-023 scopes the space bar out of the curriculum, so it has no
        # lesson class. The window gives it the text `' '` (alpha-plan #14 (d)).
        assert classify(text(" ", SC_SPACE), DEFAULTS) == System()

    def test_a_release_classifies_the_same_as_its_press(self) -> None:
        for code in (config.REREAD_KEY, config.TALK_KEY, 42, SC_A):
            assert classify(KeyUp(code, 0), DEFAULTS) == classify(down(code), DEFAULTS)


class TestCaseFolding:
    """ADR-027 § Case is folded at the boundary."""

    @pytest.mark.parametrize(
        ("typed_char", "expected"),
        [
            ("F", "f"),
            ("A", "a"),
            ("\u00c4", "\u00e4"),
            ("\u00d6", "\u00f6"),
            ("\u00de", "\u00fe"),
            ("\u00c1", "\u00e1"),
        ],
    )
    def test_upper_case_folds_to_lower(self, typed_char: str, expected: str) -> None:
        assert classify(text(typed_char), DEFAULTS) == Character(expected)

    def test_lower_case_is_unchanged(self) -> None:
        assert classify(text("f"), DEFAULTS) == Character("f")

    def test_eszett_survives_folding_as_one_character(self) -> None:
        # str.casefold() maps ß to "ss" -- two characters, which would make the
        # German curriculum untypeable because no prompt target is ever two
        # characters. str.lower() is what the boundary uses, and this pins it.
        assert classify(text("\u00df"), DEFAULTS) == Character("\u00df")
        assert classify(text("\u1e9e"), DEFAULTS) == Character("\u00df")
