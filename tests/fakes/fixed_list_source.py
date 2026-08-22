import random

from takki.language import (
    compute_bigram_weights,
    compute_grapheme_weights,
    compute_key_frequencies,
    rank_graphemes,
    sample_bigrams,
)
from takki.platform.layout import Layout


class FixedListSource:
    def __init__(self, word_weights: dict[str, float]) -> None:
        self._word_weights = word_weights

    def letter_ranking(self, layout: Layout) -> list[str]:
        return rank_graphemes(layout, self.grapheme_weights(layout))

    def grapheme_weights(self, layout: Layout) -> dict[str, float]:
        return compute_grapheme_weights(self._word_weights, layout)

    def key_frequencies(self, layout: Layout) -> dict[str, float]:
        return compute_key_frequencies(layout, self.grapheme_weights(layout))

    def bigrams(self, layout: Layout, count: int, rng: random.Random) -> list[str]:
        return sample_bigrams(compute_bigram_weights(self._word_weights, layout), count, rng)
