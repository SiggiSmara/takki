"""
Spike: where do the rest-key letters go in the introduction order?

Background (design discussion of 2026-10-10, to be written up as ADR-033): the
child finds the F/J bumps by touch, every other finger gets a rest key in its
own column, and letters are then introduced "by usefulness" so real words come
early. A letter that sits on a rest key has no location to learn, so it is
tempting to introduce those early. This spike measures what that costs in
typeable words, per language, for five orders:

  useful        Each hand takes its most-used remaining key. Rest letters get
                no special treatment.
  alternating   Each hand alternates: most-used non-rest key, then its next
                rest key, and so on until its rest keys run out.
  floor 2%      As alternating, but a rest key only takes an early turn if it
  floor 3%      carries at least that share of the language's key presses.
                Weaker rest keys wait their turn by usefulness.
  rest first    Each hand takes all its rest keys first, then the others.

Model, and what it leaves out:

  - The two bump keys (row 3, columns 4 and 7) are known from the start.
  - Rest keys are the other row-3 keys of the conventional position (columns
    1-3 and 8-10). A child's own rest keys may differ; this spike does not
    model that.
  - A step adds one key per hand. "Day one" is three steps, because six keys
    may be unlearned at once (ADR-010) and the bumps take no slot.
  - A word counts once every key it needs is known. A composite letter (dead
    key, AltGr, Shift) costs no step of its own, which flatters every order
    by the same amount.
  - Words are wordfreq's top 3000 for the language, 3-6 letters, unfiltered:
    some are junk (acronyms, names). All orders see the same list.
  - Key usefulness is the key's share of key presses over that same top 3000,
    weighted by word frequency. This is close to, but not the same as, the
    engine's letter ranking, so step sequences differ slightly from Takki's.
  - LAYOUT TABLES: only en, de and is match the tables in
    src/takki/platform/layout.py. The other sixteen were typed from memory
    and have not been checked against a real keyboard.

Run from repo root (no hardware needed):
    uv run python spikes/rest_letter_order_spike.py

Output: a printed report plus spikes/results/rest_letter_order_results.txt.
"""

import sys
from collections import Counter
from itertools import zip_longest
from pathlib import Path

from wordfreq import top_n_list, word_frequency

RESULTS_PATH = Path(__file__).resolve().parent / "results" / "rest_letter_order_results.txt"

TOP_WORDS = 3000
MIN_LEN, MAX_LEN = 3, 6
DAY_ONE_STEPS = 3
STEPS = 6
STRONG_SHARE = 0.02  # a rest key at or above this share is "strong" in the report

REST_CELLS = {(3, 1), (3, 2), (3, 3), (3, 8), (3, 9), (3, 10)}
BUMP_CELLS = {(3, 4), (3, 7)}

# mode -> floor on a rest key's share for it to take an early turn (None = no
# alternation at all; "first" = all rest keys before anything else)
MODES = {
    "useful": None,
    "alternating": 0.0,
    "floor 2%": 0.02,
    "floor 3%": 0.03,
    "rest first": "first",
}


# ------------------------------------------------------------------ layouts --

def rows(row2: str, row3: str, row4: str, extra: dict | None = None) -> dict:
    """Letters -> (row, col). Rows are space-separated; "_" skips a column."""
    table = {}
    for row, letters in ((2, row2), (3, row3), (4, row4)):
        for col, letter in enumerate(letters.split(), 1):
            if letter != "_":
                table[letter] = (row, col)
    table.update(extra or {})
    return table


QWERTY = ("q w e r t y u i o p", "a s d f g h j k l", "z x c v b n m")
QWERTZ = ("q w e r t z u i o p", "a s d f g h j k l", "y x c v b n m")
ACUTE = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u"}


def dead(name: str, letters: dict) -> dict:
    return {composed: (name, base) for composed, base in letters.items()}


