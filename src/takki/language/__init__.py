import random
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

from takki.platform.layout import Layout


class WordSource(Protocol):
    def letter_ranking(self, layout: Layout) -> list[str]: ...

    def grapheme_weights(self, layout: Layout) -> dict[str, float]: ...

    # The weights themselves, not a sample of them: the drill generator
    # restricts the pool to the child's Active graphemes before sampling
    # (ADR-024 § Steady-state), and rejection-sampling `bigrams()` down to two
    # active keys out of twenty-six would be a lottery, not a drill.
    def bigram_weights(self, layout: Layout) -> dict[str, float]: ...

    def bigrams(self, layout: Layout, count: int, rng: random.Random) -> list[str]: ...

    # Each physical key's share of the language's key presses, keyed by key name
    # (ADR-032 § A key's share of key presses). Every key of the layout is present.
    def key_shares(self, layout: Layout) -> dict[str, float]: ...


def warm(source: WordSource, layout: Layout) -> None:
    """Force the derived tables before the loop is entered (concurrency-model.md § Startup).

    They come from one walk over the corpus -- ~1.4 s for English and ~4.0 s
    for German on the dev box, against a 16 ms frame budget -- and they are
    read from inside the loop: `bigram_weights` builds every drill block and
    `letter_ranking` (which is `grapheme_weights` plus a sort) is re-derived on
    every introduction step. A lazy first call would stall a tick for seconds.
    """
    source.grapheme_weights(layout)
    source.bigram_weights(layout)
    source.key_shares(layout)


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


@dataclass(frozen=True)
class DerivedTables:
    grapheme_weights: dict[str, float]
    bigram_weights: dict[str, float]
    key_shares: dict[str, float]


def compute_tables(word_weights: dict[str, float], layout: Layout) -> DerivedTables:
    # One walk for all three: each is a pass over the whole corpus, and the
    # share as a pass of its own added about a third to startup (measured
    # 2026-11-08, concurrency-model.md § Startup).
    # The share takes every eligible word; the other two keep their floors.
    native = frozenset(layout.graphemes)
    graphemes: dict[str, float] = defaultdict(float)
    bigrams: dict[str, float] = defaultdict(float)
    occurrences: dict[str, float] = defaultdict(float)
    for lower, freq in _eligible_words(word_weights, native, min_len=1):
        for char in lower:
            occurrences[char] += freq
        if len(lower) >= 2:
            # min_len=2 -- a bigram only needs two characters, so short real
            # words like "of"/"to"/"in" still contribute their own bigram.
            for i in range(len(lower) - 1):
                bigrams[lower[i : i + 2]] += freq
        if len(lower) >= 3:
            # The Layer 2 floor -- prevents short articles skewing the
            # per-letter weight.
            for char in frozenset(lower):
                graphemes[char] += freq
    return DerivedTables(dict(graphemes), dict(bigrams), _key_shares(occurrences, layout))


def _key_shares(occurrences: dict[str, float], layout: Layout) -> dict[str, float]:
    # Each occurrence of a letter presses every key it needs once, a
    # composite's modifier and base included. No Shift and no space.
    presses = dict.fromkeys(layout.keys, 0.0)
    for char, weight in occurrences.items():
        for key in layout.graphemes[char].prereq_keys:
            presses[key] += weight
    total = sum(presses.values())
    if total == 0:
        return presses
    return {key: count / total for key, count in presses.items()}


def sample_bigrams(weights: dict[str, float], count: int, rng: random.Random) -> list[str]:
    # Takes precomputed weights: building them is a full pass over the corpus,
    # while sampling is cheap enough to run inside the drill loop.
    if not weights:
        return []
    population = list(weights.keys())
    return rng.choices(population, weights=list(weights.values()), k=count)
