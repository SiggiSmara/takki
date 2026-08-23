from collections.abc import Set as AbstractSet
from typing import ClassVar

import pytest

from takki.language import WordSource
from takki.language.wordfreq_source import WordfreqSource
from takki.lesson.introducer import (
    DEFAULT_STRATEGY,
    IntroductionSlot,
    IntroductionStep,
    KeyIntroducer,
    KeyIntroduction,
    Location,
    anchor_keys,
    describe,
    home_row_fill,
    introduction_sequence,
    phase1_slots,
    phase2_slots,
)
from takki.lesson.key_state import KeyStates
from takki.persistence import Store
from takki.platform.layout import Grapheme, Layout, PhysicalKey, build_de, build_en, build_is
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
    return [[k.grapheme for k in step.keys] for step in steps]


def stages(steps: list[IntroductionStep]) -> list[int]:
    return [step.stage for step in steps]


def flat(steps: list[IntroductionStep]) -> list[KeyIntroduction]:
    return [k for step in steps for k in step.keys]


def sequence(layout: Layout, words: dict[str, float] = EN_WORDS) -> list[IntroductionStep]:
    return introduction_sequence(layout, source(words))


def phase1(layout: Layout) -> list[list[str]]:
    """Ordering A's first phase in isolation.

    Phase 1 and Phase 2 are the *strategy's* internal structure and no longer
    appear on `IntroductionStep` (ADR-032 § What this changes item 3), so a test
    about the phases asks the strategy directly.
    """
    return [list(slot.keys) for slot in phase1_slots(layout, set(anchor_keys(layout)))]


def phase2(layout: Layout, words: dict[str, float] = EN_WORDS) -> list[list[str]]:
    had = set(anchor_keys(layout))
    had |= {name for row in phase1(layout) for name in row}
    return [list(slot.keys) for slot in phase2_slots(layout, source(words), had)]


def phase2_steps(layout: Layout, words: dict[str, float] = EN_WORDS) -> list[IntroductionStep]:
    return sequence(layout, words)[3 + len(phase1(layout)) :]


def stocked(store: Store, profile_id: int, *chars: str) -> None:
    """Make each grapheme Active: one counted keystroke creates the row (ADR-027)."""
    for char in chars:
        store.upsert_key_stat(profile_id, char, True, "2026-01-01T10:00:00")


def introducer(
    layout: Layout, store: Store, profile_id: int, words: dict[str, float] = EN_WORDS
) -> KeyIntroducer:
    return KeyIntroducer(layout, source(words), KeyStates(store, profile_id))


class TestPhase1Order:
    """ADR-023 § Phase 1 — the symmetric-pair table, reproduced exactly."""

    def test_english_full_phase_1(self) -> None:
        # F+J is the strategy's own first pair and Stage 0 has already spent
        # it, so Phase 1 opens at the middle fingers.
        assert phase1(build_en()) == [["d", "k"], ["s", "l"], ["a"], ["g", "h"]]

    def test_english_step_4_is_solo_because_the_right_pinky_home_is_not_a_letter(self) -> None:
        assert phase1(build_en())[2] == ["a"]

    def test_german_full_phase_1_pairs_a_with_o_umlaut_and_tails_a_umlaut(self) -> None:
        assert phase1(build_de()) == [
            ["d", "k"],
            ["s", "l"],
            ["a", "ö"],
            ["g", "h"],
            ["ä"],
        ]

    def test_icelandic_full_phase_1_pairs_a_with_ae_and_has_no_tail(self) -> None:
        assert phase1(build_is()) == [["d", "k"], ["s", "l"], ["a", "æ"], ["g", "h"]]

    def test_icelandic_dead_acute_is_on_the_home_row_but_not_in_phase_1(self) -> None:
        layout = build_is()
        assert layout.keys["dead-acute"].row == 3
        assert "dead-acute" not in [name for row in phase1(layout) for name in row]

    def test_phase_1_is_exactly_the_home_row_letters_stage_0_did_not_take(self) -> None:
        layout = build_de()
        introduced = {name for row in phase1(layout) for name in row}
        assert introduced == {n for n, key in layout.keys.items() if key.row == 3} - {"f", "j"}

    def test_left_member_always_precedes_right(self) -> None:
        for step in sequence(build_de()):
            assert [k.side for k in step.keys] in (["L"], ["R"], ["L", "R"])


