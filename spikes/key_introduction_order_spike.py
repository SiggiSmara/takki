"""
Spike: key introduction order — algorithms × languages × composite mechanisms

For each of nine languages, computes the order in which keys would be
introduced under four different rules, then evaluates two coverage curves
(per-keystroke and per-grapheme) and emits a draft YAML preset.

Languages (9):
  en  US QWERTY              direct only
  de  German QWERTZ           direct only (pre-composed ä/ö/ü/ß)
  fi  Finnish                 direct only (pre-composed å/ä/ö)
  is  Icelandic               direct (þ/ð/æ/ö) + dead-key acute (á/é/í/ó/ú/ý)
  fr  French AZERTY           direct (é/è/ç/à/ù) + dead-key ^ and ¨
  es  Spanish ISO             direct (ñ) + dead-key acute (á/é/í/ó/ú) and ¨ (ü)
  cs  Czech QWERTZ            direct on number row (ě/š/č/ř/ž/ý/á/í/é/ú/ů)
  pl  Polish Programmers      AltGr-chord (ą/ć/ę/ł/ń/ó/ś/ź/ż)
  lv  Latvian LVS 24-93       dual mechanism — generated twice: AltGr vs dead-key

Algorithms (all share a fixed home-row anchor phase per ADR-023):
  A  SYMMETRIC PAIRS       post-home physical-position symmetric pairs, then
                           remaining keys swept by aggregate frequency.
  B  PURE FREQUENCY        post-home single-key by aggregate frequency.
  C  FREQ-LEADER-PER-HAND  post-home top-remaining left + right per step.
  D  COVERAGE-GREEDY       post-home pick key with highest marginal coverage
                           gain — newly-typeable grapheme frequency given
                           currently-known keys.
  E  COVERAGE-PER-HAND     coverage-greedy constrained to one pick per hand
                           per round. Included to test whether D's milestone
                           advantage over C is the dynamic scoring or just
                           the relaxed hand-balance constraint.

C is the chosen algorithm (per ADR-023, re-confirmed by this spike). D
reaches milestones 1–3 steps earlier than C on most languages, but E (same
scoring as D, hand-balanced like C) ties C in ~18 of 20 measured milestone
cells across nine layouts — proving D's advantage was hand imbalance, not
smarter selection. C's parallel motor development is therefore not paid for
in coverage; it is genuinely free.

Data model:
  PhysicalKey   single keystroke unit (letter, dead-key, AltGr modifier).
  Grapheme      a letter as it appears in text — direct, dead-key composite
                (2 strokes), or AltGr chord (1 stroke). Typeable when all
                prereq physical keys are known.

Coverage curves:
  per-grapheme    each typeable grapheme contributes its frequency once.
  per-keystroke   weighted by keystrokes (dead-key composites cost 2). Gap
                  between curves quantifies motor cost of composites.

Outputs:
  Tables to stdout.
  spikes/results/key_introduction_order_spike_results.txt
  spikes/results/key_intro_{lang}.yaml — DRAFT preset per language.

Run from repo root:
    uv run python spikes/key_introduction_order_spike.py
"""

import sys
from collections import defaultdict
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path

from wordfreq import get_frequency_dict


# ---------------------------------------------------------------- fingers --

L_PINK, L_RING, L_MID, L_IDX = "L-pink", "L-ring", "L-mid", "L-idx"
R_IDX, R_MID, R_RING, R_PINK = "R-idx", "R-mid", "R-ring", "R-pink"

ALL_FINGERS = [L_PINK, L_RING, L_MID, L_IDX, R_IDX, R_MID, R_RING, R_PINK]
LEFT_FINGERS = {L_PINK, L_RING, L_MID, L_IDX}
RIGHT_FINGERS = {R_IDX, R_MID, R_RING, R_PINK}

COL_TO_FINGER = {
    1: L_PINK, 2: L_RING, 3: L_MID,
    4: L_IDX,   # left-index home
    5: L_IDX,   # left-index right-stretch
    6: R_IDX,   # right-index left-stretch
    7: R_IDX,   # right-index home
    8: R_MID, 9: R_RING, 10: R_PINK,
    11: R_PINK, 12: R_PINK, 13: R_PINK,
}


def finger_for_col(col: int) -> str:
    return COL_TO_FINGER[col]


# ---------------------------------------------------------- home-row plan --

HOME_ROW_PAIRS = [(4, 7), (3, 8), (2, 9), (1, 10)]   # FJ, DK, SL, A+pinky
HOME_ROW_STRETCH = (5, 6)                             # G + H positions

# Post-home symmetric-pair sequence by (row, left_col, right_col).
POST_HOME_SYMMETRIC = [
    (2, 4, 7), (2, 3, 8), (2, 2, 9), (2, 1, 10),  # row 2 home pairs
    (2, 5, 6),                                      # row 2 stretches
    (4, 4, 7), (4, 3, 8), (4, 2, 9), (4, 1, 10),  # row 4 home pairs
    (4, 5, 6),                                      # row 4 stretches
]


# ------------------------------------------------------------ data model --

@dataclass(frozen=True)
class PhysicalKey:
    name: str
    row: int
    col: int

    @property
    def finger(self) -> str:
        return finger_for_col(self.col)

    @property
    def side(self) -> str:
        return "L" if self.finger in LEFT_FINGERS else "R"


@dataclass(frozen=True)
class Grapheme:
    char: str
    mechanism: str                  # 'direct' | 'dead-key' | 'altgr-chord'
    prereq_keys: tuple[str, ...]    # PhysicalKey names that must be known
    keystrokes: int = 1
    base: str | None = None         # base letter for composites
    dead_key: str | None = None     # dead-key name for dead-key composites


