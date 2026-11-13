import unicodedata
from dataclasses import dataclass
from typing import Literal

from takki import config

L_PINK, L_RING, L_MID, L_IDX = "L-pink", "L-ring", "L-mid", "L-idx"
R_IDX, R_MID, R_RING, R_PINK = "R-idx", "R-mid", "R-ring", "R-pink"

COL_TO_FINGER: dict[int, str] = {
    1: L_PINK,
    2: L_RING,
    3: L_MID,
    4: L_IDX,
    5: L_IDX,
    6: R_IDX,
    7: R_IDX,
    8: R_MID,
    9: R_RING,
    10: R_PINK,
    11: R_PINK,
    12: R_PINK,
    13: R_PINK,
}

# Set-1 scan codes are positional -- they name the physical key, not the
# character on it -- so this table is a property of the keyboard rather than of
# any layout, and it is the half Windows will not report: no API returns a row
# or a column. It must agree with build_en/build_de/build_is exactly, because
# COL_TO_FINGER is a pure function of `col`; an off-by-one here reassigns
# fingers rather than merely moving a letter. Pinned by tests/test_platform.py
# and, against Windows itself, by tests/test_windows_layout.py.
#
# Two keys, and every key that produces no character, are deliberately left
# out (ADR-026 § Every cell of the grid): 0x56, the extra key ISO keyboards
# carry left of Z, which an ANSI keyboard does not have and Windows cannot tell
# is missing; and 0x29, left of `1` (roadmap § C17).
_SHARED_GRID: dict[int, tuple[int, int]] = {
    **{sc: (1, col) for col, sc in enumerate(range(0x02, 0x0E), start=1)},
    **{sc: (2, col) for col, sc in enumerate(range(0x10, 0x1C), start=1)},
    **{sc: (3, col) for col, sc in enumerate(range(0x1E, 0x29), start=1)},
    **{sc: (4, col) for col, sc in enumerate(range(0x2C, 0x36), start=1)},
}

# The one cell the keyboard's shape moves: 0x2B is left of Enter on ISO and
# above it on ANSI. Windows sends the same code for both and cannot tell the
# two keyboards apart, so the shape is a setting (config.KEYBOARD_SHAPE).
_CELL_0X2B: dict[str, tuple[int, int]] = {"iso": (3, 12), "ansi": (2, 13)}

KeyboardShape = Literal["iso", "ansi"]


def scan_code_grid(shape: KeyboardShape | None = None) -> dict[int, tuple[int, int]]:
    """Set-1 scan code → (row, col) on a keyboard of `shape`; the setting when None."""
    return {**_SHARED_GRID, 0x2B: _CELL_0X2B[shape or config.KEYBOARD_SHAPE]}


# Every position on either shape names one scan code, so a key's scan code
# needs no shape: (3, 12) and (2, 13) both name 0x2B.
_SCAN_CODES: dict[tuple[int, int], int] = {
    **{cell: sc for sc, cell in _SHARED_GRID.items()},
    **{cell: 0x2B for cell in _CELL_0X2B.values()},
}


@dataclass(frozen=True)
class PhysicalKey:
    name: str  # the character it produces unshifted, or "dead-acute", "altgr"
    row: int  # 1 = number row, 2 = top alpha, 3 = home, 4 = bottom alpha
    col: int  # 1-13, left to right

    @property
    def finger(self) -> str:
        return COL_TO_FINGER[self.col]

    @property
    def dead(self) -> bool:
        # From the name, which the reader derives for every dead key
        # (dead_key_name), so a flag and a name can never disagree.
        return self.name.startswith("dead-")

    @property
    def scan_code(self) -> int:
        # Derived, not stored: the position is the key's identity (ADR-033's
        # landing is a row and a column), and the scan code is that position in
        # Windows' numbering, so the two cannot disagree.
        return _SCAN_CODES[(self.row, self.col)]

    @property
    def side(self) -> str:
        return "L" if self.col <= 5 else "R"


@dataclass(frozen=True)
class Grapheme:
    char: str
    mechanism: Literal["direct", "dead-key", "altgr-chord"]
    prereq_keys: tuple[str, ...]
    keystrokes: int = 1
    base: str | None = None
    dead_key: str | None = None


