import sys

import pytest

from takki.input import KeyEvent

pytestmark = pytest.mark.windows_only


def test_regular_letter_translates_to_char_event() -> None:
    if sys.platform == "win32":
        import pynput.keyboard as keyboard

        from takki.input.pynput_stream import translate

        event = translate(keyboard.KeyCode.from_char("a"), pressed=True)
        assert event == KeyEvent(pressed=True, char="a", name=None)


def test_release_sets_pressed_false() -> None:
    if sys.platform == "win32":
        import pynput.keyboard as keyboard

        from takki.input.pynput_stream import translate

        event = translate(keyboard.KeyCode.from_char("a"), pressed=False)
        assert event == KeyEvent(pressed=False, char="a", name=None)


def test_special_key_translates_to_name_event() -> None:
    if sys.platform == "win32":
        import pynput.keyboard as keyboard

        from takki.input.pynput_stream import translate

        assert translate(keyboard.Key.esc, pressed=True) == KeyEvent(
            pressed=True, char=None, name="esc"
        )
        assert translate(keyboard.Key.ctrl_r, pressed=True) == KeyEvent(
            pressed=True, char=None, name="ctrl_r"
        )
        assert translate(keyboard.Key.backspace, pressed=True) == KeyEvent(
            pressed=True, char=None, name="backspace"
        )


def test_composing_keycode_with_no_char_translates_to_none_none() -> None:
    if sys.platform == "win32":
        import pynput.keyboard as keyboard

        from takki.input.pynput_stream import translate

        composing = keyboard.KeyCode(vk=0, char=None)
        event = translate(composing, pressed=True)
        assert event.char is None
        assert event.name is None