@dataclass
class Layout:
    lang: str
    name: str
    keys: dict[str, PhysicalKey]    # name -> PhysicalKey
    graphemes: dict[str, Grapheme]  # char -> Grapheme


# ------------------------------------------------------- layout builders --

def _direct(char: str, row: int, col: int) -> tuple[PhysicalKey, Grapheme]:
    return (PhysicalKey(char, row, col),
            Grapheme(char, "direct", (char,), 1))


def _modifier(name: str, row: int, col: int) -> PhysicalKey:
    return PhysicalKey(name, row, col)


def _deadkey_grapheme(char: str, base: str, dead_name: str) -> Grapheme:
    return Grapheme(char, "dead-key", (dead_name, base), 2,
                    base=base, dead_key=dead_name)


def _altgr_grapheme(char: str, base: str) -> Grapheme:
    return Grapheme(char, "altgr-chord", ("altgr", base), 1, base=base)


def _layout_from_direct_table(lang: str, name: str,
                              direct: dict[str, tuple[int, int]],
                              modifiers: list[PhysicalKey] | None = None,
                              composites: list[Grapheme] | None = None) -> Layout:
    keys: dict[str, PhysicalKey] = {}
    graphemes: dict[str, Grapheme] = {}
    for c, (r, k) in direct.items():
        pk, g = _direct(c, r, k)
        keys[pk.name] = pk
        graphemes[g.char] = g
    for m in modifiers or []:
        keys[m.name] = m
    for g in composites or []:
        graphemes[g.char] = g
    return Layout(lang=lang, name=name, keys=keys, graphemes=graphemes)


def build_en() -> Layout:
    # US QWERTY
    direct = {
        "q": (2, 1), "w": (2, 2), "e": (2, 3), "r": (2, 4), "t": (2, 5),
        "y": (2, 6), "u": (2, 7), "i": (2, 8), "o": (2, 9), "p": (2, 10),
        "a": (3, 1), "s": (3, 2), "d": (3, 3), "f": (3, 4), "g": (3, 5),
        "h": (3, 6), "j": (3, 7), "k": (3, 8), "l": (3, 9),
        "z": (4, 1), "x": (4, 2), "c": (4, 3), "v": (4, 4), "b": (4, 5),
        "n": (4, 6), "m": (4, 7),
    }
    return _layout_from_direct_table("en", "US QWERTY", direct)


def build_de() -> Layout:
    # German QWERTZ — pre-composed ä, ö, ü, ß
    direct = {
        "q": (2, 1), "w": (2, 2), "e": (2, 3), "r": (2, 4), "t": (2, 5),
        "z": (2, 6), "u": (2, 7), "i": (2, 8), "o": (2, 9), "p": (2, 10),
        "ü": (2, 11),
        "a": (3, 1), "s": (3, 2), "d": (3, 3), "f": (3, 4), "g": (3, 5),
        "h": (3, 6), "j": (3, 7), "k": (3, 8), "l": (3, 9),
        "ö": (3, 10), "ä": (3, 11),
        "y": (4, 1), "x": (4, 2), "c": (4, 3), "v": (4, 4), "b": (4, 5),
        "n": (4, 6), "m": (4, 7),
        "ß": (1, 11),
    }
    return _layout_from_direct_table("de", "German QWERTZ", direct)


def build_fi() -> Layout:
    # Finnish — å/ä/ö pre-composed, no dead-key composites in core orthography.
    direct = {
        "q": (2, 1), "w": (2, 2), "e": (2, 3), "r": (2, 4), "t": (2, 5),
        "y": (2, 6), "u": (2, 7), "i": (2, 8), "o": (2, 9), "p": (2, 10),
        "å": (2, 11),
        "a": (3, 1), "s": (3, 2), "d": (3, 3), "f": (3, 4), "g": (3, 5),
        "h": (3, 6), "j": (3, 7), "k": (3, 8), "l": (3, 9),
        "ö": (3, 10), "ä": (3, 11),
        "z": (4, 1), "x": (4, 2), "c": (4, 3), "v": (4, 4), "b": (4, 5),
        "n": (4, 6), "m": (4, 7),
    }
    return _layout_from_direct_table("fi", "Finnish", direct)


def build_is() -> Layout:
    # Icelandic ISO — pre-composed þ/ð/æ/ö, dead-acute for á/é/í/ó/ú/ý.
    direct = {
        "q": (2, 1), "w": (2, 2), "e": (2, 3), "r": (2, 4), "t": (2, 5),
        "y": (2, 6), "u": (2, 7), "i": (2, 8), "o": (2, 9), "p": (2, 10),
        "ð": (2, 11),
        "a": (3, 1), "s": (3, 2), "d": (3, 3), "f": (3, 4), "g": (3, 5),
        "h": (3, 6), "j": (3, 7), "k": (3, 8), "l": (3, 9),
        "æ": (3, 10),
        "z": (4, 1), "x": (4, 2), "c": (4, 3), "v": (4, 4), "b": (4, 5),
        "n": (4, 6), "m": (4, 7),
        "þ": (1, 1),
        "ö": (1, 11),
    }
    modifiers = [_modifier("dead-acute", 2, 12)]  # right-pinky stretch
    composites = [
        _deadkey_grapheme("á", "a", "dead-acute"),
        _deadkey_grapheme("é", "e", "dead-acute"),
        _deadkey_grapheme("í", "i", "dead-acute"),
        _deadkey_grapheme("ó", "o", "dead-acute"),
        _deadkey_grapheme("ú", "u", "dead-acute"),
        _deadkey_grapheme("ý", "y", "dead-acute"),
    ]
    return _layout_from_direct_table("is", "Icelandic ISO", direct,
                                     modifiers, composites)


