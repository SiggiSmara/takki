from dataclasses import dataclass
from typing import Literal

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


@dataclass(frozen=True)
class PhysicalKey:
    name: str  # character it produces, or modifier name ("altgr", "dead-acute")
    row: int  # 1 = number row, 2 = top alpha, 3 = home, 4 = bottom alpha
    col: int  # 1-13, left to right

    @property
    def finger(self) -> str:
        return COL_TO_FINGER[self.col]

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


def _direct_layout(lang: str, direct: dict[str, tuple[int, int]]) -> Layout:
    keys: dict[str, PhysicalKey] = {}
    graphemes: dict[str, Grapheme] = {}
    for char, (row, col) in direct.items():
        keys[char] = PhysicalKey(char, row, col)
        graphemes[char] = Grapheme(char, "direct", (char,), 1)
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


def build_en() -> Layout:
    """US QWERTY layout — 26 direct lowercase letters."""
    direct: dict[str, tuple[int, int]] = {**_QWERTY_COMMON, "y": (2, 6), "z": (4, 1)}
    return _direct_layout("en", direct)


def build_de() -> Layout:
    """German QWERTZ layout — 26 direct lowercase letters plus ä, ö, ü, ß."""
    direct: dict[str, tuple[int, int]] = {
        **_QWERTY_COMMON,
        "z": (2, 6),
        "y": (4, 1),
        "ü": (2, 11),
        "ö": (3, 10),
        "ä": (3, 11),
        "ß": (1, 11),
    }
    return _direct_layout("de", direct)


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


def build_is() -> Layout:
    """Icelandic layout — direct letters plus the six dead-acute composites."""
    direct: dict[str, tuple[int, int]] = {
        **_QWERTY_COMMON,
        "y": (2, 6),
        "z": (4, 1),
        "ð": (2, 11),
        "æ": (3, 10),
        "þ": (4, 10),
        "ö": (1, 11),
    }
    layout = _direct_layout("is", direct)
    layout.keys["dead-acute"] = PhysicalKey("dead-acute", 3, 11)
    for composed, base in _ICELANDIC_ACUTES.items():
        layout.graphemes[composed] = Grapheme(
            composed, "dead-key", ("dead-acute", base), 2, base=base, dead_key="dead-acute"
        )
    return layout
