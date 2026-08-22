import random

import pytest

from takki.language import WordSource
from takki.language.wordfreq_source import WordfreqSource
from takki.platform.layout import Grapheme, Layout, PhysicalKey, build_de, build_en
from tests.fakes.fixed_list_source import FixedListSource

# Static structural conformance — pyright fails if either impl drifts from the Protocol.
_conforms_fixed: WordSource = FixedListSource({})
_conforms_wordfreq: WordSource = WordfreqSource()


@pytest.fixture(scope="module")
def wordfreq_source() -> WordfreqSource:
    # Shared across the real-corpus tests: a fresh instance re-loads the
    # frequency dict and recomputes every derived table from scratch.
    return WordfreqSource()


def _composite_layout() -> Layout:
    """Synthetic layout with one dead-key modifier, for modifier-aggregate tests."""
    keys = {
        "a": PhysicalKey("a", 3, 1),
        "e": PhysicalKey("e", 2, 3),
        "dead-acute": PhysicalKey("dead-acute", 2, 11),
    }
    graphemes = {
        "a": Grapheme("a", "direct", ("a",), 1),
        "e": Grapheme("e", "direct", ("e",), 1),
        "á": Grapheme("á", "dead-key", ("dead-acute", "a"), 2, base="a", dead_key="dead-acute"),
        "é": Grapheme("é", "dead-key", ("dead-acute", "e"), 2, base="e", dead_key="dead-acute"),
    }
    return Layout(lang="xx", keys=keys, graphemes=graphemes)


class TestFixedListSourceGraphemeWeights:
    def test_exact_values(self) -> None:
        source = FixedListSource({"aaa": 40.0, "bbb": 30.0, "ccc": 20.0, "ddd": 10.0})
        assert source.grapheme_weights(build_en()) == {"a": 40.0, "b": 30.0, "c": 20.0, "d": 10.0}

    def test_excludes_words_under_three_chars(self) -> None:
        source = FixedListSource({"aaa": 40.0, "ab": 1000.0})
        assert source.grapheme_weights(build_en()) == {"a": 40.0}

    def test_excludes_non_alpha_words(self) -> None:
        source = FixedListSource({"aaa": 40.0, "a1a": 1000.0})
        assert source.grapheme_weights(build_en()) == {"a": 40.0}

    def test_excludes_words_with_non_native_chars(self) -> None:
        # "café" has a char ('é') not on the plain English layout — the whole
        # word drops out, not just the offending character.
        source = FixedListSource({"aaa": 40.0, "café": 1000.0})
        assert source.grapheme_weights(build_en()) == {"a": 40.0}

    def test_word_contributes_once_per_distinct_char(self) -> None:
        source = FixedListSource({"aab": 5.0})
        assert source.grapheme_weights(build_en()) == {"a": 5.0, "b": 5.0}


class TestFixedListSourceLetterRanking:
    def test_order_is_descending_by_weight(self) -> None:
        source = FixedListSource({"aaa": 40.0, "bbb": 30.0, "ccc": 20.0, "ddd": 10.0})
        ranking = source.letter_ranking(build_en())
        assert ranking[:4] == ["a", "b", "c", "d"]

    def test_includes_every_native_grapheme_even_with_zero_weight(self) -> None:
        # A corpus that only ever mentions "a" must still rank all 26 native
        # letters -- the ranking covers the layout's alphabet, not just the
        # words the corpus happened to contain.
        source = FixedListSource({"aaa": 1.0})
        ranking = source.letter_ranking(build_en())
        assert set(ranking) == set("abcdefghijklmnopqrstuvwxyz")
        assert ranking[0] == "a"

    def test_zero_weight_ties_break_alphabetically(self) -> None:
        source = FixedListSource({"aaa": 1.0})
        ranking = source.letter_ranking(build_en())
        assert ranking[1:] == sorted(set("abcdefghijklmnopqrstuvwxyz") - {"a"})


class TestFixedListSourceKeyFrequencies:
    def test_direct_only_layout_matches_grapheme_weights_for_seen_letters(self) -> None:
        # key_frequencies covers every physical key (zero for unseen letters);
        # grapheme_weights only carries entries that actually occurred.
        source = FixedListSource({"aaa": 40.0, "bbb": 30.0})
        layout = build_en()
        key_freqs = source.key_frequencies(layout)
        assert key_freqs["a"] == 40.0
        assert key_freqs["b"] == 30.0
        assert key_freqs["z"] == 0.0

    def test_modifier_scores_by_aggregate_composite_frequency(self) -> None:
        source = FixedListSource({"aaa": 5.0, "eee": 3.0, "ááá": 2.0, "ééé": 1.0})
        layout = _composite_layout()
        assert source.key_frequencies(layout) == {
            "a": 7.0,  # direct "a" (5) + composite "á" depends on it (2)
            "e": 4.0,  # direct "e" (3) + composite "é" depends on it (1)
            "dead-acute": 3.0,  # zero own frequency; sum of á (2) + é (1)
        }