def build_pl() -> Layout:
    # Polish Programmers — base QWERTY + AltGr-chord composites.
    direct = {
        "q": (2, 1), "w": (2, 2), "e": (2, 3), "r": (2, 4), "t": (2, 5),
        "y": (2, 6), "u": (2, 7), "i": (2, 8), "o": (2, 9), "p": (2, 10),
        "a": (3, 1), "s": (3, 2), "d": (3, 3), "f": (3, 4), "g": (3, 5),
        "h": (3, 6), "j": (3, 7), "k": (3, 8), "l": (3, 9),
        "z": (4, 1), "x": (4, 2), "c": (4, 3), "v": (4, 4), "b": (4, 5),
        "n": (4, 6), "m": (4, 7),
    }
    # AltGr key — physically the right-thumb / right-pinky region. Modelled at
    # col 11 R-pinky stretch since the right pinky reaches the modifier in
    # touch-typing posture (right thumb holds spacebar).
    modifiers = [_modifier("altgr", 4, 11)]
    composites = [
        _altgr_grapheme("ą", "a"),
        _altgr_grapheme("ć", "c"),
        _altgr_grapheme("ę", "e"),
        _altgr_grapheme("ł", "l"),
        _altgr_grapheme("ń", "n"),
        _altgr_grapheme("ó", "o"),
        _altgr_grapheme("ś", "s"),
        _altgr_grapheme("ź", "x"),  # programmers layout: AltGr+X → ź
        _altgr_grapheme("ż", "z"),
    ]
    return _layout_from_direct_table("pl", "Polish Programmers", direct,
                                     modifiers, composites)


def build_fr() -> Layout:
    # French AZERTY — pre-composed é/è/ç/à on row 1, ù on row 3, plus
    # dead-circumflex (^) and dead-diaeresis (¨) at row 2 col 11.
    direct = {
        # Number row pre-composed
        "é": (1, 2), "è": (1, 7), "ç": (1, 9), "à": (1, 10),
        # Row 2 — AZERTY positions
        "a": (2, 1), "z": (2, 2), "e": (2, 3), "r": (2, 4), "t": (2, 5),
        "y": (2, 6), "u": (2, 7), "i": (2, 8), "o": (2, 9), "p": (2, 10),
        # Row 3
        "q": (3, 1), "s": (3, 2), "d": (3, 3), "f": (3, 4), "g": (3, 5),
        "h": (3, 6), "j": (3, 7), "k": (3, 8), "l": (3, 9), "m": (3, 10),
        "ù": (3, 11),
        # Row 4
        "w": (4, 1), "x": (4, 2), "c": (4, 3), "v": (4, 4), "b": (4, 5),
        "n": (4, 6),
    }
    modifiers = [
        _modifier("dead-circ", 2, 11),   # ^/¨ key
        _modifier("dead-diaer", 2, 11),  # shift-^ — same physical key but
                                          # we model as a distinct modifier
    ]
    composites = [
        _deadkey_grapheme("â", "a", "dead-circ"),
        _deadkey_grapheme("ê", "e", "dead-circ"),
        _deadkey_grapheme("î", "i", "dead-circ"),
        _deadkey_grapheme("ô", "o", "dead-circ"),
        _deadkey_grapheme("û", "u", "dead-circ"),
        _deadkey_grapheme("ë", "e", "dead-diaer"),
        _deadkey_grapheme("ï", "i", "dead-diaer"),
        _deadkey_grapheme("ü", "u", "dead-diaer"),
    ]
    return _layout_from_direct_table("fr", "French AZERTY", direct,
                                     modifiers, composites)


def build_es() -> Layout:
    # Spanish ISO — pre-composed ñ, dead-acute for áéíóú, dead-diaer for ü.
    direct = {
        "q": (2, 1), "w": (2, 2), "e": (2, 3), "r": (2, 4), "t": (2, 5),
        "y": (2, 6), "u": (2, 7), "i": (2, 8), "o": (2, 9), "p": (2, 10),
        "a": (3, 1), "s": (3, 2), "d": (3, 3), "f": (3, 4), "g": (3, 5),
        "h": (3, 6), "j": (3, 7), "k": (3, 8), "l": (3, 9),
        "ñ": (3, 10),
        "z": (4, 1), "x": (4, 2), "c": (4, 3), "v": (4, 4), "b": (4, 5),
        "n": (4, 6), "m": (4, 7),
    }
    modifiers = [
        _modifier("dead-acute", 3, 11),
        _modifier("dead-diaer", 3, 11),  # shift form of same key
    ]
    composites = [
        _deadkey_grapheme("á", "a", "dead-acute"),
        _deadkey_grapheme("é", "e", "dead-acute"),
        _deadkey_grapheme("í", "i", "dead-acute"),
        _deadkey_grapheme("ó", "o", "dead-acute"),
        _deadkey_grapheme("ú", "u", "dead-acute"),
        _deadkey_grapheme("ü", "u", "dead-diaer"),
    ]
    return _layout_from_direct_table("es", "Spanish ISO", direct,
                                     modifiers, composites)


