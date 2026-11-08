"""
Spike: what "a key's share of key presses" should mean in the engine.

ADR-033 makes a rest letter strong when its key carries at least
REST_LETTER_MIN_SHARE (2%) of the language's key presses, and asks the ADR-032
amendment (alpha #12m, 2026-11-08) to define that share from language data. The
rest-letter order spike measured shares one way; the engine ranks letters
another way. This spike compares candidate definitions on the three layouts
that exist in product code (en, de, is from src/takki/platform/layout.py), so
the choice is made on numbers:

  presses    every occurrence of a grapheme presses each key it needs (a
             composite presses its modifier and its base), weighted by the
             word's frequency, over every word the language data has whose
             letters are all graphemes of the layout. Any length.
  min3       as presses, but only words of 3+ letters (grapheme_weights' floor).
  own        as presses, but a composite presses nothing for its base key: a
             key carries only its own letter's occurrences (the letter's share).
  +space     as presses, plus one space press per word.
  spike      as presses, over the rest-letter order spike's corpus (wordfreq's
             top 3000 words). Not an exact replay of that spike: this one drops
             a word with any letter outside the layout, which that one did not.

For each, every letter cell in the columns of the six fingers that are not
index fingers is classed strong (share >= 2%) or weak, and cells whose class
differs between definitions are flagged.

It then builds ADR-033's per-hand order for the conventional rest position with
every finger ready, two ways, and checks the alternation rule the ADR-032
amendment proposes (a hand's next turn is a rest letter when it has had more
useful letters than strong rest letters) against the spike's queue:

  by share     useful = key share, as the rest-letter spike ranked.
  by ranking   useful = the engine's letter_ranking (word-presence weights),
               which is what ADR-033 names as "most useful".

Both are checked against the spike's own interleave over the whole order, for
the layouts with no composite (en, de). English is also run with the left
middle finger resting on e, one row up, to show a per-child rest letter.

Run from repo root (no hardware needed):
    uv run python spikes/key_share_definition_spike.py

Output: a printed report plus spikes/results/key_share_definition_results.txt.
"""

import sys
from collections import defaultdict
from pathlib import Path

from wordfreq import get_frequency_dict, top_n_list

from takki.language import compute_grapheme_weights, rank_graphemes
from takki.platform.layout import Layout, build_de, build_en, build_is

RESULTS_PATH = Path(__file__).resolve().parent / "results" / "key_share_definition_results.txt"

FLOOR = 0.02
STEPS = 8
BUMP_CELLS = {(3, 4), (3, 7)}
REST_CELLS = {(3, 1), (3, 2), (3, 3), (3, 8), (3, 9), (3, 10)}  # the conventional row only
NON_INDEX_COLS = {1, 2, 3, 8, 9, 10, 11, 12, 13}

LAYOUTS = {"en": build_en, "de": build_de, "is": build_is}


def key_presses(
    words: dict[str, float], layout: Layout, *, min_len: int, composite_to_base: bool, space: bool
) -> dict[str, float]:
    native = frozenset(layout.graphemes)
    presses: dict[str, float] = defaultdict(float)
    for word, freq in words.items():
        if not word.isalpha() or len(word) < min_len:
            continue
        lower = word.lower()
        if not frozenset(lower) <= native:
            continue
        for char in lower:
            grapheme = layout.graphemes[char]
            keys = grapheme.prereq_keys if composite_to_base or grapheme.mechanism == "direct" else ()
            for key in keys:
                presses[key] += freq
        if space:
            presses[" "] += freq
    total = sum(presses.values())
    return {key: value / total for key, value in presses.items()}


def per_hand_order(
    layout: Layout, useful: list[str], share: dict[str, float], rest_cells: set[tuple[int, int]]
) -> list[tuple[str, ...]]:
    """ADR-033's order, every finger ready, by the count rule the amendment proposes."""
    by_cell = {(k.row, k.col): name for name, k in layout.keys.items() if name in layout.graphemes}
    bumps = [by_cell[c] for c in sorted(BUMP_CELLS, key=lambda c: c[1])]
    strong = {by_cell[c] for c in rest_cells if c in by_cell and share.get(by_cell[c], 0) >= FLOOR}
    had = set(bumps)
    steps: list[tuple[str, ...]] = [tuple(bumps)]
    counts = {"L": [0, 0], "R": [0, 0]}  # useful had, strong rest had (bumps excluded)

    def side(name: str) -> str:
        g = layout.graphemes[name]
        return layout.keys[g.base or g.char].side

    def eligible(name: str) -> bool:
        g = layout.graphemes[name]
        return g.mechanism == "direct" or g.base in had

    while True:
        step = []
        for hand in "LR":
            u, r = counts[hand]
            useful_q = [n for n in useful if n not in had and n not in strong and side(n) == hand]
            rest_q = sorted(
                (n for n in strong if n not in had and side(n) == hand), key=lambda n: -share[n]
            )
            useful_q = [n for n in useful_q if eligible(n)]
            turn = rest_q if (u > r and rest_q) or not useful_q else useful_q
            if turn:
                name = turn[0]
                step.append(name)
                counts[hand][1 if name in strong else 0] += 1
        if not step:
            return steps
        had.update(step)
        steps.append(tuple(step))


