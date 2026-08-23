from typing import ClassVar

from takki.language import WordSource
from takki.language.wordfreq_source import WordfreqSource
from takki.lesson.introducer import (
    IntroductionStep,
    KeyIntroducer,
    KeyIntroduction,
    Location,
    describe,
    introduction_sequence,
)
from takki.lesson.key_state import KeyStates
from takki.persistence import Store
from takki.platform.layout import Layout, build_de, build_en, build_is
from tests.fakes.fake_platform import FakePlatformInterface
from tests.fakes.fake_store import FakeStore
from tests.fakes.fixed_list_source import FixedListSource

# One word per letter of interest, weighted so the Phase 2 order is fully
# determined by this table rather than by any corpus. Words are >= 3 chars
# (the grapheme-weight floor) and share no letters except deliberately.
EN_WORDS: dict[str, float] = {
    "eee": 100.0,
    "nnn": 90.0,
    "ttt": 80.0,
    "ooo": 70.0,
    "rrr": 60.0,
    "iii": 50.0,
    "www": 40.0,
    "uuu": 30.0,
    "bbb": 20.0,
    "ppp": 10.0,
}


def source(words: dict[str, float]) -> WordSource:
    return FixedListSource(words)


def names(steps: list[IntroductionStep]) -> list[list[str]]:
    return [[k.key for k in step.keys] for step in steps]


def phases(steps: list[IntroductionStep]) -> list[int]:
    return [step.phase for step in steps]


def flat(steps: list[IntroductionStep]) -> list[KeyIntroduction]:
    return [k for step in steps for k in step.keys]


def sequence(layout: Layout, words: dict[str, float] = EN_WORDS) -> list[IntroductionStep]:
    return introduction_sequence(layout, source(words))


def stocked(store: Store, profile_id: int, *chars: str) -> None:
    """Make each character Active: one counted keystroke creates the row (ADR-027)."""
    for char in chars:
        store.upsert_key_stat(profile_id, char, True, "2026-01-01T10:00:00")


def introducer(
    layout: Layout, store: Store, profile_id: int, words: dict[str, float] = EN_WORDS
) -> KeyIntroducer:
    return KeyIntroducer(layout, source(words), KeyStates(store, profile_id))


class TestPhase1Order:
    """ADR-023 § Phase 1 — the symmetric-pair table, reproduced exactly."""

    def test_english_full_phase_1(self) -> None:
        steps = [s for s in sequence(build_en()) if s.phase == 1]
        assert names(steps) == [["f", "j"], ["d", "k"], ["s", "l"], ["a"], ["g", "h"]]

    def test_english_step_4_is_solo_because_the_right_pinky_home_is_not_a_letter(self) -> None:
        assert names(sequence(build_en()))[3] == ["a"]

    def test_german_full_phase_1_pairs_a_with_o_umlaut_and_tails_a_umlaut(self) -> None:
        steps = [s for s in sequence(build_de()) if s.phase == 1]
        assert names(steps) == [
            ["f", "j"],
            ["d", "k"],
            ["s", "l"],
            ["a", "ö"],
            ["g", "h"],
            ["ä"],
        ]

    def test_icelandic_full_phase_1_pairs_a_with_ae_and_has_no_tail(self) -> None:
        steps = [s for s in sequence(build_is()) if s.phase == 1]
        assert names(steps) == [["f", "j"], ["d", "k"], ["s", "l"], ["a", "æ"], ["g", "h"]]

    def test_icelandic_dead_acute_is_on_the_home_row_but_not_in_phase_1(self) -> None:
        layout = build_is()
        assert layout.keys["dead-acute"].row == 3
        assert "dead-acute" not in [k.key for s in sequence(layout) if s.phase == 1 for k in s.keys]

    def test_phase_1_is_exactly_the_home_row_letters(self) -> None:
        layout = build_de()
        introduced = {k.key for s in sequence(layout) if s.phase == 1 for k in s.keys}
        assert introduced == {n for n, key in layout.keys.items() if key.row == 3}

    def test_left_member_always_precedes_right(self) -> None:
        for step in sequence(build_de()):
            assert [k.side for k in step.keys] in (["L"], ["R"], ["L", "R"])


