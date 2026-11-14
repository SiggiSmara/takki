# Windows set-1 scan code (with its extended flag) -> SDL scancode. The layout
# grid speaks set-1 (layout.scan_code_grid), the window's KEYDOWN/KEYUP speak
# SDL, and this is the bridge between them (research/key-capture-source.md).
# Mirrors SDL 2's windows_scancode_table for every key of the grid and the
# keys around it; a key missing here is simply no cell. Brought in from
# spikes/key_capture_source_spike.py, less its entry for the low-level hook's
# extended Right Shift, which the window never reports.
SET1_TO_SDL: dict[tuple[int, bool], int] = {
    (0x01, False): 41,  # Escape
    (0x0E, False): 42,  # Backspace
    (0x0F, False): 43,  # Tab
    (0x1C, False): 40,  # Enter
    (0x1C, True): 88,  # keypad Enter
    (0x39, False): 44,  # Space
    (0x3A, False): 57,  # Caps Lock
    (0x2A, False): 225,  # Left Shift
    (0x36, False): 229,  # Right Shift
    (0x1D, False): 224,  # Left Ctrl, and AltGr's fake Left Ctrl
    (0x1D, True): 228,  # Right Ctrl
    (0x38, False): 226,  # Left Alt
    (0x38, True): 230,  # Right Alt (AltGr)
    (0x5B, True): 227,  # Left Windows
    (0x5C, True): 231,  # Right Windows
    (0x5D, True): 101,  # Menu
    (0x29, False): 53,  # left of 1
    (0x0C, False): 45,
    (0x0D, False): 46,
    (0x1A, False): 47,
    (0x1B, False): 48,
    (0x27, False): 51,
    (0x28, False): 52,
    (0x2B, False): 49,  # left of Enter (ISO) or above it (ANSI): one code for both
    (0x33, False): 54,
    (0x34, False): 55,
    (0x35, False): 56,
    (0x56, False): 100,  # the ISO key left of Z
    (0x53, True): 76,  # Delete
    (0x48, True): 82,  # Up
    (0x50, True): 81,  # Down
    (0x4B, True): 80,  # Left
    (0x4D, True): 79,  # Right
    **{(sc, False): 30 + i for i, sc in enumerate(range(0x02, 0x0B))},  # 1..9
    (0x0B, False): 39,  # 0
    **{(0x10 + i, False): sdl for i, sdl in enumerate((20, 26, 8, 21, 23, 28, 24, 12, 18, 19))},
    **{(0x1E + i, False): sdl for i, sdl in enumerate((4, 22, 7, 9, 10, 11, 13, 14, 15))},
    **{(0x2C + i, False): sdl for i, sdl in enumerate((29, 27, 6, 25, 5, 17, 16))},
    **{(0x3B + i, False): 58 + i for i in range(10)},  # F1..F10
    (0x57, False): 68,  # F11
    (0x58, False): 69,  # F12
}

SDL_TO_SET1: dict[int, tuple[int, bool]] = {sdl: set1 for set1, sdl in SET1_TO_SDL.items()}