# lang: (title, direct letters, modifier keys, composites as letter -> (modifier, base))
LAYOUTS = {
    "en": ("English, QWERTY", rows(*QWERTY), {}, {}),
    "de": (
        "German, QWERTZ",
        rows(*QWERTZ, {"ü": (2, 11), "ö": (3, 10), "ä": (3, 11), "ß": (1, 12)}),
        {},
        {},
    ),
    "nl": (
        "Dutch, US-International",
        rows(*QWERTY),
        {"dead-acute": (3, 11), "dead-diaer": (3, 11)},
        {**dead("dead-acute", {"é": "e"}), **dead("dead-diaer", {"ë": "e", "ï": "i"})},
    ),
    "is": (
        "Icelandic",
        rows(*QWERTY, {"ð": (2, 11), "æ": (3, 10), "þ": (4, 10), "ö": (1, 11)}),
        {"dead-acute": (3, 11)},
        dead("dead-acute", {**ACUTE, "ý": "y"}),
    ),
    "sv": ("Swedish", rows(*QWERTY, {"å": (2, 11), "ö": (3, 10), "ä": (3, 11)}), {}, {}),
    "fi": ("Finnish", rows(*QWERTY, {"å": (2, 11), "ö": (3, 10), "ä": (3, 11)}), {}, {}),
    "nb": ("Norwegian", rows(*QWERTY, {"å": (2, 11), "ø": (3, 10), "æ": (3, 11)}), {}, {}),
    "da": ("Danish", rows(*QWERTY, {"å": (2, 11), "æ": (3, 10), "ø": (3, 11)}), {}, {}),
    "es": (
        "Spanish",
        rows(*QWERTY, {"ñ": (3, 10)}),
        {"dead-acute": (3, 11), "dead-diaer": (3, 11)},
        {**dead("dead-acute", ACUTE), **dead("dead-diaer", {"ü": "u"})},
    ),
    "pt": (
        "Portuguese, ABNT2",
        rows(*QWERTY, {"ç": (3, 10)}),
        {
            "dead-acute": (2, 11),
            "dead-grave": (2, 11),
            "dead-tilde": (3, 11),
            "dead-circ": (3, 11),
        },
        {
            **dead("dead-acute", ACUTE),
            **dead("dead-grave", {"à": "a"}),
            **dead("dead-tilde", {"ã": "a", "õ": "o"}),
            **dead("dead-circ", {"â": "a", "ê": "e", "ô": "o"}),
        },
    ),
    "it": (
        "Italian",
        rows(*QWERTY, {"è": (2, 11), "ò": (3, 10), "à": (3, 11), "ù": (3, 12), "ì": (1, 12)}),
        {"shift": (4, 0)},
        {"é": ("shift", "è")},
    ),
    "fr": (
        "French, AZERTY",
        rows(
            "a z e r t y u i o p",
            "q s d f g h j k l m",
            "w x c v b n",
            {"é": (1, 2), "è": (1, 7), "ç": (1, 9), "à": (1, 10), "ù": (3, 11)},
        ),
        {"dead-circ": (2, 11), "dead-diaer": (2, 11)},
        {
            **dead("dead-circ", {"â": "a", "ê": "e", "î": "i", "ô": "o", "û": "u"}),
            **dead("dead-diaer", {"ë": "e", "ï": "i"}),
        },
    ),
    "pl": (
        "Polish, programmer's",
        rows(*QWERTY),
        {"altgr": (5, 8)},
        dead(
            "altgr",
            {
                "ą": "a", "ć": "c", "ę": "e", "ł": "l", "ń": "n",
                "ó": "o", "ś": "s", "ż": "z", "ź": "x",
            },
        ),
    ),
    "cs": (
        "Czech, QWERTZ",
        rows(
            *QWERTZ,
            {
                "ě": (1, 2), "š": (1, 3), "č": (1, 4), "ř": (1, 5), "ž": (1, 6),
                "ý": (1, 7), "á": (1, 8), "í": (1, 9), "é": (1, 10),
                "ú": (2, 11), "ů": (3, 10),
            },
        ),
        {"dead-caron": (1, 13), "dead-acute": (1, 13)},
        {**dead("dead-caron", {"ď": "d", "ť": "t", "ň": "n"}), **dead("dead-acute", {"ó": "o"})},
    ),
    "hu": (
        "Hungarian, QWERTZ",
        rows(
            *QWERTZ,
            {
                "ö": (1, 11), "ü": (1, 12), "ó": (1, 13), "ő": (2, 11), "ú": (2, 12),
                "é": (3, 10), "á": (3, 11), "ű": (3, 12), "í": (4, 0),
            },
        ),
        {},
        {},
    ),
    "tr": (
        "Turkish Q",
        rows("q w e r t y u ı o p ğ ü", "a s d f g h j k l ş i", "z x c v b n m ö ç"),
        {},
        {},
    ),
    "ru": (
        "Russian",
        rows(
            "й ц у к е н г ш щ з х ъ",
            "ф ы в а п р о л д ж э",
            "я ч с м и т ь б ю",
            {"ё": (1, 0)},
        ),
        {},
        {},
    ),
    "el": (
        "Greek",
        rows("_ ς ε ρ τ υ θ ι ο π", "α σ δ φ γ η ξ κ λ", "ζ χ ψ ω β ν μ"),
        {"dead-tonos": (3, 10)},
        dead(
            "dead-tonos",
            {"ά": "α", "έ": "ε", "ή": "η", "ί": "ι", "ό": "ο", "ύ": "υ", "ώ": "ω"},
        ),
    ),
    "he": (
        "Hebrew",
        rows("_ _ ק ר א ט ו ן ם פ", "ש ד ג כ ע י ח ל ך ף", "ז ס ב ה נ מ צ ת ץ"),
        {},
        {},
    ),
}


