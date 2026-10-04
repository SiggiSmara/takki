"""ADR-024 § Ramp-up variability — the recorded phases, the bars, the invariants."""

import random
from itertools import pairwise

import pytest

from takki import config
from takki.lesson import rampup
from takki.lesson.introducer import HOME_ROW, base_key, introduction_sequence
from takki.lesson.rampup import RampUpPhase, RampUpProgress
from takki.persistence import Attempt, PhaseRecord
from takki.platform.layout import Layout, build_en
from tests.fakes.fake_store import FakeStore
from tests.fakes.fixed_list_source import FixedListSource
from tests.test_drills import EN_WORDS, Fixture, make_step

THROUGH_A = "." * config.PHASE_A_STREAK
THROUGH_B = "." * config.PHASE_B_ATTEMPTS
THROUGH_C = "." * config.PHASE_C_ATTEMPTS


def rows(pattern: str, latency_ms: int | None = None) -> list[Attempt]:
    """`.` is correct, `x` is a rejection — one row each, in order."""
    return [
        Attempt(
            correct=mark == ".", attempted_at="2026-09-29T10:00:00+00:00", latency_ms=latency_ms
        )
        for mark in pattern
    ]


class TestBars:
    def test_phase_a_wants_a_streak_that_an_error_resets(self) -> None:
        assert rampup.bar_met(RampUpPhase.A, rows(THROUGH_A))
        assert not rampup.bar_met(RampUpPhase.A, rows(THROUGH_A[:-1] + "x"))
        assert not rampup.bar_met(RampUpPhase.A, rows("...x" + "." * 9))

    def test_phase_b_spends_its_rejection_budget_once(self) -> None:
        assert rampup.bar_met(RampUpPhase.B, rows("." * 10 + "x" + "." * 10))
        assert not rampup.bar_met(RampUpPhase.B, rows("." * 10 + "xx" + "." * 10))

    def test_phase_b_counts_the_live_run_not_the_best_one(self) -> None:
        # A child who overspends the budget has lost what came before it, and a
        # block sized off their old best run would be sized for progress they
        # no longer have.
        spent = rows("." * 19 + "xx" + "." * 5)
        assert rampup.live_run(spent) == 5
        assert rampup.remaining(RampUpPhase.B, spent) == config.PHASE_B_ATTEMPTS - 5

    def test_phase_b_counts_back_from_the_latest_press(self) -> None:
        # A second miss is not a restart from zero: what lies between the last
        # two misses still counts, with the latest miss as the one allowed.
        assert rampup.live_run(rows("." * 12 + "x" + "." * 3 + "x" + "." * 5)) == 8
        # And it buys no fresh allowance: twenty correct holding two misses is
        # not the bar, however the misses fall.
        assert not rampup.bar_met(RampUpPhase.B, rows("." * 10 + "x" + "." * 5 + "x" + "." * 5))
        assert rampup.bar_met(RampUpPhase.B, rows("xx" + "." * 10 + "x" + "." * 10))

    @pytest.mark.parametrize(
        "gaps",
        [
            # The two histories alpha-plan #12j's repro found, as correct answers
            # between misses. Counted forward from the first press, the capped
            # read passed the first child at press 91 and the full read never
            # did; the second child was the reverse.
            [0, 4, 3, 10, 1, 4, 5, 2, 1, 16, 9, 9, 16],
            [0, 5, 4, 12, 0, 0, 2, 14, 10, 5, 3, 3, 7, 14],
        ],
    )
    def test_phase_b_does_not_depend_on_where_the_read_starts(self, gaps: list[int]) -> None:
        history = rows("x".join("." * gap for gap in gaps))
        assert len(history) > rampup.EVIDENCE_ROWS
        for presses in range(1, len(history) + 1):
            seen = history[:presses]
            assert rampup.bar_met(RampUpPhase.B, seen) == rampup.bar_met(
                RampUpPhase.B, seen[-rampup.EVIDENCE_ROWS :]
            )

    @pytest.mark.parametrize("seed", range(20))
    def test_phase_b_reads_the_same_through_the_cap_for_any_history(self, seed: int) -> None:
        rng = random.Random(seed)
        history = rows("".join(rng.choice("....x") for _ in range(3 * rampup.EVIDENCE_ROWS)))
        for presses in range(1, len(history) + 1):
            seen = history[:presses]
            capped = seen[-rampup.EVIDENCE_ROWS :]
            # Equal until the bar is met, which is all a bar or a block size reads.
            assert min(rampup.live_run(seen), config.PHASE_B_ATTEMPTS) == min(
                rampup.live_run(capped), config.PHASE_B_ATTEMPTS
            )

    def test_phase_c_wants_thirty_at_the_accuracy_bar(self) -> None:
        assert rampup.bar_met(RampUpPhase.C, rows(THROUGH_C))
        assert not rampup.bar_met(RampUpPhase.C, rows(THROUGH_C[:-1]))
        # 24 of 30 is 80%, under PHASE_C_MIN_ACCURACY.
        assert not rampup.bar_met(RampUpPhase.C, rows("." * 24 + "x" * 6))

    def test_phase_c_owes_another_thirty_when_the_bar_is_missed(self) -> None:
        # The bar reads the trailing thirty, so a child sitting below it is owed
        # a full block again -- not nothing, which is what a plain countdown gave
        # and which collapsed every later block to one unit per member.
        missed = rows("." * 24 + "x" * 6)
        assert not rampup.bar_met(RampUpPhase.C, missed)
        assert rampup.remaining(RampUpPhase.C, missed) == config.PHASE_C_ATTEMPTS

    def test_remaining_is_never_zero_inside_a_phase(self) -> None:
        for phase in RampUpPhase:
            assert rampup.remaining(phase, rows("." * 200)) >= 1


