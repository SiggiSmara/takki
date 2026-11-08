import random

from wordfreq import get_frequency_dict

from takki.language import DerivedTables, compute_tables, rank_graphemes, sample_bigrams
from takki.platform.layout import Layout

# Keyed per layout rather than per language: two layouts can share a language
# code while exposing different graphemes (Latvian's AltGr and dead-key
# variants), and they must not collide in the cache. The keys and each
# letter's prereq_keys are in it too, because the key shares are built from
# them: the same letters reached through other keys press other keys.
_LayoutKey = tuple[str, tuple[str, ...], tuple[tuple[str, tuple[str, ...]], ...]]


def _layout_key(layout: Layout) -> _LayoutKey:
    return (
        layout.lang,
        tuple(sorted(layout.keys)),
        tuple(sorted((char, g.prereq_keys) for char, g in layout.graphemes.items())),
    )


class WordfreqSource:
    def __init__(self) -> None:
        self._words: dict[str, dict[str, float]] = {}
        self._tables: dict[_LayoutKey, DerivedTables] = {}

    def _word_weights(self, lang: str) -> dict[str, float]:
        if lang not in self._words:
            freq: dict[str, float] = get_frequency_dict(lang)
            self._words[lang] = freq
        return self._words[lang]

    def _derived(self, layout: Layout) -> DerivedTables:
        # A full pass over the corpus (~320k words for English), so it is
        # computed once per layout. Callers get copies -- the same
        # free-to-mutate dicts FixedListSource hands back.
        key = _layout_key(layout)
        if key not in self._tables:
            self._tables[key] = compute_tables(self._word_weights(layout.lang), layout)
        return self._tables[key]

    def letter_ranking(self, layout: Layout) -> list[str]:
        return rank_graphemes(layout, self._derived(layout).grapheme_weights)

    def grapheme_weights(self, layout: Layout) -> dict[str, float]:
        return dict(self._derived(layout).grapheme_weights)

    def bigram_weights(self, layout: Layout) -> dict[str, float]:
        return dict(self._derived(layout).bigram_weights)

    def bigrams(self, layout: Layout, count: int, rng: random.Random) -> list[str]:
        return sample_bigrams(self._derived(layout).bigram_weights, count, rng)

    def key_shares(self, layout: Layout) -> dict[str, float]:
        return dict(self._derived(layout).key_shares)
