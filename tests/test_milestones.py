from takki import config
from takki.lesson.introducer import anchor_keys
from takki.lesson.key_state import DEFAULT_CRITERION, is_known
from takki.lesson.milestones import (
    ANCHOR,
    ANCHOR_CRITERION,
    LADDER,
    anchor_reached,
    grapheme_thresholds,
    satisfied_rungs,
)
from takki.persistence import WindowStats
from takki.platform.layout import Layout, build_de, build_en, build_is

AT_THE_BAR = WindowStats(attempt_count=25, correct_count=24, distinct_days=2)


def anchored(layout: Layout, stats: WindowStats = AT_THE_BAR) -> dict[str, WindowStats]:
    return dict.fromkeys(anchor_keys(layout), stats)


def known(layout: Layout, count: int) -> set[str]:
    return set(sorted(layout.graphemes)[:count])


class TestLadderShape:
    """ADR-027 § Milestone Ladder — six rungs, the anchor gate first."""

    def test_the_ladder_is_the_six_slugs_in_order(self) -> None:
        assert LADDER == ("anchor", "third", "half", "two_thirds", "five_sixths", "alphabet")

    def test_english_thresholds(self) -> None:
        assert grapheme_thresholds(build_en()) == {
            "third": 8,
            "half": 13,
            "two_thirds": 17,
            "five_sixths": 21,
            "alphabet": 26,
        }

    def test_german_thresholds(self) -> None:
        assert grapheme_thresholds(build_de()) == {
            "third": 10,
            "half": 15,
            "two_thirds": 20,
            "five_sixths": 25,
            "alphabet": 30,
        }

    def test_icelandic_thresholds(self) -> None:
        # 36 graphemes: the layout's 30 direct keys plus the six acutes. The
        # dead key itself is keystroke mechanics and is not in the denominator
        # (ADR-027 § Milestone Denominator).
        layout = build_is()
        assert len(layout.graphemes) == 36
        assert "dead-acute" not in layout.graphemes
        assert grapheme_thresholds(layout) == {
            "third": 12,
            "half": 18,
            "two_thirds": 24,
            "five_sixths": 30,
            "alphabet": 36,
        }

    def test_rung_2_clears_the_layer_2_unlock_in_every_layout(self) -> None:
        # ADR-027's claim that reaching `third` means real words are typeable:
        # ADR-010 unlocks Layer 2 at >= 8 keys, and floor(N/3) is >= 8 for
        # every layout in the v1 target set.
        for build in (build_en, build_de, build_is):
            assert grapheme_thresholds(build())["third"] >= 8

    def test_the_anchor_rung_is_six_named_keys_and_not_a_grapheme_count(self) -> None:
        # It is absent from the counted thresholds on purpose: six Known
        # graphemes are not an anchor, and a milestone fired by mistake is
        # never revoked (ADR-027 § Key States).
        for build in (build_en, build_de, build_is):
            layout = build()
            assert len(anchor_keys(layout)) == 6
            assert ANCHOR not in grapheme_thresholds(layout)
            assert ANCHOR in LADDER


