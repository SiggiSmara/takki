import math
import random
from collections import Counter
from datetime import datetime, timedelta
from itertools import pairwise
from typing import ClassVar

import pytest

from takki import config
from takki.language import WordSource
from takki.lesson.drills import (
    MAX_KEY_SHARE,
    DrillBlock,
    DrillGenerator,
    RampUpPhase,
    plan_targets,
    presses_needed,
)
from takki.lesson.introducer import (
    CURRICULUM,
    STAGE_0,
    IntroductionStep,
    KeyIntroduction,
    base_key,
    home_anchor_keys,
    introduction_sequence,
)
from takki.lesson.key_state import CONFIDENCE_Z, Evidence, KeyStates, accuracy_bound
from takki.lesson.rampup import RampUpProgress
from takki.persistence import PhaseRecord
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
        now: str | None = None,
    ) -> None:
        self.layout = layout or build_en()
        self.source = source or FixedListSource(EN_WORDS)
        self.store = FakeStore()
        self.profile = self.store.create_profile("child").id
        # `now` is the wall clock evidence ages against (ADR-027); None is the
        # system's, which suits rows the fake store stamps itself.
        self.states = KeyStates(
            self.store,
            self.profile,
            now=None if now is None else lambda: now,
            bump_keys=home_anchor_keys(self.layout),
        )
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


def press(
    fixture: Fixture,
    grapheme: str,
    count: int,
    *,
    correct: bool = True,
    latency_ms: int | None = None,
) -> None:
    for _ in range(count):
        fixture.attempt(grapheme, correct, latency_ms=latency_ms)


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


