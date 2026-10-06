from takki import config
from takki.lesson.introducer import anchor_keys
from takki.lesson.key_state import DEFAULT_CRITERION, Evidence, KeyStates, qualifies
from takki.lesson.milestones import (
    ANCHOR,
    ANCHOR_CRITERION,
    LADDER,
    MilestoneDetector,
    anchor_reached,
    grapheme_thresholds,
    satisfied_rungs,
)
from takki.persistence import Store, WindowStats
from takki.platform.layout import Layout, build_de, build_en, build_is
from tests.fakes.fake_store import FakeStore

# The shortest window that reaches the anchor bar: 25 presses, and at 25 the
# lower bound on 0.95 allows no miss (ADR-027 § The Anchor Gate).
AT_THE_BAR = WindowStats(attempt_count=25, correct_count=25, distinct_days=2)


def fresh(stats: WindowStats) -> Evidence:
    """A window practised just now: nothing in it has aged."""
    return Evidence(
        stats.attempt_count,
        stats.distinct_days,
        float(stats.attempt_count),
        float(stats.correct_count),
    )


def anchored(layout: Layout, stats: WindowStats = AT_THE_BAR) -> dict[str, Evidence]:
    return dict.fromkeys(anchor_keys(layout), fresh(stats))


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
        assert anchor_reached(build_en(), anchored(build_en(), WindowStats(25, 25, 2)))
        # One miss is carried by 52 presses, two by 79 (ADR-027).
        assert anchor_reached(build_en(), anchored(build_en(), WindowStats(52, 51, 2)))
        assert anchor_reached(build_en(), anchored(build_en(), WindowStats(79, 77, 2)))

    def test_twenty_four_of_twenty_five_no_longer_reaches_it(self) -> None:
        # The case the bound is for: 96% raw met the old test.
        assert 24 / 25 >= config.ANCHOR_MIN_ACCURACY
        assert not anchor_reached(build_en(), anchored(build_en(), WindowStats(25, 24, 2)))

    def test_one_attempt_short_is_not(self) -> None:
        assert not anchor_reached(build_en(), anchored(build_en(), WindowStats(24, 24, 2)))

    def test_accuracy_below_the_bar_is_not(self) -> None:
        assert not anchor_reached(build_en(), anchored(build_en(), WindowStats(51, 50, 2)))
        assert not anchor_reached(build_en(), anchored(build_en(), WindowStats(78, 76, 2)))

    def test_one_practice_day_is_not(self) -> None:
        assert not anchor_reached(build_en(), anchored(build_en(), WindowStats(25, 25, 1)))

    def test_a_key_known_at_the_general_bar_can_still_miss_the_anchor_bar(self) -> None:
        ninety_three_percent = WindowStats(attempt_count=90, correct_count=84, distinct_days=2)
        assert qualifies(fresh(ninety_three_percent))
        assert not anchor_reached(build_en(), anchored(build_en(), ninety_three_percent))

    def test_the_anchor_is_reachable_long_before_a_key_is_known(self) -> None:
        assert not qualifies(fresh(AT_THE_BAR))
        assert anchor_reached(build_en(), anchored(build_en()))


class TestAnchorKeys:
    def test_all_six_must_clear_the_bar(self) -> None:
        for missed in anchor_keys(build_en()):
            stats = anchored(build_en())
            stats[missed] = fresh(WindowStats(24, 24, 2))
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


DAY1 = "2026-01-01T10:00:00+00:00"
DAY2 = "2026-01-02T10:00:00+00:00"
KNOWN = WindowStats(attempt_count=90, correct_count=90, distinct_days=2)
# The order `introduction_sequence` emits for English: Stage 0's six, then the
# home-row-fill strategy. Spelled out rather than derived, so a change to the
# ordering shows up here as a diff rather than silently redefining the walk.
EN_INTRODUCTION_ORDER = "fjruvmdkslaghentociwybpxqz"


class RecordingStore(FakeStore):
    """FakeStore that keeps every `record_milestone` call, duplicates included.

    The store itself is idempotent, so `achieved_milestones()` cannot tell a
    rung written once from one written on every check. The write count is the
    thing under test.
    """

    def __init__(self) -> None:
        super().__init__()
        self.writes: list[str] = []

    def record_milestone(self, profile_id: int, level: str, achieved_at: str | None = None) -> None:
        self.writes.append(level)
        super().record_milestone(profile_id, level, achieved_at)


