from takki import config
from takki.lesson.introducer import KeyIntroducer, introduction_sequence
from takki.lesson.key_state import KeyStates
from takki.lesson.progression import (
    active_graphemes,
    layer_two_unlocked,
    ready_for_new_key,
)
from takki.persistence import Store
from takki.platform.layout import Layout, build_de, build_en, build_is
from tests.fakes.fake_store import FakeStore
from tests.fakes.fixed_list_source import FixedListSource

DAY1 = "2026-01-01T10:00:00"

# Enough English that every home-row key the strategy reaches has a frequency;
# the unlock walk only cares about the order, not the weights.
EN_WORDS: dict[str, float] = {
    "the": 100.0,
    "and": 90.0,
    "for": 80.0,
    "his": 70.0,
    "not": 60.0,
    "you": 50.0,
    "with": 40.0,
    "have": 30.0,
    "this": 20.0,
    "from": 10.0,
    "jump": 9.0,
    "very": 8.0,
    "quick": 7.0,
    "box": 6.0,
    "lazy": 5.0,
    "dogs": 4.0,
}


def answer(store: Store, char: str, *, correct: int = 0, wrong: int = 0) -> None:
    """Answer prompts for one key, as AttemptCounter would."""
    for i in range(correct + wrong):
        right = i < correct
        store.upsert_key_stat(1, char, right, DAY1)
        store.append_attempt(1, char, right, DAY1)


def states(store: Store) -> KeyStates:
    return KeyStates(store, 1)


def introducer(layout: Layout, store: Store) -> KeyIntroducer:
    return KeyIntroducer(layout, FixedListSource(EN_WORDS), states(store))


class TestLayerTwoUnlock:
    """ADR-010: real words at >= 8 keys, counted Active (ADR-028 § Layer-2 unlock)."""

    def test_the_threshold_is_the_configured_one(self) -> None:
        assert config.LAYER_2_MIN_KEYS == 8

    def test_it_counts_active_and_not_known(self) -> None:
        # One answered prompt each is enough: Active is row presence, and no
        # key here is anywhere near Known (90 attempts over two days).
        store = FakeStore()
        for char in "fjruvmdk":
            answer(store, char, correct=1)
        assert states(store).known_keys() == set()
        assert layer_two_unlocked(build_en(), states(store))

    def test_seven_active_keys_is_still_locked(self) -> None:
        store = FakeStore()
        for char in "fjruvmd":
            answer(store, char, correct=1)
        assert not layer_two_unlocked(build_en(), states(store))

    def test_the_adr_028_walk_of_the_english_count(self) -> None:
        # ADR-028 § Layer-2 unlock walks 2, 4, 6, 7, 9 for a home-row-fill
        # curriculum with no Stage 0 in front of it: F+J, D+K, S+L, A solo
        # (the right pinky's home position is `;`, not a letter), G+H.
        layout = build_en()
        store = FakeStore()
        locked_at: list[int] = []
        for pair in ("fj", "dk", "sl", "a", "gh"):
            for char in pair:
                answer(store, char, correct=1)
            count = len(active_graphemes(layout, states(store)))
            if not layer_two_unlocked(layout, states(store)):
                locked_at.append(count)
        assert locked_at == [2, 4, 6, 7]
        assert len(active_graphemes(layout, states(store))) == 9

    def test_the_shipped_english_walk_unlocks_one_step_earlier_at_exactly_8(self) -> None:
        # Stage 0 (ADR-023, alpha session 8b) sits in front of the strategy and
        # its three steps are all pairs, so the shipped count goes 2, 4, 6, 8 --
        # never 7, and the unlock lands on the threshold exactly. ADR-028's
        # arithmetic predates the stage; its conclusion ("layouts whose home
        # rows yield exactly 8 trigger the unlock at the same count, no change
        # to the threshold is needed") is what survives.
        layout, store = build_en(), FakeStore()
        keys = introducer(layout, store)
        walk: list[tuple[int, bool]] = []
        for _ in range(4):
            step = keys.introduce_next()
            assert step is not None
            for member in step.keys:
                answer(store, member.grapheme, correct=1)
            walk.append(
                (
                    len(active_graphemes(layout, states(store))),
                    layer_two_unlocked(layout, states(store)),
                )
            )
        assert walk == [(2, False), (4, False), (6, False), (8, True)]

    def test_a_grapheme_the_current_layout_cannot_produce_does_not_count(self) -> None:
        # key_stats survives a profile's language change.
        store = FakeStore()
        for char in "fjruvm":
            answer(store, char, correct=1)
        for char in "äöü":
            answer(store, char, correct=1)
        assert len(active_graphemes(build_en(), states(store))) == 6
        assert not layer_two_unlocked(build_en(), states(store))
        assert layer_two_unlocked(build_de(), states(store))

    def test_every_layout_in_the_target_set_unlocks_below_its_first_rung(self) -> None:
        # ADR-027 § Milestone Ladder leans on this: by `third` the child can
        # type real words in any language.
        for build in (build_en, build_de, build_is):
            layout = build()
            store = FakeStore()
            for char in sorted(layout.graphemes)[: config.LAYER_2_MIN_KEYS]:
                answer(store, char, correct=1)
            assert layer_two_unlocked(layout, states(store))