def build_cs() -> Layout:
    # Czech QWERTZ — most lowercase accented letters pre-composed on the
    # number row. Dead-acute on row 2 col 11. Lowercase ó has no own key and
    # requires dead-acute + o; all other lowercase accents are direct.
    direct = {
        # Number row pre-composed (in place of digits 2-0 + others)
        "ě": (1, 2), "š": (1, 3), "č": (1, 4), "ř": (1, 5), "ž": (1, 6),
        "ý": (1, 7), "á": (1, 8), "í": (1, 9), "é": (1, 10),
        # Row 2 — QWERTZ swaps Y and Z
        "q": (2, 1), "w": (2, 2), "e": (2, 3), "r": (2, 4), "t": (2, 5),
        "z": (2, 6), "u": (2, 7), "i": (2, 8), "o": (2, 9), "p": (2, 10),
        "ú": (2, 11),
        # Row 3
        "a": (3, 1), "s": (3, 2), "d": (3, 3), "f": (3, 4), "g": (3, 5),
        "h": (3, 6), "j": (3, 7), "k": (3, 8), "l": (3, 9),
        "ů": (3, 10),
        # Row 4
        "y": (4, 1), "x": (4, 2), "c": (4, 3), "v": (4, 4), "b": (4, 5),
        "n": (4, 6), "m": (4, 7),
    }
    # Dead-acute (rare in lowercase Czech — needed for ó only) and dead-caron
    # (uppercase only — skip for lowercase-only spike).
    modifiers = [_modifier("dead-acute", 2, 12)]
    composites = [
        _deadkey_grapheme("ó", "o", "dead-acute"),
    ]
    return _layout_from_direct_table("cs", "Czech QWERTZ", direct,
                                     modifiers, composites)


def build_lv_altgr() -> Layout:
    # Latvian LVS 24-93 — AltGr-path variant.
    direct = {
        "q": (2, 1), "w": (2, 2), "e": (2, 3), "r": (2, 4), "t": (2, 5),
        "y": (2, 6), "u": (2, 7), "i": (2, 8), "o": (2, 9), "p": (2, 10),
        "a": (3, 1), "s": (3, 2), "d": (3, 3), "f": (3, 4), "g": (3, 5),
        "h": (3, 6), "j": (3, 7), "k": (3, 8), "l": (3, 9),
        "z": (4, 1), "x": (4, 2), "c": (4, 3), "v": (4, 4), "b": (4, 5),
        "n": (4, 6), "m": (4, 7),
    }
    modifiers = [_modifier("altgr", 4, 11)]
    # Latvian diacritics: ā č ē ģ ī ķ ļ ņ š ū ž (no ō or ŗ in modern usage).
    composites = [
        _altgr_grapheme("ā", "a"),
        _altgr_grapheme("č", "c"),
        _altgr_grapheme("ē", "e"),
        _altgr_grapheme("ģ", "g"),
        _altgr_grapheme("ī", "i"),
        _altgr_grapheme("ķ", "k"),
        _altgr_grapheme("ļ", "l"),
        _altgr_grapheme("ņ", "n"),
        _altgr_grapheme("š", "s"),
        _altgr_grapheme("ū", "u"),
        _altgr_grapheme("ž", "z"),
    ]
    return _layout_from_direct_table("lv", "Latvian LVS 24-93 (AltGr path)",
                                     direct, modifiers, composites)


def build_lv_deadkey() -> Layout:
    # Latvian LVS 24-93 — dead-key path variant.
    direct = {
        "q": (2, 1), "w": (2, 2), "e": (2, 3), "r": (2, 4), "t": (2, 5),
        "y": (2, 6), "u": (2, 7), "i": (2, 8), "o": (2, 9), "p": (2, 10),
        "a": (3, 1), "s": (3, 2), "d": (3, 3), "f": (3, 4), "g": (3, 5),
        "h": (3, 6), "j": (3, 7), "k": (3, 8), "l": (3, 9),
        "z": (4, 1), "x": (4, 2), "c": (4, 3), "v": (4, 4), "b": (4, 5),
        "n": (4, 6), "m": (4, 7),
    }
    # Latvian uses three diacritic dead-keys: macron (ā/ē/ī/ū), caron
    # (č/š/ž), and cedilla-comma (ģ/ķ/ļ/ņ).
    modifiers = [
        _modifier("dead-macron", 2, 12),
        _modifier("dead-caron", 2, 13),
        _modifier("dead-cedilla", 3, 12),
    ]
    composites = [
        _deadkey_grapheme("ā", "a", "dead-macron"),
        _deadkey_grapheme("ē", "e", "dead-macron"),
        _deadkey_grapheme("ī", "i", "dead-macron"),
        _deadkey_grapheme("ū", "u", "dead-macron"),
        _deadkey_grapheme("č", "c", "dead-caron"),
        _deadkey_grapheme("š", "s", "dead-caron"),
        _deadkey_grapheme("ž", "z", "dead-caron"),
        _deadkey_grapheme("ģ", "g", "dead-cedilla"),
        _deadkey_grapheme("ķ", "k", "dead-cedilla"),
        _deadkey_grapheme("ļ", "l", "dead-cedilla"),
        _deadkey_grapheme("ņ", "n", "dead-cedilla"),
    ]
    return _layout_from_direct_table("lv", "Latvian LVS 24-93 (dead-key path)",
                                     direct, modifiers, composites)


LAYOUT_BUILDERS = {
    "en": [build_en],
    "de": [build_de],
    "fi": [build_fi],
    "is": [build_is],
    "fr": [build_fr],
    "es": [build_es],
    "cs": [build_cs],
    "pl": [build_pl],
    "lv": [build_lv_altgr, build_lv_deadkey],
}


# ----------------------------------------------------- frequency analysis --

def grapheme_frequencies(freq_dict: dict, layout: Layout) -> dict[str, float]:
    """Frequency-weighted occurrence of each grapheme in the language corpus.

    Restricts the corpus to alphabetic words ≥3 chars whose lower-cased
    character set is a subset of the layout's typeable graphemes.
    """
    char_set = frozenset(layout.graphemes.keys())
    weight: dict[str, float] = defaultdict(float)
    for w, f in freq_dict.items():
        if not w.isalpha() or len(w) < 3:
            continue
        wlow = w.lower()
        chars = frozenset(wlow)
        if not chars <= char_set:
            continue
        for c in chars:
            weight[c] += f
    return dict(weight)