class TestLatency:
    def test_no_baseline_skips_the_term(self) -> None:
        # Every profile's first days, Stage 0 included: a term that failed closed
        # would hold the curriculum behind a measurement that cannot be made.
        assert rampup.bar_met(RampUpPhase.C, rows(THROUGH_C, 9999), None)

    def test_within_the_ratio_passes_and_outside_it_does_not(self) -> None:
        assert rampup.bar_met(RampUpPhase.C, rows(THROUGH_C, 1000), 800.0)
        assert not rampup.bar_met(RampUpPhase.C, rows(THROUGH_C, 2000), 800.0)

    def test_unmeasured_rows_never_fail_a_bar(self) -> None:
        assert rampup.bar_met(RampUpPhase.C, rows(THROUGH_C, None), 800.0)

    def test_the_baseline_pools_the_known_windows(self) -> None:
        assert rampup.baseline_latency([rows("..", 100), rows("..", 300)]) == 200.0
        assert rampup.baseline_latency([rows(".."), rows("..")]) is None


class TestRecordedPhases:
    """The durable half: a passed phase is an event, not a re-derivation."""

    def progress(self) -> tuple[FakeStore, int, RampUpProgress]:
        store = FakeStore()
        profile = store.create_profile("kid").id
        return store, profile, RampUpProgress(store, profile)

    def answer(self, store: FakeStore, profile: int, name: str, pattern: str) -> None:
        # A solo key: its step reaches a phase the moment it passes the one
        # before, so the phase it is in is begun before it is answered.
        progress = RampUpProgress(store, profile)
        member = progress.member(name)
        if member.phase is not None and not member.begun:
            progress.begin(member)
        for mark in pattern:
            store.upsert_key_stat(profile, name, mark == ".")
            store.append_attempt(profile, name, mark == ".")

    def test_a_fresh_member_is_in_phase_a_with_no_evidence(self) -> None:
        _, _, progress = self.progress()
        member = progress.member("d")
        assert (member.phase, member.evidence, member.attempts) == (RampUpPhase.A, (), 0)

    def test_advancing_writes_the_completion_once(self) -> None:
        store, profile, progress = self.progress()
        self.answer(store, profile, "d", THROUGH_A)
        assert progress.advance(progress.member("d")) is True
        assert store.phase_records(profile, "d") == {"A": PhaseRecord(0, config.PHASE_A_STREAK)}
        # Nothing further to record until the next bar is met.
        assert progress.advance(progress.member("d")) is False

    def test_the_next_phase_starts_with_no_evidence_of_its_own(self) -> None:
        store, profile, progress = self.progress()
        self.answer(store, profile, "d", THROUGH_A)
        progress.advance(progress.member("d"))
        member = progress.member("d")
        assert (member.phase, member.evidence) == (RampUpPhase.B, ())

    def test_the_phases_are_measured_over_disjoint_stretches(self) -> None:
        # Read cumulatively, one run of twenty would satisfy Phase A's ten and
        # Phase B's twenty at once and the ramp-up would be a third shorter.
        store, profile, progress = self.progress()
        self.answer(store, profile, "d", "." * config.PHASE_B_ATTEMPTS)
        progress.advance(progress.member("d"))
        assert progress.member("d").phase is RampUpPhase.B
        assert progress.advance(progress.member("d")) is False

    def test_a_completion_survives_the_window_rolling_past_its_evidence(self) -> None:
        # The defect this design exists for. `key_attempts` is a 200-row window
        # that forgets, so a re-derived phase sent a child who had answered a key
        # hundreds of times back to Phase A -- and, since the loop will not
        # introduce during a ramp-up, could lock the curriculum for good.
        store, profile, progress = self.progress()
        self.answer(store, profile, "d", THROUGH_A)
        progress.advance(progress.member("d"))
        self.answer(store, profile, "d", THROUGH_B)
        progress.advance(progress.member("d"))
        assert progress.member("d").phase is RampUpPhase.C
        # Well past ATTEMPT_WINDOW, at an accuracy that never meets Phase C.
        self.answer(store, profile, "d", ("." * 4 + "x") * 60)
        assert len(store.window_attempts(profile, "d")) == config.ATTEMPT_WINDOW
        assert progress.member("d").phase is RampUpPhase.C
        through_b = config.PHASE_A_STREAK + config.PHASE_B_ATTEMPTS
        assert store.phase_records(profile, "d") == {
            "A": PhaseRecord(0, config.PHASE_A_STREAK),
            "B": PhaseRecord(config.PHASE_A_STREAK, through_b),
            "C": PhaseRecord(through_b),
        }

    def test_a_finished_member_stays_finished_after_a_bad_patch(self) -> None:
        # The stickiness the old in-memory `done` flag had: a member that met the
        # bar keeps being prompted while its partner catches up, and must not
        # un-finish, or a pair step's ramp-up could never end.
        store, profile, progress = self.progress()
        for pattern in (THROUGH_A, THROUGH_B, THROUGH_C):
            self.answer(store, profile, "d", pattern)
            progress.advance(progress.member("d"))
        assert progress.member("d").phase is None
        self.answer(store, profile, "d", "x" * 20)
        assert progress.member("d").phase is None

    def test_a_step_ends_only_when_every_member_is_done(self) -> None:
        store, profile, progress = self.progress()
        for name in ("d", "k"):
            for pattern in (THROUGH_A, THROUGH_B, THROUGH_C):
                self.answer(store, profile, name, pattern)
                progress.advance(progress.member(name))
            if name == "d":
                assert progress.step_phase(["d", "k"]) is RampUpPhase.A
        assert progress.step_phase(["d", "k"]) is None

    def test_the_least_advanced_member_sets_the_phase(self) -> None:
        store, profile, progress = self.progress()
        self.answer(store, profile, "d", THROUGH_A)
        progress.advance(progress.member("d"))
        self.answer(store, profile, "k", "..")
        assert progress.step_phase(["d", "k"]) is RampUpPhase.A

    def test_a_member_whose_step_has_not_reached_its_phase_is_not_judged(self) -> None:
        # alpha-plan #12j, O1. `d` passed Phase A and its partner has not, so
        # Phase B has not begun for it: whatever it answers while it waits is
        # evidence for nothing.
        store, profile, progress = self.progress()
        self.answer(store, profile, "d", THROUGH_A)
        assert progress.advance(progress.member("d")) is True
        for mark in THROUGH_B + THROUGH_C:
            store.upsert_key_stat(profile, "d", mark == ".")
            store.append_attempt(profile, "d", mark == ".")
        waiting = progress.member("d")
        assert (waiting.phase, waiting.begun, waiting.evidence) == (RampUpPhase.B, False, ())
        assert progress.advance(waiting) is False
        assert store.phase_records(profile, "d") == {"A": PhaseRecord(0, config.PHASE_A_STREAK)}
        # When the step gets there, the phase starts at the attempts it has now.
        begun = progress.begin(waiting)
        assert (begun.begun, begun.evidence) == (True, ())
        assert store.phase_records(profile, "d")["B"] == PhaseRecord(waiting.attempts)
        assert progress.member("d").evidence == ()

    def test_evidence_reads_are_bounded(self) -> None:
        # A keypress must not pull the whole 200-row window back out of SQLite.
        store, profile, progress = self.progress()
        self.answer(store, profile, "d", "." * 199 + "x")
        assert len(progress.member("d").evidence) == rampup.EVIDENCE_ROWS


