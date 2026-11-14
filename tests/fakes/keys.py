"""Key events as Takki's window reports them, built for a character of a layout.

The one helper session tests build key events through. It does not run the real
reader (tests/test_window_keys.py tests that), so each press is the sequence the
reader produces: KEYDOWN, its fresh text, KEYUP.
"""

from takki.input.window_keys import KeyDown, KeyUp, TextTyped, WindowKeyEvent
from takki.platform.layout import Layout
from takki.platform.scan_codes import SET1_TO_SDL


def scancode(layout: Layout, char: str) -> int:
    """The SDL scan code of the key that types `char` on `layout`, folded or composed."""
    name = char.lower()
    key = layout.keys.get(name)
    if key is None:
        # A composite is typed on its base letter's key, after its dead key.
        grapheme = layout.graphemes[name]
        assert grapheme.base is not None, char
        key = layout.keys[grapheme.base]
    return SET1_TO_SDL[(key.scan_code, False)]


def keystroke(code: int, text: str | None = None, *, release: bool = True) -> list[WindowKeyEvent]:
    """One press of the key `code`, its text if it types one, and its release."""
    events: list[WindowKeyEvent] = [KeyDown(code, 0)]
    if text is not None:
        events.append(TextTyped(text, code, fresh=True))
    if release:
        events.append(KeyUp(code, 0))
    return events


def typed(layout: Layout, char: str, *, release: bool = True) -> list[WindowKeyEvent]:
    """A press of the key that types `char`, as the window reports it."""
    return keystroke(scancode(layout, char), char, release=release)