def practise(store: Store, profile_id: int, char: str, window: WindowStats = KNOWN) -> None:
    """Answer `window` prompts for one key, as AttemptCounter would.

    `attempt_count` prompts, `correct_count` of them right, spread over
    `distinct_days` days. Both writes, because Active is `key_stats` row
    presence and Known is the `key_attempts` window (ADR-027 § Key States) --
    a key with attempts and no row is a state the counter never produces.
    Appends: two calls on one key sum, they do not replace.
    """
    for i in range(window.attempt_count):
        day = DAY1 if window.distinct_days == 1 or i % 2 == 0 else DAY2
        correct = i < window.correct_count
        store.upsert_key_stat(profile_id, char, correct, day)
        store.append_attempt(profile_id, char, correct, day)


def states(store: Store, profile_id: int = 1) -> KeyStates:
    # Read on the second practice day, so nothing has had time to age.
    return KeyStates(store, profile_id, now=lambda: DAY2)


def detector(store: Store, layout: Layout, profile_id: int = 1) -> MilestoneDetector:
    return MilestoneDetector(store, profile_id, layout, states(store, profile_id))


def make_known(store: Store, profile_id: int, layout: Layout, count: int) -> None:
    """Bring the first `count` graphemes of the layout to the Known bar."""
    for char in sorted(layout.graphemes)[:count]:
        if store.window_stats(profile_id, char).attempt_count == 0:
            practise(store, profile_id, char)


class TestFiringOnce:
    """The rolling query is not once; the `milestones` rows are what make it so."""

    def test_a_rung_fires_on_the_check_that_crosses_it_and_never_again(self) -> None:
        store, layout = RecordingStore(), build_en()
        found = detector(store, layout)
        make_known(store, 1, layout, 7)
        assert found.check() == ()
        make_known(store, 1, layout, 8)
        assert found.check() == ("third",)
        assert found.check() == ()
        assert found.check() == ()
        assert store.writes == ["third"]
        assert store.achieved_milestones(1) == ["third"]

    def test_a_key_only_speed_keeps_from_known_does_not_count_towards_a_rung(self) -> None:
        # alpha-plan #12f: the rungs count Known, and Known has a speed term.
        store, layout = RecordingStore(), build_en()
        eight = sorted(layout.graphemes)[:8]
        for char in eight:
            ms = 2500 if char == eight[0] else 1000
            for i in range(config.KNOWN_MIN_ATTEMPTS):
                day = DAY1 if i % 2 == 0 else DAY2
                store.upsert_key_stat(1, char, True, day)
                store.append_attempt(1, char, True, day, ms)
        found = detector(store, layout)
        assert states(store).slow_keys() == {eight[0]}
        assert found.check() == ()
        for _ in range(config.SPEED_SAMPLE):
            store.append_attempt(1, eight[0], True, DAY2, 1000)
        assert found.check() == ("third",)

    def test_the_rung_sequence_of_a_full_english_walk(self) -> None:
        """Zero to the full alphabet, in the order the introducer emits keys.

        Each rung fires on the check that crosses it, once, and the writes are
        the ladder in order. The anchor rung comes first and comes from Stage 0
        -- at that point not one key is Known.
        """
        store, layout = RecordingStore(), build_en()
        found = detector(store, layout)
        fired: list[tuple[str, tuple[str, ...]]] = []

        assert set(EN_INTRODUCTION_ORDER) == set(layout.graphemes)
        assert found.check() == ()
        for char in anchor_keys(layout):
            practise(store, 1, char, AT_THE_BAR)
        assert states(store).known_keys() == set()
        fired.append(("stage 0 done at the anchor bar", found.check()))

        for position, char in enumerate(EN_INTRODUCTION_ORDER, start=1):
            practise(store, 1, char)
            crossed = found.check()
            if crossed:
                fired.append((f"{position} graphemes Known", crossed))

        assert fired == [
            ("stage 0 done at the anchor bar", ("anchor",)),
            ("8 graphemes Known", ("third",)),
            ("13 graphemes Known", ("half",)),
            ("17 graphemes Known", ("two_thirds",)),
            ("21 graphemes Known", ("five_sixths",)),
            ("26 graphemes Known", ("alphabet",)),
        ]
        assert tuple(store.writes) == LADDER

    def test_a_fresh_detector_does_not_re_fire_what_the_store_already_holds(self) -> None:
        # The reason the persisted set is the authority: the detector is
        # session-local, the milestone is not. An in-memory record would
        # congratulate the child on a third of the alphabet every session.
        store, layout = RecordingStore(), build_en()
        make_known(store, 1, layout, 13)
        assert detector(store, layout).check() == ("third", "half")
        assert detector(store, layout).check() == ()
        assert store.writes == ["third", "half"]

    def test_two_detectors_on_one_profile_do_not_double_fire(self) -> None:
        store, layout = RecordingStore(), build_en()
        first, second = detector(store, layout), detector(store, layout)
        make_known(store, 1, layout, 8)
        assert first.check() == ("third",)
        assert second.check() == ()
        assert store.writes == ["third"]

    def test_two_profiles_earn_their_rungs_independently(self) -> None:
        store, layout = RecordingStore(), build_en()
        make_known(store, 1, layout, 8)
        assert detector(store, layout, 1).check() == ("third",)
        assert detector(store, layout, 2).check() == ()
        assert store.achieved_milestones(2) == []


