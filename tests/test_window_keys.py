import pygame
import pytest

from takki.input.window_keys import (
    KeyDown,
    KeymapChanged,
    KeyUp,
    TextTyped,
    WindowKeyEvent,
    WindowKeyReader,
)
from takki.platform.layout import scan_code_grid
from takki.platform.scan_codes import SDL_TO_SET1, SET1_TO_SDL

# SDL scancodes and keycodes as the laptop reported them (research/key-capture-source.md).
SC_A, SC_F, SC_K, SC_L = 4, 9, 14, 15
SC_SPACE, SC_LSHIFT, SC_ENTER = 44, 225, 40
SC_IS_DEAD_ACUTE = 52
K_A, K_F, K_K, K_L = 97, 102, 107, 108
K_DEAD_ACUTE = 180
ACUTE = "\u00b4"  # the accent's own text, when the dead key cannot combine


def down(scancode: int, key: int) -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYDOWN, scancode=scancode, key=key)


def up(scancode: int, key: int) -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYUP, scancode=scancode, key=key)


def text(t: str) -> pygame.event.Event:
    return pygame.event.Event(pygame.TEXTINPUT, text=t)


def read_all(events: list[pygame.event.Event]) -> list[WindowKeyEvent | None]:
    reader = WindowKeyReader()
    return [reader.read(e) for e in events]


