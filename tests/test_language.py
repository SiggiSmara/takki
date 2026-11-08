import random
from collections.abc import Callable

import pytest

from takki.language import DerivedTables, WordSource, warm
from takki.language.wordfreq_source import WordfreqSource
from takki.platform.layout import Grapheme, Layout, PhysicalKey, build_de, build_en, build_is
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


class TestCompositeRanking:
    """ADR-032 § Decision 1 — a composite is ranked as the letter it is, and a
    modifier has no score at all. The aggregate-composite-frequency rule this
    class replaces existed only to place a modifier in a key-ordered sequence,
    and the sequence is grapheme-ordered now."""

    def test_a_composite_ranks_by_its_own_weight(self) -> None:
        source = FixedListSource({"aaa": 5.0, "eee": 3.0, "ááá": 2.0, "ééé": 1.0})
        layout = _composite_layout()
        assert source.grapheme_weights(layout) == {"a": 5.0, "e": 3.0, "á": 2.0, "é": 1.0}
        assert source.letter_ranking(layout) == ["a", "e", "á", "é"]

    def test_the_modifier_appears_in_neither_table(self) -> None:
        source = FixedListSource({"ááá": 2.0, "ééé": 1.0})
        layout = _composite_layout()
        assert "dead-acute" in layout.keys
        assert "dead-acute" not in source.grapheme_weights(layout)
        assert "dead-acute" not in source.letter_ranking(layout)


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


def _shares(layout: Layout, pressed: dict[str, float]) -> dict[str, float]:
    """Every key of the layout at zero, except the ones given."""
    return {**dict.fromkeys(layout.keys, 0.0), **pressed}


class TestFixedListSourceKeyShares:
    """ADR-032 § A key's share of key presses: every press of every key a
    letter needs, over every eligible word of any length, weighted by
    frequency, divided by the same count for every key."""

    def test_every_occurrence_of_every_word_is_a_press(self) -> None:
        # No length floor: "a" and "ab" count. A doubled letter is two presses.
        # Presses: a 1 + 2 = 3, b 2 + 3 = 5, e 3 * 2 = 6; 14 in all.
        source = FixedListSource({"a": 1.0, "ab": 2.0, "bee": 3.0})
        layout = build_en()
        assert source.key_shares(layout) == _shares(layout, {"a": 3 / 14, "b": 5 / 14, "e": 6 / 14})

    def test_a_word_that_is_not_alphabetic_or_has_a_letter_off_the_layout_is_left_out(
        self,
    ) -> None:
        source = FixedListSource({"ab": 1.0, "a1": 1000.0, "café": 1000.0})
        layout = build_en()
        assert source.key_shares(layout) == _shares(layout, {"a": 0.5, "b": 0.5})

    def test_a_composite_presses_its_modifier_and_its_base(self) -> None:
        # "bá" presses b, dead-acute and a; "ad" presses a and d. 5 in all.
        source = FixedListSource({"bá": 1.0, "ad": 1.0})
        layout = build_is()
        assert source.key_shares(layout) == _shares(
            layout, {"b": 0.2, "dead-acute": 0.2, "a": 0.4, "d": 0.2}
        )

    def test_a_cell_with_no_letter_has_a_share_of_zero(self) -> None:
        layout = build_en()
        assert ";" in layout.keys and ";" not in layout.graphemes
        shares = FixedListSource({"ab": 1.0}).key_shares(layout)
        assert shares[";"] == 0.0
        assert set(shares) == set(layout.keys)

    @pytest.mark.parametrize("words", [{}, {"café": 1.0, "a1": 1.0}], ids=["empty", "none-fit"])
    def test_every_key_is_zero_when_no_word_fits(self, words: dict[str, float]) -> None:
        layout = build_en()
        assert FixedListSource(words).key_shares(layout) == _shares(layout, {})