class TestPairAdvancesTogether:
    """alpha-plan #12j, O1: a member is judged only for the phase its step is in.

    A member that met its bar first kept being judged for the *next* phase on
    its own evidence, while the step was still drilling this one's content, and
    could record the whole ramp-up without ever being given Phase B or C.
    """

    @pytest.mark.parametrize(
        ("pair", "stage", "active"),
        [(("d", "k"), CURRICULUM, ANCHOR_SIX), (("f", "j"), STAGE_0, "")],
    )
    def test_a_member_ahead_of_its_partner_records_nothing_while_it_waits(
        self, pair: tuple[str, str], stage: int, active: str
    ) -> None:
        # The review's own scenario: one member right every time, the other
        # wrong every time, for eight blocks.
        fixture = Fixture(active=active)
        ahead, behind = pair
        fixture.generator.begin_step(make_step(fixture.layout, *pair, stage=stage))
        began_at = fixture.store.key_stats(fixture.profile).get(ahead)
        start = began_at.attempt_count if began_at is not None else 0
        for _ in range(8):
            block = fixture.generator.next_block()
            assert {len(unit) for unit in block.units} == {1}
            for grapheme in block.prompts:
                fixture.attempt(grapheme, grapheme == ahead)
            assert fixture.generator.ramp_up is not None
            assert fixture.generator.ramp_up.phase is RampUpPhase.A
        assert fixture.store.phase_records(fixture.profile, ahead) == {
            "A": PhaseRecord(start, start + config.PHASE_A_STREAK)
        }
        assert fixture.store.phase_records(fixture.profile, behind) == {"A": PhaseRecord(start)}

    def test_the_next_phase_starts_for_both_when_the_slower_member_arrives(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.generator.begin_step(make_step(fixture.layout, "d", "k"))
        waited = 7
        press(fixture, "d", config.PHASE_A_STREAK + waited)
        press(fixture, "k", config.PHASE_A_STREAK)
        ramp = fixture.generator.ramp_up
        assert ramp is not None and ramp.phase is RampUpPhase.B
        # `d` starts Phase B where the step did, not where it passed Phase A:
        # the presses it made while waiting were on Phase A's content.
        d_start = config.PHASE_A_STREAK + waited
        assert fixture.store.phase_records(fixture.profile, "d") == {
            "A": PhaseRecord(0, config.PHASE_A_STREAK),
            "B": PhaseRecord(d_start),
        }
        assert fixture.store.phase_records(fixture.profile, "k") == {
            "A": PhaseRecord(0, config.PHASE_A_STREAK),
            "B": PhaseRecord(config.PHASE_A_STREAK),
        }
        assert ramp.progress["d"].evidence == ()
        # So all of Phase B's twenty are still owed, and the twentieth passes it.
        press(fixture, "d", config.PHASE_B_ATTEMPTS - 1)
        assert fixture.store.phase_records(fixture.profile, "d")["B"] == PhaseRecord(d_start)
        press(fixture, "d", 1)
        assert fixture.store.phase_records(fixture.profile, "d")["B"] == PhaseRecord(
            d_start, d_start + config.PHASE_B_ATTEMPTS
        )
        # And `d` now waits again: Phase C has not begun for it.
        assert "C" not in fixture.store.phase_records(fixture.profile, "d")
        assert ramp.phase is RampUpPhase.B

    def test_a_block_is_sized_by_the_member_still_in_the_phase(self) -> None:
        # The member that is ahead owes this phase nothing. It used to be sized
        # as if it owed the whole of the next one.
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.generator.begin_step(make_step(fixture.layout, "d", "k"))
        owed = 3
        press(fixture, "d", config.PHASE_A_STREAK)
        press(fixture, "k", config.PHASE_A_STREAK - owed)
        block = fixture.generator.next_block()
        assert Counter(block.units) == {("d",): owed, ("k",): owed}

    def test_a_start_that_was_never_written_is_written_on_the_next_read(self) -> None:
        # A session killed after the last member's completion was recorded and
        # before the next phase was begun. The next session begins it.
        fixture = Fixture(active=ANCHOR_SIX)
        step = make_step(fixture.layout, "d", "k")
        fixture.generator.begin_step(step)
        press(fixture, "d", config.PHASE_A_STREAK)
        for _ in range(config.PHASE_A_STREAK):
            fixture.store.upsert_key_stat(fixture.profile, "k", True)
            fixture.store.append_attempt(fixture.profile, "k", True)
        assert fixture.progress.advance(fixture.progress.member("k")) is True
        assert "B" not in fixture.store.phase_records(fixture.profile, "k")

        restarted = DrillGenerator(
            fixture.layout,
            fixture.source,
            fixture.states,
            fixture.clock,
            random.Random(7),
            RampUpProgress(fixture.store, fixture.profile),
        )
        assert restarted.resume_step(step) is True
        assert restarted.ramp_up is not None and restarted.ramp_up.phase is RampUpPhase.B
        for name in ("d", "k"):
            assert fixture.store.phase_records(fixture.profile, name) == {
                "A": PhaseRecord(0, config.PHASE_A_STREAK),
                "B": PhaseRecord(config.PHASE_A_STREAK),
            }


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

    def test_a_new_letter_past_twice_the_bump_keys_speed_stays_in_phase_c(self) -> None:
        # alpha-plan #12f: `f` and `j` are the baseline from the first step on,
        # so the term is no longer skipped until something is Known.
        fixture = Fixture(active=ANCHOR_SIX)
        for name in home_anchor_keys(fixture.layout):
            press(fixture, name, config.SPEED_MIN_SAMPLE, latency_ms=1000)
        self._into_phase_c(fixture, "d")
        slow = round(1000 * config.PHASE_C_MAX_LATENCY_RATIO) + 1
        press(fixture, "d", config.PHASE_C_ATTEMPTS, latency_ms=slow)
        assert fixture.generator.ramp_up is not None
        assert fixture.generator.ramp_up.phase is RampUpPhase.C
        # The bar reads the median of the latest thirty, so it clears when
        # more than half of them are within the ratio.
        press(fixture, "d", config.PHASE_C_ATTEMPTS // 2, latency_ms=slow - 1)
        assert fixture.generator.ramp_up is not None
        press(fixture, "d", 1, latency_ms=slow - 1)
        assert fixture.generator.ramp_up is None

    def test_the_bump_keys_own_ramp_up_has_no_speed_term(self) -> None:
        # Stage 0's first step: `f` nine times slower than `j` and through.
        fixture = Fixture()
        self._into_phase_c(fixture, "f", "j")
        press(fixture, "j", config.PHASE_C_ATTEMPTS, latency_ms=1000)
        press(fixture, "f", config.PHASE_C_ATTEMPTS, latency_ms=9000)
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

    def test_the_partners_are_the_most_frequent_keys_the_child_has(self) -> None:
        # u, r and m carry the weight and f, j and v none, and `d` meets only
        # `u` in this corpus. Every weight is under 1, so a key missing from
        # the table cannot outrank one that is in it.
        source = FixedListSource({"dud": 0.5, "red": 0.3, "mud": 0.2})
        fixture = Fixture(source=source, active=ANCHOR_SIX)
        self._into_phase_c(fixture, "d")
        block = fixture.generator.next_block()
        assert block.units
        assert all("u" in unit for unit in block.units)

    def test_a_letter_no_bigram_carries_is_paired_with_the_heaviest_partner(self) -> None:
        source = FixedListSource({"uuu": 0.5, "rrr": 0.3, "mmm": 0.2})
        fixture = Fixture(source=source, active=ANCHOR_SIX)
        self._into_phase_c(fixture, "d")
        assert set(fixture.generator.next_block().units) == {("u", "d")}

    def test_a_trigram_is_two_corpus_bigrams_drawn_by_weight(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(config, "PHASE_C_TRIGRAM_CHANCE", 1.0)
        source = FixedListSource({"dud": 1000.0, "mud": 1.0})
        fixture = Fixture(source=source, active=ANCHOR_SIX)
        self._into_phase_c(fixture, "d")
        bigrams = set(source.bigram_weights(fixture.layout))
        units = [unit for _ in range(5) for unit in fixture.generator.next_block().units]
        assert all(len(unit) == 3 for unit in units)
        assert all(first + second in bigrams for unit in units for first, second in pairwise(unit))
        # `mu` is one two-thousandth of what `ud` can grow from, and a third of
        # it when the weights are ignored.
        assert units.count(("m", "u", "d")) <= 1


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


# Every letter's only carrier is its own double, so each unit names the key it
# was planned for and a block's per-key counts are the plan's, exactly.
def doubles(letters: str) -> FixedListSource:
    return FixedListSource({letter * 2: 1.0 for letter in letters})


# What a finished ramp-up leaves in each member's window (ADR-024 § New-key
# ramp-up): the presses of phases A, B and C, all correct.
RAMP_UP_PRESSES = config.PHASE_A_STREAK + config.PHASE_B_ATTEMPTS + config.PHASE_C_ATTEMPTS
FIRST_SLOTS = config.FIRST_BLOCK_PROMPTS // 2


def cap(slots: int, keys: int) -> int:
    return max(1, math.floor(slots * MAX_KEY_SHARE), math.ceil(slots / keys))


def stats(attempts: int, correct: int, *, kept: float = 1.0) -> Evidence:
    # `kept` is the share of its weight each press still has: 1.0 is a window
    # practised just now, 0.5 one that is a half-life old.
    return Evidence(attempts, distinct_days=1, weight=attempts * kept, correct=correct * kept)


class TestAccuracyBound:
    def test_no_presses_is_no_evidence(self) -> None:
        assert accuracy_bound(0, 0) == 0.0

    @pytest.mark.parametrize("presses", [1, 3, 25, 60, 90, 200])
    def test_a_perfect_key_is_bounded_by_its_evidence(self, presses: int) -> None:
        # Wilson's bound at p = 1 reduces to n / (n + z^2): a perfect run is
        # only as sure as it is long.
        expected = presses / (presses + CONFIDENCE_Z**2)
        assert math.isclose(accuracy_bound(presses, presses), expected)

    def test_more_correct_presses_raise_the_bound(self) -> None:
        assert accuracy_bound(81, 101) > accuracy_bound(80, 100)


class TestPressesNeeded:
    def test_a_key_fresh_from_its_ramp_up_needs_the_rest_of_known_s_floor(self) -> None:
        need = presses_needed(stats(RAMP_UP_PRESSES, RAMP_UP_PRESSES), config.ANCHOR_MIN_ACCURACY)
        assert need == config.KNOWN_MIN_ATTEMPTS - RAMP_UP_PRESSES

    def test_a_perfect_key_at_the_floor_needs_nothing(self) -> None:
        floor = config.KNOWN_MIN_ATTEMPTS
        assert presses_needed(stats(floor, floor), config.ANCHOR_MIN_ACCURACY) == 0

    # The grid includes the case #12e was made for -- a key well past Known's
    # floor that is still missing its bar, which a count rule would call done --
    # and keys short on both counts at once.
    @pytest.mark.parametrize(
        ("attempts", "wrong"),
        [
            (attempts, wrong)
            for attempts in (0, 5, 30, RAMP_UP_PRESSES, 90, 120, 200)
            for wrong in (0, 1, 4, 12, 40)
            if wrong <= attempts
        ],
    )
    @pytest.mark.parametrize("bar", [config.KNOWN_MIN_ACCURACY, config.ANCHOR_MIN_ACCURACY])
    def test_need_is_the_larger_shortfall_and_exactly_enough(
        self, attempts: int, wrong: int, bar: float
    ) -> None:
        correct = attempts - wrong
        need = presses_needed(stats(attempts, correct), bar)
        gap = max(0, config.KNOWN_MIN_ATTEMPTS - attempts)
        assert need >= gap
        # Enough correct presses clear the bar, and one fewer would not --
        # unless the gap, not the bar, is what sets the number.
        assert accuracy_bound(correct + need, attempts + need) >= bar
        if need > gap:
            assert accuracy_bound(correct + need - 1, attempts + need - 1) < bar

    # Alpha-plan #12f: the same windows after time away. The grid is the case
    # decay is for -- a key at or past Known's floor, clean or nearly so, that
    # had no need when it was last practised.
    @pytest.mark.parametrize(
        ("attempts", "wrong"), [(90, 0), (90, 5), (150, 6), (200, 0), (200, 4)]
    )
    @pytest.mark.parametrize("half_lives", [0.0, 0.1, 1.0, 2.0, 4.0, 6.0, 12.0])
    @pytest.mark.parametrize("bar", [config.KNOWN_MIN_ACCURACY, config.ANCHOR_MIN_ACCURACY])
    def test_need_after_time_away_is_exactly_enough_to_restore_the_bound(
        self, attempts: int, wrong: int, half_lives: float, bar: float
    ) -> None:
        aged = stats(attempts, attempts - wrong, kept=0.5**half_lives)
        need = presses_needed(aged, bar)
        # The dose is counted as it happened: time away never reopens the gap.
        assert aged.attempts >= config.KNOWN_MIN_ATTEMPTS
        assert accuracy_bound(aged.correct + need, aged.weight + need) >= bar
        if need:
            assert accuracy_bound(aged.correct + need - 1, aged.weight + need - 1) < bar

    @pytest.mark.parametrize(("attempts", "wrong"), [(90, 0), (150, 6), (200, 4)])
    def test_need_only_grows_with_time_away_and_is_bounded_by_a_key_with_no_history(
        self, attempts: int, wrong: int
    ) -> None:
        bar = config.KNOWN_MIN_ACCURACY
        needs = [
            presses_needed(stats(attempts, attempts - wrong, kept=0.5**half_lives), bar)
            for half_lives in (0.0, 1.0, 2.0, 4.0, 8.0, 16.0, 40.0)
        ]
        assert needs[0] == 0
        assert needs == sorted(needs)
        # However long the absence, coming back costs no more than confirming a
        # key from nothing: old misses fade with the old hits.
        from_nothing = presses_needed(Evidence(attempts, 1, 0.0, 0.0), bar)
        assert 0 < needs[-1] <= from_nothing


class TestNeedFromTheStore:
    """Alpha-plan #12f, through `KeyStates`: the need is read off stored presses and the clock."""

    DAY1 = "2026-01-01T10:00:00+00:00"
    DAY2 = "2026-01-02T10:00:00+00:00"

    def practised(self, now: str, *, days: int = 2) -> Fixture:
        fixture = Fixture(now=now)
        stamps = [self.DAY1, self.DAY2][:days]
        for index in range(config.KNOWN_MIN_ATTEMPTS):
            stamp = stamps[index % len(stamps)]
            fixture.store.upsert_key_stat(fixture.profile, "f", True, stamp)
            fixture.store.append_attempt(fixture.profile, "f", True, stamp)
        return fixture

    def need(self, fixture: Fixture) -> int:
        return presses_needed(fixture.states.evidence("f"), config.ANCHOR_MIN_ACCURACY)

    def test_a_key_at_its_bar_has_no_need_after_a_long_weekend(self) -> None:
        assert self.need(self.practised("2026-01-05T10:00:00+00:00")) == 0

    def test_the_same_key_has_need_again_after_half_a_year_away(self) -> None:
        need = self.need(self.practised("2026-07-01T10:00:00+00:00"))
        # More than nothing, and less than confirming a key never seen: the old
        # presses still count for something.
        from_nothing = presses_needed(
            Evidence(config.KNOWN_MIN_ATTEMPTS, 2, 0.0, 0.0), config.ANCHOR_MIN_ACCURACY
        )
        assert 0 < need < from_nothing

    def test_decay_does_not_give_a_one_day_key_need_the_next_morning(self) -> None:
        # Why ADR-024's second-day rule stays: a clean first day keeps its
        # bound for months, so decay never asks for the press that would make
        # the key Known.
        fixture = self.practised(self.DAY2, days=1)
        assert fixture.states.evidence("f").distinct_days == 1
        assert self.need(fixture) == 0


class TestPlanTargets:
    def test_two_equal_needs_split_the_block_ties_by_name(self) -> None:
        counts = plan_targets({"j": 30, "f": 30}, FIRST_SLOTS, random.Random(1))
        assert counts == {"f": -(-FIRST_SLOTS // 2), "j": FIRST_SLOTS // 2}

    def test_a_struggling_key_takes_no_more_than_the_cap(self) -> None:
        needs = {"e": 10_000} | dict.fromkeys("fjruvmdk", 0)
        counts = plan_targets(needs, FIRST_SLOTS, random.Random(1))
        limit = cap(FIRST_SLOTS, len(needs))
        assert counts["e"] == limit
        # The rest goes round the others evenly.
        others = [counts[name] for name in "fjruvmdk"]
        assert sum(others) == FIRST_SLOTS - limit
        assert max(others) - min(others) <= 1

    def test_shares_follow_need_when_the_cap_does_not_bind(self) -> None:
        # D'Hondt by hand, 12 slots, cap max(4, 2) = 4. Quotients above 10:
        # a 40, 20, 13.3; b 20 -- four slots. At 10: a's fourth, b's second, and
        # c d e f's first -- six more, a now at its cap. Then b's 6.7, then a
        # five-way tie at 5 between b's fourth and c d e f's second, which b
        # takes by name.
        needs = {"a": 40, "b": 20, "c": 10, "d": 10, "e": 10, "f": 10}
        assert cap(12, len(needs)) == 4
        counts = plan_targets(needs, 12, random.Random(1))
        assert counts == {"a": 4, "b": 4, "c": 1, "d": 1, "e": 1, "f": 1}

    def test_a_key_with_a_small_need_keeps_one_slot_in_a_crowded_block(self) -> None:
        # Alpha-plan #12g. Four keys at the cap would take 20 of 15 slots, and
        # by D'Hondt alone the key that needs one press would get none.
        needs = {"a": 1} | dict.fromkeys("bcde", 10_000)
        assert 4 * cap(FIRST_SLOTS, len(needs)) > FIRST_SLOTS
        counts = plan_targets(needs, FIRST_SLOTS, random.Random(1))
        assert counts["a"] == 1
        assert sum(counts.values()) == FIRST_SLOTS

    def test_more_keys_in_need_than_slots_serves_the_neediest(self) -> None:
        needs = {"a": 1, "b": 9, "c": 5, "d": 7}
        assert plan_targets(needs, 3, random.Random(1)) == {"a": 0, "b": 1, "c": 1, "d": 1}

    def test_slots_nobody_needs_go_round_evenly(self) -> None:
        counts = plan_targets(dict.fromkeys("fjruvm", 0), 12, random.Random(1))
        assert counts == dict.fromkeys("fjruvm", 2)

    def test_each_further_slot_goes_to_the_most_need_per_slot_held(self) -> None:
        # D'Hondt by hand, 12 slots, cap max(4, 3) = 4. One each takes five,
        # and e is then served. The other seven, by need over slots held plus
        # one: a and b at 2.5, then both at 1.67, then c and d at 1.5, then a
        # at 1.25, which wins the tie with b by name.
        needs = {"a": 5, "b": 5, "c": 3, "d": 3, "e": 1}
        assert cap(12, len(needs)) == 4
        counts = plan_targets(needs, 12, random.Random(1))
        assert counts == {"a": 4, "b": 3, "c": 2, "d": 2, "e": 1}

    def test_no_keys_or_no_slots_plans_nothing(self) -> None:
        assert plan_targets({}, 5, random.Random(1)) == {}
        assert plan_targets({"f": 3}, 0, random.Random(1)) == {"f": 0}

    # Seeds and need shapes chosen to include a starved key beside a flooded
    # one, which is the case the plan exists for.
    @pytest.mark.parametrize("seed", range(5))
    @pytest.mark.parametrize(
        "needs",
        [
            {"f": 0, "j": 30},
            {"f": 30, "j": 30},
            {"f": 10_000, "j": 0, "r": 0},
            {"f": 3, "j": 1, "r": 0, "u": 200, "v": 0, "m": 7},
            dict.fromkeys("abcdefghijklmnopq", 5),
        ],
    )
    @pytest.mark.parametrize("slots", [1, 2, 5, 15, 25])
    def test_every_slot_is_planned_and_no_key_passes_the_cap(
        self, needs: dict[str, int], slots: int, seed: int
    ) -> None:
        counts = plan_targets(needs, slots, random.Random(seed))
        assert sum(counts.values()) == slots
        assert max(counts.values()) <= cap(slots, len(needs))


class TestSteadyPlan:
    def test_stage_0_keys_fresh_from_their_ramp_up_get_the_block(self) -> None:
        # f j r u are at Known's floor and perfect; v and m have just finished
        # their ramp-up. The two new keys take the cap each, and what is left
        # goes round the other four.
        fixture = Fixture(source=doubles(ANCHOR_SIX))
        for name in "fjru":
            fixture.activate(name, attempts=config.KNOWN_MIN_ATTEMPTS)
        for name in "vm":
            fixture.activate(name, attempts=RAMP_UP_PRESSES)
        limit = cap(FIRST_SLOTS, len(ANCHOR_SIX))
        assert config.KNOWN_MIN_ATTEMPTS - RAMP_UP_PRESSES >= limit
        counts = Counter(unit[0] for unit in fixture.generator.next_block().units)
        assert counts["v"] == counts["m"] == limit
        rest = [counts[name] for name in "fjru"]
        assert sum(rest) == FIRST_SLOTS - 2 * limit
        assert max(rest) - min(rest) <= 1

    def test_a_stage_0_key_is_planned_against_the_anchor_bar(self) -> None:
        # Alpha-plan #12f. Five early misses in ninety presses over two days
        # is past Known's 90% and short of the anchor's 95%, so f and j still
        # have need and d, k, s and l have none: the two take the cap and the
        # rest share what is left.
        letters = "fjdksl"
        stamps = ["2026-01-01T10:00:00+00:00", "2026-01-02T10:00:00+00:00"]
        fixture = Fixture(source=doubles(letters), now=stamps[1])
        for name in letters:
            for index in range(config.KNOWN_MIN_ATTEMPTS):
                stamp = stamps[index % 2]
                fixture.store.upsert_key_stat(fixture.profile, name, index >= 5, stamp)
                fixture.store.append_attempt(fixture.profile, name, index >= 5, stamp)
        evidence = fixture.states.evidence("f")
        assert presses_needed(evidence, config.KNOWN_MIN_ACCURACY) == 0
        assert presses_needed(evidence, config.ANCHOR_MIN_ACCURACY) > 0
        limit = cap(FIRST_SLOTS, len(letters))
        counts = Counter(unit[0] for unit in fixture.generator.next_block().units)
        assert counts["f"] == counts["j"] == limit
        rest = [counts[name] for name in "dksl"]
        assert sum(rest) == FIRST_SLOTS - 2 * limit
        assert max(rest) - min(rest) <= 1

    @pytest.mark.parametrize(("days", "planned"), [(1, 1), (2, 0)])
    def test_a_key_that_lacks_only_its_second_day_is_planned_once(
        self, days: int, planned: int
    ) -> None:
        # Alpha-plan #12g: f is at Known's floor and perfect. With one day
        # behind it, one press today makes it Known and frees its slot, so the
        # block carries exactly one -- in a block the other five would fill.
        stamps = ["2026-01-01T10:00:00+00:00", "2026-01-02T10:00:00+00:00"][:days]
        fixture = Fixture(source=doubles(ANCHOR_SIX), now="2026-01-02T10:00:00+00:00")
        for index in range(config.KNOWN_MIN_ATTEMPTS):
            stamp = stamps[index % len(stamps)]
            fixture.store.upsert_key_stat(fixture.profile, "f", True, stamp)
            fixture.store.append_attempt(fixture.profile, "f", True, stamp)
        for name in "jruvm":
            fixture.activate(name)
        assert 5 * cap(FIRST_SLOTS, len(ANCHOR_SIX)) > FIRST_SLOTS
        counts = Counter(unit[0] for unit in fixture.generator.next_block().units)
        assert counts["f"] == planned
        assert sum(counts.values()) == FIRST_SLOTS

    @pytest.mark.parametrize(("latency_ms", "slow"), [(2500, True), (1900, False)])
    def test_a_key_only_speed_keeps_from_known_is_planned(
        self, latency_ms: int, slow: bool
    ) -> None:
        # alpha-plan #12f: every key is past its accuracy bar, so accuracy asks
        # for nothing. `d` answers 2.5 times slower than the rest, is not Known
        # and holds a slot, and without a need of its own would be practised no
        # more than the keys that are done.
        letters = ANCHOR_SIX + "dk"
        stamps = ["2026-01-01T10:00:00+00:00", "2026-01-02T10:00:00+00:00"]
        fixture = Fixture(source=doubles(letters), now=stamps[1])
        for name in letters:
            ms = latency_ms if name == "d" else 1000
            for index in range(config.KNOWN_MIN_ATTEMPTS):
                stamp = stamps[index % 2]
                fixture.store.upsert_key_stat(fixture.profile, name, True, stamp)
                fixture.store.append_attempt(fixture.profile, name, True, stamp, ms)
        assert fixture.states.slow_keys() == ({"d"} if slow else set())
        counts = Counter(unit[0] for unit in fixture.generator.next_block().units)
        assert sum(counts.values()) == FIRST_SLOTS
        even_share = math.ceil(FIRST_SLOTS / len(letters))
        planned = min(cap(FIRST_SLOTS, len(letters)), config.SLOW_KEY_NEED)
        assert planned > even_share
        if slow:
            assert counts["d"] == planned
        else:
            assert counts["d"] <= even_share
        rest = [counts[name] for name in letters if name != "d"]
        assert max(rest) - min(rest) <= 1

    def test_a_key_pressed_this_session_is_no_longer_waiting_for_a_day(self) -> None:
        # Today is already one of its days, so another press cannot make it
        # Known. This is a child's first day: every key at the floor, one day.
        fixture = Fixture(source=doubles(ANCHOR_SIX))
        fixture.activate("f", attempts=config.KNOWN_MIN_ATTEMPTS)
        for name in "jruvm":
            fixture.activate(name)
        first = Counter(unit[0] for unit in fixture.generator.next_block().units)
        assert first["f"] == 1
        press(fixture, "f", 1)
        second = Counter(unit[0] for unit in fixture.generator.next_block().units)
        assert second["f"] == 0

    def test_a_key_at_the_session_ceiling_is_not_planned(self) -> None:
        fixture = Fixture(source=doubles("dk"))
        fixture.activate("k", attempts=RAMP_UP_PRESSES)
        fixture.activate("d")
        # Wrong every time: d needs more practice than anything, and has had
        # all this sitting should give it.
        press(fixture, "d", config.SESSION_KEY_CEILING, correct=False)
        units = fixture.generator.next_block().units
        assert len(units) == FIRST_SLOTS
        assert set(units) == {("k", "k")}

    def test_when_every_key_is_at_the_ceiling_none_is_excluded(self) -> None:
        fixture = Fixture(source=doubles("dk"))
        for name in "dk":
            fixture.activate(name)
            press(fixture, name, config.SESSION_KEY_CEILING)
        units = fixture.generator.next_block().units
        # Neither needs anything, so the block goes round both evenly.
        counts = Counter(units)
        assert set(counts) == {("d", "d"), ("k", "k")}
        assert sorted(counts.values()) == [FIRST_SLOTS // 2, -(-FIRST_SLOTS // 2)]

    def test_equal_groups_interleave_evenly(self) -> None:
        # d is fresh from its ramp-up and takes the cap, a third of the block;
        # k and l need nothing and share the rest. Three groups of five, each
        # spread at a fifth of the block from its own phase, so every stretch of
        # a fifth holds exactly one unit of each: every key recurs every third
        # unit, never twice running.
        fixture = Fixture(source=doubles("dkl"))
        fixture.activate("d", attempts=RAMP_UP_PRESSES)
        for name in "kl":
            fixture.activate(name, attempts=config.KNOWN_MIN_ATTEMPTS)
        units = fixture.generator.next_block().units
        assert Counter(units) == {("d", "d"): 5, ("k", "k"): 5, ("l", "l"): 5}
        for name in "dkl":
            positions = [i for i, unit in enumerate(units) if unit[0] == name]
            assert [b - a for a, b in pairwise(positions)] == [3] * 4

    def test_the_fallback_partner_breaks_weight_ties_by_name(self) -> None:
        # No bigram in this corpus carries z, so its units fall back to pairing
        # it with the heaviest active letter -- and f and j weigh the same,
        # which without a name tie-break would resolve by set order.
        fixture = Fixture(source=FixedListSource({"fff": 10.0, "jjj": 10.0}), active="fjz", seed=3)
        carried = [unit for unit in fixture.generator.next_block().units if "z" in unit]
        assert carried
        assert set(carried) == {("z", "f")}


class TestStarvationRegression:
    """Alpha-plan #12e: frequency-weighted steady state starved the letter being learned.

    Reproduced in #12b-2 with real English over {f, j}: 80 answers came out 76
    `f` and 4 `j`, because the language offers almost only `ff`. The corpus here
    carries those four bigrams at English's weights. Steady state is reached
    deliberately -- both keys as a finished ramp-up leaves them -- since #12d
    closed the restart route to it.
    """

    ENGLISH_FJ: ClassVar[dict[str, float]] = {
        "ff": 0.0047,
        "fj": 0.000008,
        "jf": 0.000002,
        "jj": 0.000002,
    }

    def test_j_holds_half_of_every_block_over_a_long_session(self) -> None:
        fixture = Fixture(source=FixedListSource(self.ENGLISH_FJ))
        for name in "fj":
            fixture.activate(name, attempts=RAMP_UP_PRESSES)
        prompts: list[str] = []
        for _ in range(20):
            block = fixture.generator.next_block()
            # Every j unit carries at least one j, and j's need never falls
            # below f's -- f gets two presses from each `ff` -- so j is planned
            # for at least the smaller half of every block.
            assert sum("j" in unit for unit in block.units) >= len(block.units) // 2
            fixture.answer(block.prompts, seconds_each=2.0)
            prompts += block.prompts
        shares = Counter(prompts)
        assert len(prompts) > 2 * config.SESSION_KEY_CEILING
        # At least one j in at least half of the units: a quarter of the prompts.
        assert shares["j"] * 4 >= len(prompts)


class TestAnchorMaintenance:
    # Doubles only, so the one unit that is a reach followed by its anchor can
    # only have come from the maintenance path.
    def fixture(self) -> Fixture:
        fixture = Fixture(source=doubles(ANCHOR_SIX + "dk"), seed=5)
        for name in ANCHOR_SIX + "dk":
            fixture.activate(name, attempts=config.KNOWN_MIN_ATTEMPTS)
        return fixture

    def return_drills(self, units: tuple[tuple[str, ...], ...]) -> list[tuple[str, ...]]:
        reaches = {"f": ("r", "v"), "j": ("u", "m")}
        return [u for u in units if len(u) == 2 and u[0] in reaches.get(u[1], ())]

    def slipping(self, *graphemes: str) -> Fixture:
        fixture = self.fixture()
        for grapheme in graphemes:
            # Well past ANCHOR_MIN_ATTEMPTS, well under ANCHOR_MIN_ACCURACY.
            press(fixture, grapheme, 40, correct=False)
        return fixture

    def test_the_bump_keys_are_the_maintained_ones(self) -> None:
        assert home_anchor_keys(build_en()) == ("f", "j")

    def test_a_slipping_anchor_gets_one_return_drill_in_a_block_of_the_same_length(self) -> None:
        units = self.slipping("f").generator.next_block().units
        assert [unit[1] for unit in self.return_drills(units)] == ["f"]
        assert len(units) == FIRST_SLOTS

    def test_both_anchors_slipping_take_one_slot_each(self) -> None:
        units = self.slipping("f", "j").generator.next_block().units
        assert sorted(unit[1] for unit in self.return_drills(units)) == ["f", "j"]
        assert len(units) == FIRST_SLOTS

    def test_the_second_anchor_slipping_alone_gets_its_drill(self) -> None:
        units = self.slipping("j").generator.next_block().units
        assert [unit[1] for unit in self.return_drills(units)] == ["j"]

    def test_an_anchor_with_no_reach_does_not_cost_the_other_its_drill(self) -> None:
        # Neither r nor v is Active, so nothing in f's column can be drilled
        # back to it. j still has u and m.
        letters = "fjumdk"
        fixture = Fixture(source=doubles(letters), seed=5)
        for name in letters:
            fixture.activate(name, attempts=config.KNOWN_MIN_ATTEMPTS)
        for name in "fj":
            press(fixture, name, 40, correct=False)
        units = fixture.generator.next_block().units
        assert [unit[1] for unit in self.return_drills(units)] == ["j"]

    def test_a_slipping_ordinary_key_gets_no_return_drill(self) -> None:
        assert self.return_drills(self.slipping("d").generator.next_block().units) == []

    def test_an_anchor_above_the_bar_gets_nothing(self) -> None:
        fixture = self.fixture()
        press(fixture, "f", 1, correct=False)
        evidence = fixture.states.evidence("f")
        assert accuracy_bound(evidence.correct, evidence.weight) >= config.ANCHOR_MIN_ACCURACY
        assert self.return_drills(fixture.generator.next_block().units) == []

    def test_slipping_is_read_off_the_bound_and_not_the_raw_share(self) -> None:
        # alpha-plan #12f, raised by both of its reviews: 90 of 93 is 96.8%,
        # over the bar as a share, and its bound is under it. The rung and the
        # block plan read the bound, and the return-drill did not.
        fixture = self.fixture()
        press(fixture, "f", 3, correct=False)
        stats_f = fixture.store.window_stats(fixture.profile, "f")
        assert stats_f.correct_count / stats_f.attempt_count >= config.ANCHOR_MIN_ACCURACY
        evidence = fixture.states.evidence("f")
        assert accuracy_bound(evidence.correct, evidence.weight) < config.ANCHOR_MIN_ACCURACY
        units = fixture.generator.next_block().units
        assert [unit[1] for unit in self.return_drills(units)] == ["f"]

    @pytest.mark.parametrize(("days_away", "drilled"), [(3, []), (200, ["f", "j"])])
    def test_an_anchor_not_practised_for_months_is_slipping(
        self, days_away: int, drilled: list[str]
    ) -> None:
        # The case decay was added for. Every press was right, so the raw
        # share never moves; what goes is how much the old presses still say.
        stamps = ["2026-01-01T10:00:00+00:00", "2026-01-02T10:00:00+00:00"]
        now = (datetime.fromisoformat(stamps[1]) + timedelta(days=days_away)).isoformat()
        fixture = Fixture(source=doubles(ANCHOR_SIX + "dk"), seed=5, now=now)
        for name in ANCHOR_SIX + "dk":
            for index in range(config.KNOWN_MIN_ATTEMPTS):
                stamp = stamps[index % 2]
                fixture.store.upsert_key_stat(fixture.profile, name, True, stamp)
                fixture.store.append_attempt(fixture.profile, name, True, stamp)
        units = fixture.generator.next_block().units
        assert sorted(unit[1] for unit in self.return_drills(units)) == drilled

    def test_the_sample_floor_is_enough_to_be_slipping(self) -> None:
        fixture = Fixture(source=doubles(ANCHOR_SIX), seed=5)
        for name in ANCHOR_SIX:
            fixture.activate(name)
        press(fixture, "f", config.ANCHOR_MIN_ATTEMPTS - 1, correct=False)
        attempts = fixture.store.window_stats(fixture.profile, "f").attempt_count
        assert attempts == config.ANCHOR_MIN_ATTEMPTS
        units = fixture.generator.next_block().units
        assert [unit[1] for unit in self.return_drills(units)] == ["f"]

    def test_too_few_attempts_is_not_a_slipping_anchor(self) -> None:
        fixture = Fixture(source=doubles(ANCHOR_SIX), seed=5)
        for name in ANCHOR_SIX:
            fixture.activate(name)
        press(fixture, "f", config.ANCHOR_MIN_ATTEMPTS - 2, correct=False)
        attempts = fixture.store.window_stats(fixture.profile, "f").attempt_count
        assert attempts == config.ANCHOR_MIN_ATTEMPTS - 1
        assert self.return_drills(fixture.generator.next_block().units) == []


class TestLanguageWeights:
    """ADR-024: the learner's need picks the key, and the language picks what carries it."""

    def test_a_keys_carrier_is_drawn_by_bigram_weight(self) -> None:
        # `fj` is a thousand to one against either double, and one in two when
        # the weights are ignored.
        source = FixedListSource({"fj": 1000.0, "ff": 1.0, "jj": 1.0})
        fixture = Fixture(source=source, active="fj")
        units = [unit for _ in range(4) for unit in fixture.generator.next_block().units]
        assert len(units) == 4 * FIRST_SLOTS
        assert len([unit for unit in units if unit[0] == unit[1]]) <= 2

    def test_a_key_no_bigram_carries_is_paired_with_the_heaviest_other_key(self) -> None:
        # j is in both words and f in one, so j is the heavier; r is in neither.
        source = FixedListSource({"fjj": 10.0, "jjj": 5.0})
        fixture = Fixture(source=source, active="fjr")
        units = fixture.generator.next_block().units
        assert {unit for unit in units if "r" in unit} == {("r", "j")}

    def test_a_lone_key_no_bigram_carries_is_doubled(self) -> None:
        fixture = Fixture(source=FixedListSource({"jjj": 1.0}), active="f")
        assert set(fixture.generator.next_block().units) == {("f", "f")}


class TestAnchorChoice:
    def test_a_new_key_alternates_with_its_own_fingers_home_key(self) -> None:
        # ADR-024 Phase B. `r` is the nearer key to `t` and on the same hand,
        # and `f` is the home key of the finger that types it.
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.generator.begin_step(make_step(fixture.layout, "t"))
        press(fixture, "t", config.PHASE_A_STREAK)
        units = fixture.generator.next_block().units
        assert {frozenset(unit) for unit in units if "t" in unit} == {frozenset("ft")}


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

    def test_a_phase_a_block_is_one_cycle_when_one_press_is_owed(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.generator.begin_step(make_step(fixture.layout, "d"))
        press(fixture, "d", config.PHASE_A_STREAK - 1)
        assert Counter(fixture.generator.next_block().prompts) == {"d": 1, "j": 1}

    def test_a_phase_b_block_is_one_cycle_when_one_press_is_owed(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.generator.begin_step(make_step(fixture.layout, "d"))
        press(fixture, "d", config.PHASE_A_STREAK)
        press(fixture, "d", config.PHASE_B_ATTEMPTS - 1)
        assert Counter(fixture.generator.next_block().prompts) == {"f": 1, "d": 1, "j": 1}

    def test_a_phase_c_block_is_one_unit_when_one_press_is_owed(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.generator.begin_step(make_step(fixture.layout, "d"))
        press(fixture, "d", config.PHASE_A_STREAK + config.PHASE_B_ATTEMPTS)
        press(fixture, "d", config.PHASE_C_ATTEMPTS - 1)
        (unit,) = fixture.generator.next_block().units
        assert "d" in unit

    def test_a_phase_c_block_is_filled_to_the_target_and_no_further(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Bigrams only, so the count is exact: the member owes thirty rounds
        # and the block's thirty prompts are reached after fifteen.
        monkeypatch.setattr(config, "PHASE_C_TRIGRAM_CHANCE", 0.0)
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.generator.begin_step(make_step(fixture.layout, "d"))
        press(fixture, "d", config.PHASE_A_STREAK + config.PHASE_B_ATTEMPTS)
        block = fixture.generator.next_block()
        assert all(len(unit) == 2 for unit in block.units)
        assert len(block.prompts) == config.FIRST_BLOCK_PROMPTS

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

    def test_the_floor_is_reached_on_its_last_press_and_not_before(self) -> None:
        fixture = Fixture(active="fj")
        for name in "fj":
            press(fixture, name, config.SESSION_KEY_FLOOR - 1)
        press(fixture, "f", 1)
        assert not fixture.generator.session_complete
        press(fixture, "j", 1)
        assert fixture.generator.session_complete

    def test_a_profile_with_no_active_keys_is_not_complete(self) -> None:
        assert not Fixture().generator.session_complete
