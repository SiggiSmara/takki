import random

from wordfreq import get_frequency_dict

from takki.language import (
    compute_bigram_weights,
    compute_grapheme_weights,
    compute_key_frequencies,
    rank_graphemes,
    sample_bigrams,
)
from takki.platform.layout import Layout

# Keyed per layout rather than per language: two layouts can share a language
# code while exposing different graphemes (Latvian's AltGr and dead-key
# variants), and they must not collide in the cache.
_LayoutKey = tuple[str, tuple[str, ...]]


def _layout_key(layout: Layout) -> _LayoutKey:
    return layout.lang, tuple(sorted(layout.graphemes))


class WordfreqSource:
    def __init__(self) -> None:
        self._words: dict[str, dict[str, float]] = {}
        self._graphemes: dict[_LayoutKey, dict[str, float]] = {}
        self._bigrams: dict[_LayoutKey, dict[str, float]] = {}

    def _word_weights(self, lang: str) -> dict[str, float]:
        if lang not in self._words:
            freq: dict[str, float] = get_frequency_dict(lang)
            self._words[lang] = freq
        return self._words[lang]

    def letter_ranking(self, layout: Layout) -> list[str]:
        return rank_graphemes(layout, self.grapheme_weights(layout))

    def grapheme_weights(self, layout: Layout) -> dict[str, float]:
        # A full pass over the corpus (~320k words for English), so it is
        # computed once per layout and copied out -- callers get the same
        # free-to-mutate dict FixedListSource hands back.
        key = _layout_key(layout)
        if key not in self._graphemes:
            self._graphemes[key] = compute_grapheme_weights(self._word_weights(layout.lang), layout)
        return dict(self._graphemes[key])

    def key_frequencies(self, layout: Layout) -> dict[str, float]:
        # Cheap once the grapheme weights are cached: one pass over the
        # layout's graphemes, not over the corpus.
        return compute_key_frequencies(layout, self.grapheme_weights(layout))

    def bigrams(self, layout: Layout, count: int, rng: random.Random) -> list[str]:
        key = _layout_key(layout)
        if key not in self._bigrams:
            self._bigrams[key] = compute_bigram_weights(self._word_weights(layout.lang), layout)
        return sample_bigrams(self._bigrams[key], count, rng)