class TestWarm:
    def test_warm_builds_every_table(self) -> None:
        calls: list[str] = []

        class Recording(FixedListSource):
            def grapheme_weights(self, layout: Layout) -> dict[str, float]:
                calls.append("grapheme_weights")
                return super().grapheme_weights(layout)

            def bigram_weights(self, layout: Layout) -> dict[str, float]:
                calls.append("bigram_weights")
                return super().bigram_weights(layout)

            def key_shares(self, layout: Layout) -> dict[str, float]:
                calls.append("key_shares")
                return super().key_shares(layout)

        warm(Recording({"ab": 1.0}), build_en())
        assert calls == ["grapheme_weights", "bigram_weights", "key_shares"]


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

    def test_bigrams_returns_requested_count_of_two_char_strings(
        self, wordfreq_source: WordfreqSource
    ) -> None:
        bigrams = wordfreq_source.bigrams(build_en(), count=20, rng=random.Random(1))
        assert len(bigrams) == 20
        assert all(len(b) == 2 for b in bigrams)

    def test_derived_tables_are_computed_once_per_layout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The derived tables are one full pass over ~320k words. Recomputing
        # per call would put a multi-second scan inside the drill loop, which
        # has a ~16 ms frame budget (concurrency-model.md).
        import takki.language.wordfreq_source as mod

        calls: list[str] = []
        real = mod.compute_tables

        def counting(words: dict[str, float], layout: Layout) -> DerivedTables:
            calls.append(layout.lang)
            return real(words, layout)

        def tiny_corpus(lang: str) -> dict[str, float]:
            return {"aaa": 1.0}

        monkeypatch.setattr(mod, "compute_tables", counting)
        monkeypatch.setattr(mod, "get_frequency_dict", tiny_corpus)

        source = WordfreqSource()
        layout = build_en()
        for _ in range(3):
            source.letter_ranking(layout)
            source.grapheme_weights(layout)
            source.bigram_weights(layout)
            source.bigrams(layout, count=5, rng=random.Random(0))
            source.key_shares(layout)
        assert calls == ["en"]

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
        assert calls == ["en"]


def _corpus(words: dict[str, float]) -> Callable[[str], dict[str, float]]:
    def get_frequency_dict(lang: str) -> dict[str, float]:
        return words

    return get_frequency_dict


class TestWordfreqSourceKeyShares:
    def test_the_cache_tells_apart_layouts_whose_letters_need_other_keys(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Same language and letters; only the keys "á" needs differ. Keyed on
        # language and letters alone, the second layout got the first's shares.
        import takki.language.wordfreq_source as mod

        monkeypatch.setattr(mod, "get_frequency_dict", _corpus({"bá": 1.0}))
        dead = build_is()
        chord = build_is()
        chord.keys["altgr"] = PhysicalKey("altgr", 4, 11)
        chord.graphemes["á"] = Grapheme("á", "altgr-chord", ("altgr", "a"), 2, base="a")
        source = WordfreqSource()
        third = 1 / 3
        assert source.key_shares(dead) == _shares(
            dead, {"b": third, "dead-acute": third, "a": third}
        )
        assert source.key_shares(chord) == _shares(chord, {"b": third, "altgr": third, "a": third})

    def test_key_shares_caller_cannot_corrupt_the_cache(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import takki.language.wordfreq_source as mod

        monkeypatch.setattr(mod, "get_frequency_dict", _corpus({"ab": 1.0}))
        source = WordfreqSource()
        layout = build_en()
        source.key_shares(layout)["a"] = -1.0
        assert source.key_shares(layout)["a"] == 0.5

    @pytest.mark.slow
    @pytest.mark.parametrize(
        ("build", "key", "percent"),
        [
            (build_en, "a", 8.29),
            (build_en, "k", 0.90),
            (build_is, "k", 2.93),
            (build_is, "d", 1.45),
        ],
    )
    def test_the_shares_the_amendment_records(
        self, wordfreq_source: WordfreqSource, build: Callable[[], Layout], key: str, percent: float
    ) -> None:
        # ADR-032's table, from spikes/key_share_definition_spike.py.
        assert round(wordfreq_source.key_shares(build())[key] * 100, 2) == percent


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