class TestWindowKeyReader:
    def test_a_letter_is_a_press_its_fresh_text_and_a_release(self) -> None:
        assert read_all([down(SC_A, K_A), text("a"), up(SC_A, K_A)]) == [
            KeyDown(SC_A, K_A),
            TextTyped("a", SC_A, fresh=True),
            KeyUp(SC_A, K_A),
        ]

    def test_a_held_key_gives_one_fresh_text_and_then_repeats(self) -> None:
        assert read_all([down(SC_L, K_L), text("l"), text("l"), text("l"), up(SC_L, K_L)]) == [
            KeyDown(SC_L, K_L),
            TextTyped("l", SC_L, fresh=True),
            TextTyped("l", SC_L, fresh=False),
            TextTyped("l", SC_L, fresh=False),
            KeyUp(SC_L, K_L),
        ]

    def test_the_same_key_pressed_twice_gives_two_fresh_texts(self) -> None:
        events = [down(SC_L, K_L), text("l"), up(SC_L, K_L)] * 2
        assert [e for e in read_all(events) if isinstance(e, TextTyped)] == [
            TextTyped("l", SC_L, fresh=True),
            TextTyped("l", SC_L, fresh=True),
        ]

    def test_a_dead_key_has_no_text_and_the_next_letter_carries_the_composition(self) -> None:
        events = [
            down(SC_IS_DEAD_ACUTE, K_DEAD_ACUTE),
            up(SC_IS_DEAD_ACUTE, K_DEAD_ACUTE),
            down(SC_A, K_A),
            text("á"),
            up(SC_A, K_A),
        ]
        assert read_all(events) == [
            KeyDown(SC_IS_DEAD_ACUTE, K_DEAD_ACUTE),
            KeyUp(SC_IS_DEAD_ACUTE, K_DEAD_ACUTE),
            KeyDown(SC_A, K_A),
            TextTyped("á", SC_A, fresh=True),
            KeyUp(SC_A, K_A),
        ]

    def test_a_press_that_produced_two_characters_is_fresh_once(self) -> None:
        # Dead acute then `k`: the dead key cannot combine, so k's one KEYDOWN
        # is followed by two TEXTINPUTs. One press, one attempt, judged by the accent.
        events = [
            down(SC_IS_DEAD_ACUTE, K_DEAD_ACUTE),
            up(SC_IS_DEAD_ACUTE, K_DEAD_ACUTE),
            down(SC_K, K_K),
            text(ACUTE),
            text("k"),
            up(SC_K, K_K),
        ]
        assert read_all(events) == [
            KeyDown(SC_IS_DEAD_ACUTE, K_DEAD_ACUTE),
            KeyUp(SC_IS_DEAD_ACUTE, K_DEAD_ACUTE),
            KeyDown(SC_K, K_K),
            TextTyped(ACUTE, SC_K, fresh=True),
            TextTyped("k", SC_K, fresh=False),
            KeyUp(SC_K, K_K),
        ]

    def test_shift_gives_no_text_and_the_letter_under_it_is_fresh(self) -> None:
        k_lshift = pygame.K_LSHIFT
        events = [
            down(SC_LSHIFT, k_lshift),
            down(SC_A, K_A),
            text("A"),
            up(SC_LSHIFT, k_lshift),
            up(SC_A, K_A),
        ]
        assert read_all(events) == [
            KeyDown(SC_LSHIFT, k_lshift),
            KeyDown(SC_A, K_A),
            TextTyped("A", SC_A, fresh=True),
            KeyUp(SC_LSHIFT, k_lshift),
            KeyUp(SC_A, K_A),
        ]

    def test_enter_gives_a_press_and_a_release_and_no_text(self) -> None:
        assert read_all([down(SC_ENTER, pygame.K_RETURN), up(SC_ENTER, pygame.K_RETURN)]) == [
            KeyDown(SC_ENTER, pygame.K_RETURN),
            KeyUp(SC_ENTER, pygame.K_RETURN),
        ]

    def test_space_gives_text_like_any_key(self) -> None:
        # Space stays System by its key (#14 (d)); that is the taxonomy's
        # decision, made in 14b. The reader reports what SDL said.
        assert read_all([down(SC_SPACE, pygame.K_SPACE), text(" ")]) == [
            KeyDown(SC_SPACE, pygame.K_SPACE),
            TextTyped(" ", SC_SPACE, fresh=True),
        ]

    def test_a_held_key_released_by_sdl_at_focus_loss_is_a_plain_release(self) -> None:
        # SDL sends a KEYUP for every held key just before WINDOWFOCUSLOST; the
        # focus event is the drain's to handle, not the reader's.
        events = [
            down(SC_F, K_F),
            text("f"),
            text("f"),
            up(SC_F, K_F),
            pygame.event.Event(pygame.WINDOWFOCUSLOST),
        ]
        assert read_all(events) == [
            KeyDown(SC_F, K_F),
            TextTyped("f", SC_F, fresh=True),
            TextTyped("f", SC_F, fresh=False),
            KeyUp(SC_F, K_F),
            None,
        ]

    def test_text_with_no_press_behind_it_is_neither_fresh_nor_any_key(self) -> None:
        assert read_all([text("x")]) == [TextTyped("x", None, fresh=False)]

    def test_text_after_a_tap_of_a_key_with_no_text_is_not_fresh(self) -> None:
        # Shift tapped, then text with no KEYDOWN behind it: what a repeat
        # still running as focus returns would look like (#14 (j)).
        events = [down(SC_LSHIFT, pygame.K_LSHIFT), up(SC_LSHIFT, pygame.K_LSHIFT), text("l")]
        assert read_all(events) == [
            KeyDown(SC_LSHIFT, pygame.K_LSHIFT),
            KeyUp(SC_LSHIFT, pygame.K_LSHIFT),
            TextTyped("l", None, fresh=False),
        ]

    def test_a_dead_key_released_before_its_letter_still_lets_the_letter_be_fresh(self) -> None:
        events = [
            down(SC_IS_DEAD_ACUTE, K_DEAD_ACUTE),
            up(SC_IS_DEAD_ACUTE, K_DEAD_ACUTE),
            text(ACUTE),
            down(SC_A, K_A),
            text("a"),
        ]
        # A dead key's own text never arrives before the next KEYDOWN; if it
        # did, it is not fresh, and the letter after it still is.
        assert read_all(events)[2:] == [
            TextTyped(ACUTE, None, fresh=False),
            KeyDown(SC_A, K_A),
            TextTyped("a", SC_A, fresh=True),
        ]

    def test_text_after_the_pressing_key_was_released_belongs_to_no_key(self) -> None:
        events = [down(SC_A, K_A), text("a"), up(SC_A, K_A), text("b")]
        assert read_all(events)[-1] == TextTyped("b", None, fresh=False)

    def test_each_keymap_change_is_reported(self) -> None:
        # An injected switch gave up to three; none is merged here.
        events = [pygame.event.Event(pygame.KEYMAPCHANGED)] * 3
        assert read_all(events) == [KeymapChanged()] * 3

    @pytest.mark.parametrize(
        "event",
        [
            pygame.event.Event(pygame.TEXTEDITING, text="", start=0, length=0),
            pygame.event.Event(pygame.MOUSEMOTION, pos=(1, 1)),
            pygame.event.Event(pygame.WINDOWFOCUSGAINED),
            pygame.event.Event(pygame.QUIT),
        ],
    )
    def test_every_other_event_gives_nothing_and_leaves_the_press_fresh(
        self, event: pygame.event.Event
    ) -> None:
        assert read_all([down(SC_A, K_A), event, text("a")]) == [
            KeyDown(SC_A, K_A),
            None,
            TextTyped("a", SC_A, fresh=True),
        ]


