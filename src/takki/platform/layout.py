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


def key_positions(layout: Layout) -> dict[str, tuple[int, int]]:
    """Every physical key as name → (row, col). The comparable shape of a layout."""
    return {name: (key.row, key.col) for name, key in layout.keys.items()}


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
    places.
    """
    if expected.lang != actual.lang:
        return (
            f"language {expected.lang!r} is configured but the active keyboard is {actual.lang!r}"
        )
    want, have = key_positions(expected), key_positions(actual)
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
