import random
from collections import defaultdict
from collections.abc import Iterator
from typing import Protocol

from takki.platform.layout import Layout


class WordSource(Protocol):
    def letter_ranking(self, layout: Layout) -> list[str]: ...

    def grapheme_weights(self, layout: Layout) -> dict[str, float]: ...

    def key_frequencies(self, layout: Layout) -> dict[str, float]: ...

    def bigrams(self, layout: Layout, count: int, rng: random.Random) -> list[str]: ...


def rank_graphemes(layout: Layout, weights: dict[str, float]) -> list[str]:
    # Every native grapheme is ranked, including ones the corpus never used
    # (weight 0) -- the ranking must cover the whole alphabet, not just the
    # subset that happened to appear. Ties (including all the zero-weight
    # ones) break alphabetically so the order is fully deterministic.
    full = {char: weights.get(char, 0.0) for char in layout.graphemes}
    return sorted(full, key=lambda c: (-full[c], c))


def _eligible_words(
    word_weights: dict[str, float], native: frozenset[str], min_len: int
) -> Iterator[tuple[str, float]]:
    # Native alphabet membership is read straight off the layout (ADR-007)
    # -- never computed statistically.
    for word, freq in word_weights.items():
        if not word.isalpha() or len(word) < min_len:
            continue
        lower = word.lower()
        if not frozenset(lower) <= native:
            continue
        yield lower, freq


def compute_grapheme_weights(word_weights: dict[str, float], layout: Layout) -> dict[str, float]:
    # min_len=3 is the Layer 2 floor -- prevents short articles skewing the
    # per-letter weight.
    native = frozenset(layout.graphemes)
    weights: dict[str, float] = defaultdict(float)
    for lower, freq in _eligible_words(word_weights, native, min_len=3):
        for char in frozenset(lower):
            weights[char] += freq
    return dict(weights)


def compute_key_frequencies(layout: Layout, grapheme_weights: dict[str, float]) -> dict[str, float]:
    # A modifier's own text frequency is zero -- its score is the summed
    # weight of every grapheme that lists it as a prerequisite (ADR-023
    # Composite letters).
    scores: dict[str, float] = defaultdict(float)
    for g in layout.graphemes.values():
        weight = grapheme_weights.get(g.char, 0.0)
        for key_name in g.prereq_keys:
            scores[key_name] += weight
    return {key_name: scores.get(key_name, 0.0) for key_name in layout.keys}


def compute_bigram_weights(word_weights: dict[str, float], layout: Layout) -> dict[str, float]:
    # min_len=2 -- a bigram only needs two characters, so short real words
    # like "of"/"to"/"in" still contribute their own bigram.
    native = frozenset(layout.graphemes)
    weights: dict[str, float] = defaultdict(float)
    for lower, freq in _eligible_words(word_weights, native, min_len=2):
        for i in range(len(lower) - 1):
            weights[lower[i : i + 2]] += freq
    return dict(weights)


def sample_bigrams(weights: dict[str, float], count: int, rng: random.Random) -> list[str]:
    # Takes precomputed weights: building them is a full pass over the corpus,
    # while sampling is cheap enough to run inside the drill loop.
    if not weights:
        return []
    population = list(weights.keys())
    return rng.choices(population, weights=list(weights.values()), k=count)
