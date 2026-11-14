from dataclasses import dataclass

import pygame

# Takki's own window as the key source (alpha-plan #13, research/key-capture-source.md).
# SDL's KEYDOWN/KEYUP name the physical key; its TEXTINPUT carries the
# character Windows composed for the window, dead keys included. pygame's
# KEYDOWN.unicode is never read: for `^` `k` it reports `^` twice.


@dataclass(frozen=True)
class KeyDown:
    scancode: int  # SDL scancode: the physical key, whatever the layout
    key: int  # SDL keycode: follows the layout, and names keys with no text


@dataclass(frozen=True)
class KeyUp:
    scancode: int
    key: int


@dataclass(frozen=True)
class TextTyped:
    text: str
    # The key still down whose press produced this text, or None when none is
    # (no KEYDOWN since the last release of the key that was).
    scancode: int | None
    # True for the first TEXTINPUT after a KEYDOWN while that key is down, and
    # only for it, so text with no key behind it is never fresh. pygame
    # drops SDL's auto-repeat KEYDOWNs, so an OS repeat is a TEXTINPUT with no
    # KEYDOWN since the last one: 764 of 764 agreed with SDL's own repeat flag.
    # A press that produced two characters (dead acute then `k`, a dead key that could
    # not combine) is one press: its first character is fresh and the second
    # is not, so it is one attempt, judged by the first. Merging the two would
    # read the same from the queue as a press and its first repeat delivered in
    # one drain after a stall of the loop.
    fresh: bool


@dataclass(frozen=True)
class KeymapChanged:
    """The Windows keyboard layout changed under the window (Win+Space)."""


WindowKeyEvent = KeyDown | KeyUp | TextTyped | KeymapChanged


class WindowKeyReader:
    """One SDL event in, at most one key event out, in the order the drain hands them over.

    Holds no queue of its own: it is fed from the window's one drain, never by
    a second get() (ADR-028 § C8).
    """

    def __init__(self) -> None:
        self._down: int | None = None
        self._fresh = False

    def read(self, event: pygame.event.Event) -> WindowKeyEvent | None:
        if event.type == pygame.KEYDOWN:
            self._down = event.scancode
            self._fresh = True
            return KeyDown(event.scancode, event.key)
        if event.type == pygame.KEYUP:
            if event.scancode == self._down:
                # A press that is over can make nothing fresh: after a tap of
                # Shift, text with no KEYDOWN behind it (a repeat still running
                # as focus returns, #14 (j)) would otherwise count as a press.
                self._down = None
                self._fresh = False
            return KeyUp(event.scancode, event.key)
        if event.type == pygame.TEXTINPUT:
            fresh = self._fresh
            self._fresh = False
            return TextTyped(event.text, self._down, fresh)
        if event.type == pygame.KEYMAPCHANGED:
            return KeymapChanged()
        return None