@dataclass
class Layout:
    lang: str
    keys: dict[str, PhysicalKey]  # name → PhysicalKey
    graphemes: dict[str, Grapheme]  # char → Grapheme


def key_positions(layout: Layout) -> dict[str, tuple[int, int]]:
    """Every physical key as name → (row, col)."""
    return {name: (key.row, key.col) for name, key in layout.keys.items()}


def letters_by_position(layout: Layout) -> dict[tuple[int, int], str]:
    """(row, col) → letter, for every cell that carries one."""
    # `keys` also holds every punctuation and digit cell (ADR-026, 2026-11-01),
    # so anything that looks a letter up by position asks this.
    return {
        (key.row, key.col): name for name, key in layout.keys.items() if name in layout.graphemes
    }


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


def cell_of(layout: Layout, char: str) -> tuple[int, int] | None:
    """The cell a press of `char` came from, or None if it is no cell of `layout`.

    A dead key is a cell like any other (ADR-033: a rest key in every
    language). Today's key source hands its press over as the character it
    produces on its own, the Icelandic acute accent, which names the key (#12m session (7)).
    """
    key = layout.keys.get(char) or layout.keys.get(dead_key_name(char))
    return None if key is None else (key.row, key.col)


def curriculum_positions(layout: Layout) -> dict[str, tuple[int, int]]:
    """Letters, modifiers and dead keys as name → (row, col): what describe_mismatch compares."""
    needed = {key for grapheme in layout.graphemes.values() for key in grapheme.prereq_keys}
    return {
        name: (key.row, key.col) for name, key in layout.keys.items() if name in needed or key.dead
    }


def describe_mismatch(expected: Layout, actual: Layout) -> str | None:
    """None when `actual` can teach `expected`'s curriculum; else why it cannot.

    ADR-006 makes Windows authoritative for the layout ("the app teaches on
    whatever layout Windows reports as active"), so this never overrides what
    the machine reports -- it decides whether the *language* the config asks
    for can be taught on it, and Alpha stops rather than teach a curriculum
    against a keyboard it does not match (ADR-025 § Language and layout must
    agree).

    Position equality, not layout identity: Takki teaches letters and nothing
    else -- no space, no Shift, no punctuation (roadmap § What is deliberately
    never taught). US and UK QWERTY differ only outside that set, so comparing
    KLIDs would reject a UK keyboard that types the English curriculum
    perfectly. What matters is whether the same characters sit in the same
    places. For the same reason the cells that carry neither a letter nor a
    dead key are not compared (ADR-026, 2026-11-01): they are rest keys, never
    typing targets, and UK's `#` against US's `\\` must not stop startup.
    """
    if expected.lang != actual.lang:
        return (
            f"language {expected.lang!r} is configured but the active keyboard is {actual.lang!r}"
        )
    want, have = curriculum_positions(expected), curriculum_positions(actual)
    if want == have:
        return None
    missing = sorted(set(want) - set(have))
    extra = sorted(set(have) - set(want))
    moved = sorted(k for k in set(want) & set(have) if want[k] != have[k])
    parts: list[str] = []
    if missing:
        parts.append(f"missing {' '.join(missing)}")
    if extra:
        parts.append(f"unexpected {' '.join(extra)}")
    if moved:
        parts.append(f"moved {' '.join(f'{k}{have[k]}!={want[k]}' for k in moved)}")
    return "; ".join(parts)


def _direct_layout(
    lang: str, direct: dict[str, tuple[int, int]], cells: dict[str, tuple[int, int]]
) -> Layout:
    keys: dict[str, PhysicalKey] = {}
    graphemes: dict[str, Grapheme] = {}
    for char, (row, col) in direct.items():
        keys[char] = PhysicalKey(char, row, col)
        graphemes[char] = Grapheme(char, "direct", (char,), 1)
    for char, (row, col) in cells.items():
        keys[char] = PhysicalKey(char, row, col)
    return Layout(lang=lang, keys=keys, graphemes=graphemes)