def native_layout(freq_dict: dict, layout: Layout,
                  threshold: float = 0.001) -> Layout:
    """Filter graphemes to those exceeding the native-alphabet threshold."""
    g_freq = grapheme_frequencies(freq_dict, layout)
    total = sum(g_freq.values()) or 1.0

    native_graphemes = {
        c: g for c, g in layout.graphemes.items()
        if g_freq.get(c, 0.0) / total >= threshold
    }
    # Keep all physical keys that any kept grapheme depends on.
    needed_keys: set[str] = set()
    for g in native_graphemes.values():
        for k in g.prereq_keys:
            needed_keys.add(k)
    native_keys = {n: k for n, k in layout.keys.items() if n in needed_keys}
    # Always keep home-row physical keys at cols 1-10 even if a letter happens
    # not to clear the threshold — phase-1 anchoring is universal.
    for n, k in layout.keys.items():
        if k.row == 3 and 1 <= k.col <= 10:
            native_keys[n] = k
            # If this key is a direct letter with a grapheme, keep that too.
            if n in layout.graphemes and layout.graphemes[n].mechanism == "direct":
                native_graphemes[n] = layout.graphemes[n]

    return Layout(lang=layout.lang, name=layout.name,
                  keys=native_keys, graphemes=native_graphemes)


def key_aggregate_freq(key_name: str, layout: Layout,
                       g_freq: dict[str, float]) -> float:
    """For ranking: sum of grapheme frequencies that depend on this key."""
    total = 0.0
    for g in layout.graphemes.values():
        if key_name in g.prereq_keys:
            total += g_freq.get(g.char, 0.0)
    return total


# ----------------------------------------------------------- coverage --

@dataclass
class CorpusIndex:
    """Precomputed word data for fast coverage queries.

    word_prereqs[i]    frozenset of physical keys needed to type word i
    word_freq[i]       wordfreq frequency
    word_penalty[i]    len(word) / total_keystrokes — penalises composite-heavy
                       words in the per-keystroke curve
    key_to_words[k]    indices of words that depend on key k
    total              sum of all word_freq (denominator for coverage %)
    """
    word_prereqs: list[frozenset[str]]
    word_freq: list[float]
    word_penalty: list[float]
    key_to_words: dict[str, list[int]]
    total: float


def build_corpus_index(layout: Layout, freq_dict: dict) -> CorpusIndex:
    char_set = frozenset(layout.graphemes.keys())
    prereqs_list: list[frozenset[str]] = []
    freq_list: list[float] = []
    penalty_list: list[float] = []
    key_to_words: dict[str, list[int]] = defaultdict(list)
    total = 0.0
    for w, f in freq_dict.items():
        if not w.isalpha() or len(w) < 3:
            continue
        wlow = w.lower()
        if not frozenset(wlow) <= char_set:
            continue
        prereqs = frozenset(
            k for c in wlow for k in layout.graphemes[c].prereq_keys
        )
        strokes = sum(layout.graphemes[c].keystrokes for c in wlow)
        penalty = len(wlow) / strokes
        idx = len(prereqs_list)
        prereqs_list.append(prereqs)
        freq_list.append(f)
        penalty_list.append(penalty)
        for k in prereqs:
            key_to_words[k].append(idx)
        total += f
    return CorpusIndex(prereqs_list, freq_list, penalty_list,
                       dict(key_to_words), total or 1.0)


def typeable_now(known: set[str], layout: Layout) -> set[str]:
    return {c for c, g in layout.graphemes.items()
            if all(k in known for k in g.prereq_keys)}


def coverage_curves(key_order: list[str],
                    corpus: CorpusIndex) -> tuple[list[float], list[float]]:
    """Returns (per_grapheme_curve, per_keystroke_curve) for given key order.

    Incremental: each new key updates per-word missing counts; words flip to
    typeable when their count hits zero. O(W + Σ|prereqs|) total, not O(W·K).
    """
    word_missing = [len(p) for p in corpus.word_prereqs]
    known: set[str] = set()
    per_grapheme: list[float] = []
    per_keystroke: list[float] = []
    cum_g = 0.0
    cum_k = 0.0
    total = corpus.total
    for step_key in key_order:
        if step_key not in known:
            known.add(step_key)
            for wi in corpus.key_to_words.get(step_key, ()):
                if word_missing[wi] > 0:
                    word_missing[wi] -= 1
                    if word_missing[wi] == 0:
                        cum_g += corpus.word_freq[wi]
                        cum_k += corpus.word_freq[wi] * corpus.word_penalty[wi]
        per_grapheme.append(cum_g / total)
        per_keystroke.append(cum_k / total)
    return per_grapheme, per_keystroke


# ----------------------------------------------------------- algorithms --

def is_letter_key(name: str, layout: Layout) -> bool:
    """True iff this physical key produces a direct grapheme (i.e. a letter,
    not a modifier such as 'altgr' or 'dead-acute')."""
    g = layout.graphemes.get(name)
    return g is not None and g.mechanism == "direct"