class TestSatisfiedRungs:
    """Pure: (layout, Known graphemes) -> the rungs earned. Detection is #10."""

    def test_nothing_known_and_no_anchor_earns_nothing(self) -> None:
        assert satisfied_rungs(build_en(), set()) == ()

    def test_the_anchor_rung_comes_from_stage_0_not_from_the_known_set(self) -> None:
        layout = build_en()
        assert satisfied_rungs(layout, set(anchor_keys(layout))) == ()
        assert satisfied_rungs(layout, set(), anchor=True) == (ANCHOR,)

    def test_english_rungs_at_each_threshold(self) -> None:
        layout = build_en()
        assert satisfied_rungs(layout, known(layout, 7)) == ()
        assert satisfied_rungs(layout, known(layout, 8)) == ("third",)
        assert satisfied_rungs(layout, known(layout, 12)) == ("third",)
        assert satisfied_rungs(layout, known(layout, 13)) == ("third", "half")
        assert satisfied_rungs(layout, known(layout, 17)) == ("third", "half", "two_thirds")
        assert satisfied_rungs(layout, known(layout, 21)) == (
            "third",
            "half",
            "two_thirds",
            "five_sixths",
        )
        assert satisfied_rungs(layout, known(layout, 25)) == (
            "third",
            "half",
            "two_thirds",
            "five_sixths",
        )
        assert satisfied_rungs(layout, known(layout, 26), anchor=True) == LADDER

    def test_the_top_rung_needs_every_grapheme(self) -> None:
        for build in (build_de, build_is):
            layout = build()
            full = set(layout.graphemes)
            assert "alphabet" not in satisfied_rungs(layout, full - {sorted(full)[0]})
            assert "alphabet" in satisfied_rungs(layout, full)

    def test_a_composite_counts_towards_the_rungs_it_is_in_the_denominator_of(self) -> None:
        layout = build_is()
        direct = {c for c, g in layout.graphemes.items() if g.mechanism == "direct"}
        assert satisfied_rungs(layout, direct) == ("third", "half", "two_thirds", "five_sixths")
        assert satisfied_rungs(layout, set(layout.graphemes)) == LADDER[1:]

    def test_a_key_that_is_not_on_this_layout_does_not_count(self) -> None:
        # key_stats survives a profile's language change; the denominator is
        # this layout's graphemes, so the count must be too.
        layout = build_en()
        assert satisfied_rungs(layout, known(layout, 7) | {"ä", "ö", "ü"}) == ()


class TestAnchorCriterion:
    """ADR-027 § The Anchor Gate — 25 attempts, 95%, 2 days."""

    def test_the_bar_is_the_configured_one(self) -> None:
        assert ANCHOR_CRITERION.min_attempts == config.ANCHOR_MIN_ATTEMPTS == 25
        assert ANCHOR_CRITERION.min_accuracy == config.ANCHOR_MIN_ACCURACY == 0.95
        assert ANCHOR_CRITERION.min_distinct_days == config.KNOWN_MIN_DISTINCT_DAYS == 2

    def test_it_is_shorter_and_stricter_than_known(self) -> None:
        assert ANCHOR_CRITERION.min_attempts < DEFAULT_CRITERION.min_attempts
        assert ANCHOR_CRITERION.min_accuracy > DEFAULT_CRITERION.min_accuracy

    def test_exactly_at_every_floor_is_reached(self) -> None:
        assert anchor_reached(build_en(), anchored(build_en(), WindowStats(25, 24, 2)))
        assert anchor_reached(build_en(), anchored(build_en(), WindowStats(60, 57, 2)))

    def test_one_attempt_short_is_not(self) -> None:
        assert not anchor_reached(build_en(), anchored(build_en(), WindowStats(24, 24, 2)))

    def test_accuracy_below_the_bar_is_not(self) -> None:
        assert not anchor_reached(build_en(), anchored(build_en(), WindowStats(60, 56, 2)))

    def test_one_practice_day_is_not(self) -> None:
        assert not anchor_reached(build_en(), anchored(build_en(), WindowStats(25, 25, 1)))

    def test_a_key_known_at_the_general_bar_can_still_miss_the_anchor_bar(self) -> None:
        ninety_three_percent = WindowStats(attempt_count=90, correct_count=84, distinct_days=2)
        assert is_known(ninety_three_percent)
        assert not anchor_reached(build_en(), anchored(build_en(), ninety_three_percent))

    def test_the_anchor_is_reachable_long_before_a_key_is_known(self) -> None:
        assert not is_known(AT_THE_BAR)
        assert anchor_reached(build_en(), anchored(build_en()))


class TestAnchorKeys:
    def test_all_six_must_clear_the_bar(self) -> None:
        for missed in anchor_keys(build_en()):
            stats = anchored(build_en())
            stats[missed] = WindowStats(24, 24, 2)
            assert not anchor_reached(build_en(), stats)

    def test_a_key_with_no_attempts_at_all_blocks_the_gate(self) -> None:
        stats = anchored(build_en())
        del stats["m"]
        assert not anchor_reached(build_en(), stats)

    def test_the_stretch_columns_are_not_part_of_the_gate(self) -> None:
        # t g b / y h n train lateral displacement, a different skill.
        layout = build_en()
        assert not set("tgbyhn") & set(anchor_keys(layout))
        assert anchor_reached(layout, anchored(layout))