# Positions shared by every QWERTY-derived layout in the v1 target set — the
# letters that don't move between US QWERTY and German QWERTZ.
_QWERTY_COMMON: dict[str, tuple[int, int]] = {
    "q": (2, 1),
    "w": (2, 2),
    "e": (2, 3),
    "r": (2, 4),
    "t": (2, 5),
    "u": (2, 7),
    "i": (2, 8),
    "o": (2, 9),
    "p": (2, 10),
    "a": (3, 1),
    "s": (3, 2),
    "d": (3, 3),
    "f": (3, 4),
    "g": (3, 5),
    "h": (3, 6),
    "j": (3, 7),
    "k": (3, 8),
    "l": (3, 9),
    "x": (4, 2),
    "c": (4, 3),
    "v": (4, 4),
    "b": (4, 5),
    "n": (4, 6),
    "m": (4, 7),
}

# The cells that carry neither a letter nor a dead key (ADR-026, 2026-11-01).
# They are rest keys, never typing targets, so they are in `keys` and never in
# `graphemes`. Each is named by the character the key produces unshifted, as
# Windows reports it; tests/test_windows_layout.py pins all three tables to it.
_SHARED_CELLS: dict[str, tuple[int, int]] = {
    **{str(col % 10): (1, col) for col in range(1, 11)},
    ",": (4, 8),
    ".": (4, 9),
}


def build_en(shape: KeyboardShape | None = None) -> Layout:
    """US QWERTY layout — 26 direct lowercase letters, and the other 20 cells."""
    direct: dict[str, tuple[int, int]] = {**_QWERTY_COMMON, "y": (2, 6), "z": (4, 1)}
    cells: dict[str, tuple[int, int]] = {
        **_SHARED_CELLS,
        "-": (1, 11),
        "=": (1, 12),
        "[": (2, 11),
        "]": (2, 12),
        ";": (3, 10),
        "'": (3, 11),
        "\\": scan_code_grid(shape)[0x2B],
        "/": (4, 10),
    }
    return _direct_layout("en", direct, cells)


def build_de(shape: KeyboardShape | None = None) -> Layout:
    """German QWERTZ layout — 26 letters plus ä, ö, ü, ß, and every other cell but one."""
    # The one left out is the dead acute at (1, 12): declaring it is roadmap
    # § C17's fix, and since describe_mismatch compares dead keys it would make
    # German startable with a curriculum nobody has decided.
    direct: dict[str, tuple[int, int]] = {
        **_QWERTY_COMMON,
        "z": (2, 6),
        "y": (4, 1),
        "ü": (2, 11),
        "ö": (3, 10),
        "ä": (3, 11),
        "ß": (1, 11),
    }
    cells: dict[str, tuple[int, int]] = {
        **_SHARED_CELLS,
        "+": (2, 12),
        "#": scan_code_grid(shape)[0x2B],
        "-": (4, 10),
    }
    return _direct_layout("de", direct, cells)


# Icelandic: æ takes the right-pinky home position, the acute dead key sits
# outboard of it, and ö is pushed onto the number row.
_ICELANDIC_ACUTES: dict[str, str] = {
    "á": "a",
    "é": "e",
    "í": "i",
    "ó": "o",
    "ú": "u",
    "ý": "y",
}


def build_is(shape: KeyboardShape | None = None) -> Layout:
    """Icelandic layout — direct letters, the six dead-acute composites, and every other cell."""
    direct: dict[str, tuple[int, int]] = {
        **_QWERTY_COMMON,
        "y": (2, 6),
        "z": (4, 1),
        "ð": (2, 11),
        "æ": (3, 10),
        "þ": (4, 10),
        "ö": (1, 11),
    }
    cells: dict[str, tuple[int, int]] = {
        **_SHARED_CELLS,
        "-": (1, 12),
        "'": (2, 12),
        "+": scan_code_grid(shape)[0x2B],
    }
    layout = _direct_layout("is", direct, cells)
    layout.keys["dead-acute"] = PhysicalKey("dead-acute", 3, 11)
    for composed, base in _ICELANDIC_ACUTES.items():
        layout.graphemes[composed] = Grapheme(
            composed, "dead-key", ("dead-acute", base), 2, base=base, dead_key="dead-acute"
        )
    return layout