def home_row_order(layout: Layout) -> list[str]:
    """Universal home-row anchor — symmetric pairs by physical column.

    Only letter keys are anchored here. Modifiers (AltGr, dead keys) — even
    if their physical position happens to fall on row 3 — are introduced
    later by the post-home algorithm, since 'home row anchoring' as a motor
    concept applies to letters, not modifier keys.
    """
    used: set[str] = set()
    out: list[str] = []

    def take_at(row: int, col: int) -> None:
        for n, k in layout.keys.items():
            if (k.row == row and k.col == col and n not in used
                    and is_letter_key(n, layout)):
                out.append(n)
                used.add(n)
                return

    for lc, rc in HOME_ROW_PAIRS:
        take_at(3, lc)
        take_at(3, rc)
    for c in HOME_ROW_STRETCH:
        take_at(3, c)
    # Extras on row 3 at cols > 10 (German Ä, Icelandic Æ at col 10 is already
    # caught by the pinky pair).
    for n, k in sorted(layout.keys.items(), key=lambda kv: kv[1].col):
        if (k.row == 3 and n not in used and is_letter_key(n, layout)):
            out.append(n)
            used.add(n)
    return out


def algo_symmetric(layout: Layout, g_freq: dict[str, float]) -> list[str]:
    out = home_row_order(layout)
    used = set(out)

    def take_at(row: int, col: int) -> None:
        for n, k in layout.keys.items():
            if k.row == row and k.col == col and n not in used:
                out.append(n)
                used.add(n)
                return

    for row, lc, rc in POST_HOME_SYMMETRIC:
        take_at(row, lc)
        take_at(row, rc)
    remaining = sorted(
        [n for n in layout.keys if n not in used],
        key=lambda n: -key_aggregate_freq(n, layout, g_freq),
    )
    out.extend(remaining)
    return out


def algo_pure_freq(layout: Layout, g_freq: dict[str, float]) -> list[str]:
    out = home_row_order(layout)
    used = set(out)
    remaining = sorted(
        [n for n in layout.keys if n not in used],
        key=lambda n: -key_aggregate_freq(n, layout, g_freq),
    )
    out.extend(remaining)
    return out


def algo_freq_per_hand(layout: Layout, g_freq: dict[str, float]) -> list[str]:
    out = home_row_order(layout)
    used = set(out)

    def remaining_on_side(side_fingers: set[str]) -> list[str]:
        return sorted(
            [n for n, k in layout.keys.items()
             if n not in used and k.finger in side_fingers],
            key=lambda n: -key_aggregate_freq(n, layout, g_freq),
        )

    while True:
        left = remaining_on_side(LEFT_FINGERS)
        right = remaining_on_side(RIGHT_FINGERS)
        if not left and not right:
            break
        if left:
            out.append(left[0])
            used.add(left[0])
        if right:
            out.append(right[0])
            used.add(right[0])
    return out


def _score_candidates(word_missing: list[set[str]],
                      corpus: CorpusIndex) -> tuple[dict, dict]:
    """Marginal-coverage scoring for every key with missing prereqs.

    Returns (unlock_gain, contrib): unlock_gain[k] = freq sum of words that
    would be fully typeable if k is added now; contrib[k] = shared partial
    credit from words still missing 2+ prereqs.
    """
    unlock_gain: dict[str, float] = defaultdict(float)
    contrib: dict[str, float] = defaultdict(float)
    for wi, missing in enumerate(word_missing):
        if not missing:
            continue
        f = corpus.word_freq[wi]
        if len(missing) == 1:
            unlock_gain[next(iter(missing))] += f
        else:
            share = f / len(missing)
            for cand in missing:
                contrib[cand] += share
    return unlock_gain, contrib


def _coverage_pick(candidates: list[str], unlock_gain: dict,
                   contrib: dict, layout: Layout) -> str:
    return max(candidates,
               key=lambda c: (unlock_gain[c], contrib[c],
                              -layout.keys[c].row, -layout.keys[c].col))


def algo_coverage_greedy(layout: Layout, corpus: CorpusIndex) -> list[str]:
    """At each step, pick the unknown key whose addition would yield the
    largest *new* coverage. No hand-balance constraint."""
    out = home_row_order(layout)
    known = set(out)
    word_missing: list[set[str]] = [set(p - known) for p in corpus.word_prereqs]

    while True:
        candidates = [n for n in layout.keys if n not in known]
        if not candidates:
            break
        unlock_gain, contrib = _score_candidates(word_missing, corpus)
        best = _coverage_pick(candidates, unlock_gain, contrib, layout)
        out.append(best)
        known.add(best)
        for wi in corpus.key_to_words.get(best, ()):
            word_missing[wi].discard(best)
    return out


def algo_coverage_greedy_per_hand(layout: Layout,
                                  corpus: CorpusIndex) -> list[str]:
    """Like coverage-greedy but constrained: each round picks the best
    unknown key from each hand under the *same* score state, mirroring
    algorithm C's hand-balance discipline. Isolates whether the coverage-
    greedy advantage over freq-per-hand is the scoring criterion or the
    relaxed hand-balance constraint."""
    out = home_row_order(layout)
    known = set(out)
    word_missing: list[set[str]] = [set(p - known) for p in corpus.word_prereqs]

    while True:
        candidates = [n for n in layout.keys if n not in known]
        if not candidates:
            break
        unlock_gain, contrib = _score_candidates(word_missing, corpus)
        left = [c for c in candidates
                if layout.keys[c].finger in LEFT_FINGERS]
        right = [c for c in candidates
                 if layout.keys[c].finger in RIGHT_FINGERS]
        picks = []
        if left:
            picks.append(_coverage_pick(left, unlock_gain, contrib, layout))
        if right:
            picks.append(_coverage_pick(right, unlock_gain, contrib, layout))
        if not picks:
            break
        for p in picks:
            out.append(p)
            known.add(p)
            for wi in corpus.key_to_words.get(p, ()):
                word_missing[wi].discard(p)
    return out


ALGORITHMS = {
    "A symmetric pairs": algo_symmetric,
    "B pure frequency": algo_pure_freq,
    "C freq-per-hand": algo_freq_per_hand,
    "D coverage-greedy": algo_coverage_greedy,
    "E coverage-per-hand": algo_coverage_greedy_per_hand,
}

