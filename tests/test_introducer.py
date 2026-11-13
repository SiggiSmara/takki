from collections.abc import Callable
from collections.abc import Set as AbstractSet
from typing import ClassVar

import pytest

from takki.language import WordSource
from takki.language.wordfreq_source import WordfreqSource
from takki.lesson.introducer import (
    DEFAULT_STRATEGY,
    IntroductionSlot,
    IntroductionStep,
    IntroductionStrategy,
    KeyIntroducer,
    KeyIntroduction,
    Location,
    Rest,
    RestCell,
    current_rest,
    describe,
    describe_location,
    home_anchor_keys,
    home_row_fill,
    introduction_sequence,
    may_introduce,
    per_hand_alternation,
    phase1_slots,
    phase2_slots,
    resume_step,
)
from takki.lesson.key_state import KeyStates
from takki.persistence import Store
from takki.platform.layout import (
    Grapheme,
    KeyboardShape,
    Layout,
    PhysicalKey,
    build_de,
    build_en,
    build_is,
)
from tests.fakes.fake_platform import FakePlatformInterface
from tests.fakes.fake_store import FakeStore
from tests.fakes.fixed_list_source import FixedListSource
from tests.rest import READY

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


def ordered(
    layout: Layout,
    words: WordSource,
    had: AbstractSet[str] = frozenset(),
    strategy: IntroductionStrategy = home_row_fill,
    rest: Rest = READY,
) -> list[IntroductionStep]:
    """The order, on Ordering A with every finger ready unless told otherwise.

    Most tests here are about Ordering A's own structure -- its phases and the
    locations its order produces -- so it is named, not taken from the default.
    """
    return introduction_sequence(layout, words, had, rest, strategy)


def names(steps: list[IntroductionStep]) -> list[list[str]]:
    return [[k.grapheme for k in step.keys] for step in steps]


def flat(steps: list[IntroductionStep]) -> list[KeyIntroduction]:
    return [k for step in steps for k in step.keys]


def sequence(layout: Layout, words: dict[str, float] = EN_WORDS) -> list[IntroductionStep]:
    return ordered(layout, source(words))


def phase1(layout: Layout) -> list[list[str]]:
    """Ordering A's first phase in isolation.

    Phase 1 and Phase 2 are the *strategy's* internal structure and no longer
    appear on `IntroductionStep` (ADR-032 § What this changes item 3), so a test
    about the phases asks the strategy directly.
    """
    return [list(slot.keys) for slot in phase1_slots(layout, set(), READY)]


def phase2(layout: Layout, words: dict[str, float] = EN_WORDS) -> list[list[str]]:
    had = {name for row in phase1(layout) for name in row}
    return [list(slot.keys) for slot in phase2_slots(layout, source(words), had, READY)]


def phase2_steps(layout: Layout, words: dict[str, float] = EN_WORDS) -> list[IntroductionStep]:
    return sequence(layout, words)[len(phase1(layout)) :]


def stocked(store: Store, profile_id: int, *chars: str) -> None:
    """Make each grapheme Active: one counted keystroke creates the row (ADR-027)."""
    for char in chars:
        store.upsert_key_stat(profile_id, char, True, "2026-01-01T10:00:00+00:00")


def introducer(
    layout: Layout, store: Store, profile_id: int, words: dict[str, float] = EN_WORDS
) -> KeyIntroducer:
    return KeyIntroducer(
        layout, source(words), KeyStates(store, profile_id), lambda: READY, home_row_fill
    )


class TestPhase1Order:
    """ADR-023 § Phase 1 — the symmetric-pair table, reproduced exactly."""

    def test_english_full_phase_1(self) -> None:
        # With Stage 0 gone (ADR-033), Phase 1 opens at the column pair (4, 7):
        # the bump letters, ADR-033's first step under every ordering.
        assert phase1(build_en()) == [["f", "j"], ["d", "k"], ["s", "l"], ["a"], ["g", "h"]]

    def test_english_step_4_is_solo_because_the_right_pinky_home_is_not_a_letter(self) -> None:
        assert phase1(build_en())[3] == ["a"]

    def test_german_full_phase_1_pairs_a_with_o_umlaut_and_tails_a_umlaut(self) -> None:
        assert phase1(build_de()) == [
            ["f", "j"],
            ["d", "k"],
            ["s", "l"],
            ["a", "ö"],
            ["g", "h"],
            ["ä"],
        ]

    def test_icelandic_full_phase_1_pairs_a_with_ae_and_has_no_tail(self) -> None:
        assert phase1(build_is()) == [["f", "j"], ["d", "k"], ["s", "l"], ["a", "æ"], ["g", "h"]]

    def test_icelandic_dead_acute_is_on_the_home_row_but_not_in_phase_1(self) -> None:
        layout = build_is()
        assert layout.keys["dead-acute"].row == 3
        assert "dead-acute" not in [name for row in phase1(layout) for name in row]

    def test_phase_1_is_exactly_the_home_row_letters(self) -> None:
        layout = build_de()
        introduced = {name for row in phase1(layout) for name in row}
        home_letters = {n for n, key in layout.keys.items() if key.row == 3} & set(layout.graphemes)
        assert introduced == home_letters

    def test_left_member_always_precedes_right(self) -> None:
        for step in sequence(build_de()):
            assert [k.side for k in step.keys] in (["L"], ["R"], ["L", "R"])