# ----------------------------------------------------------------- analysis --

def queue(mode: str, keys: list[str], rest: set[str], share: dict[str, float]) -> list[str]:
    """One hand's keys in introduction order. `keys` is already most-used first."""
    floor = MODES[mode]
    if floor is None:
        return list(keys)
    if floor == "first":
        return [k for k in keys if k in rest] + [k for k in keys if k not in rest]
    early = [k for k in keys if k in rest and share[k] >= floor]
    others = [k for k in keys if k not in early]
    out = []
    while others or early:
        if others:
            out.append(others.pop(0))
        if early:
            out.append(early.pop(0))
    return out


def analyse(lang: str) -> dict:
    title, direct, modifiers, composites = LAYOUTS[lang]
    position = {**direct, **modifiers}
    needs = {letter: {letter} for letter in direct}
    for letter, (modifier, base) in composites.items():
        needs[letter] = {modifier} | needs[base]

    words = top_n_list(lang, TOP_WORDS)
    presses: Counter[str] = Counter()
    for word in words:
        frequency = word_frequency(word, lang)
        for letter in word:
            for key in needs.get(letter, ()):
                presses[key] += frequency
    total = sum(presses.values()) or 1.0
    share = {key: presses[key] / total for key in position}

    pool = [
        w for w in words
        if w.isalpha() and MIN_LEN <= len(w) <= MAX_LEN and len(set(w)) > 1 and set(w) <= set(needs)
    ]
    word_keys = [set().union(*(needs[c] for c in w)) for w in pool]

    bumps = {k for k, cell in position.items() if cell in BUMP_CELLS}
    rest = {k for k, cell in position.items() if cell in REST_CELLS}
    strong = {k for k in rest if share[k] >= STRONG_SHARE}
    ranked = sorted((k for k in position if k not in bumps), key=lambda k: -share[k])
    hands = {
        side: [k for k in ranked if (position[k][1] <= 5) == (side == "L")] for side in "LR"
    }

    orders = {}
    for mode in MODES:
        steps = list(zip_longest(*(queue(mode, hands[s], rest, share) for s in "LR")))
        known = set(bumps)
        counts, strong_in, day_one = [], None, []
        for n, pair in enumerate(steps, 1):
            known |= {k for k in pair if k}
            if strong_in is None and strong <= known:
                strong_in = n
            if n <= STEPS:
                typeable = [w for w, keys in zip(pool, word_keys) if keys <= known]
                counts.append(len(typeable))
                if n == DAY_ONE_STEPS:
                    day_one = typeable[:8]
        orders[mode] = {
            "steps": steps[:STEPS], "counts": counts, "strong_in": strong_in, "day_one": day_one,
        }
    return {
        "title": title,
        "pool": len(pool),
        "bumps": sorted(bumps),
        "rest": sorted(rest, key=lambda k: -share[k]),
        "share": share,
        "strong": strong,
        "orders": orders,
    }