# US engraving of each key, so the table is checked against SDL's own names.
# pygame names every key here but one, which is given as SDL's number.
_US_NAMES: dict[tuple[int, bool], str | int] = {
    **{(sc, False): str(n % 10) for n, sc in enumerate(range(0x02, 0x0C), start=1)},
    (0x0C, False): "MINUS",
    (0x0D, False): "EQUALS",
    **{(0x10 + i, False): c for i, c in enumerate("QWERTYUIOP")},
    (0x1A, False): "LEFTBRACKET",
    (0x1B, False): "RIGHTBRACKET",
    **{(0x1E + i, False): c for i, c in enumerate("ASDFGHJKL")},
    (0x27, False): "SEMICOLON",
    (0x28, False): "APOSTROPHE",
    (0x29, False): "GRAVE",
    (0x2B, False): "BACKSLASH",
    **{(0x2C + i, False): c for i, c in enumerate("ZXCVBNM")},
    (0x33, False): "COMMA",
    (0x34, False): "PERIOD",
    (0x35, False): "SLASH",
    (0x56, False): "NONUSBACKSLASH",
    (0x01, False): "ESCAPE",
    (0x0E, False): "BACKSPACE",
    (0x0F, False): "TAB",
    (0x1C, False): "RETURN",
    (0x1C, True): "KP_ENTER",
    (0x39, False): "SPACE",
    (0x3A, False): "CAPSLOCK",
    (0x2A, False): "LSHIFT",
    (0x36, False): "RSHIFT",
    (0x1D, False): "LCTRL",
    (0x1D, True): "RCTRL",
    (0x38, False): "LALT",
    (0x38, True): "RALT",
    (0x5B, True): "LGUI",
    (0x5C, True): "RGUI",
    (0x5D, True): 101,  # SDL_SCANCODE_APPLICATION, the Menu key
    (0x53, True): "DELETE",
    (0x48, True): "UP",
    (0x50, True): "DOWN",
    (0x4B, True): "LEFT",
    (0x4D, True): "RIGHT",
    **{(0x3B + i, False): f"F{i + 1}" for i in range(10)},
    (0x57, False): "F11",
    (0x58, False): "F12",
}


class TestScanCodes:
    def test_every_entry_is_the_sdl_scancode_of_the_same_key(self) -> None:
        expected = {
            set1: name if isinstance(name, int) else getattr(pygame, f"KSCAN_{name}")
            for set1, name in _US_NAMES.items()
        }
        assert SET1_TO_SDL == expected

    @pytest.mark.parametrize("shape", ["iso", "ansi"])
    def test_every_cell_of_the_grid_has_an_sdl_scancode(self, shape: str) -> None:
        grid = scan_code_grid(shape)  # type: ignore[arg-type]
        missing = [hex(sc) for sc in grid if (sc, False) not in SET1_TO_SDL]
        assert missing == []

    def test_the_inverse_loses_nothing(self) -> None:
        assert len(SDL_TO_SET1) == len(SET1_TO_SDL)
        assert all(SET1_TO_SDL[set1] == sdl for sdl, set1 in SDL_TO_SET1.items())