class TestPhase1ToPhase2Boundary:
    """The boundary is exhaustion of the Phase 1 segment, not Bronze."""

    def test_boundary_is_positional_not_accuracy_based(self) -> None:
        layout = build_en()
        steps = sequence(layout)
        assert stages(steps) == [0] * 3 + [1] * 12
        assert names(steps)[3:7] == phase1(layout)
        assert names(steps)[7:] == phase2(layout)

    def test_phase_2_opens_once_every_home_row_key_is_active(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Ana")
        stocked(store, profile.id, *"asdfghjkl", *"ruvm")
        step = introducer(build_en(), store, profile.id).introduce_next()
        assert step is not None
        assert [k.grapheme for k in step.keys] == ["e", "n"]

    def test_one_missing_home_row_key_holds_phase_2_shut(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Ana")
        stocked(store, profile.id, *"asdfhjkl", *"ruvm")  # no g
        step = introducer(build_en(), store, profile.id).introduce_next()
        assert step is not None
        assert [k.grapheme for k in step.keys] == ["g"]

    def test_home_row_active_but_far_from_known_still_opens_phase_2(self) -> None:
        # One counted keystroke per key: Active, nowhere near ADR-027's Known
        # floors. Bronze is later than this boundary, deliberately.
        store = FakeStore()
        profile = store.create_profile("Ana")
        stocked(store, profile.id, *"asdfghjkl", *"ruvm")
        assert KeyStates(store, profile.id).known_keys() == set()
        step = introducer(build_en(), store, profile.id).introduce_next()
        assert step is not None
        assert [k.grapheme for k in step.keys] == ["e", "n"]


class TestPhase2Order:
    """ADR-032 § Ordering A — frequency leader per hand, over graphemes."""

    def test_english_full_phase_2_takes_one_key_per_hand(self) -> None:
        assert phase2(build_en()) == [
            ["e", "n"],
            ["t", "o"],
            ["w", "i"],
            ["b", "p"],
            ["c", "y"],
            ["q"],
            ["x"],
            ["z"],
        ]

    def test_solo_steps_drain_the_surviving_pool_to_the_end(self) -> None:
        # ADR-023 point 5 reads as though one solo step ends the phase; the
        # left pool outlives the right by three keys on QWERTY.
        steps = phase2_steps(build_en())
        assert names(steps[-3:]) == [["q"], ["x"], ["z"]]
        assert all(k.side == "L" for k in flat(steps[-3:]))

    def test_every_grapheme_on_the_layout_is_introduced_exactly_once(self) -> None:
        for build in (build_en, build_de, build_is):
            layout = build()
            introduced = [k.grapheme for k in flat(sequence(layout))]
            assert sorted(introduced) == sorted(layout.graphemes)

    def test_zero_weight_keys_rank_last_and_break_ties_alphabetically(self) -> None:
        # c, q, v, x and z appear in no word above, so they tail the left pool
        # in alphabetical order -- rank_graphemes' tie-break.
        left = [
            k.grapheme
            for k in flat(sequence(build_en()))
            if k.side == "L" and k.grapheme not in "asdfg" + "rfv"
        ]
        assert left == ["e", "t", "w", "b", "c", "q", "x", "z"]

    def test_a_pool_that_empties_first_stops_appearing(self) -> None:
        steps = phase2_steps(build_en())
        sides = [[k.side for k in step.keys] for step in steps]
        assert sides == [["L", "R"]] * 5 + [["L"]] * 3


class TestCompositeIntroduction:
    """ADR-032 § Decision 1 — a composite enters at its own frequency rank, and
    the modifier rides in on the first one that needs it."""

    IS_WORDS: ClassVar[dict[str, float]] = {
        "ááá": 100.0,
        "ééé": 90.0,
        "rrr": 80.0,
        "nnn": 70.0,
        "sss": 60.0,
    }

    # A composite that outranks its own base letter: "ééé" is the only heavy
    # word and é's base, e, barely appears. Both are left-hand Phase 2 keys, so
    # nothing else decides their order.
    ELIGIBILITY_WORDS: ClassVar[dict[str, float]] = {"ééé": 100.0, "eee": 1.0}

    def test_the_dead_key_is_never_an_ordered_item(self) -> None:
        order = [k.grapheme for k in flat(sequence(build_is(), self.IS_WORDS))]
        assert "dead-acute" not in order
        assert sorted(order) == sorted(build_is().graphemes)

    def test_the_sequence_terminates_instead_of_repeating_the_modifier(self) -> None:
        # Replaces the roadmap-B8 pin (deleted 2026-08-23, session 8c): the
        # accent key used to be re-announced forever once every letter was
        # Active, because nothing could ever retire it. It is not in the order
        # at all now, so an all-Active child is simply finished.
        store = FakeStore()
        profile = store.create_profile("Ana")
        stocked(store, profile.id, *build_is().graphemes)
        intro = introducer(build_is(), store, profile.id, self.IS_WORDS)
        assert intro.introduce_next() is None
        assert intro.introduce_next() is None

    def test_composites_rank_by_their_own_frequency_and_pair_with_direct_keys(self) -> None:
        # á outweighs every remaining letter in this corpus, so it opens Phase
        # 2 as an ordinary left-hand leader, paired with the right pool's own.
        assert phase2(build_is(), self.IS_WORDS)[0] == ["á", "n"]

    def test_a_composite_is_pooled_by_the_hand_of_its_base_stroke(self) -> None:
        # ADR-032 § Decision 1 rule 2 -- not by the modifier, which is R-pink
        # for all six and balances nothing.
        sides = {
            k.grapheme: k.side for k in flat(introduction_sequence(build_is(), WordfreqSource()))
        }
        assert [sides[c] for c in "áéíóúý"] == ["L", "L", "R", "R", "R", "R"]

    def test_a_step_may_carry_two_graphemes_and_three_physical_keys(self) -> None:
        # The combination ADR-028 § Pair ramp-up did not obviously cover before
        # 2026-08-23: a composite paired with an ordinary letter.
        step = next(
            s
            for s in introduction_sequence(build_is(), WordfreqSource())
            if any(k.is_composite for k in s.keys) and len(s.keys) == 2
        )
        assert [k.grapheme for k in step.keys] == ["á", "ð"]
        assert [k.keys for k in step.keys] == [("dead-acute", "a"), ("ð",)]

    def test_a_composite_waits_for_its_base_letter_and_is_not_dropped(self) -> None:
        order = [k.grapheme for k in flat(sequence(build_is(), self.ELIGIBILITY_WORDS))]
        assert order.count("é") == 1
        assert order.index("e") < order.index("é")

    def test_the_ineligible_leader_is_skipped_rather_than_stalled_on(self) -> None:
        # é outranks e but cannot come first, so the left pool hands over its
        # next eligible member and keeps é at its head for the very next step.
        assert phase2(build_is(), self.ELIGIBILITY_WORDS)[:2] == [["e", "i"], ["é", "n"]]

    def test_german_has_no_composite_anywhere_in_the_sequence(self) -> None:
        assert not any(k.is_composite for k in flat(sequence(build_de())))
        assert all(k.modifier is None for k in flat(sequence(build_de())))

    def test_a_modifier_is_never_the_reference_for_another_key(self) -> None:
        for k in flat(sequence(build_is(), self.IS_WORDS)):
            references = [k.location] + ([k.modifier.location] if k.modifier else [])
            for location in references:
                if location is not None:
                    assert location.reference != "dead-acute"

    def test_the_modifier_gets_a_finger_and_a_location_of_its_own(self) -> None:
        first = next(k for k in flat(sequence(build_is(), self.IS_WORDS)) if k.modifier)
        assert first.grapheme == "á"
        assert first.modifier is not None
        assert first.modifier.key == "dead-acute"
        assert first.modifier.finger == "R-pink"
        assert first.modifier.location == Location(reference="æ", row_delta=0, col_delta=1)
        assert first.modifier.mechanism == "dead-key"

    def test_only_the_first_composite_of_a_class_carries_the_modifier(self) -> None:
        composites = [k for k in flat(sequence(build_is(), self.IS_WORDS)) if k.is_composite]
        assert [k.grapheme for k in composites] == ["á", "é", "í", "ó", "ú", "ý"]
        assert [k.modifier is not None for k in composites] == [True] + [False] * 5

    def test_a_composite_carries_its_base_and_both_keystrokes(self) -> None:
        composite = next(k for k in flat(sequence(build_is(), self.IS_WORDS)) if k.is_composite)
        assert composite.base == "a"
        assert composite.keys == ("dead-acute", "a")
        assert composite.mechanism == "dead-key"
        # No location clause: the script names the base letter outright, and
        # locating á against the `a` it already requires is a self-reference.
        assert composite.location is None

    def test_a_direct_strike_grapheme_is_one_key_and_no_modifier(self) -> None:
        for k in flat(sequence(build_de())):
            assert k.keys == (k.grapheme,)
            assert k.base == k.grapheme
            assert k.mechanism == "direct"


class TestModifierAnnouncementMemory:
    """Seam 2 — whether the modifier has already been announced is *derived*
    from the keys behind the graphemes the child has, not tracked separately.

    The two candidates differ in exactly one case: a composite introduced and
    never answered. Derivation re-announces it next session, which is what
    ADR-023 § What the introducer remembers already decided for letters — the
    script is that letter's only teaching moment, and the modifier clause is
    part of it.
    """

    ACUTES: ClassVar[tuple[str, ...]] = ("á", "é", "í", "ó", "ú", "ý")

    @classmethod
    def only_acutes_left(cls, store: Store, profile_id: int) -> None:
        stocked(
            store,
            profile_id,
            *(name for name in build_is().graphemes if name not in cls.ACUTES),
        )

    def test_the_first_composite_of_a_step_carries_the_modifier_and_the_rest_do_not(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Ana")
        self.only_acutes_left(store, profile.id)
        intro = introducer(build_is(), store, profile.id)
        first, second = intro.introduce_next(), intro.introduce_next()
        assert first is not None and second is not None
        assert [k.grapheme for k in first.keys] == ["á", "í"]
        assert [k.modifier is not None for k in first.keys] == [True, False]
        assert [k.grapheme for k in second.keys] == ["é", "ó"]
        assert [k.modifier is not None for k in second.keys] == [False, False]

    def test_a_composite_never_answered_is_re_announced_with_its_modifier(self) -> None:
        # The case that separates derivation from a session-local set. Nothing
        # was answered, so no key_stats row exists for á and the derived answer
        # is "not taught yet" -- which is the wanted one: the script is that
        # letter's only teaching moment, modifier clause included.
        store = FakeStore()
        profile = store.create_profile("Ana")
        self.only_acutes_left(store, profile.id)
        introducer(build_is(), store, profile.id).introduce_next()
        step = introducer(build_is(), store, profile.id).introduce_next()
        assert step is not None
        assert [k.grapheme for k in step.keys] == ["á", "í"]
        assert step.keys[0].modifier is not None
        assert step.keys[0].modifier.mechanism == "dead-key"

    def test_a_composite_that_was_answered_retires_the_modifier_for_good(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Ana")
        self.only_acutes_left(store, profile.id)
        stocked(store, profile.id, "á")
        step = introducer(build_is(), store, profile.id).introduce_next()
        assert step is not None
        assert [k.grapheme for k in step.keys] == ["é", "í"]
        assert all(k.modifier is None for k in step.keys)


class TestLocation:
    """ADR-023 § Location — closest same-finger key, else closest known key."""

    def test_the_very_first_key_has_no_reference(self) -> None:
        first = flat(sequence(build_en()))[0]
        assert first.grapheme == "f"
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
        e = next(k for k in flat(steps) if k.grapheme == "e")
        assert e.location == Location(reference="d", row_delta=-1, col_delta=0)

    def test_different_finger_fallback_when_the_finger_has_nothing_yet(self) -> None:
        # K is the second key of step 2, so the right middle finger owns
        # nothing; the closest key the child has is J, one column left.
        k = next(k for k in flat(sequence(build_en())) if k.grapheme == "k")
        assert k.location == Location(reference="j", row_delta=0, col_delta=1)

    def test_the_right_hand_member_may_anchor_to_its_own_step_partner(self) -> None:
        j = next(k for k in flat(sequence(build_en())) if k.grapheme == "j")
        assert j.location == Location(reference="f", row_delta=0, col_delta=3)

    def test_vertical_reach_beats_a_horizontal_one_at_equal_distance(self) -> None:
        # T is at (2,5), left index. Same-finger candidates by then include
        # G (3,5) and R (2,4), both Manhattan distance 1 away; G is the
        # straight vertical reach and wins on the |dcol| tie-break.
        t = next(k for k in flat(sequence(build_en())) if k.grapheme == "t")
        assert t.location == Location(reference="g", row_delta=-1, col_delta=0)

    def test_a_number_row_letter_measures_two_rows_up(self) -> None:
        sharp_s = next(k for k in flat(sequence(build_de())) if k.grapheme == "ß")
        assert sharp_s.location is not None
        assert sharp_s.location.row_delta == -2


class TestScript:
    """Placeholder English, in focus_model's style — ADR-022's YAML tier is unwritten."""

    def test_adr_023s_worked_example_verbatim(self) -> None:
        e = next(k for k in flat(sequence(build_en())) if k.grapheme == "e")
        assert describe(e) == "New letter: E. Use your left middle finger. Reach one row up from D."

    def test_the_first_key_drops_the_location_clause(self) -> None:
        f = flat(sequence(build_en()))[0]
        assert describe(f) == "New letter: F. Use your left index finger."

    def test_the_first_composite_of_a_class_explains_the_mechanism(self) -> None:
        first = next(
            k
            for k in flat(sequence(build_is(), TestCompositeIntroduction.IS_WORDS))
            if k.is_composite
        )
        assert describe(first) == (
            "New letter: Á. Press the accent key first, then A. "
            "The accent key is one position to the right from Æ. "
            "It will not make a sound on its own — it changes the next letter you press."
        )

    def test_a_later_composite_of_the_same_class_is_two_sentences(self) -> None:
        later = [
            k
            for k in flat(sequence(build_is(), TestCompositeIntroduction.IS_WORDS))
            if k.is_composite
        ][1]
        assert describe(later) == "New letter: É. Press the accent key first, then E."

    def test_plural_and_diagonal_reaches_read_correctly(self) -> None:
        j = next(k for k in flat(sequence(build_en())) if k.grapheme == "j")
        assert describe(j) == (
            "New letter: J. Use your right index finger. Reach three positions to the right from F."
        )

    def test_sharp_s_is_not_upper_cased_into_two_letters(self) -> None:
        # "ß".upper() is "SS", which would be spoken as two letters.
        sharp_s = next(k for k in flat(sequence(build_de())) if k.grapheme == "ß")
        assert describe(sharp_s).startswith("New letter: ß.")

    def test_every_generated_script_renders_as_a_letter(self) -> None:
        # Nothing is announced as anything but a letter now: the modifier has
        # no step of its own to be announced in (ADR-032 § Decision 1).
        for build in (build_en, build_de, build_is):
            for k in flat(sequence(build())):
                assert describe(k).startswith("New letter: ")


class TestIntroducerMemory:
    """Seam 1 — the introducer's own record of what it has already said."""

    def test_first_call_yields_the_first_step(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Ana")
        step = introducer(build_en(), store, profile.id).introduce_next()
        assert step is not None
        assert [k.grapheme for k in step.keys] == ["f", "j"]

    def test_a_step_is_not_repeated_even_though_nothing_was_pressed(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Ana")
        intro = introducer(build_en(), store, profile.id)
        assert names([s for s in (intro.introduce_next(), intro.introduce_next()) if s]) == [
            ["f", "j"],
            ["r", "u"],
        ]

    def test_a_fresh_introducer_re_introduces_what_was_never_answered(self) -> None:
        # The memory is session-local on purpose: a key the child never pressed
        # was never taught, and the script plays once per introduction.
        store = FakeStore()
        profile = store.create_profile("Ana")
        introducer(build_en(), store, profile.id).introduce_next()
        step = introducer(build_en(), store, profile.id).introduce_next()
        assert step is not None
        assert [k.grapheme for k in step.keys] == ["f", "j"]

    def test_a_fresh_introducer_skips_what_was_answered(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Ana")
        stocked(store, profile.id, "f", "j")
        step = introducer(build_en(), store, profile.id).introduce_next()
        assert step is not None
        assert [k.grapheme for k in step.keys] == ["r", "u"]

    def test_an_active_key_is_never_re_introduced(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Ana")
        stocked(store, profile.id, *"asdfghjkl", "e", "n", "t")
        intro = introducer(build_en(), store, profile.id)
        emitted: list[str] = []
        while (step := intro.introduce_next()) is not None:
            emitted.extend(k.grapheme for k in step.keys)
        assert not set(emitted) & set("asdfghjklent")
        assert sorted(emitted) == sorted("bcimopquvwxyzr")
        # Stage 0 keys the child never answered are still owed, and Stage 0
        # still runs first even though the home row is already Active.
        assert emitted[:4] == ["r", "u", "v", "m"]

    def test_a_half_answered_pair_re_introduces_only_the_missing_member(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Ana")
        stocked(store, profile.id, "f")
        step = introducer(build_en(), store, profile.id).introduce_next()
        assert step is not None
        assert [k.grapheme for k in step.keys] == ["j"]

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
        assert final is not None and [k.grapheme for k in final.keys] == ["z"]
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

    def test_a_composite_in_the_active_set_brings_its_modifier_with_it(self) -> None:
        # The two running sets come apart here: 'á' belongs to what has been
        # introduced and has no position of its own, while 'dead-acute' belongs
        # to what the child can strike and must never be introduced again.
        layout = build_is()
        steps = introduction_sequence(layout, source(EN_WORDS), {"á", "a", "æ"})
        assert "á" not in [k.grapheme for k in flat(steps)]
        assert all(k.modifier is None for k in flat(steps))

    def test_a_key_is_never_the_reference_for_itself(self) -> None:
        # `struck` can hold a key before the curriculum introduces it, because
        # a composite pulls its base stroke in. Without the self-exclusion the
        # base's own step anchors it to itself at distance zero and the script
        # says "reach nowhere from A".
        layout = build_is()
        steps = introduction_sequence(layout, source(EN_WORDS), {"á"})
        for k in flat(steps):
            assert k.location is None or k.location.reference != k.base

    def test_a_composite_whose_base_is_not_a_grapheme_fails_loudly(self) -> None:
        # ADR-032 § Decision 1 rule 1 assumes a composite's base is a letter
        # the curriculum teaches. A layout that breaks that assumption would
        # otherwise drop the composite silently.
        layout = build_is()
        del layout.graphemes["a"]
        with pytest.raises(ValueError, match="not a grapheme of this layout"):
            introduction_sequence(layout, source(EN_WORDS))

    def test_a_name_the_layout_does_not_produce_is_ignored(self) -> None:
        layout = build_en()
        assert names(introduction_sequence(layout, source(EN_WORDS), {"ß"})) == names(
            sequence(layout)
        )

    def test_the_default_layout_from_the_fake_platform_sequences(self) -> None:
        platform = FakePlatformInterface()
        steps = introduction_sequence(platform.get_layout_positions(), source(EN_WORDS))
        assert names(steps)[0] == ["f", "j"]


def scrambled_index_columns() -> Layout:
    """A layout whose index columns carry different letters (Dvorak's, as it
    happens). Stage 0 must follow the positions, not the letters."""
    positions = {"p": (2, 4), "u": (3, 4), "k": (4, 4), "g": (2, 7), "h": (3, 7), "m": (4, 7)}
    keys = {c: PhysicalKey(c, row, col) for c, (row, col) in positions.items()}
    graphemes = {c: Grapheme(c, "direct", (c,), 1) for c in positions}
    return Layout(lang="xx", keys=keys, graphemes=graphemes)


def alphabetical(
    layout: Layout, source: WordSource, had: AbstractSet[str]
) -> list[IntroductionSlot]:
    """A trivial second ordering: every remaining grapheme solo, alphabetically.

    Not a curriculum — it exists to show the order below Stage 0 is selectable,
    and lives in the test file for exactly that reason (ADR-032 § Decision 2
    ships one strategy).
    """
    return [IntroductionSlot(1, (name,)) for name in sorted(set(layout.graphemes) - set(had))]


class TestStage0:
    """ADR-023 § Stage 0 — anchor establishment, ahead of every strategy."""

    def test_the_six_keys_are_the_two_index_home_columns(self) -> None:
        for build in (build_en, build_de, build_is):
            assert anchor_keys(build()) == ("f", "j", "r", "u", "v", "m")

    def test_the_six_keys_are_derived_by_position(self) -> None:
        wanted = {(2, 4), (3, 4), (4, 4), (2, 7), (3, 7), (4, 7)}
        for build in (build_en, build_de, build_is):
            layout = build()
            assert {(layout.keys[n].row, layout.keys[n].col) for n in anchor_keys(layout)} == wanted

    def test_a_layout_with_other_letters_on_those_positions_yields_those_letters(self) -> None:
        assert anchor_keys(scrambled_index_columns()) == ("u", "h", "p", "g", "k", "m")

    def test_stage_0_is_three_position_pairs_home_row_first_then_up_then_down(self) -> None:
        layout = build_en()
        steps = [s for s in sequence(layout) if s.stage == 0]
        assert names(steps) == [["f", "j"], ["r", "u"], ["v", "m"]]
        assert [[layout.keys[k.grapheme].row for k in step.keys] for step in steps] == [
            [3, 3],
            [2, 2],
            [4, 4],
        ]

    def test_stage_0_comes_first_for_every_layout(self) -> None:
        for build in (build_en, build_de, build_is):
            assert stages(sequence(build()))[:3] == [0, 0, 0]
            assert names(sequence(build()))[:3] == [["f", "j"], ["r", "u"], ["v", "m"]]

    def test_stage_is_zero_for_exactly_the_three_stage_0_steps(self) -> None:
        # ADR-032 § What this changes item 3: the field carries 0 or 1 and
        # nothing else -- Phase 2's old `2` is not a value any more.
        for build in (build_en, build_de, build_is):
            found = stages(sequence(build()))
            assert found[:3] == [0, 0, 0]
            assert set(found[3:]) == {1}

    def test_the_stage_teaches_the_reach_and_return_from_the_bump(self) -> None:
        located = {k.grapheme: k.location for k in flat(sequence(build_en()))[:6]}
        assert located == {
            "f": None,
            "j": Location(reference="f", row_delta=0, col_delta=3),
            "r": Location(reference="f", row_delta=-1, col_delta=0),
            "u": Location(reference="j", row_delta=-1, col_delta=0),
            "v": Location(reference="f", row_delta=1, col_delta=0),
            "m": Location(reference="j", row_delta=1, col_delta=0),
        }

    def test_the_strategy_never_re_introduces_a_stage_0_key(self) -> None:
        for build in (build_en, build_de, build_is):
            layout = build()
            below = [k.grapheme for s in sequence(layout) if s.stage != 0 for k in s.keys]
            assert not set(below) & set(anchor_keys(layout))
            assert sorted(below) == sorted(set(layout.graphemes) - set(anchor_keys(layout)))

    def test_the_consumed_home_row_pair_leaves_no_degenerate_step(self) -> None:
        # F+J is _PHASE1_COLUMN_PAIRS' first slot as well; fully consumed, it
        # must vanish rather than emit an empty step.
        steps = sequence(build_en())
        assert all(step.keys for step in steps)
        assert len(phase1(build_en())) == 4

    def test_a_half_finished_stage_0_resumes_key_by_key(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Ana")
        stocked(store, profile.id, "f", "j", "r")
        intro = introducer(build_en(), store, profile.id)
        assert names([s for s in (intro.introduce_next(), intro.introduce_next()) if s]) == [
            ["u"],
            ["v", "m"],
        ]


class TestFullIntroductionOrder:
    """The whole curriculum, Stage 0 in front, against the fixed corpus.

    English and German are direct-strike throughout, so ADR-032's model change
    must leave their orders untouched: the two lists below are byte-identical
    to the ones session 8b pinned, and only the `stage` column has moved (`2`
    collapsed into `1`, because Phase 2 is not a protocol concept).
    """

    def test_english(self) -> None:
        steps = sequence(build_en())
        assert names(steps) == [
            ["f", "j"],
            ["r", "u"],
            ["v", "m"],
            ["d", "k"],
            ["s", "l"],
            ["a"],
            ["g", "h"],
            ["e", "n"],
            ["t", "o"],
            ["w", "i"],
            ["b", "p"],
            ["c", "y"],
            ["q"],
            ["x"],
            ["z"],
        ]
        assert stages(steps) == [0] * 3 + [1] * 12

    def test_german(self) -> None:
        steps = sequence(build_de())
        assert names(steps) == [
            ["f", "j"],
            ["r", "u"],
            ["v", "m"],
            ["d", "k"],
            ["s", "l"],
            ["a", "ö"],
            ["g", "h"],
            ["ä"],
            ["e", "n"],
            ["t", "o"],
            ["w", "i"],
            ["b", "p"],
            ["c", "z"],
            ["q", "ß"],
            ["x", "ü"],
            ["y"],
        ]
        assert stages(steps) == [0] * 3 + [1] * 13

    def test_icelandic(self) -> None:
        # The dead key has left the order and the six acutes have entered it,
        # each at its own rank in this fixed corpus (all six weigh zero here,
        # so they tie alphabetically behind the letters that do not).
        steps = sequence(build_is())
        assert names(steps) == [
            ["f", "j"],
            ["r", "u"],
            ["v", "m"],
            ["d", "k"],
            ["s", "l"],
            ["a", "æ"],
            ["g", "h"],
            ["e", "n"],
            ["t", "o"],
            ["w", "i"],
            ["b", "p"],
            ["c", "y"],
            ["q", "í"],
            ["x", "ð"],
            ["z", "ó"],
            ["á", "ö"],
            ["é", "ú"],
            ["ý"],
            ["þ"],
        ]
        assert stages(steps) == [0] * 3 + [1] * 16


class TestRealIcelandic:
    """The numbers no fixture can manufacture — real wordfreq Icelandic."""

    def test_a_acute_is_the_highest_ranked_composite_at_about_one_and_a_third_percent(
        self,
    ) -> None:
        layout = build_is()
        weights = WordfreqSource().grapheme_weights(layout)
        share = {c: weights[c] / sum(weights.values()) for c in "áéíóúý"}
        assert max(share, key=lambda c: share[c]) == "á"
        assert 0.013 < share["á"] < 0.014

    def test_the_accent_key_arrives_with_a_acute_and_not_twenty_keys_earlier(self) -> None:
        steps = introduction_sequence(build_is(), WordfreqSource())
        announced = [k for k in flat(steps) if k.modifier is not None]
        assert [k.grapheme for k in announced] == ["á"]
        order = [k.grapheme for k in flat(steps)]
        assert order.index("á") == 18
        # ADR-023 § Spike validation put the dead key at step 18 of a sequence
        # with no Stage 0, and session 8b's build shipped it as the 20th key.
        # It is now not a step at all.
        assert "dead-acute" not in order

    def test_the_full_real_icelandic_order(self) -> None:
        steps = introduction_sequence(build_is(), WordfreqSource())
        assert names(steps) == [
            ["f", "j"],
            ["r", "u"],
            ["v", "m"],
            ["d", "k"],
            ["s", "l"],
            ["a", "æ"],
            ["g", "h"],
            ["e", "i"],
            ["t", "n"],
            ["á", "ð"],
            ["b", "o"],
            ["é", "þ"],
            ["c", "y"],
            ["w", "í"],
            ["x", "ó"],
            ["z", "ö"],
            ["q", "p"],
            ["ú"],
            ["ý"],
        ]


class TestStrategySeam:
    """ADR-032 § Decision 2 — the ordering below Stage 0 is selectable."""

    def test_the_default_is_the_two_phase_home_row_fill_order(self) -> None:
        assert DEFAULT_STRATEGY is home_row_fill
        explicit = introduction_sequence(build_en(), source(EN_WORDS), strategy=home_row_fill)
        assert names(explicit) == names(sequence(build_en()))

    def test_swapping_the_strategy_leaves_stage_0_identical(self) -> None:
        swapped = introduction_sequence(build_en(), source(EN_WORDS), strategy=alphabetical)
        assert names(swapped)[:3] == [["f", "j"], ["r", "u"], ["v", "m"]]
        assert stages(swapped)[:3] == [0, 0, 0]

    def test_swapping_the_strategy_changes_the_order_below_stage_0(self) -> None:
        swapped = introduction_sequence(build_en(), source(EN_WORDS), strategy=alphabetical)
        assert names(swapped)[3:] == [[c] for c in "abcdeghiklnopqstwxyz"]
        assert names(swapped)[3:] != names(sequence(build_en()))[3:]

    def test_the_strategy_is_handed_stage_0s_keys_as_already_had(self) -> None:
        seen: list[set[str]] = []

        def recording(
            layout: Layout, source: WordSource, had: AbstractSet[str]
        ) -> list[IntroductionSlot]:
            seen.append(set(had))
            return []

        layout = build_en()
        introduction_sequence(layout, source(EN_WORDS), {"e"}, recording)
        assert seen == [set(anchor_keys(layout)) | {"e"}]

    def test_the_introducer_uses_the_strategy_it_was_given(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Ana")
        intro = KeyIntroducer(
            build_en(), source(EN_WORDS), KeyStates(store, profile.id), alphabetical
        )
        emitted: list[list[str]] = []
        while (step := intro.introduce_next()) is not None:
            emitted.append([k.grapheme for k in step.keys])
        assert emitted == [["f", "j"], ["r", "u"], ["v", "m"]] + [
            [c] for c in "abcdeghiklnopqstwxyz"
        ]