class TestReadyForNewKey:
    """ADR-010: a new key arrives at >= 90% over >= 50 presses on the current set."""

    def test_the_thresholds_are_the_configured_ones(self) -> None:
        assert config.INTRODUCE_MIN_PRESSES == 50
        assert config.INTRODUCE_MIN_ACCURACY == 0.90

    def test_an_empty_active_set_is_ready(self) -> None:
        # Otherwise the first key of a profile could never be introduced.
        store = FakeStore()
        assert active_graphemes(build_en(), states(store)) == set()
        assert ready_for_new_key(build_en(), states(store))

    def test_below_the_press_floor_is_not_ready_however_accurate(self) -> None:
        store = FakeStore()
        answer(store, "f", correct=49)
        assert not ready_for_new_key(build_en(), states(store))

    def test_exactly_at_the_press_floor_is_ready(self) -> None:
        store = FakeStore()
        answer(store, "f", correct=50)
        assert ready_for_new_key(build_en(), states(store))

    def test_the_floor_is_the_current_set_summed_not_one_key(self) -> None:
        # Two keys at 25 presses each clear a 50-press floor together; neither
        # would alone. ADR-023 § Where the phase boundary is: "on the current
        # set", and a per-key reading would be a second, stricter definition of
        # Known.
        store = FakeStore()
        answer(store, "f", correct=20)
        answer(store, "j", correct=20)
        assert not ready_for_new_key(build_en(), states(store))
        answer(store, "f", correct=5)
        answer(store, "j", correct=5)
        assert ready_for_new_key(build_en(), states(store))

    def test_accuracy_is_the_sets_and_not_the_worst_keys(self) -> None:
        # 'j' on its own is at 60%, well under the bar. The set is at 98%, and
        # the gate is the set's -- a struggling key is the weighting engine's
        # problem (ADR-027 § Key States), not the curriculum's pace.
        store = FakeStore()
        answer(store, "f", correct=190)
        answer(store, "j", correct=6, wrong=4)
        assert states(store).window_stats("j").correct_count == 6
        assert ready_for_new_key(build_en(), states(store))

    def test_the_whole_set_slipping_does_close_it(self) -> None:
        store = FakeStore()
        answer(store, "f", correct=45, wrong=5)
        answer(store, "j", correct=45, wrong=5)
        assert ready_for_new_key(build_en(), states(store))
        answer(store, "f", wrong=20)
        answer(store, "j", wrong=20)
        assert not ready_for_new_key(build_en(), states(store))

    def test_exactly_at_the_accuracy_floor_is_ready(self) -> None:
        store = FakeStore()
        answer(store, "f", correct=90, wrong=10)
        assert ready_for_new_key(build_en(), states(store))

    def test_one_press_under_the_accuracy_floor_is_not(self) -> None:
        store = FakeStore()
        answer(store, "f", correct=89, wrong=11)
        assert not ready_for_new_key(build_en(), states(store))

    def test_it_is_a_rolling_query_that_can_close_again(self) -> None:
        # Unlike a milestone. The child stops being ready for a new key when
        # the set they already have slips.
        store = FakeStore()
        answer(store, "f", correct=60)
        assert ready_for_new_key(build_en(), states(store))
        answer(store, "f", wrong=20)
        assert not ready_for_new_key(build_en(), states(store))

    def test_a_grapheme_the_current_layout_cannot_produce_does_not_pace_it(self) -> None:
        store = FakeStore()
        answer(store, "f", correct=60)
        answer(store, "ä", wrong=60)
        assert ready_for_new_key(build_en(), states(store))
        assert not ready_for_new_key(build_de(), states(store))


class TestProgressionIsNotAMilestone:
    def test_neither_predicate_writes_anything(self) -> None:
        layout, store = build_en(), FakeStore()
        for char in "fjruvmdk":
            answer(store, char, correct=10)
        before = store.achieved_milestones(1)
        assert layer_two_unlocked(layout, states(store))
        assert ready_for_new_key(layout, states(store))
        assert store.achieved_milestones(1) == before == []

    def test_the_shipped_sequence_covers_the_whole_layout(self) -> None:
        # Guards the walk above: if the strategy ever stopped emitting every
        # grapheme, the counts it asserts would quietly stop meaning anything.
        layout = build_en()
        steps = introduction_sequence(layout, FixedListSource(EN_WORDS))
        emitted = [member.grapheme for step in steps for member in step.keys]
        assert sorted(emitted) == sorted(layout.graphemes)