def spike_queue(useful: list[str], strong_by_share: list[str]) -> list[str]:
    """rest_letter_order_spike.queue for the 'floor' modes, verbatim in effect."""
    early = list(strong_by_share)
    others = [k for k in useful if k not in early]
    out = []
    while others or early:
        if others:
            out.append(others.pop(0))
        if early:
            out.append(early.pop(0))
    return out


class _Tee:
    def __init__(self, *streams):
        self._streams = streams

    def write(self, text):
        for stream in self._streams:
            stream.write(text)

    def flush(self):
        for stream in self._streams:
            stream.flush()


def analyse(lang: str) -> None:
    layout = LAYOUTS[lang]()
    words = get_frequency_dict(lang)
    upper = sum(1 for w in words if w != w.lower())
    top = {w: words[w] for w in top_n_list(lang, 3000) if w in words}
    definitions = {
        "presses": key_presses(words, layout, min_len=1, composite_to_base=True, space=False),
        "min3": key_presses(words, layout, min_len=3, composite_to_base=True, space=False),
        "own": key_presses(words, layout, min_len=1, composite_to_base=False, space=False),
        "+space": key_presses(words, layout, min_len=1, composite_to_base=True, space=True),
        "spike": key_presses(top, layout, min_len=1, composite_to_base=True, space=False),
    }
    print(f"\n{'=' * 96}\n  {lang}: {len(words)} words in wordfreq, {upper} with an upper-case letter\n{'=' * 96}")
    if "+space" in definitions:
        print(f"  space's own share under +space: {definitions['+space'][' ']:.1%}")
    if "dead-acute" in layout.keys:
        print("  dead-acute share: " + "  ".join(
            f"{d} {definitions[d].get('dead-acute', 0):.1%}" for d in definitions))

    cells = sorted(
        (k for name, k in layout.keys.items() if name in layout.graphemes and k.col in NON_INDEX_COLS),
        key=lambda k: (k.col, k.row),
    )
    print(f"\n  {'cell':8} {'key':4} " + " ".join(f"{d:>8}" for d in definitions) + "   class")
    flips = 0
    for k in cells:
        row = [definitions[d].get(k.name, 0.0) for d in definitions]
        classes = {v >= FLOOR for v in row}
        flag = "differs" if len(classes) > 1 else ("strong" if row[0] >= FLOOR else "weak")
        flips += len(classes) > 1
        rest = "*" if (k.row, k.col) in REST_CELLS else " "
        print(f"  ({k.row},{k.col:2}){rest} {k.name:4} " + " ".join(f"{v:>8.2%}" for v in row) + f"   {flag}")
    print(f"  (* = a conventional rest cell)   cells whose strong/weak class differs: {flips}")

    share = definitions["presses"]
    ranking = rank_graphemes(layout, compute_grapheme_weights(words, layout))
    by_cell = {(k.row, k.col): n for n, k in layout.keys.items() if n in layout.graphemes}
    bumps = {by_cell[c] for c in BUMP_CELLS}
    by_share = sorted((n for n in layout.graphemes if n not in bumps), key=lambda n: -share.get(n, 0))
    strong = {by_cell[c] for c in REST_CELLS if c in by_cell and share.get(by_cell[c], 0) >= FLOOR}

    for label, useful in (("by share", by_share), ("by ranking", [n for n in ranking if n not in bumps])):
        steps = per_hand_order(layout, useful, share, REST_CELLS)
        print(f"\n  order, {label:10}: " + "  ".join("+".join(s) for s in steps[:STEPS]))
        if all(g.mechanism == "direct" for g in layout.graphemes.values()):
            hands = {}
            for hand in "LR":
                mine = [n for n in useful if layout.keys[n].side == hand]
                hands[hand] = spike_queue(
                    [n for n in mine if n not in strong],
                    sorted((n for n in mine if n in strong), key=lambda n: -share[n]),
                )
            from itertools import zip_longest

            expected = [tuple(sorted(bumps, key=lambda n: layout.keys[n].col))] + [
                tuple(x for x in pair if x) for pair in zip_longest(hands["L"], hands["R"])
            ]
            same = expected == steps
            print(f"  {'':18}count rule equals the spike's interleave over the whole order: {same}")
            if not same:
                print("  spike interleave:  " + "  ".join("+".join(s) for s in expected[:STEPS]))

    if lang == "en":
        own_rest = (REST_CELLS - {(3, 3)}) | {(2, 3)}
        steps = per_hand_order(layout, [n for n in ranking if n not in bumps], share, own_rest)
        print("\n  order, by ranking, left middle finger resting on e: "
              + "  ".join("+".join(s) for s in steps[:STEPS]))


def main() -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    orig_stdout = sys.stdout
    with RESULTS_PATH.open("w", encoding="utf-8") as fh:
        sys.stdout = _Tee(orig_stdout, fh)
        try:
            print("Key-Share Definition Spike")
            print(f"Python: {sys.version.split()[0]}   Platform: {sys.platform}")
            print(f"Floor: {FLOOR:.0%}   Layouts: {', '.join(LAYOUTS)} (product tables)")
            for lang in LAYOUTS:
                analyse(lang)
            print(f"\n  Results written to {RESULTS_PATH}")
        finally:
            sys.stdout = orig_stdout


if __name__ == "__main__":
    main()
