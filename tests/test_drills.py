import random
from collections import Counter
from itertools import pairwise

import pytest

from takki import config
from takki.language import WordSource
from takki.lesson.drills import DrillBlock, DrillGenerator, RampUpPhase
from takki.lesson.introducer import (
    CURRICULUM,
    STAGE_0,
    IntroductionStep,
    KeyIntroduction,
    base_key,
    home_anchor_keys,
    introduction_sequence,
)
from takki.lesson.key_state import KeyStates
from takki.lesson.rampup import RampUpProgress
from takki.platform.layout import Layout, build_en, build_is
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_store import FakeStore
from tests.fakes.fixed_list_source import FixedListSource

# Real English words so the bigram pool is a real one, weighted so the drill
# content is decided by this table and not by a corpus.
EN_WORDS: dict[str, float] = {
    "the": 100.0,
    "and": 90.0,
    "for": 80.0,
    "fur": 70.0,
    "jam": 60.0,
    "run": 50.0,
    "dark": 45.0,
    "very": 40.0,
    "kind": 35.0,
    "much": 30.0,
    "five": 20.0,
    "just": 10.0,
}

ANCHOR_SIX = "fjruvm"


def member(layout: Layout, name: str) -> KeyIntroduction:
    grapheme = layout.graphemes[name]
    key = base_key(layout, name)
    return KeyIntroduction(
        grapheme=name,
        mechanism=grapheme.mechanism,
        keys=grapheme.prereq_keys,
        base=key.name,
        finger=key.finger,
        side=key.side,
        location=None,
        modifier=None,
    )


def make_step(layout: Layout, *names: str, stage: int = CURRICULUM) -> IntroductionStep:
    return IntroductionStep(stage, tuple(member(layout, name) for name in names))


class Fixture:
    """One profile, one generator, and the store behind both."""

    def __init__(
        self,
        layout: Layout | None = None,
        source: WordSource | None = None,
        *,
        active: str = "",
        seed: int = 7,
    ) -> None:
        self.layout = layout or build_en()
        self.source = source or FixedListSource(EN_WORDS)
        self.store = FakeStore()
        self.profile = self.store.create_profile("child").id
        self.states = KeyStates(self.store, self.profile)
        self.clock = FakeClock()
        for name in active:
            self.activate(name)
        self.progress = RampUpProgress(self.store, self.profile)
        self.generator = DrillGenerator(
            self.layout,
            self.source,
            self.states,
            self.clock,
            random.Random(seed),
            self.progress,
        )

    def activate(self, grapheme: str, *, attempts: int = 1, wrong: int = 0) -> None:
        for index in range(attempts):
            correct = index >= wrong
            self.store.upsert_key_stat(self.profile, grapheme, correct)
            self.store.append_attempt(self.profile, grapheme, correct)

    def attempt(self, grapheme: str, correct: bool, *, latency_ms: int | None = None) -> None:
        # The store first, then the generator -- the order the session loop uses
        # (`AttemptCounter.press` writes, then `DrillGenerator.record_attempt`).
        # Since 2026-09-29 it is load-bearing: the ramp-up's phase is derived
        # from these rows, so a generator told about an attempt that was never
        # written would read the window as one attempt short.
        self.store.upsert_key_stat(self.profile, grapheme, correct)
        self.store.append_attempt(self.profile, grapheme, correct, latency_ms=latency_ms)
        self.generator.record_attempt(grapheme, correct)

    def answer(
        self, block_prompts: tuple[str, ...], *, correct: bool = True, seconds_each: float = 0.0
    ) -> None:
        for grapheme in block_prompts:
            self.clock.advance(seconds_each)
            self.attempt(grapheme, correct)

    def practise_all(self) -> None:
        for grapheme in sorted(self.states.active_keys()):
            self.attempt(grapheme, True)


def press(fixture: Fixture, grapheme: str, count: int, *, correct: bool = True) -> None:
    for _ in range(count):
        fixture.attempt(grapheme, correct)