def assert_returns_home(layout: Layout, prompts: tuple[str, ...]) -> None:
    """ADR-024 property 2, as the generator actually promises it.

    Checked per hand, and only for a hand these prompts contain a home key for.
    That is the guarantee: a hand the inventory cannot bring home is one the
    invariant says nothing about -- a non-Stage-0 Phase A for a solo reach key is
    `w` and the other hand's anchor, and ADR-024 specifies repetition there.
    Every anchored phase, and all of Stage 0, carries the home key and is bound.
    """
    guarded = {
        base_key(layout, prompt).side
        for prompt in prompts
        if base_key(layout, prompt).row == HOME_ROW
    }
    off_home: set[str] = set()
    for prompt in prompts:
        key = base_key(layout, prompt)
        if key.row == HOME_ROW:
            off_home.discard(key.side)
            continue
        if key.side in guarded:
            assert key.side not in off_home, f"{prompts} reaches twice on {key.side}"
        off_home.add(key.side)


class TestBlockInvariants:
    """ADR-024 properties 1, 2 and 5, over generated blocks rather than one example."""

    def cycle_blocks(self, seed: int, *, solo: bool) -> list[tuple[Layout, tuple[str, ...]]]:
        """Every cycle block of a few steps, at several points in the ramp-up.

        Phase C and steady-state blocks are excluded: their content is sampled
        from corpus bigrams, where `ff` is a word's own double letter and a hand
        does reach twice in a row. These invariants are the cycle's.
        """
        layout = build_en()
        source = FixedListSource(EN_WORDS)
        steps = introduction_sequence(layout, source)
        chosen = [s for s in steps if (len(s.keys) == 1) == solo][:4]
        assert chosen, "no steps of the requested shape"
        produced: list[tuple[Layout, tuple[str, ...]]] = []
        for step in chosen:
            fixture = Fixture(layout, source, active="fjruvmdk", seed=seed)
            fixture.generator.begin_step(step)
            for _ in range(6):
                ramp = fixture.generator.ramp_up
                if ramp is None or ramp.phase is RampUpPhase.C:
                    break
                block = fixture.generator.next_block()
                produced.append((layout, block.prompts))
                fixture.answer(block.prompts)
        assert produced, "no cycle blocks were generated"
        return produced

    @pytest.mark.parametrize("solo", [False, True])
    @pytest.mark.parametrize("seed", range(8))
    def test_no_prompt_ever_follows_itself(self, seed: int, solo: bool) -> None:
        for _, prompts in self.cycle_blocks(seed, solo=solo):
            assert [a for a, b in pairwise(prompts) if a == b] == []

    @pytest.mark.parametrize("solo", [False, True])
    @pytest.mark.parametrize("seed", range(8))
    def test_a_hand_returns_home_between_two_reaches(self, seed: int, solo: bool) -> None:
        # ADR-027 § The Anchor Gate depends on this: with it, first-press accuracy
        # on `f` is return-to-anchor accuracy whatever order the units come in.
        # Solo steps are parametrised in because the borrowed other-hand unit was
        # introduced here, and a property test blind to solo steps could not see
        # that pairing it with the member broke exactly this.
        for layout, prompts in self.cycle_blocks(seed, solo=solo):
            assert_returns_home(layout, prompts)

    @pytest.mark.parametrize("seed", range(4))
    def test_a_hand_left_off_home_returns_in_the_next_block(self, seed: int) -> None:
        # The hands do not go home because a block ended. Resetting that state per
        # block let the first prompt of a block reach again on a hand already off
        # home -- invisible to any single-block assertion.
        layout = build_en()
        fixture = Fixture(layout, FixedListSource(EN_WORDS), active="fjruvmdk", seed=seed)
        fixture.generator.begin_step(make_step(layout, "e"))
        # Past Phase A, whose solo inventory has no left-hand home key to return
        # to and so guards nothing (ADR-024's pure repetition).
        fixture.answer(("e",) * config.PHASE_A_STREAK)
        blocks: list[tuple[str, ...]] = []
        for _ in range(4):
            ramp = fixture.generator.ramp_up
            if ramp is None or ramp.phase is RampUpPhase.C:
                break
            block = fixture.generator.next_block()
            blocks.append(block.prompts)
            fixture.answer(block.prompts)
        assert len(blocks) > 1, "needs at least two blocks to say anything about the boundary"
        assert_returns_home(layout, tuple(prompt for prompts in blocks for prompt in prompts))

    def test_the_inventory_never_grows_beyond_the_step_and_its_anchors(self) -> None:
        # Property 4: variability comes from order and direction, not from new
        # content. Anything else would be interference this ADR did not buy.
        layout = build_en()
        fixture = Fixture(layout, FixedListSource(EN_WORDS), active="fjruvm", seed=3)
        fixture.generator.begin_step(make_step(layout, "d"))
        assert set(fixture.generator.next_block().prompts) == {"d", "j"}

    def test_both_directions_of_a_unit_are_used(self) -> None:
        # The point of varying direction: `r f` is the return that `f r` leaves
        # owed, so both forms appear over a long enough stretch.
        layout = build_en()
        fixture = Fixture(layout, FixedListSource(EN_WORDS), active="fjruvmdk", seed=1)
        fixture.generator.begin_step(make_step(layout, "e"))
        fixture.answer(("e",) * config.PHASE_A_STREAK)
        seen: set[tuple[str, ...]] = set()
        for _ in range(6):
            block = fixture.generator.next_block()
            seen.update(unit for unit in block.units if set(unit) == {"d", "e"})
            fixture.answer(block.prompts)
        assert seen == {("d", "e"), ("e", "d")}

    @pytest.mark.parametrize("seed", range(8))
    def test_no_hand_is_given_a_long_run_of_its_own(self, seed: int) -> None:
        # The shuffle must not clump. A block emitting every left-hand prompt and
        # then every right-hand one satisfies the counts, the no-repeat rule and
        # the return invariant, and is exactly what ADR-028's L-R interleave
        # exists to prevent -- so the run length is asserted directly.
        for layout, prompts in self.cycle_blocks(seed, solo=False):
            sides = [base_key(layout, prompt).side for prompt in prompts]
            longest = run = 1
            for earlier, later in pairwise(sides):
                run = run + 1 if earlier == later else 1
                longest = max(longest, run)
            # Four, not two: a unit is two prompts on one hand, so two same-hand
            # units next to each other is the most the shuffle can produce. The
            # regression this guards against is a block of twenty left-hand
            # prompts followed by twenty right-hand ones, which satisfies the
            # counts, the no-repeat rule and the return invariant alike.
            assert longest <= 4, f"{prompts} keeps one hand for {longest} prompts"