class TestFixedListSourceBigrams:
    def test_single_possible_bigram_is_deterministic(self) -> None:
        source = FixedListSource({"aaa": 1.0})
        result = source.bigrams(build_en(), count=5, rng=random.Random(0))
        assert result == ["aa"] * 5

    def test_returns_requested_count(self) -> None:
        source = FixedListSource({"cat": 1.0, "dog": 1.0})
        result = source.bigrams(build_en(), count=12, rng=random.Random(0))
        assert len(result) == 12

    def test_same_seed_is_reproducible(self) -> None:
        source = FixedListSource({"cat": 1.0, "dog": 1.0, "bird": 1.0})
        layout = build_en()
        first = source.bigrams(layout, count=30, rng=random.Random(42))
        second = source.bigrams(layout, count=30, rng=random.Random(42))
        assert first == second

    def test_weighting_favours_the_heavier_bigram(self) -> None:
        source = FixedListSource({"aaa": 1_000_000.0, "bbb": 1.0})
        result = source.bigrams(build_en(), count=200, rng=random.Random(7))
        assert result.count("aa") > 190

    def test_excludes_bigrams_from_words_with_non_native_chars(self) -> None:
        source = FixedListSource({"aaa": 1.0, "café": 1.0})
        result = source.bigrams(build_en(), count=20, rng=random.Random(0))
        assert set(result) == {"aa"}

    def test_two_char_words_still_contribute_a_bigram(self) -> None:
        # Bigrams only need 2 characters -- unlike letter/grapheme weighting,
        # a two-letter word like "of" must not be dropped by the Layer-2
        # 3-char floor, or common short words vanish from drill content.
        source = FixedListSource({"of": 1.0})
        result = source.bigrams(build_en(), count=5, rng=random.Random(0))
        assert result == ["of"] * 5

    def test_empty_population_returns_empty_list_instead_of_crashing(self) -> None:
        # Every word here is filtered out (too short, non-alpha, or a
        # non-native char), leaving no eligible bigram at all.
        source = FixedListSource({"a": 5.0, "a1": 5.0, "café": 5.0})
        result = source.bigrams(build_en(), count=5, rng=random.Random(0))
        assert result == []


class TestWordfreqSourceEnglish:
    def test_letter_ranking_contains_all_26_letters(self, wordfreq_source: WordfreqSource) -> None:
        ranking = wordfreq_source.letter_ranking(build_en())
        assert set(ranking) == set("abcdefghijklmnopqrstuvwxyz")

    def test_letter_ranking_e_outranks_z(self, wordfreq_source: WordfreqSource) -> None:
        ranking = wordfreq_source.letter_ranking(build_en())
        assert ranking.index("e") < ranking.index("z")

    def test_grapheme_weights_all_positive(self, wordfreq_source: WordfreqSource) -> None:
        weights = wordfreq_source.grapheme_weights(build_en())
        assert all(w > 0 for w in weights.values())

    def test_key_frequencies_matches_grapheme_weights_for_direct_only_layout(
        self, wordfreq_source: WordfreqSource
    ) -> None:
        # No modifiers on English — every letter key's aggregate score is
        # exactly its own grapheme weight (nonzero for every letter here,
        # since real English text uses all 26).
        layout = build_en()
        key_freqs = wordfreq_source.key_frequencies(layout)
        grapheme_freqs = wordfreq_source.grapheme_weights(layout)
        for char in layout.graphemes:
            assert key_freqs[char] == grapheme_freqs[char]

    def test_bigrams_returns_requested_count_of_two_char_strings(
        self, wordfreq_source: WordfreqSource
    ) -> None:
        bigrams = wordfreq_source.bigrams(build_en(), count=20, rng=random.Random(1))
        assert len(bigrams) == 20
        assert all(len(b) == 2 for b in bigrams)

    def test_derived_tables_are_computed_once_per_layout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Each derived table is a full pass over ~320k words. Recomputing one
        # per call would put a multi-hundred-millisecond scan inside the drill
        # loop, which has a ~16 ms frame budget (concurrency-model.md).
        import takki.language.wordfreq_source as mod

        calls: list[str] = []
        real_graphemes = mod.compute_grapheme_weights
        real_bigrams = mod.compute_bigram_weights

        def counting_graphemes(words: dict[str, float], layout: Layout) -> dict[str, float]:
            calls.append("graphemes")
            return real_graphemes(words, layout)

        def counting_bigrams(words: dict[str, float], layout: Layout) -> dict[str, float]:
            calls.append("bigrams")
            return real_bigrams(words, layout)

        def tiny_corpus(lang: str) -> dict[str, float]:
            return {"aaa": 1.0}

        monkeypatch.setattr(mod, "compute_grapheme_weights", counting_graphemes)
        monkeypatch.setattr(mod, "compute_bigram_weights", counting_bigrams)
        monkeypatch.setattr(mod, "get_frequency_dict", tiny_corpus)

        source = WordfreqSource()
        layout = build_en()
        for _ in range(3):
            source.letter_ranking(layout)
            source.grapheme_weights(layout)
            source.key_frequencies(layout)
            source.bigrams(layout, count=5, rng=random.Random(0))
        assert calls == ["graphemes", "bigrams"]

    def test_grapheme_weights_caller_cannot_corrupt_the_cache(
        self, wordfreq_source: WordfreqSource
    ) -> None:
        layout = build_en()
        weights = wordfreq_source.grapheme_weights(layout)
        weights["e"] = -1.0
        assert wordfreq_source.grapheme_weights(layout)["e"] > 0

    def test_frequency_dict_loaded_once_per_language(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import takki.language.wordfreq_source as mod

        calls: list[str] = []

        def counting(lang: str) -> dict[str, float]:
            calls.append(lang)
            return {"aaa": 1.0}

        monkeypatch.setattr(mod, "get_frequency_dict", counting)
        source = WordfreqSource()
        source.letter_ranking(build_en())
        source.grapheme_weights(build_en())
        source.key_frequencies(build_en())
        assert calls == ["en"]


class TestWordfreqSourceGerman:
    def test_letter_ranking_e_outranks_q(self, wordfreq_source: WordfreqSource) -> None:
        ranking = wordfreq_source.letter_ranking(build_de())
        assert ranking.index("e") < ranking.index("q")

    def test_letter_ranking_covers_every_native_grapheme(
        self, wordfreq_source: WordfreqSource
    ) -> None:
        layout = build_de()
        ranking = wordfreq_source.letter_ranking(layout)
        assert set(ranking) == set(layout.graphemes)
