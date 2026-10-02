import pytest

from takki import config
from takki.lesson.introducer import KeyIntroducer, introduction_sequence
from takki.lesson.key_state import KeyStates
from takki.lesson.progression import (
    active_graphemes,
    keys_in_progress,
    layer_two_unlocked,
    room_for_step,
)
from takki.persistence import Store
from takki.platform.layout import Layout, build_de, build_en, build_is
from tests.fakes.fake_store import FakeStore
from tests.fakes.fixed_list_source import FixedListSource

DAY1 = "2026-01-01T10:00:00"
DAY2 = "2026-01-02T10:00:00"

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


def answer(store: Store, char: str, *, correct: int = 0, wrong: int = 0, day: str = DAY1) -> None:
    """Answer prompts for one key, as AttemptCounter would."""
    for i in range(correct + wrong):
        right = i < correct
        store.upsert_key_stat(1, char, right, day)
        store.append_attempt(1, char, right, day)


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


class TestRoomForStep:
    """ADR-010: a step is introduced only if it leaves at most the cap of keys short of Known."""

    def test_the_cap_is_the_configured_one(self) -> None:
        assert config.MAX_KEYS_IN_PROGRESS == 6

    def test_nothing_in_progress_is_always_room(self) -> None:
        # Otherwise a cap below the first step's size would never let it in.
        store = FakeStore()
        assert room_for_step(build_en(), states(store), ["f", "j"])
        assert room_for_step(build_en(), states(store), ["f", "j"], cap=1)

    def test_a_key_in_progress_is_active_and_not_known(self) -> None:
        store = FakeStore()
        answer(store, "f", correct=config.KNOWN_MIN_ATTEMPTS)
        answer(store, "j", correct=1)
        assert keys_in_progress(build_en(), states(store)) == {"f", "j"}
        answer(store, "f", correct=1, day=DAY2)
        assert states(store).known_keys() == {"f"}
        assert keys_in_progress(build_en(), states(store)) == {"j"}

    @pytest.mark.parametrize("in_progress", range(1, config.MAX_KEYS_IN_PROGRESS + 1))
    def test_a_step_fits_only_if_the_total_stays_within_the_cap(self, in_progress: int) -> None:
        store = FakeStore()
        for char in "fjruvm"[:in_progress]:
            answer(store, char, correct=1)
        free = config.MAX_KEYS_IN_PROGRESS - in_progress
        assert room_for_step(build_en(), states(store), ["d"]) is (free >= 1)
        assert room_for_step(build_en(), states(store), ["d", "k"]) is (free >= 2)

    def test_each_known_key_frees_exactly_one_slot(self) -> None:
        store = FakeStore()
        for char in "fjruvm":
            answer(store, char, correct=config.KNOWN_MIN_ATTEMPTS)
        assert not room_for_step(build_en(), states(store), ["d"])
        answer(store, "f", correct=1, day=DAY2)
        assert room_for_step(build_en(), states(store), ["d"])
        assert not room_for_step(build_en(), states(store), ["d", "k"])
        answer(store, "j", correct=1, day=DAY2)
        assert room_for_step(build_en(), states(store), ["d", "k"])

    def test_a_key_that_stops_being_known_takes_its_slot_back(self) -> None:
        # A rolling query, unlike a milestone: Known is read off the window, so
        # a key whose accuracy slips under the bar is in progress again.
        store = FakeStore()
        for char in "fjruvm":
            answer(store, char, correct=config.KNOWN_MIN_ATTEMPTS)
        answer(store, "f", correct=1, day=DAY2)
        assert room_for_step(build_en(), states(store), ["d"])
        answer(store, "f", wrong=20, day=DAY2)
        assert states(store).known_keys() == set()
        assert not room_for_step(build_en(), states(store), ["d"])

    def test_a_member_that_is_already_active_is_not_counted_twice(self) -> None:
        # A pair one member of which was answered and the other never was.
        store = FakeStore()
        for char in "fjruv":
            answer(store, char, correct=1)
        assert room_for_step(build_en(), states(store), ["v", "m"])
        assert not room_for_step(build_en(), states(store), ["d", "k"])

    def test_a_cap_passed_in_is_honoured(self) -> None:
        store = FakeStore()
        for char in "fjruvm":
            answer(store, char, correct=1)
        assert not room_for_step(build_en(), states(store), ["d", "k"])
        assert room_for_step(build_en(), states(store), ["d", "k"], cap=8)
        assert not room_for_step(build_en(), states(store), ["d", "k"], cap=7)

    def test_a_grapheme_the_current_layout_cannot_produce_holds_no_slot(self) -> None:
        store = FakeStore()
        for char in "fjruv":
            answer(store, char, correct=1)
        answer(store, "ä", correct=1)
        assert room_for_step(build_en(), states(store), ["m"])
        assert not room_for_step(build_de(), states(store), ["m"])


class TestProgressionIsNotAMilestone:
    def test_neither_predicate_writes_anything(self) -> None:
        layout, store = build_en(), FakeStore()
        for char in "fjruvmdk":
            answer(store, char, correct=10)
        before = store.achieved_milestones(1)
        assert layer_two_unlocked(layout, states(store))
        assert not room_for_step(layout, states(store), ["a"])
        assert store.achieved_milestones(1) == before == []

    def test_the_shipped_sequence_covers_the_whole_layout(self) -> None:
        # Guards the walk above: if the strategy ever stopped emitting every
        # grapheme, the counts it asserts would quietly stop meaning anything.
        layout = build_en()
        steps = introduction_sequence(layout, FixedListSource(EN_WORDS))
        emitted = [member.grapheme for step in steps for member in step.keys]
        assert sorted(emitted) == sorted(layout.graphemes)