class TestNeverRevoked:
    def test_a_rung_stays_fired_when_the_known_count_falls_back_below_it(self) -> None:
        store, layout = RecordingStore(), build_en()
        found = detector(store, layout)
        make_known(store, 1, layout, 13)
        assert found.check() == ("third", "half")
        # 'a' loses its accuracy: 90 correct then 20 wrong is 110 attempts at
        # 81.8%, under the Known floor. The Known count drops to 12, one under
        # `half` -- ADR-027 § Key States: milestones are never reverted.
        for _ in range(20):
            store.append_attempt(1, "a", False, DAY2)
        assert satisfied_rungs(layout, states(store).known_keys()) == ("third",)
        assert found.check() == ()
        assert store.achieved_milestones(1) == ["third", "half"]
        assert store.writes == ["third", "half"]

    def test_a_dropped_anchor_is_not_a_milestone_change(self) -> None:
        # ADR-027 § The Anchor Gate: a dropped anchor is remediation (session
        # 9's re-exposure slot with an accuracy trigger), not a withdrawal.
        store, layout = RecordingStore(), build_en()
        found = detector(store, layout)
        for char in anchor_keys(layout):
            practise(store, 1, char, AT_THE_BAR)
        assert found.check() == (ANCHOR,)
        for _ in range(40):
            store.append_attempt(1, "f", False, DAY2)
        assert not anchor_reached(layout, {"f": states(store).evidence("f")})
        assert found.check() == ()
        assert store.writes == [ANCHOR]


class TestSeveralRungsAtOnce:
    def test_a_jump_past_two_rungs_writes_both_in_ladder_order(self) -> None:
        store, layout = RecordingStore(), build_en()
        found = detector(store, layout)
        make_known(store, 1, layout, 7)
        assert found.check() == ()
        make_known(store, 1, layout, 13)
        assert found.check() == ("third", "half")
        assert store.writes == ["third", "half"]

    def test_the_whole_ladder_can_land_on_one_check(self) -> None:
        # A profile restored from a backup, or one nothing ever checked. At 90
        # attempts and 100% each the six anchor keys are past the anchor bar as
        # well as the Known bar, so every rung including the first is due.
        store, layout = RecordingStore(), build_en()
        make_known(store, 1, layout, 26)
        assert detector(store, layout).check() == LADDER
        assert tuple(store.writes) == LADDER