# ------------------------------------------------------------------- report --

class _Tee:
    def __init__(self, *streams):
        self._streams = streams

    def write(self, text):
        for stream in self._streams:
            stream.write(text)

    def flush(self):
        for stream in self._streams:
            stream.flush()


def section(title: str) -> None:
    print(f"\n{'=' * 100}\n  {title}\n{'=' * 100}")


def print_summary(results: list[dict]) -> None:
    for label, index in (("day one (3 steps)", DAY_ONE_STEPS - 1), (f"{STEPS} steps", STEPS - 1)):
        section(f"Typeable words after {label}")
        print(f"  {'language':26} {'pool':>5}  " + "  ".join(f"{m:>11}" for m in MODES))
        ratios = {m: [] for m in MODES}
        verdict = {m: Counter() for m in MODES}
        for r in results:
            base = r["orders"]["useful"]["counts"][index]
            cells = []
            for mode in MODES:
                count = r["orders"][mode]["counts"][index]
                cells.append(f"{count:>11}")
                ratios[mode].append(count / max(base, 1))
                verdict[mode]["ahead" if count > base else "behind" if count < base else "equal"] += 1
            print(f"  {r['title']:26} {r['pool']:>5}  " + "  ".join(cells))
        print(f"  {'mean ratio to useful':32}  "
              + "  ".join(f"{sum(ratios[m]) / len(results):>11.2f}" for m in MODES))
        for outcome, label in (("ahead", "ahead of"), ("equal", "level with"), ("behind", "behind")):
            print(f"  {'languages ' + label + ' useful':32}  "
                  + "  ".join(f"{verdict[m][outcome]:>11}" for m in MODES))

    section(f"Step by which every strong rest key (>= {STRONG_SHARE:.0%} of key presses) is introduced")
    print(f"  {'language':26} {'strong/rest':>11}  " + "  ".join(f"{m:>11}" for m in MODES))
    totals = Counter()
    for r in results:
        cells = []
        for mode in MODES:
            step = r["orders"][mode]["strong_in"]
            totals[mode] += step
            cells.append(f"{step:>11}")
        ratio = f"{len(r['strong'])}/{len(r['rest'])}"
        print(f"  {r['title']:26} {ratio:>11}  " + "  ".join(cells))
    print(f"  {'mean':38}  " + "  ".join(f"{totals[m] / len(results):>11.1f}" for m in MODES))


def print_language(r: dict) -> None:
    section(r["title"])
    shares = "  ".join(f"{k} {r['share'][k]:.1%}" for k in r["rest"])
    print(f"  bump keys: {' '.join(r['bumps'])}")
    print(f"  rest keys, by share of key presses: {shares}")
    for mode in ("useful", "floor 2%", "alternating"):
        order = r["orders"][mode]
        steps = "  ".join("+".join(k for k in pair if k) for pair in order["steps"])
        print(f"  {mode:12} {steps}")
        print(f"  {'':12} words after each step: {order['counts']}")
        print(f"  {'':12} first words on day one: {' '.join(order['day_one'])}")


def main() -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    orig_stdout = sys.stdout
    with RESULTS_PATH.open("w", encoding="utf-8") as fh:
        sys.stdout = _Tee(orig_stdout, fh)
        try:
            print("Rest-Letter Order Spike")
            print(f"Python: {sys.version.split()[0]}   Platform: {sys.platform}")
            print(f"Languages: {', '.join(LAYOUTS)}")
            print(f"Orders: {', '.join(MODES)}")
            print(f"Word band: {MIN_LEN}-{MAX_LEN} letters from wordfreq's top {TOP_WORDS}, unfiltered")
            print("Layout tables: en, de, is match src/takki/platform/layout.py; "
                  "the rest are from memory, unchecked")
            results = [analyse(lang) for lang in LAYOUTS]
            print_summary(results)
            for r in results:
                print_language(r)
            print(f"\n  Results written to {RESULTS_PATH}")
        finally:
            sys.stdout = orig_stdout


if __name__ == "__main__":
    main()