COVERAGE_ALGORITHMS = {"D coverage-greedy", "E coverage-per-hand"}


def run_algorithm(name: str, layout: Layout,
                  corpus: CorpusIndex,
                  g_freq: dict[str, float]) -> list[str]:
    fn = ALGORITHMS[name]
    if name in COVERAGE_ALGORITHMS:
        return fn(layout, corpus)
    return fn(layout, g_freq)


# ------------------------------------------------------------- reporting --

def section(title: str) -> None:
    print(f"\n{'='*78}")
    print(f"  {title}")
    print(f"{'='*78}")


def fmt_key(n: str, layout: Layout) -> str:
    k = layout.keys[n]
    short = n if len(n) <= 12 else n[:11] + "…"
    return f"{short:<12}({k.side},{k.finger.split('-')[1]:<4})"


def print_intro_table(label: str, orders: dict[str, list[str]],
                      layout: Layout,
                      curves: dict[str, tuple[list[float], list[float]]]) -> None:
    section(f"{label} — introduction order  (key (side, finger) cov-grapheme%)")
    algos = list(orders.keys())
    max_len = max(len(o) for o in orders.values())

    header = f"  {'step':>4}  " + "  ".join(f"{a:<32}" for a in algos)
    print(header)
    print("  " + "-" * (len(header) - 2))
    for k in range(max_len):
        row = f"  {k+1:>4}  "
        for a in algos:
            o = orders[a]
            if k < len(o):
                n = o[k]
                cov_g, _ = curves[a]
                cell = f"{fmt_key(n, layout)} {cov_g[k]*100:5.1f}%"
            else:
                cell = ""
            row += f"{cell:<32}  "
        print(row.rstrip())


def print_coverage_milestones(label: str, orders: dict[str, list[str]],
                              curves: dict[str, tuple[list[float], list[float]]]) -> None:
    section(f"{label} — coverage milestones (step at which X% is reached)")
    print(f"  per-grapheme    {'Algorithm':<24}  "
          f"{'10%':>6}{'25%':>6}{'50%':>6}{'75%':>6}{'90%':>6}")
    for a in orders:
        g_curve, _ = curves[a]
        cells = []
        for t in (0.10, 0.25, 0.50, 0.75, 0.90):
            hit = next((i + 1 for i, c in enumerate(g_curve) if c >= t), None)
            cells.append(f"{hit:>6}" if hit else "   n/a")
        print(f"                  {a:<24}  " + "".join(cells))

    print(f"\n  per-keystroke   {'Algorithm':<24}  "
          f"{'10%':>6}{'25%':>6}{'50%':>6}{'75%':>6}{'90%':>6}")
    for a in orders:
        _, k_curve = curves[a]
        cells = []
        for t in (0.10, 0.25, 0.50, 0.75, 0.90):
            hit = next((i + 1 for i, c in enumerate(k_curve) if c >= t), None)
            cells.append(f"{hit:>6}" if hit else "   n/a")
        print(f"                  {a:<24}  " + "".join(cells))


def print_finger_balance(label: str, orders: dict[str, list[str]],
                         layout: Layout, at_step: int) -> None:
    section(f"{label} — physical keys per finger at step {at_step}")
    headers = "  ".join(f"{f.split('-')[1][:4]:>5}" for f in ALL_FINGERS)
    sides = "  L     L     L     L  |  R     R     R     R"
    print(f"  {'Algorithm':<24}  {sides}  total")
    print(f"  {'':<24}  {headers}")
    for a, o in orders.items():
        counts = {f: 0 for f in ALL_FINGERS}
        for n in o[:at_step]:
            counts[layout.keys[n].finger] += 1
        row = (f"  {a:<24}  "
               + "  ".join(f"{counts[f]:>5}" for f in ALL_FINGERS)
               + f"  {sum(counts.values()):>5}")
        print(row)


# ---------------------------------------------------------- YAML output --

def yaml_escape(s: str) -> str:
    if any(c in s for c in ":#-?,[]{}&*!|>'\"%@`") or " " in s:
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
    return s