class TestAnchorRungDetection:
    def test_it_fires_on_its_own_criterion_with_nothing_known(self) -> None:
        store, layout = RecordingStore(), build_en()
        for char in anchor_keys(layout):
            practise(store, 1, char, AT_THE_BAR)
        assert states(store).known_keys() == set()
        assert detector(store, layout).check() == (ANCHOR,)

    def test_it_does_not_ask_how_fast_the_six_keys_are(self) -> None:
        # alpha-plan #12f: Known has a speed term and this rung does not. It
        # asks whether the child finds home, and `r` nine times slower than the
        # other five still has.
        store, layout = RecordingStore(), build_en()
        for char in anchor_keys(layout):
            ms = 9000 if char == "r" else 1000
            for i in range(AT_THE_BAR.attempt_count):
                day = DAY1 if i % 2 == 0 else DAY2
                store.upsert_key_stat(1, char, True, day)
                store.append_attempt(1, char, True, day, ms)
        assert detector(store, layout).check() == (ANCHOR,)

    def test_six_known_letters_that_are_not_the_anchor_keys_do_not_fire_it(self) -> None:
        store, layout = RecordingStore(), build_en()
        for char in "abcdeg":
            practise(store, 1, char)
        assert len(states(store).known_keys()) == 6
        assert detector(store, layout).check() == ()
        assert store.writes == []

    def test_one_practice_day_at_the_bar_does_not_fire_it(self) -> None:
        store, layout = RecordingStore(), build_en()
        for char in anchor_keys(layout):
            practise(store, 1, char, WindowStats(25, 25, 1))
        found = detector(store, layout)
        assert found.check() == ()
        # The same six keys, practised again the next day, clear it.
        for char in anchor_keys(layout):
            store.append_attempt(1, char, True, DAY2)
        assert found.check() == (ANCHOR,)
        assert store.writes == [ANCHOR]

    def test_five_of_six_at_the_bar_does_not_fire_it(self) -> None:
        store, layout = RecordingStore(), build_en()
        for char in anchor_keys(layout)[:5]:
            practise(store, 1, char, AT_THE_BAR)
        assert detector(store, layout).check() == ()

    def test_an_anchor_missed_at_stage_0_fires_late_and_out_of_ladder_order(self) -> None:
        """Pinned, not endorsed — see ADR-027 § The Anchor Gate's amendment.

        The gate is a rolling query until it passes, so a child who ends Stage
        0 just under the bar on one key earns the rung later, off a window that
        ordinary drilling has since refilled, after `third` has already fired.
        The alternative — close the window when Stage 0 ends — is a rung that
        can never fire for any child the curriculum lets past, which is the
        roadmap § D question and not this module's to answer.
        """
        store, layout = RecordingStore(), build_en()
        found = detector(store, layout)
        for char in anchor_keys(layout):
            practise(store, 1, char, AT_THE_BAR)
        practise(store, 1, "m", WindowStats(25, 19, 2))  # m leaves Stage 0 at 86%
        assert found.check() == ()

        # The curriculum runs on and the child reaches a third of the alphabet.
        make_known(store, 1, layout, 13)
        assert found.check() == ("third",)

        # Only now does m's rolling window come back over the bar: the misses
        # have to leave the window, not merely be outnumbered.
        clean = WindowStats(config.ATTEMPT_WINDOW, config.ATTEMPT_WINDOW, distinct_days=2)
        practise(store, 1, "m", clean)
        assert found.check() == (ANCHOR,)
        assert store.writes == ["third", ANCHOR]

    def test_it_is_not_re_measured_once_it_has_fired(self) -> None:
        # A detector holding a fired anchor must not touch the window at all:
        # `check` short-circuits on the persisted set, so a store that would
        # answer differently is never asked.
        store, layout = RecordingStore(), build_en()
        for char in anchor_keys(layout):
            practise(store, 1, char, AT_THE_BAR)
        found = detector(store, layout)
        assert found.check() == (ANCHOR,)
        for char in anchor_keys(layout):
            for _ in range(200):
                store.append_attempt(1, char, False, DAY2)
        assert found.check() == ()
        assert store.achieved_milestones(1) == [ANCHOR]


class TestOtherLayouts:
    def test_icelandics_denominator_is_the_layouts_36_graphemes(self) -> None:
        # roadmap D records 32 vs 36 as contested; the ladder is built on the
        # layout reading and the detector inherits it unchanged. `third` fires
        # at 12, not at 10 (which is floor(32/3)).
        store, layout = RecordingStore(), build_is()
        found = detector(store, layout)
        make_known(store, 1, layout, 11)
        assert found.check() == ()
        make_known(store, 1, layout, 12)
        assert found.check() == ("third",)

    def test_a_german_walk_fires_at_the_german_thresholds(self) -> None:
        store, layout = RecordingStore(), build_de()
        found = detector(store, layout)
        make_known(store, 1, layout, 9)
        assert found.check() == ()
        make_known(store, 1, layout, 15)
        assert found.check() == ("third", "half")