class TestPhase1ToPhase2Boundary:
    """The boundary is exhaustion of the Phase 1 segment, not Bronze."""

    def test_boundary_is_positional_not_accuracy_based(self) -> None:
        layout = build_en()
        steps = sequence(layout)
        assert len(steps) == 15
        assert names(steps)[:5] == phase1(layout)
        assert names(steps)[5:] == phase2(layout)

    def test_phase_2_opens_once_every_home_row_key_is_active(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Ana")
        stocked(store, profile.id, *"asdfghjkl")
        step = introducer(build_en(), store, profile.id).introduce_next()
        assert step is not None
        assert [k.grapheme for k in step.keys] == ["e", "n"]

    def test_one_missing_home_row_key_holds_phase_2_shut(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Ana")
        stocked(store, profile.id, *"asdfhjkl")  # no g
        step = introducer(build_en(), store, profile.id).introduce_next()
        assert step is not None
        assert [k.grapheme for k in step.keys] == ["g"]

    def test_home_row_active_but_far_from_known_still_opens_phase_2(self) -> None:
        # One counted keystroke per key: Active, nowhere near ADR-027's Known
        # floors. Bronze is later than this boundary, deliberately.
        store = FakeStore()
        profile = store.create_profile("Ana")
        stocked(store, profile.id, *"asdfghjkl")
        assert KeyStates(store, profile.id).known_keys() == set()
        step = introducer(build_en(), store, profile.id).introduce_next()
        assert step is not None
        assert [k.grapheme for k in step.keys] == ["e", "n"]


class TestPhase2Order:
    """ADR-032 § Ordering A — frequency leader per hand, over graphemes."""

    def test_english_full_phase_2_takes_one_key_per_hand(self) -> None:
        # r u v m are ordinary letters now (ADR-033), each at its own rank.
        assert phase2(build_en()) == [
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
        steps = phase2_steps(build_en())
        assert names(steps[-3:]) == [["v"], ["x"], ["z"]]
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
            if k.side == "L" and k.grapheme not in "asdfg"
        ]
        assert left == ["e", "t", "r", "w", "b", "c", "q", "v", "x", "z"]

    def test_a_pool_that_empties_first_stops_appearing(self) -> None:
        steps = phase2_steps(build_en())
        sides = [[k.side for k in step.keys] for step in steps]
        assert sides == [["L", "R"]] * 7 + [["L"]] * 3


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
        sides = {k.grapheme: k.side for k in flat(ordered(build_is(), WordfreqSource()))}
        assert [sides[c] for c in "áéíóúý"] == ["L", "L", "R", "R", "R", "R"]

    def test_a_step_may_carry_two_graphemes_and_three_physical_keys(self) -> None:
        # The combination ADR-028 § Pair ramp-up did not obviously cover before
        # 2026-08-23: a composite paired with an ordinary letter.
        step = next(
            s
            for s in ordered(build_is(), WordfreqSource())
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
        assert phase2(build_is(), self.ELIGIBILITY_WORDS)[:2] == [["e", "i"], ["é", "m"]]

    def test_german_has_no_composite_anywhere_in_the_sequence(self) -> None:
        assert not any(k.is_composite for k in flat(sequence(build_de())))
        assert all(k.modifier is None for k in flat(sequence(build_de())))

    def test_the_modifier_gets_a_finger_and_a_location_of_its_own(self) -> None:
        first = next(k for k in flat(sequence(build_is(), self.IS_WORDS)) if k.modifier)
        assert first.grapheme == "á"
        assert first.modifier is not None
        assert first.modifier.key == "dead-acute"
        assert first.modifier.finger == "R-pink"
        assert first.modifier.location == Location(0, 1)
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


def intro(
    layout: Layout, name: str, rest: Rest = READY, had: AbstractSet[str] = frozenset()
) -> KeyIntroduction:
    """One letter's introduction, built as the step builder builds it."""
    (only,) = resume_step(layout, [name], had, rest).keys
    return only


def script(
    layout: Layout, name: str, rest: Rest = READY, had: AbstractSet[str] = frozenset()
) -> str:
    return describe(intro(layout, name, rest, had))[1]


class TestLocation:
    """ADR-023 § Location, amended 2026-11-09: every key from its finger's rest key."""

    def test_the_bump_letters_are_at_their_rest_keys(self) -> None:
        first = sequence(build_en())[0]
        assert [(k.grapheme, k.location) for k in first.keys] == [
            ("f", Location(0, 0)),
            ("j", Location(0, 0)),
        ]

    def test_a_reach_on_each_axis_is_measured_from_the_rest_key(self) -> None:
        layout = build_en()
        assert intro(layout, "e").location == Location(-1, 0)
        assert intro(layout, "c").location == Location(1, 0)
        assert intro(layout, "g").location == Location(0, 1)
        assert intro(layout, "h").location == Location(0, -1)
        assert intro(layout, "t").location == Location(-1, 1)
        assert intro(build_de(), "ß").location == Location(-2, 1)

    def test_a_letter_the_child_has_is_not_the_reference(self) -> None:
        # Under the old rule `t` was located from `g` once the child had it.
        layout = build_en()
        assert intro(layout, "t", had={"f", "j", "g", "r"}).location == Location(-1, 1)

    def test_a_rest_key_with_no_letter_still_locates(self) -> None:
        # The right little finger rests on `;` in English, which is no letter.
        assert intro(build_en(), "p").location == Location(-1, 0)

    def test_a_middle_finger_resting_on_e_locates_d_from_e(self) -> None:
        rest = with_rest(L_mid=RestCell(2, 3, True))
        assert intro(build_en(), "e", rest).location == Location(0, 0)
        assert intro(build_en(), "d", rest).location == Location(1, 0)
        assert intro(build_en(), "c", rest).location == Location(2, 0)

    def test_a_finger_with_no_rest_key_gives_no_location(self) -> None:
        assert intro(build_en(), "e", with_rest(L_mid=None)).location is None

    def test_a_composite_spends_its_location_on_its_modifier(self) -> None:
        a_acute = intro(build_is(), "á", had={"a"})
        assert a_acute.location is None
        assert a_acute.modifier is not None
        assert a_acute.modifier.location == Location(0, 1)

    def test_a_modifier_is_located_from_its_own_fingers_rest_key(self) -> None:
        # The accent key's finger is the right little finger, not `a`'s.
        moved = with_rest(R_pink=RestCell(2, 11, True))
        a_acute = intro(build_is(), "á", moved, had={"a"})
        assert a_acute.modifier is not None
        assert a_acute.modifier.location == Location(1, 0)

    def test_a_modifier_that_is_its_fingers_rest_key_is_at_rest(self) -> None:
        on_it = with_rest(R_pink=RestCell(3, 11, False))
        a_acute = intro(build_is(), "á", on_it, had={"a"})
        assert a_acute.modifier is not None
        assert a_acute.modifier.location == Location(0, 0)

    @pytest.mark.parametrize(
        ("shape", "cell", "location"),
        [("iso", (3, 12), Location(-1, -2)), ("ansi", (2, 13), Location(0, -3))],
    )
    def test_a_little_finger_resting_on_0x2b_follows_the_keyboard_shape(
        self, shape: KeyboardShape, cell: tuple[int, int], location: Location
    ) -> None:
        layout = build_en(shape)
        assert (layout.keys["\\"].row, layout.keys["\\"].col) == cell
        rest = with_rest(R_pink=RestCell(*cell, True))
        assert intro(layout, "p", rest).location == location


class TestScript:
    """Placeholder English, in focus_model's style — ADR-022's YAML tier is unwritten."""

    def test_a_bump_letter_is_where_its_finger_rests_on_the_bump(self) -> None:
        f, j = sequence(build_en())[0].keys
        assert describe(f) == (
            "New letter:",
            "Use your left index finger. It is the key with the bump, where that finger rests.",
        )
        assert describe(j) == (
            "New letter:",
            "Use your right index finger. It is the key with the bump, where that finger rests.",
        )

    def test_another_rest_letter_is_where_its_finger_rests(self) -> None:
        assert script(build_en(), "s") == (
            "Use your left ring finger. It is the key where that finger rests."
        )
        e_rest = with_rest(L_mid=RestCell(2, 3, True))
        assert script(build_en(), "e", e_rest) == (
            "Use your left middle finger. It is the key where that finger rests."
        )

    def test_adr_023s_worked_example_from_the_rest_key(self) -> None:
        assert script(build_en(), "e") == (
            "Use your left middle finger. Reach one row up from where that finger rests."
        )

    def test_a_reach_on_each_axis(self) -> None:
        layout = build_en()
        assert script(layout, "v") == (
            "Use your left index finger. Reach one row down from where that finger rests."
        )
        assert script(layout, "g") == (
            "Use your left index finger. "
            "Reach one position to the right from where that finger rests."
        )
        assert script(layout, "h") == (
            "Use your right index finger. "
            "Reach one position to the left from where that finger rests."
        )
        assert script(layout, "t") == (
            "Use your left index finger. "
            "Reach one row up and one position to the right from where that finger rests."
        )

    def test_a_reach_from_a_rest_key_with_no_letter(self) -> None:
        assert script(build_en(), "p") == (
            "Use your right little finger. Reach one row up from where that finger rests."
        )

    def test_d_from_a_middle_finger_resting_on_e(self) -> None:
        e_rest = with_rest(L_mid=RestCell(2, 3, True))
        assert script(build_en(), "d", e_rest) == (
            "Use your left middle finger. Reach one row down from where that finger rests."
        )

    @pytest.mark.parametrize(
        ("shape", "cell", "reach"),
        [
            ("iso", (3, 12), "one row up and two positions to the left"),
            ("ansi", (2, 13), "three positions to the left"),
        ],
    )
    def test_a_reach_from_0x2b_on_both_keyboard_shapes(
        self, shape: KeyboardShape, cell: tuple[int, int], reach: str
    ) -> None:
        rest = with_rest(R_pink=RestCell(*cell, True))
        assert script(build_en(shape), "p", rest) == (
            f"Use your right little finger. Reach {reach} from where that finger rests."
        )

    def test_a_finger_with_no_rest_key_drops_the_location_clause(self) -> None:
        assert script(build_en(), "e", with_rest(L_mid=None)) == "Use your left middle finger."

    def test_a_reach_past_the_number_words_is_spoken_in_digits(self) -> None:
        assert describe_location(Location(0, 4)) == "four positions to the right"
        assert describe_location(Location(0, 5)) == "5 positions to the right"
        assert describe_location(Location(-2, 0)) == "two rows up"

    def test_the_first_composite_of_a_class_explains_the_mechanism(self) -> None:
        first = next(
            k
            for k in flat(sequence(build_is(), TestCompositeIntroduction.IS_WORDS))
            if k.is_composite
        )
        assert describe(first) == (
            "New letter:",
            "Press the accent key first, then A. "
            "The accent key is one position to the right from where your right little finger rests. "
            "It will not make a sound on its own — it changes the next letter you press.",
        )

    def test_a_modifier_on_its_fingers_rest_key_is_where_that_finger_rests(self) -> None:
        on_it = with_rest(R_pink=RestCell(3, 11, False))
        assert script(build_is(), "á", on_it, had={"a"}) == (
            "Press the accent key first, then A. "
            "The accent key is where your right little finger rests. "
            "It will not make a sound on its own — it changes the next letter you press."
        )

    def test_a_later_composite_of_the_same_class_names_only_its_keys(self) -> None:
        later = [
            k
            for k in flat(sequence(build_is(), TestCompositeIntroduction.IS_WORDS))
            if k.is_composite
        ][1]
        assert describe(later) == ("New letter:", "Press the accent key first, then E.")

    def test_the_letter_itself_is_not_in_the_script(self) -> None:
        # alpha-plan #12l: the caller speaks it between the two parts, through
        # the letter source, so the child hears the sound a prompt will make.
        # The script used to name it as a capital.
        e = next(k for k in flat(sequence(build_en())) if k.grapheme == "e")
        assert "E" not in "".join(describe(e))

    def test_every_generated_script_renders_as_a_letter(self) -> None:
        # Nothing is announced as anything but a letter now: the modifier has
        # no step of its own to be announced in (ADR-032 § Decision 1).
        for build in (build_en, build_de, build_is):
            for k in flat(sequence(build())):
                lead, rest = describe(k)
                assert lead == "New letter:"
                assert rest != ""


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
        assert [k.grapheme for k in step.keys] == ["f", "j"]

    def test_a_fresh_introducer_skips_what_was_answered(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Ana")
        stocked(store, profile.id, "f", "j")
        step = introducer(build_en(), store, profile.id).introduce_next()
        assert step is not None
        assert [k.grapheme for k in step.keys] == ["d", "k"]

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
        # With the home row Active, the order goes straight to Phase 2.
        assert emitted[:2] == ["r", "o"]

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
        steps = ordered(layout, source(EN_WORDS), {"á", "a", "æ"})
        assert "á" not in [k.grapheme for k in flat(steps)]
        assert all(k.modifier is None for k in flat(steps))

    def test_only_a_rest_letter_is_at_rest(self) -> None:
        # A zero reach is spoken as "where that finger rests", so it must mean
        # exactly that. Under the old rule a composite's base, struck before it
        # was introduced, could be located against itself ("reach nowhere").
        layout = build_is()
        steps = ordered(layout, source(EN_WORDS), {"á"})
        at_rest = [k.grapheme for k in flat(steps) if k.location and k.location.at_rest]
        rest_cells = {(cell.row, cell.col) for cell in READY.values()}
        assert sorted(at_rest) == sorted(
            name for name, key in layout.keys.items() if (key.row, key.col) in rest_cells
        )

    def test_a_composite_whose_base_is_not_a_grapheme_fails_loudly(self) -> None:
        # ADR-032 § Decision 1 rule 1 assumes a composite's base is a letter
        # the curriculum teaches. A layout that breaks that assumption would
        # otherwise drop the composite silently.
        layout = build_is()
        del layout.graphemes["a"]
        with pytest.raises(ValueError, match="not a grapheme of this layout"):
            ordered(layout, source(EN_WORDS))

    def test_a_name_the_layout_does_not_produce_is_ignored(self) -> None:
        layout = build_en()
        assert names(ordered(layout, source(EN_WORDS), {"ß"})) == names(sequence(layout))

    def test_the_default_layout_from_the_fake_platform_sequences(self) -> None:
        platform = FakePlatformInterface()
        steps = ordered(platform.get_layout_positions(), source(EN_WORDS))
        assert names(steps)[0] == ["f", "j"]


def scrambled_index_columns() -> Layout:
    """A layout whose index columns carry different letters (Dvorak's, as it
    happens). The bump letters follow the positions, not the letters."""
    positions = {"p": (2, 4), "u": (3, 4), "k": (4, 4), "g": (2, 7), "h": (3, 7), "m": (4, 7)}
    keys = {c: PhysicalKey(c, row, col) for c, (row, col) in positions.items()}
    graphemes = {c: Grapheme(c, "direct", (c,), 1) for c in positions}
    return Layout(lang="xx", keys=keys, graphemes=graphemes)


def alphabetical(
    layout: Layout, source: WordSource, had: AbstractSet[str], rest: Rest
) -> list[IntroductionSlot]:
    """A trivial ordering: every remaining grapheme solo, alphabetically.

    Not a curriculum -- it exists to show the order is selectable, and lives in
    the test file for that reason. It obeys the rest rules like every strategy
    (decided 2026-11-09): the bump letters come first from above it, and it
    applies rules 2 and 3 itself, which for one-letter steps is a filter.
    """
    return [
        IntroductionSlot((name,))
        for name in sorted(set(layout.graphemes) - set(had))
        if may_introduce(layout, name, had, rest)
    ]


class TestBumpLetters:
    """ADR-033 — no Stage 0. The bump letters stay, as positions, and open the order."""

    def test_the_bump_letters_are_f_and_j_on_every_layout(self) -> None:
        for build in (build_en, build_de, build_is):
            assert home_anchor_keys(build()) == ("f", "j")

    def test_the_bump_letters_are_derived_by_position(self) -> None:
        for build in (build_en, build_de, build_is):
            layout = build()
            found = [(layout.keys[n].row, layout.keys[n].col) for n in home_anchor_keys(layout)]
            assert found == [(3, 4), (3, 7)]

    def test_a_layout_with_other_letters_on_those_positions_yields_those_letters(self) -> None:
        assert home_anchor_keys(scrambled_index_columns()) == ("u", "h")

    def test_a_bump_position_with_no_letter_still_fails_loudly(self) -> None:
        # Since ADR-026's 2026-11-01 amendment `keys` holds punctuation cells,
        # so a non-letter at a bump must not be taken as the bump letter.
        layout = build_en()
        del layout.keys["f"], layout.graphemes["f"]
        layout.keys["#"] = PhysicalKey("#", 3, 4)
        with pytest.raises(KeyError, match=r"\(3, 4\)"):
            home_anchor_keys(layout)

    def test_the_first_step_is_the_bump_letters_for_every_layout(self) -> None:
        for build in (build_en, build_de, build_is):
            assert names(sequence(build()))[0] == ["f", "j"]

    def test_r_u_v_m_are_ordinary_letters_introduced_once_at_their_rank(self) -> None:
        # Stage 0's other four keys are no longer a stage: the strategy ranks them.
        order = [k.grapheme for k in flat(sequence(build_en()))]
        assert [order.index(c) for c in "ruvm"] == [13, 16, 23, 20]
        assert sorted(order) == sorted(build_en().graphemes)

    def test_the_bump_pair_leaves_no_degenerate_step_once_had(self) -> None:
        # Fully had, the pair must vanish rather than emit an empty step.
        steps = ordered(build_en(), source(EN_WORDS), {"f", "j"})
        assert all(step.keys for step in steps)
        assert names(steps)[0] == ["d", "k"]

    def test_a_half_had_bump_pair_resumes_key_by_key(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Ana")
        stocked(store, profile.id, "f")
        intro = introducer(build_en(), store, profile.id)
        assert names([s for s in (intro.introduce_next(), intro.introduce_next()) if s]) == [
            ["j"],
            ["d", "k"],
        ]


class TestFullIntroductionOrder:
    """The whole curriculum against the fixed corpus, with no Stage 0 (ADR-033).

    Ordering A opens at its own first pair, the bump letters, and `r u v m`
    enter Phase 2 at their frequency rank.
    """

    def test_english(self) -> None:
        steps = sequence(build_en())
        assert names(steps) == [
            ["f", "j"],
            ["d", "k"],
            ["s", "l"],
            ["a"],
            ["g", "h"],
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

    def test_german(self) -> None:
        steps = sequence(build_de())
        assert names(steps) == [
            ["f", "j"],
            ["d", "k"],
            ["s", "l"],
            ["a", "ö"],
            ["g", "h"],
            ["ä"],
            ["e", "n"],
            ["t", "o"],
            ["r", "i"],
            ["w", "u"],
            ["b", "p"],
            ["c", "m"],
            ["q", "z"],
            ["v", "ß"],
            ["x", "ü"],
            ["y"],
        ]

    def test_icelandic(self) -> None:
        # The dead key has left the order and the six acutes have entered it,
        # each at its own rank in this fixed corpus (all six weigh zero here,
        # so they tie alphabetically behind the letters that do not).
        steps = sequence(build_is())
        assert names(steps) == [
            ["f", "j"],
            ["d", "k"],
            ["s", "l"],
            ["a", "æ"],
            ["g", "h"],
            ["e", "n"],
            ["t", "o"],
            ["r", "i"],
            ["w", "u"],
            ["b", "p"],
            ["c", "m"],
            ["q", "y"],
            ["v", "í"],
            ["x", "ð"],
            ["z", "ó"],
            ["á", "ö"],
            ["é", "ú"],
            ["ý"],
            ["þ"],
        ]


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
        steps = ordered(build_is(), WordfreqSource())
        announced = [k for k in flat(steps) if k.modifier is not None]
        assert [k.grapheme for k in announced] == ["á"]
        order = [k.grapheme for k in flat(steps)]
        assert order.index("á") == 18
        # ADR-023 § Spike validation put the dead key at step 18, and session
        # 8b's build shipped it as the 20th key. It is now not a step at all.
        assert "dead-acute" not in order

    def test_the_full_real_icelandic_order(self) -> None:
        steps = ordered(build_is(), WordfreqSource())
        assert names(steps) == [
            ["f", "j"],
            ["d", "k"],
            ["s", "l"],
            ["a", "æ"],
            ["g", "h"],
            ["r", "i"],
            ["e", "n"],
            ["t", "u"],
            ["v", "m"],
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
    """ADR-032 § Decision 2 — the ordering is selectable."""

    def test_the_default_is_ordering_c(self) -> None:
        # ADR-032 § What Alpha ships, restated: C is the compiled default and A
        # stays selectable. Ordering B is retired, so nothing builds it.
        assert DEFAULT_STRATEGY is per_hand_alternation
        default = introduction_sequence(build_en(), source(EN_WORDS), set(), READY)
        assert names(default) == names(
            ordered(build_en(), source(EN_WORDS), strategy=per_hand_alternation)
        )
        assert names(default) != names(sequence(build_en()))

    def test_swapping_the_strategy_changes_the_order_after_the_bump_letters(self) -> None:
        # Rest rule 1 sits above every strategy, this one included.
        swapped = ordered(build_en(), source(EN_WORDS), strategy=alphabetical)
        rest = [[c] for c in sorted(build_en().graphemes) if c not in "fj"]
        assert names(swapped) == [["f", "j"], *rest]
        assert names(swapped) != names(sequence(build_en()))

    def test_the_strategy_is_handed_what_was_had_and_the_bump_letters(self) -> None:
        seen: list[tuple[set[str], Rest]] = []

        def recording(
            layout: Layout, source: WordSource, had: AbstractSet[str], rest: Rest
        ) -> list[IntroductionSlot]:
            seen.append((set(had), rest))
            return []

        steps = ordered(build_en(), source(EN_WORDS), {"e"}, recording)
        assert seen == [({"e", "f", "j"}, READY)]
        assert names(steps) == [["f", "j"]]

    def test_the_introducer_uses_the_strategy_it_was_given(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Ana")
        intro = KeyIntroducer(
            build_en(), source(EN_WORDS), KeyStates(store, profile.id), lambda: READY, alphabetical
        )
        emitted: list[list[str]] = []
        while (step := intro.introduce_next()) is not None:
            emitted.append([k.grapheme for k in step.keys])
        assert emitted == [
            ["f", "j"],
            *([c] for c in sorted(build_en().graphemes) if c not in "fj"),
        ]


class TestRemember:
    def test_a_remembered_step_becomes_the_one_the_re_read_key_speaks(self) -> None:
        # A resumed session's step is not emitted by the introducer (alpha-plan
        # #12d), so it has to be handed over: ADR-023 makes `last_step` how the
        # child re-hears the script, and a None there is silence.
        layout = build_en()
        source = FixedListSource(EN_WORDS)
        store = FakeStore()
        profile = store.create_profile("kid").id
        introducer = KeyIntroducer(
            layout, source, KeyStates(store, profile), lambda: READY, home_row_fill
        )
        assert introducer.last_step is None
        step = ordered(layout, source)[0]
        introducer.remember(step)
        assert introducer.last_step is step

    def test_a_remembered_step_is_not_introduced_again(self) -> None:
        layout = build_en()
        source = FixedListSource(EN_WORDS)
        store = FakeStore()
        profile = store.create_profile("kid").id
        introducer = KeyIntroducer(
            layout, source, KeyStates(store, profile), lambda: READY, home_row_fill
        )
        first, second = ordered(layout, source)[:2]
        introducer.remember(first)
        emitted = introducer.introduce_next()
        assert emitted is not None
        assert [k.grapheme for k in emitted.keys] == [k.grapheme for k in second.keys]


class TestResumeStep:
    """alpha-plan #12j, O2: a resumed step carries the script the child first heard."""

    @pytest.mark.parametrize("build", [build_en, build_de, build_is])
    def test_every_step_is_rebuilt_as_it_was_first_emitted(
        self, build: Callable[[], Layout]
    ) -> None:
        # Location and modifier clauses included: they depend on what the child
        # had when the step was introduced, so the rebuild is handed exactly that.
        layout = build()
        words = WordfreqSource()
        had: set[str] = set()
        steps = ordered(layout, words)
        assert any(intro.modifier for intro in flat(steps)) == (build is build_is)
        for step in steps:
            members = [intro.grapheme for intro in step.keys]
            assert resume_step(layout, members, had, READY) == step
            had.update(members)

    def test_the_step_itself_is_not_among_what_the_child_had(self) -> None:
        # A caller that hands over everything introduced, the step included,
        # must still hear the modifier its step brought in.
        layout = build_is()
        words = TestCompositeIntroduction.IS_WORDS
        step = next(s for s in ordered(layout, source(words)) if any(k.modifier for k in s.keys))
        members = [k.grapheme for k in step.keys]
        had = {name for name in layout.graphemes if layout.graphemes[name].mechanism == "direct"}
        assert resume_step(layout, members, had | set(members), READY) == step

    def test_a_rest_key_changed_since_is_described_from_todays(self) -> None:
        # Decided 2026-11-09 (#12m session (5b)): the finger starts from where
        # it rests now, and the record of where it rested then is not read.
        layout = build_en()
        then = resume_step(layout, ["c", "m"], {"f", "j"}, READY)
        today = resume_step(layout, ["c", "m"], {"f", "j"}, with_rest(L_mid=RestCell(2, 3, True)))
        assert [k.location for k in then.keys] == [Location(1, 0), Location(1, 0)]
        assert [k.location for k in today.keys] == [Location(2, 0), Location(1, 0)]
        assert describe(today.keys[0])[1] == (
            "Use your left middle finger. Reach two rows down from where that finger rests."
        )


# Ordering C's fixture (#12m session (5)): `s`, `l` and `a` are rest letters
# well above REST_LETTER_MIN_SHARE, `k` is one far below it, and `d` and `;`
# carry nothing. Every other letter weighs zero and ranks alphabetically.
C_WORDS: dict[str, float] = {
    "sss": 100.0,
    "eee": 90.0,
    "nnn": 80.0,
    "lll": 70.0,
    "ttt": 60.0,
    "ooo": 50.0,
    "aaa": 40.0,
    "iii": 30.0,
    "kkk": 1.0,
}


def members(steps: list[list[str]]) -> list[str]:
    return [name for step in steps for name in step]


def c_order(rest: Rest, had: AbstractSet[str] = frozenset()) -> list[list[str]]:
    return names(ordered(build_en(), source(C_WORDS), had, per_hand_alternation, rest))


def with_rest(**cells: RestCell | None) -> dict[str, RestCell]:
    """READY with some fingers moved (a cell), or removed (None). Keyword `L_mid` is `L-mid`."""
    rest = dict(READY)
    for name, cell in cells.items():
        finger = name.replace("_", "-")
        if cell is None:
            del rest[finger]
        else:
            rest[finger] = cell
    return rest


STRATEGIES = [per_hand_alternation, home_row_fill, alphabetical]


class TestRestRuleOne:
    """ADR-032 rest rule 1: the bump letters first, together, once both index fingers are ready."""

    @pytest.mark.parametrize("strategy", STRATEGIES)
    @pytest.mark.parametrize(
        "rest",
        [
            {},
            with_rest(L_idx=RestCell(3, 4, False)),
            with_rest(R_idx=RestCell(3, 7, False)),
            with_rest(L_idx=None),
            with_rest(L_idx=RestCell(3, 4, False), R_idx=RestCell(3, 7, False)),
        ],
    )
    def test_nothing_until_both_index_fingers_are_ready(
        self, strategy: IntroductionStrategy, rest: Rest
    ) -> None:
        assert ordered(build_en(), source(C_WORDS), set(), strategy, rest) == []

    @pytest.mark.parametrize("strategy", STRATEGIES)
    def test_the_bump_letters_open_every_strategy(self, strategy: IntroductionStrategy) -> None:
        steps = names(ordered(build_en(), source(C_WORDS), set(), strategy, READY))
        assert steps[0] == ["f", "j"]
        assert "f" not in members(steps[1:]) and "j" not in members(steps[1:])

    @pytest.mark.parametrize("strategy", STRATEGIES)
    def test_with_only_the_index_fingers_the_bump_letters_still_come(
        self, strategy: IntroductionStrategy
    ) -> None:
        rest = {finger: READY[finger] for finger in ("L-idx", "R-idx")}
        steps = names(ordered(build_en(), source(C_WORDS), set(), strategy, rest))
        assert steps[0] == ["f", "j"]


class TestRestRulesTwoAndThree:
    """ADR-032 rest rules 2 and 3, on Ordering C with exact sequences."""

    def test_every_finger_ready(self) -> None:
        assert c_order(READY) == [
            ["f", "j"],
            ["e", "n"],
            ["s", "l"],
            ["t", "o"],
            ["a", "i"],
            ["b", "k"],
            ["c", "h"],
            ["d", "m"],
            ["g", "p"],
            ["q", "u"],
            ["r", "y"],
            ["v"],
            ["w"],
            ["x"],
            ["z"],
        ]

    def test_a_finger_with_no_rest_key_is_passed_over(self) -> None:
        # Rule 2: only the index fingers are chosen, so only their columns
        # (4-5 and 6-7) give letters, and no rest letter takes a turn.
        rest = {finger: READY[finger] for finger in ("L-idx", "R-idx")}
        assert c_order(rest) == [
            ["f", "j"],
            ["t", "n"],
            ["b", "h"],
            ["g", "m"],
            ["r", "u"],
            ["v", "y"],
        ]

    def test_a_chosen_finger_not_ready_gives_its_rest_letter_and_nothing_else(self) -> None:
        # Rule 3: the left ring finger is chosen on `s`, not ready. `s` comes
        # at its turn; `w` and `x`, reached from it, are left out.
        rest = with_rest(L_ring=RestCell(3, 2, False))
        assert c_order(rest) == [
            ["f", "j"],
            ["e", "n"],
            ["s", "l"],
            ["t", "o"],
            ["a", "i"],
            ["b", "k"],
            ["c", "h"],
            ["d", "m"],
            ["g", "p"],
            ["q", "u"],
            ["r", "y"],
            ["v"],
            ["z"],
        ]

    def test_a_weak_rest_letter_on_a_chosen_finger_comes_at_its_rank(self) -> None:
        # `k` is under the floor, so it waits in the useful queue at its rank,
        # and needs its finger only chosen. `i`, reached from it, is passed
        # over, so the right hand takes `k`, its next letter that may come.
        rest = with_rest(R_mid=RestCell(3, 8, False))
        assert c_order(rest) == [
            ["f", "j"],
            ["e", "n"],
            ["s", "l"],
            ["t", "o"],
            ["a", "k"],
            ["b", "h"],
            ["c", "m"],
            ["d", "p"],
            ["g", "u"],
            ["q", "y"],
            ["r"],
            ["v"],
            ["w"],
            ["x"],
            ["z"],
        ]

    def test_a_rest_letter_on_an_unconventional_key_is_a_rest_letter(self) -> None:
        # ADR-033: a child whose left middle finger rests on `e` has `e` as a
        # rest letter, strong here, and `d` as an ordinary one.
        rest = with_rest(L_mid=RestCell(2, 3, True))
        assert c_order(rest) == [
            ["f", "j"],
            ["t", "n"],
            ["s", "l"],
            ["b", "o"],
            ["e", "i"],
            ["c", "k"],
            ["a", "h"],
            ["d", "m"],
            ["g", "p"],
            ["q", "u"],
            ["r", "y"],
            ["v"],
            ["w"],
            ["x"],
            ["z"],
        ]

    def test_a_finger_that_becomes_ready_brings_its_letters_from_then_on(self) -> None:
        not_ready = with_rest(L_ring=RestCell(3, 2, False))
        had = {name for step in c_order(not_ready) for name in step}
        assert c_order(READY, had) == [["w"], ["x"]]


class TestOrderingC:
    """ADR-032 § Ordering C, restated: whose turn it is, decided by a count."""

    def test_each_hands_first_turn_is_useful_and_the_bump_letters_count_as_neither(
        self,
    ) -> None:
        assert c_order(READY)[1] == ["e", "n"]
        assert c_order(READY, {"f", "j", "e", "n"})[0] == ["s", "l"]

    def test_a_hand_with_no_strong_rest_letter_left_takes_a_useful_one(self) -> None:
        # The right hand's only strong rest letter is `l`; after it, every
        # turn that would be strong falls to the useful queue.
        right = [step[-1] for step in c_order(READY)[1:11]]
        assert right == ["n", "l", "o", "i", "k", "h", "m", "p", "u", "y"]

    def test_the_count_reads_the_letters_already_had(self) -> None:
        # Had `e` and `t` (two useful) and no rest letter: the left hand's next
        # turns are strong until the count evens out -- `s`, then `a`.
        assert c_order(READY, {"f", "j", "e", "t"})[:3] == [["s", "n"], ["a", "l"], ["b", "o"]]

    def test_equal_shares_are_taken_in_ranking_order(self) -> None:
        # `a` and `s` carry the same share of key presses (two `a` in "aab",
        # one `s` in a word twice as frequent), and `s` ranks first, because a
        # letter counts once per word. Alphabetical order would put `a` first.
        words = {"aab": 10.0, "sbc": 20.0}
        shares = source(words).key_shares(build_en())
        assert shares["a"] == shares["s"]
        steps = names(ordered(build_en(), source(words), set(), per_hand_alternation))
        left = [step[0] for step in steps[1:5]]
        assert left == ["b", "s", "c", "a"]


class TestCompositeReadiness:
    """Decided 2026-11-09 (ADR-032 "What a composite would need"): reading B."""

    def test_the_modifier_s_finger_must_be_ready_when_the_composite_brings_it_in(self) -> None:
        layout = build_is()
        had = {"f", "j", "a"}
        assert may_introduce(layout, "á", had, READY)
        rest = with_rest(R_pink=RestCell(3, 10, False))
        assert not may_introduce(layout, "á", had, rest)

    def test_a_modifier_that_is_its_finger_s_rest_key_needs_it_only_chosen(self) -> None:
        rest = with_rest(R_pink=RestCell(3, 11, False))
        assert may_introduce(build_is(), "á", {"f", "j", "a"}, rest)

    def test_once_the_modifier_is_had_its_finger_is_not_read(self) -> None:
        rest = with_rest(R_pink=None)
        assert may_introduce(build_is(), "é", {"f", "j", "a", "á", "e"}, rest)

    def test_a_base_on_its_finger_s_rest_key_needs_it_only_chosen(self) -> None:
        # `á` is struck on `a`, the left little finger's rest key: no reach.
        rest = with_rest(L_pink=RestCell(3, 1, False))
        assert may_introduce(build_is(), "á", {"f", "j", "a"}, rest)

    def test_any_other_base_needs_its_finger_ready(self) -> None:
        rest = with_rest(L_mid=RestCell(3, 3, False))
        assert not may_introduce(build_is(), "é", {"f", "j", "a", "á", "e"}, rest)


class TestOrderingAUnderTheRules:
    """ADR-032 § Ordering A under the rules: pairs by column, a member passed over."""

    def test_a_member_passed_over_leaves_its_partner_alone_and_stays_out_of_phase_2(
        self,
    ) -> None:
        rest = with_rest(L_mid=None)
        steps = names(ordered(build_en(), source(C_WORDS), set(), home_row_fill, rest))
        assert steps[:5] == [["f", "j"], ["k"], ["s", "l"], ["a"], ["g", "h"]]
        assert not {"d", "e", "c"} & set(members(steps))

    @pytest.mark.parametrize("cell", [None, RestCell(2, 1, False)])
    def test_a_composite_never_comes_before_a_base_passed_over_in_phase_1(
        self, cell: RestCell | None
    ) -> None:
        # Phase 2 is handed every home-row letter as had, so `eligible` opens
        # for `á` while `a` is still waiting. `may_introduce` holds it back,
        # because `á` is struck on the same key (found by session (5)'s review).
        rest = with_rest(L_pink=cell)
        order = members(names(ordered(build_is(), WordfreqSource(), set(), home_row_fill, rest)))
        assert "a" not in order
        assert "á" not in order

    def test_it_comes_back_alone_at_the_head_of_phase_1(self) -> None:
        had = {"f", "j", "k", "s", "l", "a", "g", "h", "t", "n"}
        steps = names(ordered(build_en(), source(C_WORDS), had, home_row_fill, READY))
        assert steps[0] == ["d"]


class TestTheOrderIsAForecast:
    """ADR-032: an empty order means nothing may come now, not that the curriculum is done."""

    def test_the_introducer_reads_the_rest_state_each_time(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Ana")
        rest: dict[str, RestCell] = {}
        intro = KeyIntroducer(
            build_en(), source(C_WORDS), KeyStates(store, profile.id), lambda: rest
        )
        assert intro.upcoming() is None
        assert intro.introduce_next() is None
        rest.update(READY)
        step = intro.introduce_next()
        assert step is not None
        assert [k.grapheme for k in step.keys] == ["f", "j"]

    def test_letters_waiting_on_a_finger_do_not_raise(self) -> None:
        # Phase 2 runs dry with letters left in its pools; only a composite
        # with no base letter is an error (the test in TestPurity).
        rest = with_rest(L_mid=None)
        slots = phase2_slots(build_is(), source(C_WORDS), {"f", "j"}, rest)
        assert "e" not in {name for slot in slots for name in slot.keys}

    def test_current_rest_reads_current_keys_and_whether_they_are_ready(self) -> None:
        store = FakeStore()
        pid = store.create_profile("Ana").id
        store.choose_rest_key(pid, "L-mid", 3, 3, "landings")
        store.mark_rest_key_ready(pid, "L-mid")
        store.choose_rest_key(pid, "L-mid", 2, 3, "landings")
        store.choose_rest_key(pid, "R-mid", 3, 8, "answer")
        store.mark_rest_key_ready(pid, "R-mid")
        store.mark_rest_key_passed(pid, "R-mid")
        assert current_rest(store.rest_keys(pid)) == {
            "L-mid": RestCell(2, 3, False),
            "R-mid": RestCell(3, 8, True),
        }


@pytest.mark.slow
class TestRealOrderingC:
    """ADR-032 § Ordering C, restated: its table of orders, on the real word data.

    Every finger ready only; the spike that made the table implements the
    count rule itself, so this pins the engine against it in that one state.
    """

    @pytest.mark.parametrize(
        ("build", "rest", "expected"),
        [
            (build_en, READY, "fj en al to si rh du cm"),
            (build_de, READY, "fj en sl ri ah tu dm co"),
            (build_is, READY, "fj ri al en sk tu gm vð"),
            (build_en, with_rest(L_mid=RestCell(2, 3, True)), "fj tn el ro ai dh su cm"),
        ],
    )
    def test_the_amendments_table(
        self, build: Callable[[], Layout], rest: Rest, expected: str
    ) -> None:
        steps = ordered(build(), WordfreqSource(), set(), per_hand_alternation, rest)
        assert ["".join(step) for step in names(steps)[:8]] == expected.split()