class TestPhaseA:
    def test_solo_step_repeats_the_member_and_engages_the_other_hand(self) -> None:
        # ADR-024 property 3: Phase A keeps the new key isolated on its own hand
        # -- no same-finger anchor -- but the other hand's home key joins the
        # inventory so no hand sits idle. `a` on English is the audible case:
        # column 10's home cell holds no letter, so nothing pairs with it.
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.generator.begin_step(make_step(fixture.layout, "a"))
        block = fixture.generator.next_block()
        assert Counter(block.units) == {
            ("a",): config.PHASE_A_STREAK,
            ("j",): config.PHASE_A_STREAK,
        }

    def test_pair_engages_both_hands_without_borrowing_an_anchor(self) -> None:
        # A pair already uses both hands (ADR-028 § Pair ramp-up), so nothing is
        # borrowed and each member gets the same number of prompts. Order is
        # shuffled per ADR-024 property 1, so the count is the contract.
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.generator.begin_step(make_step(fixture.layout, "d", "k"))
        block = fixture.generator.next_block()
        assert Counter(block.units) == {
            ("d",): config.PHASE_A_STREAK,
            ("k",): config.PHASE_A_STREAK,
        }

    def test_ten_in_succession_advances(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.generator.begin_step(make_step(fixture.layout, "d", "k"))
        press(fixture, "d", 10)
        assert fixture.generator.ramp_up is not None
        assert fixture.generator.ramp_up.phase is RampUpPhase.A
        press(fixture, "k", 10)
        assert fixture.generator.ramp_up.phase is RampUpPhase.B

    def test_a_wrong_press_resets_the_streak(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.generator.begin_step(make_step(fixture.layout, "d"))
        press(fixture, "d", 9)
        fixture.attempt("d", False)
        press(fixture, "d", 9)
        assert fixture.generator.ramp_up is not None
        assert fixture.generator.ramp_up.phase is RampUpPhase.A
        press(fixture, "d", 1)
        assert fixture.generator.ramp_up.phase is RampUpPhase.B

    def test_an_anchor_press_does_not_advance_the_new_letter(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.generator.begin_step(make_step(fixture.layout, "d"))
        press(fixture, "f", 30)
        assert fixture.generator.ramp_up is not None
        assert fixture.generator.ramp_up.phase is RampUpPhase.A


class TestPhaseB:
    def test_four_way_alternation_for_a_pair(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.generator.begin_step(make_step(fixture.layout, "d", "k"))
        press(fixture, "d", 10)
        press(fixture, "k", 10)
        block = fixture.generator.next_block()
        # Each member alternates with its own anchor (ADR-028 § Pair ramp-up).
        # Either direction may be emitted -- `d f` is the return `f d` leaves
        # owed -- so the pairing is the contract and the order is not.
        assert Counter(frozenset(unit) for unit in block.units) == {
            frozenset({"f", "d"}): len(block.units) // 2,
            frozenset({"j", "k"}): len(block.units) // 2,
        }

    def test_anchor_is_the_same_finger_home_row_key(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX + "dk")
        # ADR-024's own example: E is L-mid row 2, so it alternates with D.
        fixture.generator.begin_step(make_step(fixture.layout, "e"))
        press(fixture, "e", 10)
        block = fixture.generator.next_block()
        # The other hand joins as its own unit, never paired with the member: a
        # cross-hand pair would carry the member's hand off home with no home key
        # of that hand to return to (ADR-024 properties 2 and 3).
        assert {frozenset(unit) for unit in block.units} == {
            frozenset({"d", "e"}),
            frozenset({"j"}),
        }

    def test_same_hand_fallback_when_no_same_finger_anchor_exists(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        # D is L-mid; the only home-row keys the child has are F and J, neither
        # L-mid, so the nearest key on the same hand stands in.
        fixture.generator.begin_step(make_step(fixture.layout, "d"))
        press(fixture, "d", 10)
        block = fixture.generator.next_block()
        assert {frozenset(unit) for unit in block.units} == {
            frozenset({"f", "d"}),
            frozenset({"j"}),
        }

    def test_twenty_correct_with_one_rejection_advances(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.generator.begin_step(make_step(fixture.layout, "d"))
        press(fixture, "d", 10)
        press(fixture, "d", 10)
        fixture.attempt("d", False)
        press(fixture, "d", 9)
        assert fixture.generator.ramp_up is not None
        assert fixture.generator.ramp_up.phase is RampUpPhase.B
        press(fixture, "d", 1)
        assert fixture.generator.ramp_up.phase is RampUpPhase.C

    def test_a_second_rejection_restarts_the_run(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.generator.begin_step(make_step(fixture.layout, "d"))
        press(fixture, "d", 10)
        press(fixture, "d", 19)
        fixture.attempt("d", False)
        fixture.attempt("d", False)
        press(fixture, "d", 19)
        assert fixture.generator.ramp_up is not None
        assert fixture.generator.ramp_up.phase is RampUpPhase.B
        press(fixture, "d", 1)
        assert fixture.generator.ramp_up.phase is RampUpPhase.C


class TestPhaseCAndD:
    def _into_phase_c(self, fixture: Fixture, *names: str) -> None:
        fixture.generator.begin_step(make_step(fixture.layout, *names))
        for name in names:
            press(fixture, name, config.PHASE_A_STREAK)
        for name in names:
            press(fixture, name, config.PHASE_B_ATTEMPTS)

    def test_thirty_attempts_at_the_accuracy_bar_advances_to_steady_state(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        self._into_phase_c(fixture, "d")
        assert fixture.generator.ramp_up is not None
        assert fixture.generator.ramp_up.phase is RampUpPhase.C
        press(fixture, "d", 29)
        assert fixture.generator.ramp_up is not None
        press(fixture, "d", 1)
        assert fixture.generator.ramp_up is None

    def test_below_the_accuracy_bar_takes_another_thirty(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        self._into_phase_c(fixture, "d")
        press(fixture, "d", 25)
        press(fixture, "d", 5, correct=False)  # 25/30 = 83%, under the 85% bar
        assert fixture.generator.ramp_up is not None
        assert fixture.generator.ramp_up.phase is RampUpPhase.C
        press(fixture, "d", 30)
        assert fixture.generator.ramp_up is None

    def test_every_phase_c_unit_carries_a_new_letter(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        self._into_phase_c(fixture, "d", "k")
        block = fixture.generator.next_block()
        assert all(2 <= len(unit) <= 3 for unit in block.units)
        assert all({"d", "k"} & set(unit) for unit in block.units)
        # Alternating members, so neither can be starved of its thirty attempts.
        assert ["d" in unit for unit in block.units[:4]] == [True, False, True, False]

    def test_the_two_new_letters_are_never_mixed_with_each_other(self) -> None:
        # Both are brand new, so pairing them is the several-new-keys-at-once
        # mix the ramp-up exists to prevent.
        fixture = Fixture(active=ANCHOR_SIX + "dk")
        self._into_phase_c(fixture, "e", "o")
        block = fixture.generator.next_block()
        assert block.units
        assert not any({"e", "o"} <= set(unit) for unit in block.units)


class TestComposites:
    def test_solo_composite_ramps_up_solo(self) -> None:
        layout = build_is()
        fixture = Fixture(layout, FixedListSource({"úúú": 10.0, "sumar": 5.0}), active="us")
        fixture.generator.begin_step(make_step(layout, "ú"))
        # No other hand to engage: `ú` is right-handed and `f` is not Active in
        # this fixture, and ADR-024 property 3 borrows a key the child already
        # has rather than teaching one to fill the gap.
        assert set(fixture.generator.next_block().units) == {("ú",)}
        press(fixture, "ú", config.PHASE_A_STREAK)
        # ADR-028 § Phase B: the anchor for a composite is its own base letter.
        assert {frozenset(unit) for unit in fixture.generator.next_block().units} == {
            frozenset({"u", "ú"})
        }

    def test_composite_paired_with_a_letter_takes_the_pair_path(self) -> None:
        layout = build_is()
        fixture = Fixture(layout, FixedListSource({"ást": 10.0, "æði": 5.0}), active="aæfjruvm")
        # Two members, three physical keys — the first step whose member count
        # and key count come apart (ADR-028 § Pair ramp-up, session 8c).
        step = make_step(layout, "á", "ð")
        assert sum(len(intro.keys) for intro in step.keys) == 3
        fixture.generator.begin_step(step)
        block = fixture.generator.next_block()
        assert Counter(block.units) == {
            ("á",): config.PHASE_A_STREAK,
            ("ð",): config.PHASE_A_STREAK,
        }
        press(fixture, "á", config.PHASE_A_STREAK)
        press(fixture, "ð", config.PHASE_A_STREAK)
        # Each composite alternates with its own base letter, which ADR-028
        # § Phase B makes its anchor: the same physical key with and without the
        # modifier gesture.
        block = fixture.generator.next_block()
        assert Counter(frozenset(unit) for unit in block.units) == {
            frozenset({"a", "á"}): len(block.units) // 2,
            frozenset({"æ", "ð"}): len(block.units) // 2,
        }


class TestStageZero:
    def steps(self) -> tuple[Layout, WordSource, list[IntroductionStep]]:
        layout = build_en()
        source = FixedListSource(EN_WORDS)
        return layout, source, introduction_sequence(layout, source)[:3]

    def test_the_stage_is_three_pairs(self) -> None:
        _, _, steps = self.steps()
        assert [step.stage for step in steps] == [STAGE_0] * 3
        assert [[k.grapheme for k in step.keys] for step in steps] == [
            ["f", "j"],
            ["r", "u"],
            ["v", "m"],
        ]

    def test_home_pair_alternates_the_two_anchors(self) -> None:
        layout, source, steps = self.steps()
        fixture = Fixture(layout, source)
        fixture.generator.begin_step(steps[0])
        assert Counter(fixture.generator.next_block().units) == {
            ("f",): config.PHASE_A_STREAK,
            ("j",): config.PHASE_A_STREAK,
        }

    @pytest.mark.parametrize(
        ("index", "active", "expected"),
        [
            (1, "fj", ("f", "r", "j", "u")),
            (2, "fjru", ("f", "v", "j", "m")),
        ],
    )
    def test_each_reach_alternates_with_its_own_column_anchor(
        self, index: int, active: str, expected: tuple[str, ...]
    ) -> None:
        # ADR-027 § The Anchor Gate: the stage alternates the anchor with its
        # own column reaches, which is what makes plain first-press accuracy a
        # valid return-to-anchor measure. Ordinary Phase A repetition here
        # would silently invalidate the ladder's first rung.
        layout, source, steps = self.steps()
        fixture = Fixture(layout, source, active=active)
        fixture.generator.begin_step(steps[index])
        block = fixture.generator.next_block()
        left, right = expected[:2], expected[2:]
        assert Counter(frozenset(unit) for unit in block.units) == {
            frozenset(left): len(block.units) // 2,
            frozenset(right): len(block.units) // 2,
        }

    def test_no_stage_zero_block_ever_repeats_a_prompt(self) -> None:
        layout, source, steps = self.steps()
        active = ""
        for step in steps:
            fixture = Fixture(layout, source, active=active)
            for phase_presses in (0, config.PHASE_A_STREAK):
                fixture.generator.begin_step(step)
                for intro in step.keys:
                    press(fixture, intro.grapheme, phase_presses)
                prompts = fixture.generator.next_block().prompts
                assert all(a != b for a, b in pairwise(prompts))
            active += "".join(intro.grapheme for intro in step.keys)


class TestSteadyState:
    def test_block_is_bigrams_over_the_active_set_only(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.practise_all()
        block = fixture.generator.next_block()
        assert all(len(unit) == 2 for unit in block.units)
        assert set(block.prompts) <= set(ANCHOR_SIX)

    def test_seeded_generators_agree(self) -> None:
        blocks = []
        for _ in range(2):
            fixture = Fixture(active=ANCHOR_SIX + "dk", seed=11)
            fixture.practise_all()
            blocks.append([fixture.generator.next_block() for _ in range(3)])
        assert blocks[0] == blocks[1]

    def test_a_different_seed_gives_different_content(self) -> None:
        blocks = []
        for seed in (11, 12):
            fixture = Fixture(active=ANCHOR_SIX + "dk", seed=seed)
            fixture.practise_all()
            blocks.append(fixture.generator.next_block())
        assert blocks[0] != blocks[1]


class TestReexposure:
    def baseline(self, *, stale: str | None) -> tuple[Fixture, tuple[tuple[str, ...], ...]]:
        fixture = Fixture(active=ANCHOR_SIX + "dk", seed=5)
        for grapheme in sorted(fixture.states.active_keys()):
            if grapheme != stale:
                fixture.attempt(grapheme, True)
        fixture.clock.advance(10.0)
        return fixture, fixture.generator.next_block().units

    def test_nothing_fires_when_every_key_is_fresh(self) -> None:
        _, units = self.baseline(stale=None)
        assert len(units) == config.FIRST_BLOCK_PROMPTS // 2

    def test_one_stale_key_replaces_exactly_one_unit(self) -> None:
        _, fresh = self.baseline(stale=None)
        _, reexposed = self.baseline(stale="k")
        assert len(reexposed) == len(fresh)
        differences = [i for i, unit in enumerate(reexposed) if unit != fresh[i]]
        assert len(differences) == 1
        assert "k" in reexposed[differences[0]]

    def test_the_fallback_partner_breaks_weight_ties_by_name(self) -> None:
        # No bigram in this corpus carries z, so the stale unit falls back to
        # pairing it with the heaviest active letter -- and f and j weigh the
        # same, which without a name tie-break would resolve by set order.
        fixture = Fixture(source=FixedListSource({"fff": 10.0, "jjj": 10.0}), active="fjz", seed=3)
        for grapheme in ("f", "j"):
            fixture.attempt(grapheme, True)
        fixture.clock.advance(10.0)
        injected = [unit for unit in fixture.generator.next_block().units if "z" in unit]
        assert injected == [("z", "f")]

    def test_a_key_practised_inside_the_window_is_not_stale(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX + "dk", seed=5)
        fixture.practise_all()
        fixture.clock.advance(config.REEXPOSURE_STALE_SECONDS - 1)
        before = fixture.generator.next_block().units
        assert before == self.baseline(stale=None)[1]


class TestAnchorMaintenance:
    def slipping(self, grapheme: str) -> Fixture:
        fixture = Fixture(active=ANCHOR_SIX + "dk", seed=5)
        # Well past ANCHOR_MIN_ATTEMPTS, well under ANCHOR_MIN_ACCURACY.
        fixture.activate(grapheme, attempts=40, wrong=20)
        fixture.practise_all()
        fixture.clock.advance(10.0)
        return fixture

    def test_the_bump_keys_are_the_maintained_ones(self) -> None:
        assert home_anchor_keys(build_en()) == ("f", "j")

    def test_a_slipping_anchor_gets_a_return_drill(self) -> None:
        fixture = self.slipping("f")
        units = fixture.generator.next_block().units
        injected = [unit for unit in units if unit[-1] == "f" and unit[0] in ("r", "v")]
        assert len(injected) == 1
        assert len(units) == config.FIRST_BLOCK_PROMPTS // 2

    def test_a_slipping_ordinary_key_gets_nothing(self) -> None:
        fixture = self.slipping("d")
        assert fixture.generator.next_block().units == TestReexposure().baseline(stale=None)[1]

    def test_an_anchor_above_the_bar_gets_nothing(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX + "dk", seed=5)
        fixture.activate("f", attempts=40, wrong=1)
        fixture.practise_all()
        fixture.clock.advance(10.0)
        assert fixture.generator.next_block().units == TestReexposure().baseline(stale=None)[1]

    def test_too_few_attempts_is_not_a_slipping_anchor(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX + "dk", seed=5)
        # One short of the bar: the fixture recorded one attempt on f when it
        # activated the key, and `practise_all` below records another.
        fixture.activate("f", attempts=config.ANCHOR_MIN_ATTEMPTS - 3, wrong=10)
        fixture.practise_all()
        fixture.clock.advance(10.0)
        assert fixture.generator.next_block().units == TestReexposure().baseline(stale=None)[1]

    def test_both_triggers_in_one_block_take_one_slot_each(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX + "dk", seed=5)
        fixture.activate("f", attempts=40, wrong=20)
        for grapheme in sorted(fixture.states.active_keys()):
            if grapheme != "k":
                fixture.attempt(grapheme, True)
        fixture.clock.advance(10.0)
        units = fixture.generator.next_block().units
        fresh = TestReexposure().baseline(stale=None)[1]
        differences = [i for i, unit in enumerate(units) if unit != fresh[i]]
        assert len(units) == len(fresh)
        assert len(differences) == 2
        assert units[differences[0]][-1] == "f"
        assert "k" in units[differences[1]]


class TestBlockLength:
    def test_first_block_uses_the_configured_default(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.practise_all()
        assert len(fixture.generator.next_block().prompts) == config.FIRST_BLOCK_PROMPTS

    def test_length_scales_with_the_measured_pace(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.practise_all()
        # 30 prompts at 2 s each = 0.5/s, over a 100 s block target.
        fixture.answer(fixture.generator.next_block().prompts, seconds_each=2.0)
        assert len(fixture.generator.next_block().prompts) == 50

    def test_a_ramp_up_block_stops_at_the_phase_bar(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.practise_all()
        # 3 prompts/s, which would buy a 300-prompt steady block.
        fixture.answer(fixture.generator.next_block().prompts, seconds_each=1 / 3)
        fixture.generator.begin_step(make_step(fixture.layout, "d", "k"))
        assert len(fixture.generator.next_block().prompts) == 2 * config.PHASE_A_STREAK

    def test_a_solo_step_is_sized_by_the_bar_and_not_by_the_inventory(self) -> None:
        # The member owes PHASE_A_STREAK prompts and appears once per cycle, so
        # the block is PHASE_A_STREAK cycles -- of two prompts each, the member
        # and the borrowed other hand. Counting prompts owed instead of cycles
        # owed would double it, and only a solo step can show the difference.
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.practise_all()
        fixture.answer(fixture.generator.next_block().prompts, seconds_each=1 / 3)
        fixture.generator.begin_step(make_step(fixture.layout, "d"))
        block = fixture.generator.next_block()
        assert len(block.units) == 2 * config.PHASE_A_STREAK
        assert Counter(block.prompts) == {
            "d": config.PHASE_A_STREAK,
            "j": config.PHASE_A_STREAK,
        }

    def test_a_solo_phase_b_block_is_sized_by_the_bar(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.practise_all()
        fixture.answer(fixture.generator.next_block().prompts, seconds_each=1 / 3)
        fixture.generator.begin_step(make_step(fixture.layout, "d"))
        press(fixture, "d", config.PHASE_A_STREAK)
        block = fixture.generator.next_block()
        # Inventory ('f','d') and ('j',): the member owes PHASE_B_ATTEMPTS and
        # gets one prompt per three.
        assert Counter(block.prompts)["d"] == config.PHASE_B_ATTEMPTS
        assert len(block.prompts) == 3 * config.PHASE_B_ATTEMPTS

    def test_blocks_end_on_a_unit_boundary(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.practise_all()
        # 30 prompts over 61.2 s -> 49.02 prompts per block, rounded to 49.
        fixture.answer(fixture.generator.next_block().prompts, seconds_each=2.04)
        block = fixture.generator.next_block()
        assert len(block.prompts) == 50
        assert all(len(unit) == 2 for unit in block.units)

    def test_time_the_child_was_not_typing_is_not_charged_to_their_pace(self) -> None:
        # A PAUSED interval, a walk-away, a conversation: monotonic time runs
        # through all of them, and charging them to the child would shrink
        # every block afterwards.
        paced, idle = (Fixture(active=ANCHOR_SIX) for _ in range(2))
        for fixture in (paced, idle):
            fixture.practise_all()
            prompts = fixture.generator.next_block().prompts
            fixture.answer(prompts[:15], seconds_each=2.0)
            if fixture is idle:
                fixture.clock.advance(300.0)
            fixture.answer(prompts[15:], seconds_each=2.0)
        assert len(idle.generator.next_block().prompts) == 50
        assert len(paced.generator.next_block().prompts) == 50

    def test_a_block_nobody_answered_contributes_no_pace_sample(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.practise_all()
        fixture.answer(fixture.generator.next_block().prompts, seconds_each=2.0)
        fixture.generator.next_block()
        fixture.clock.advance(600.0)
        assert len(fixture.generator.next_block().prompts) == 50

    def test_no_active_keys_gives_an_empty_block(self) -> None:
        assert Fixture().generator.next_block() == DrillBlock(())


class TestStepShape:
    def test_a_step_of_three_members_is_refused(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        with pytest.raises(ValueError, match="one or two graphemes"):
            fixture.generator.begin_step(make_step(fixture.layout, "d", "k", "s"))

    def test_an_empty_step_is_refused(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        with pytest.raises(ValueError, match="one or two graphemes"):
            fixture.generator.begin_step(IntroductionStep(CURRICULUM, ()))


class TestSessionFloor:
    def test_floor_is_per_active_key(self) -> None:
        fixture = Fixture(active="fj")
        assert not fixture.generator.session_complete
        press(fixture, "f", config.SESSION_KEY_FLOOR)
        assert not fixture.generator.session_complete
        press(fixture, "j", config.SESSION_KEY_FLOOR)
        assert fixture.generator.session_complete

    def test_a_profile_with_no_active_keys_is_not_complete(self) -> None:
        assert not Fixture().generator.session_complete