class TestPhase1ToPhase2Boundary:
    """Seam 2 — the boundary is exhaustion of the Phase 1 segment, not Bronze."""

    def test_boundary_is_positional_not_accuracy_based(self) -> None:
        assert phases(sequence(build_en())) == [1] * 5 + [2] * 10

    def test_phase_2_opens_once_every_home_row_key_is_active(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Ana")
        stocked(store, profile.id, *"asdfghjkl")
        step = introducer(build_en(), store, profile.id).introduce_next()
        assert step is not None
        assert step.phase == 2
        assert [k.key for k in step.keys] == ["e", "n"]

    def test_one_missing_home_row_key_holds_phase_2_shut(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Ana")
        stocked(store, profile.id, *"asdfhjkl")  # no g
        step = introducer(build_en(), store, profile.id).introduce_next()
        assert step is not None
        assert step.phase == 1
        assert [k.key for k in step.keys] == ["g"]

    def test_home_row_active_but_far_from_known_still_opens_phase_2(self) -> None:
        # One counted keystroke per key: Active, nowhere near ADR-027's Known
        # floors. Bronze is later than this boundary, deliberately.
        store = FakeStore()
        profile = store.create_profile("Ana")
        stocked(store, profile.id, *"asdfghjkl")
        assert KeyStates(store, profile.id).known_keys() == set()
        step = introducer(build_en(), store, profile.id).introduce_next()
        assert step is not None and step.phase == 2


class TestPhase2Order:
    """ADR-023 § Phase 2 — frequency leader per hand over key_frequencies."""

    def test_english_full_phase_2_takes_one_key_per_hand(self) -> None:
        steps = [s for s in sequence(build_en()) if s.phase == 2]
        assert names(steps) == [
            ["e", "n"],
            ["t", "o"],
            ["r", "i"],
            ["w", "u"],
            ["b", "p"],
            ["c", "m"],
            ["q", "y"],
            ["v"],
            ["x"],
            ["z"],
        ]

    def test_solo_steps_drain_the_surviving_pool_to_the_end(self) -> None:
        # ADR-023 point 5 reads as though one solo step ends the phase; the
        # left pool outlives the right by three keys on QWERTY.
        steps = [s for s in sequence(build_en()) if s.phase == 2]
        assert names(steps[-3:]) == [["v"], ["x"], ["z"]]
        assert all(k.side == "L" for k in flat(steps[-3:]))

    def test_every_key_on_the_layout_is_introduced_exactly_once(self) -> None:
        for build in (build_en, build_de, build_is):
            layout = build()
            introduced = [k.key for k in flat(sequence(layout))]
            assert sorted(introduced) == sorted(layout.keys)

    def test_zero_weight_keys_rank_last_and_break_ties_alphabetically(self) -> None:
        # c, q, v, x and z appear in no word above, so they tail the left pool
        # in alphabetical order -- rank_graphemes' tie-break, applied to keys.
        left = [k.key for k in flat(sequence(build_en())) if k.side == "L" and k.key not in "asdfg"]
        assert left == ["e", "t", "r", "w", "b", "c", "q", "v", "x", "z"]

    def test_a_pool_that_empties_first_stops_appearing(self) -> None:
        steps = [s for s in sequence(build_en()) if s.phase == 2]
        sides = [[k.side for k in step.keys] for step in steps]
        assert sides == [["L", "R"]] * 7 + [["L"]] * 3


class TestModifierIntroduction:
    """ADR-023 + ADR-028 — a modifier is a Phase 2 step, ranked by composite frequency."""

    IS_WORDS: ClassVar[dict[str, float]] = {
        "ááá": 100.0,
        "ééé": 90.0,
        "rrr": 80.0,
        "nnn": 70.0,
        "sss": 60.0,
    }

    def test_icelandic_reaches_the_dead_key_in_phase_2(self) -> None:
        steps = sequence(build_is(), self.IS_WORDS)
        modifiers = [k for k in flat(steps) if k.is_modifier]
        assert [k.key for k in modifiers] == ["dead-acute"]

    def test_dead_acute_outranks_every_other_right_hand_key_when_acutes_dominate(self) -> None:
        # á + é weight lands entirely on dead-acute, which shares the right
        # pinky column with nothing else the corpus uses.
        steps = [s for s in sequence(build_is(), self.IS_WORDS) if s.phase == 2]
        assert names(steps)[0] == ["e", "dead-acute"]

    def test_dead_acute_is_the_eighteenth_key_on_real_icelandic_frequencies(self) -> None:
        # ADR-023 § Spike validation places it at step 18. The shipped sequence
        # reproduces that against real wordfreq -- the one number in this file
        # no fixture can manufacture.
        order = [k.key for k in flat(introduction_sequence(build_is(), WordfreqSource()))]
        assert order.index("dead-acute") == 17

    def test_german_has_no_modifier_anywhere_in_the_sequence(self) -> None:
        assert not any(k.is_modifier for k in flat(sequence(build_de())))

    def test_a_modifier_is_never_the_reference_for_another_key(self) -> None:
        for k in flat(sequence(build_is(), self.IS_WORDS)):
            if k.location is not None:
                assert k.location.reference != "dead-acute"

    def test_a_modifier_repeats_every_session_until_roadmap_b8_is_resolved(self) -> None:
        # Pinned, not endorsed. A modifier can never acquire a key_stats row
        # (roadmap B8), so nothing outlives the session-local record and the
        # accent key is re-announced forever once the sequence is exhausted.
        # Delete this test when B8 is closed -- it is the marker for where.
        store = FakeStore()
        profile = store.create_profile("Ana")
        stocked(store, profile.id, *[n for n in build_is().keys if n != "dead-acute"])
        for _ in range(3):
            step = introducer(build_is(), store, profile.id, self.IS_WORDS).introduce_next()
            assert step is not None
            assert [k.key for k in step.keys] == ["dead-acute"]

    def test_the_modifier_still_gets_a_finger_and_a_location(self) -> None:
        modifier = next(k for k in flat(sequence(build_is(), self.IS_WORDS)) if k.is_modifier)
        assert modifier.finger == "R-pink"
        assert modifier.location == Location(reference="æ", row_delta=0, col_delta=1)
        assert modifier.mechanism == "dead-key"

    def test_a_direct_strike_key_has_no_mechanism(self) -> None:
        assert all(k.mechanism is None for k in flat(sequence(build_de())))


class TestLocation:
    """ADR-023 § Location — closest same-finger key, else closest known key."""

    def test_the_very_first_key_has_no_reference(self) -> None:
        first = flat(sequence(build_en()))[0]
        assert first.key == "f"
        assert first.location is None

    def test_same_finger_reference_wins_over_a_physically_closer_key(self) -> None:
        # E is at (2,3): D (3,3) is the same finger at distance 1, and so is
        # nothing else -- but R (2,4) would tie on distance if the finger
        # filter did not apply first.
        store = FakeStore()
        profile = store.create_profile("Ana")
        stocked(store, profile.id, *"asdfghjkl", "r")
        steps = introduction_sequence(
            build_en(), source(EN_WORDS), KeyStates(store, profile.id).active_keys()
        )
        e = next(k for k in flat(steps) if k.key == "e")
        assert e.location == Location(reference="d", row_delta=-1, col_delta=0)

    def test_different_finger_fallback_when_the_finger_has_nothing_yet(self) -> None:
        # K is the second key of step 2, so the right middle finger owns
        # nothing; the closest key the child has is J, one column left.
        k = next(k for k in flat(sequence(build_en())) if k.key == "k")
        assert k.location == Location(reference="j", row_delta=0, col_delta=1)

    def test_the_right_hand_member_may_anchor_to_its_own_step_partner(self) -> None:
        j = next(k for k in flat(sequence(build_en())) if k.key == "j")
        assert j.location == Location(reference="f", row_delta=0, col_delta=3)

    def test_vertical_reach_beats_a_horizontal_one_at_equal_distance(self) -> None:
        # T is at (2,5), left index. Same-finger candidates by then are F (3,4)
        # and G (3,5), both Manhattan distance 1 away; G is the straight reach.
        t = next(k for k in flat(sequence(build_en())) if k.key == "t")
        assert t.location == Location(reference="g", row_delta=-1, col_delta=0)

    def test_a_number_row_letter_measures_two_rows_up(self) -> None:
        sharp_s = next(k for k in flat(sequence(build_de())) if k.key == "ß")
        assert sharp_s.location is not None
        assert sharp_s.location.row_delta == -2


class TestScript:
    """Placeholder English, in focus_model's style — ADR-022's YAML tier is unwritten."""

    def test_adr_023s_worked_example_verbatim(self) -> None:
        e = next(k for k in flat(sequence(build_en())) if k.key == "e")
        assert describe(e) == "New letter: E. Use your left middle finger. Reach one row up from D."

    def test_the_first_key_drops_the_location_clause(self) -> None:
        f = flat(sequence(build_en()))[0]
        assert describe(f) == "New letter: F. Use your left index finger."

    def test_a_modifier_is_announced_as_a_key_not_a_letter(self) -> None:
        modifier = next(
            k
            for k in flat(sequence(build_is(), TestModifierIntroduction.IS_WORDS))
            if k.is_modifier
        )
        assert describe(modifier) == (
            "New key: the accent key. Use your right little finger. "
            "Reach one position to the right from Æ. "
            "It will not make a sound on its own — it changes the next letter you press."
        )

    def test_plural_and_diagonal_reaches_read_correctly(self) -> None:
        j = next(k for k in flat(sequence(build_en())) if k.key == "j")
        assert describe(j) == (
            "New letter: J. Use your right index finger. Reach three positions to the right from F."
        )

    def test_sharp_s_is_not_upper_cased_into_two_letters(self) -> None:
        # "ß".upper() is "SS", which would be spoken as two letters.
        sharp_s = next(k for k in flat(sequence(build_de())) if k.key == "ß")
        assert describe(sharp_s).startswith("New letter: ß.")

    def test_every_generated_script_renders(self) -> None:
        for build in (build_en, build_de, build_is):
            for k in flat(sequence(build())):
                assert describe(k).startswith(("New letter: ", "New key: "))


class TestIntroducerMemory:
    """Seam 1 — the introducer's own record of what it has already said."""

    def test_first_call_yields_the_first_step(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Ana")
        step = introducer(build_en(), store, profile.id).introduce_next()
        assert step is not None
        assert [k.key for k in step.keys] == ["f", "j"]

    def test_a_step_is_not_repeated_even_though_nothing_was_pressed(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Ana")
        intro = introducer(build_en(), store, profile.id)
        assert names([s for s in (intro.introduce_next(), intro.introduce_next()) if s]) == [
            ["f", "j"],
            ["d", "k"],
        ]

    def test_a_fresh_introducer_re_introduces_what_was_never_answered(self) -> None:
        # The memory is session-local on purpose: a key the child never pressed
        # was never taught, and the script plays once per introduction.
        store = FakeStore()
        profile = store.create_profile("Ana")
        introducer(build_en(), store, profile.id).introduce_next()
        step = introducer(build_en(), store, profile.id).introduce_next()
        assert step is not None
        assert [k.key for k in step.keys] == ["f", "j"]

    def test_a_fresh_introducer_skips_what_was_answered(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Ana")
        stocked(store, profile.id, "f", "j")
        step = introducer(build_en(), store, profile.id).introduce_next()
        assert step is not None
        assert [k.key for k in step.keys] == ["d", "k"]

    def test_an_active_key_is_never_re_introduced(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Ana")
        stocked(store, profile.id, *"asdfghjkl", "e", "n", "t")
        intro = introducer(build_en(), store, profile.id)
        emitted: list[str] = []
        while (step := intro.introduce_next()) is not None:
            emitted.extend(k.key for k in step.keys)
        assert not set(emitted) & set("asdfghjklent")
        assert sorted(emitted) == sorted("bcimopquvwxyzr")

    def test_a_half_answered_pair_re_introduces_only_the_missing_member(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Ana")
        stocked(store, profile.id, "f")
        step = introducer(build_en(), store, profile.id).introduce_next()
        assert step is not None
        assert [k.key for k in step.keys] == ["j"]

    def test_the_sequence_runs_out(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Ana")
        intro = introducer(build_en(), store, profile.id)
        steps = 0
        while intro.introduce_next() is not None:
            steps += 1
        assert steps == 15
        assert intro.introduce_next() is None

    def test_last_step_holds_the_script_for_the_re_read_key(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Ana")
        intro = introducer(build_en(), store, profile.id)
        assert intro.last_step is None
        step = intro.introduce_next()
        assert intro.last_step is step

    def test_last_step_survives_the_end_of_the_sequence(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Ana")
        stocked(store, profile.id, *"abcdefghijklmnopqrstuvwxy")
        intro = introducer(build_en(), store, profile.id)
        final = intro.introduce_next()
        assert final is not None and [k.key for k in final.keys] == ["z"]
        assert intro.introduce_next() is None
        assert intro.last_step is final

    def test_introducing_writes_nothing_to_the_store(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Ana")
        intro = introducer(build_en(), store, profile.id)
        intro.introduce_next()
        intro.introduce_next()
        assert store.key_stats(profile.id) == {}


class TestPurity:
    def test_the_sequence_is_a_pure_function(self) -> None:
        layout, words = build_de(), EN_WORDS
        assert names(sequence(layout, words)) == names(sequence(layout, words))

    def test_a_composite_grapheme_in_the_active_set_is_not_a_physical_key(self) -> None:
        # key_stats is keyed by grapheme; 'á' has no layout position of its own
        # and must not derail the sequence.
        layout = build_is()
        with_composite = introduction_sequence(layout, source(EN_WORDS), {"á", "f"})
        without = introduction_sequence(layout, source(EN_WORDS), {"f"})
        assert names(with_composite) == names(without)

    def test_the_default_layout_from_the_fake_platform_sequences(self) -> None:
        platform = FakePlatformInterface()
        steps = introduction_sequence(platform.get_layout_positions(), source(EN_WORDS))
        assert names(steps)[0] == ["f", "j"]