def write_yaml_draft(out_path: Path, layout: Layout, algorithm: str,
                     order: list[str],
                     curves: tuple[list[float], list[float]]) -> None:
    g_curve, k_curve = curves
    home_keys = set(home_row_order(layout))
    lines: list[str] = []
    lines.append("# DRAFT key-introduction preset — generated by")
    lines.append("# spikes/key_introduction_order_spike.py.")
    lines.append("#")
    lines.append("# Algorithm output, not a reviewed pedagogical sequence.")
    lines.append("# Native-speaker review required before promotion to a")
    lines.append("# real per-language key_intro/{lang}.yaml.")
    lines.append("")
    lines.append(f"language: {layout.lang}")
    lines.append(f"layout: {yaml_escape(layout.name)}")
    lines.append(f"algorithm: {yaml_escape(algorithm)}")
    lines.append("")
    lines.append("phase_1_home_row:")
    home_seq = home_row_order(layout)
    pair_step = 1
    i = 0
    while i < len(home_seq):
        if i + 1 < len(home_seq):
            a, b = home_seq[i], home_seq[i + 1]
            lines.append(f"  - step: {pair_step}")
            lines.append(f"    keys: [{yaml_escape(a)}, {yaml_escape(b)}]")
            lines.append(f"    fingers: [{layout.keys[a].finger}, "
                         f"{layout.keys[b].finger}]")
            i += 2
        else:
            a = home_seq[i]
            lines.append(f"  - step: {pair_step}")
            lines.append(f"    keys: [{yaml_escape(a)}]")
            lines.append(f"    fingers: [{layout.keys[a].finger}]")
            i += 1
        pair_step += 1

    lines.append("")
    lines.append("phase_2_post_home:")
    for idx, n in enumerate(order):
        if n in home_keys:
            continue
        k = layout.keys[n]
        step = idx + 1
        is_modifier = n not in layout.graphemes
        lines.append(f"  - step: {step}")
        if is_modifier:
            lines.append(f"    key: {yaml_escape(n)}")
            lines.append(f"    kind: modifier")
        else:
            g = layout.graphemes[n]
            lines.append(f"    key: {yaml_escape(n)}")
            lines.append(f"    grapheme: {yaml_escape(g.char)}")
            lines.append(f"    mechanism: {g.mechanism}")
        lines.append(f"    finger: {k.finger}")
        lines.append(f"    row: {k.row}")
        lines.append(f"    col: {k.col}")
        lines.append(f"    cov_grapheme: {g_curve[idx]:.3f}")
        lines.append(f"    cov_keystroke: {k_curve[idx]:.3f}")

    # Phase 3: composites unlocked by physical keys already introduced.
    composites_phase = []
    known_so_far: set[str] = set()
    for idx, n in enumerate(order):
        known_so_far.add(n)
        # Composites whose prereqs are now all known and weren't before
        for c, g in layout.graphemes.items():
            if g.mechanism == "direct":
                continue
            if all(k in known_so_far for k in g.prereq_keys):
                # Has it already been emitted?
                if not any(c == entry[0] for entry in composites_phase):
                    composites_phase.append((c, g, idx + 1))

    if composites_phase:
        lines.append("")
        lines.append("phase_3_composites_unlocked:")
        for c, g, unlock_step in composites_phase:
            lines.append(f"  - grapheme: {yaml_escape(c)}")
            lines.append(f"    mechanism: {g.mechanism}")
            lines.append(f"    prereqs: [{', '.join(yaml_escape(p) for p in g.prereq_keys)}]")
            lines.append(f"    keystrokes: {g.keystrokes}")
            lines.append(f"    unlocked_at_step: {unlock_step}")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- main --

def select_winning_algorithm() -> str:
    """Algorithm used for YAML preset emission.

    C is selected per ADR-023 and confirmed by the algorithm-E comparison
    in this spike's results: when both algorithms balance hands, dynamic-
    coverage scoring (E) matches static-frequency scoring (C) in 18 of 20
    measured milestone cells across nine layouts. The 1–3 step advantage
    that ungated coverage-greedy (D) shows is bought entirely by hand
    imbalance — see the per-finger key counts at step 16 in the results.
    Header docstring carries the full reasoning so it is not lost if this
    function is moved or renamed.
    """
    return "C freq-per-hand"


def process_layout(layout: Layout, freq_dict: dict, label: str,
                   results_dir: Path, yaml_suffix: str = "") -> None:
    native = native_layout(freq_dict, layout)
    corpus = build_corpus_index(native, freq_dict)
    g_freq = grapheme_frequencies(freq_dict, native)
    orders = {a: run_algorithm(a, native, corpus, g_freq) for a in ALGORITHMS}
    curves = {a: coverage_curves(orders[a], corpus) for a in ALGORITHMS}

    print_intro_table(label, orders, native, curves)
    print_coverage_milestones(label, orders, curves)
    max_step = max(len(o) for o in orders.values())
    for step in (10, 16, max_step):
        if step <= max_step:
            print_finger_balance(label, orders, native, step)

    yaml_name = f"key_intro_{layout.lang}{yaml_suffix}.yaml"
    yaml_path = results_dir / yaml_name
    win = select_winning_algorithm()
    write_yaml_draft(yaml_path, native, win, orders[win], curves[win])
    print(f"\n  YAML draft → {yaml_path}")


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    results_dir = repo_root / "spikes" / "results"
    results_dir.mkdir(exist_ok=True)
    txt_path = results_dir / "key_introduction_order_spike_results.txt"

    class Tee:
        def __init__(self, *streams):
            self.streams = streams

        def write(self, data):
            for s in self.streams:
                s.write(data)

        def flush(self):
            for s in self.streams:
                s.flush()

    with open(txt_path, "w", encoding="utf-8") as fh:
        tee = Tee(sys.stdout, fh)
        with redirect_stdout(tee):
            print("Key Introduction Order Spike — v2")
            print(f"Python: {sys.version.split()[0]}")
            print("Algorithms: A symmetric / B pure-freq / C freq-per-hand "
                  "/ D coverage-greedy")
            print("Home row: universal symmetric-pair anchor (per ADR-023)")
            print(f"Languages: {', '.join(LAYOUT_BUILDERS.keys())}")
            print()

            for lang, builders in LAYOUT_BUILDERS.items():
                print(f"\n  Loading {lang}...", end="", flush=True)
                freq_dict = get_frequency_dict(lang)
                print(f" {len(freq_dict):,} word entries")

                if len(builders) == 1:
                    layout = builders[0]()
                    label = f"{lang} — {layout.name}"
                    process_layout(layout, freq_dict, label, results_dir)
                else:
                    # Multi-variant language (Latvian)
                    for i, b in enumerate(builders):
                        layout = b()
                        label = f"{lang} variant {i+1} — {layout.name}"
                        suffix = f"_{layout.name.split('(')[1].rstrip(')').replace(' ', '_').replace('-', '')}" \
                                 if "(" in layout.name else f"_v{i+1}"
                        process_layout(layout, freq_dict, label,
                                       results_dir, yaml_suffix=suffix)

            section("DONE")
            print(f"  Results written to: {txt_path}")


if __name__ == "__main__":
    main()
