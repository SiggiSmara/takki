import math
import random
from datetime import datetime, timedelta
from statistics import median

import pytest

from takki import config
from takki.lesson.key_state import (
    CONFIDENCE_Z,
    Evidence,
    KeyState,
    KeyStates,
    KnownCriterion,
    accuracy_bound,
    key_speed,
    qualifies,
    weigh,
)
from takki.persistence import Attempt, Store, WindowStats
from tests.fakes.fake_store import FakeStore

DAY1 = "2026-01-01T10:00:00+00:00"
DAY2 = "2026-01-02T10:00:00+00:00"
HALF_LIFE = config.EVIDENCE_HALF_LIFE_DAYS


def later(stamp: str, days: float) -> str:
    return (datetime.fromisoformat(stamp) + timedelta(days=days)).isoformat(timespec="seconds")


def stocked(store: Store, profile_id: int, key_char: str, *, correct: int, wrong: int) -> None:
    """Practise a key over two calendar days, correct attempts first."""
    for i in range(correct):
        store.append_attempt(profile_id, key_char, True, DAY1 if i % 2 == 0 else DAY2)
    for i in range(wrong):
        store.append_attempt(profile_id, key_char, False, DAY1 if i % 2 == 0 else DAY2)


def window(attempts: int, correct: int, days: int, *, kept: float = 1.0) -> Evidence:
    # `kept` is the share of its weight each press still has: 1.0 is a window
    # practised just now, 0.5 one that is a half-life old.
    return Evidence(attempts, days, weight=attempts * kept, correct=correct * kept)


def wilson(correct: float, presses: float) -> float:
    """The lower bound written out again, so the tests do not read it off the code under test."""
    p = correct / presses
    z2 = CONFIDENCE_Z**2
    return (
        p
        + z2 / (2 * presses)
        - CONFIDENCE_Z * math.sqrt(p * (1 - p) / presses + z2 / (4 * presses**2))
    ) / (1 + z2 / presses)


class TestKnownCriterion:
    def test_compiled_defaults_are_adr_027s_floors(self) -> None:
        criterion = KnownCriterion()
        assert criterion.min_attempts == config.KNOWN_MIN_ATTEMPTS == 90
        assert criterion.min_accuracy == config.KNOWN_MIN_ACCURACY == 0.90
        assert criterion.min_distinct_days == config.KNOWN_MIN_DISTINCT_DAYS == 2

    def test_the_half_life_and_the_speed_ratio_are_in_config(self) -> None:
        assert config.EVIDENCE_HALF_LIFE_DAYS == 30.0
        assert config.KNOWN_MAX_LATENCY_RATIO == 2.0

    def test_ninety_percent_of_ninety_is_no_longer_known(self) -> None:
        # The case the bound is for: 81 of 90 met the old raw test, and its
        # lower bound is 0.864.
        assert 81 / 90 >= config.KNOWN_MIN_ACCURACY
        assert not qualifies(window(90, 81, 2))

    # ADR-027's table: the fewest correct presses that reach each bar.
    @pytest.mark.parametrize(
        ("presses", "bar", "fewest"),
        [(90, 0.90, 84), (200, 0.90, 185), (25, 0.95, 25), (50, 0.95, 50), (90, 0.95, 88)],
    )
    def test_the_accuracy_test_is_the_lower_bound(
        self, presses: int, bar: float, fewest: int
    ) -> None:
        criterion = KnownCriterion(min_attempts=presses, min_accuracy=bar)
        assert wilson(fewest, presses) >= bar > wilson(fewest - 1, presses)
        assert qualifies(window(presses, fewest, 2), criterion)
        assert not qualifies(window(presses, fewest - 1, 2), criterion)

    def test_attempts_below_floor_alone(self) -> None:
        assert qualifies(window(89, 89, 2)) is False
        assert qualifies(window(90, 90, 2)) is True

    def test_distinct_days_below_floor_alone(self) -> None:
        assert qualifies(window(100, 100, 1)) is False
        assert qualifies(window(100, 100, 2)) is True

    def test_no_attempts_is_not_known(self) -> None:
        assert not qualifies(window(0, 0, 0))

    def test_criterion_is_overridable(self) -> None:
        lenient = KnownCriterion(min_attempts=2, min_accuracy=0.5, min_distinct_days=1)
        assert qualifies(window(2, 2, 1), lenient)


class TestAccuracyBound:
    def test_no_evidence_is_a_bound_of_zero(self) -> None:
        assert accuracy_bound(0, 0) == 0.0
        assert accuracy_bound(0.0, 0.0) == 0.0

    @pytest.mark.parametrize("weight", [1e-7, 1e-160, 1e-169, 5e-324])
    def test_a_vanishing_weight_is_no_evidence_and_not_a_crash(self, weight: float) -> None:
        # Found by the review of 2026-10-04: the square of a weight this small
        # is zero, and the bound divided by it.
        assert accuracy_bound(weight, weight) == 0.0

    @pytest.mark.parametrize(
        ("correct", "presses"), [(81, 90), (84, 90), (24, 25), (12.5, 13.25), (3.7, 4.0)]
    )
    def test_it_is_wilsons_lower_bound_on_whole_and_decayed_counts(
        self, correct: float, presses: float
    ) -> None:
        assert math.isclose(accuracy_bound(correct, presses), wilson(correct, presses))


class TestDecay:
    """ADR-027 § Known reads decayed evidence: the accuracy ages, the dose and the days do not."""

    def rows(self, stamps: list[tuple[str, bool]]) -> list[Attempt]:
        return [Attempt(correct=correct, attempted_at=stamp) for stamp, correct in stamps]

    def test_a_press_halves_in_weight_every_half_life(self) -> None:
        rows = self.rows([(DAY1, True)])
        stats = WindowStats(1, 1, 1)
        for half_lives in (0, 1, 2, 3.5):
            evidence = weigh(
                stats, rows, datetime.fromisoformat(later(DAY1, half_lives * HALF_LIFE)), HALF_LIFE
            )
            assert math.isclose(evidence.weight, 0.5**half_lives)
            assert math.isclose(evidence.correct, 0.5**half_lives)

    def test_old_and_new_presses_are_weighed_each_by_its_own_age(self) -> None:
        now = later(DAY1, HALF_LIFE)
        rows = self.rows([(DAY1, False), (DAY1, True), (now, True)])
        evidence = weigh(WindowStats(3, 2, 2), rows, datetime.fromisoformat(now), HALF_LIFE)
        assert math.isclose(evidence.weight, 0.5 + 0.5 + 1.0)
        assert math.isclose(evidence.correct, 0.5 + 1.0)

    def test_the_dose_and_the_days_do_not_decay(self) -> None:
        rows = self.rows([(DAY1, True)] * 90)
        evidence = weigh(
            WindowStats(90, 90, 2), rows, datetime.fromisoformat(later(DAY1, 400)), HALF_LIFE
        )
        assert (evidence.attempts, evidence.distinct_days) == (90, 2)
        assert evidence.weight < 0.01

    def test_a_press_stamped_in_the_future_weighs_one(self) -> None:
        # The clock was corrected backwards after the press was written.
        rows = self.rows([(later(DAY1, 5), True)])
        evidence = weigh(WindowStats(1, 1, 1), rows, datetime.fromisoformat(DAY1), HALF_LIFE)
        assert evidence.weight == 1.0

    def test_the_half_life_is_the_constructors_to_set(self) -> None:
        store = FakeStore()
        p = store.create_profile("Alice")
        store.upsert_key_stat(p.id, "a", True, DAY1)
        stocked(store, p.id, "a", correct=90, wrong=0)
        away = later(DAY2, 60)
        # 90 clean presses keep their bound for a little over three half-lives.
        assert KeyStates(store, p.id, now=lambda: away).state("a") is KeyState.KNOWN
        short = KeyStates(store, p.id, now=lambda: away, half_life_days=10.0)
        assert short.state("a") is KeyState.ACTIVE

    def test_rows_stamped_decades_ago_read_as_no_evidence(self) -> None:
        # A boot with a dead clock stamps rows in 1980. Their weight is far
        # under anything a float can square, and the profile must still open.
        store = FakeStore()
        p = store.create_profile("Alice")
        store.upsert_key_stat(p.id, "a", True, "1980-01-01T00:00:00+00:00")
        for _ in range(90):
            store.append_attempt(p.id, "a", True, "1980-01-01T00:00:00+00:00")
        states = KeyStates(store, p.id, now=lambda: "2026-10-04T00:00:00+00:00")
        assert 0 < states.evidence("a").weight < 1e-100
        assert states.known_keys() == set()

    # The grid is the case the change is for: windows at and above the bar,
    # read fresh and after a weekend, a month, a summer and a year away.
    @pytest.mark.parametrize(
        ("presses", "correct"), [(90, 84), (90, 90), (150, 144), (200, 196), (200, 200)]
    )
    def test_known_lapses_with_time_away_and_never_comes_back_by_waiting(
        self, presses: int, correct: int
    ) -> None:
        verdicts = [
            qualifies(window(presses, correct, 2, kept=0.5 ** (days / HALF_LIFE)))
            for days in (0, 3, 30, 75, 365)
        ]
        assert verdicts[0] is True
        assert verdicts[-1] is False
        assert verdicts == sorted(verdicts, reverse=True)

    def test_a_long_weekend_costs_nothing(self) -> None:
        assert qualifies(window(90, 84, 2, kept=0.5 ** (3 / HALF_LIFE)))

    def test_a_key_that_is_only_just_known_lapses_after_about_a_half_life(self) -> None:
        assert qualifies(window(90, 85, 2, kept=0.5 ** (0.9)))
        assert not qualifies(window(90, 85, 2, kept=0.5 ** (1.1)))

    def test_a_few_correct_presses_bring_a_lapsed_key_back(self) -> None:
        # 200 presses at 98%, five half-lives old: the history still counts for
        # six presses' worth, so the key returns sooner than a key with no
        # history at all would reach the bar.
        lapsed = window(200, 196, 2, kept=0.5**5)
        assert not qualifies(lapsed)

        def presses_to_return(weight: float, correct: float) -> int:
            return next(
                extra
                for extra in range(1, 50)
                if wilson(correct + extra, weight + extra) >= config.KNOWN_MIN_ACCURACY
            )

        with_history = presses_to_return(lapsed.weight, lapsed.correct)
        from_nothing = presses_to_return(0.0, 0.0)
        assert 1 < with_history < from_nothing

        def after(extra: int) -> Evidence:
            return Evidence(200 + extra, 2, lapsed.weight + extra, lapsed.correct + extra)

        assert qualifies(after(with_history))
        assert not qualifies(after(with_history - 1))


class TestKeyStateDerivation:
    def test_unseen_key_has_no_row(self) -> None:
        store = FakeStore()
        p = store.create_profile("Alice")
        assert KeyStates(store, p.id).state("a") is KeyState.UNSEEN

    def test_a_practised_key_is_active(self) -> None:
        store = FakeStore()
        p = store.create_profile("Alice")
        store.upsert_key_stat(p.id, "a", True, DAY1)
        store.append_attempt(p.id, "a", True, DAY1)
        assert KeyStates(store, p.id).state("a") is KeyState.ACTIVE

    def test_active_becomes_known_when_the_criterion_is_met(self) -> None:
        store = FakeStore()
        p = store.create_profile("Alice")
        store.upsert_key_stat(p.id, "a", True, DAY1)
        states = KeyStates(store, p.id, now=lambda: DAY2)
        stocked(store, p.id, "a", correct=89, wrong=0)
        assert states.state("a") is KeyState.ACTIVE
        store.append_attempt(p.id, "a", True, DAY2)
        assert states.state("a") is KeyState.KNOWN

    def test_known_is_recomputed_not_latched(self) -> None:
        store = FakeStore()
        p = store.create_profile("Alice")
        store.upsert_key_stat(p.id, "a", True, DAY1)
        states = KeyStates(store, p.id, now=lambda: DAY2)
        stocked(store, p.id, "a", correct=90, wrong=0)
        assert states.state("a") is KeyState.KNOWN
        # Three misses leave the bound over the bar; ten more do not.
        stocked(store, p.id, "a", correct=0, wrong=3)
        assert states.state("a") is KeyState.KNOWN
        stocked(store, p.id, "a", correct=0, wrong=10)
        assert states.state("a") is KeyState.ACTIVE

    def test_known_lapses_while_the_app_is_closed_and_a_few_presses_restore_it(self) -> None:
        # Nothing is written between the two readings: only the clock moves.
        store = FakeStore()
        p = store.create_profile("Alice")
        store.upsert_key_stat(p.id, "a", True, DAY1)
        stocked(store, p.id, "a", correct=90, wrong=0)
        assert KeyStates(store, p.id, now=lambda: later(DAY2, 3)).state("a") is KeyState.KNOWN
        back = later(DAY2, 5 * HALF_LIFE)
        returned = KeyStates(store, p.id, now=lambda: back)
        assert returned.state("a") is KeyState.ACTIVE
        for _ in range(7):
            store.append_attempt(p.id, "a", True, back)
        assert returned.state("a") is KeyState.KNOWN

    def test_a_row_with_no_window_rows_is_active_not_known(self) -> None:
        store = FakeStore()
        p = store.create_profile("Alice")
        store.upsert_key_stat(p.id, "a", True, DAY1)
        assert KeyStates(store, p.id).state("a") is KeyState.ACTIVE

    def test_states_are_per_profile(self) -> None:
        store = FakeStore()
        alice = store.create_profile("Alice")
        bob = store.create_profile("Bob")
        store.upsert_key_stat(alice.id, "a", True, DAY1)
        stocked(store, alice.id, "a", correct=90, wrong=0)
        assert KeyStates(store, alice.id, now=lambda: DAY2).state("a") is KeyState.KNOWN
        assert KeyStates(store, bob.id, now=lambda: DAY2).state("a") is KeyState.UNSEEN


class TestRollingWindow:
    def test_the_cap_discards_oldest_attempts(self) -> None:
        store = FakeStore(window_cap=100)
        p = store.create_profile("Alice")
        store.upsert_key_stat(p.id, "a", False, DAY1)
        for _ in range(20):
            store.append_attempt(p.id, "a", False, DAY1)
        for _ in range(90):
            store.append_attempt(p.id, "a", True, DAY2)
        stats = store.window_stats(p.id, "a")
        assert stats == WindowStats(attempt_count=100, correct_count=90, distinct_days=2)

    def test_the_cap_can_carry_a_key_into_known(self) -> None:
        # At the cap, one clean press does two things: it adds a correct row
        # and it evicts the oldest failure. Both readings are taken at one
        # instant with every row stamped at it, so nothing has decayed and the
        # only thing that changes is which rows the window holds.
        store = FakeStore(window_cap=100)
        p = store.create_profile("Alice")
        store.upsert_key_stat(p.id, "a", False, DAY1)
        states = KeyStates(store, p.id, KnownCriterion(min_distinct_days=1), now=lambda: DAY2)
        for _ in range(8):
            store.append_attempt(p.id, "a", False, DAY2)
        for _ in range(92):
            store.append_attempt(p.id, "a", True, DAY2)
        assert store.window_stats(p.id, "a") == WindowStats(100, 92, 1)
        assert states.state("a") is KeyState.ACTIVE
        store.append_attempt(p.id, "a", True, DAY2)
        assert store.window_stats(p.id, "a") == WindowStats(100, 93, 1)
        assert states.state("a") is KeyState.KNOWN

    def test_default_cap_is_the_configured_window(self) -> None:
        store = FakeStore()
        p = store.create_profile("Alice")
        for _ in range(config.ATTEMPT_WINDOW + 5):
            store.append_attempt(p.id, "a", True, DAY1)
        assert store.window_stats(p.id, "a").attempt_count == config.ATTEMPT_WINDOW


class TestKeyEnumeration:
    def test_no_active_keys_on_a_fresh_profile(self) -> None:
        store = FakeStore()
        p = store.create_profile("Alice")
        assert KeyStates(store, p.id).active_keys() == set()
        assert KeyStates(store, p.id).known_keys() == set()

    def test_active_keys_are_every_key_with_a_row(self) -> None:
        store = FakeStore()
        p = store.create_profile("Alice")
        for char in "fjdk":
            store.upsert_key_stat(p.id, char, True, DAY1)
        assert KeyStates(store, p.id).active_keys() == {"f", "j", "d", "k"}

    def test_known_keys_are_the_subset_meeting_the_criterion(self) -> None:
        store = FakeStore()
        p = store.create_profile("Alice")
        for char in "fjd":
            store.upsert_key_stat(p.id, char, True, DAY1)
        stocked(store, p.id, "f", correct=90, wrong=0)
        stocked(store, p.id, "j", correct=95, wrong=5)
        stocked(store, p.id, "d", correct=90, wrong=10)  # 0.9 raw, bound 0.866
        states = KeyStates(store, p.id, now=lambda: DAY2)
        assert states.known_keys() == {"f", "j"}
        assert states.active_keys() == {"f", "j", "d"}

    def test_enumeration_is_per_profile(self) -> None:
        store = FakeStore()
        alice = store.create_profile("Alice")
        bob = store.create_profile("Bob")
        store.upsert_key_stat(alice.id, "f", True, DAY1)
        store.upsert_key_stat(bob.id, "j", True, DAY1)
        assert KeyStates(store, alice.id).active_keys() == {"f"}
        assert KeyStates(store, bob.id).active_keys() == {"j"}


RATIO = config.KNOWN_MAX_LATENCY_RATIO
BUMP = ("f", "j")


def timed(ms: float | None, *, correct: bool = True, timeouts: int = 0) -> Attempt:
    """One first press, `ms` after its letter was sent (ADR-011's `latency_ms`)."""
    return Attempt(
        correct=correct,
        attempted_at=DAY2,
        latency_ms=None if ms is None else round(ms),
        timeouts=timeouts,
    )


def practised(
    store: Store,
    profile_id: int,
    key_char: str,
    ms: float | None,
    *,
    presses: int = config.KNOWN_MIN_ATTEMPTS,
    timeouts: int = 0,
) -> None:
    """`presses` correct answers over two days, each `ms` after its letter was sent."""
    row = timed(ms, timeouts=timeouts)
    store.upsert_key_stat(profile_id, key_char, True, DAY1)
    for i in range(presses):
        store.append_attempt(
            profile_id,
            key_char,
            True,
            DAY1 if i % 2 == 0 else DAY2,
            row.latency_ms,
            timeouts=timeouts,
        )


def speeds(medians: dict[str, float]) -> KeyStates:
    """A profile whose keys all meet Known's floors and answer at these speeds."""
    store = FakeStore()
    profile = store.create_profile("Alice")
    for key_char, ms in medians.items():
        practised(store, profile.id, key_char, ms)
    return KeyStates(store, profile.id, now=lambda: DAY2, bump_keys=BUMP)


class TestHeld:
    """One read of each window for everything asked at a block boundary."""

    def test_inside_a_hold_a_window_is_read_once_and_outside_it_every_time(self) -> None:
        reads: list[str] = []

        class CountingStore(FakeStore):
            def window_attempts(
                self, profile_id: int, key_char: str, limit: int | None = None
            ) -> list[Attempt]:
                reads.append(key_char)
                return super().window_attempts(profile_id, key_char, limit)

        store = CountingStore()
        profile = store.create_profile("Alice")
        for name in "dfj":
            practised(store, profile.id, name, 1000)
        states = KeyStates(store, profile.id, now=lambda: DAY2, bump_keys=BUMP)
        with states.held():
            assert states.known_keys() == set("dfj")
            assert states.slow_keys() == set()
            assert states.evidence("d").attempts == config.KNOWN_MIN_ATTEMPTS
            assert states.speed_baseline("d") == 1000
        assert reads == ["d", "f", "j"]
        states.known_keys()
        states.evidence("d")
        assert reads == ["d", "f", "j", "d", "f", "j", "d"]

    def test_a_hold_ends_when_it_is_left(self) -> None:
        # Known is recomputed on every query (ADR-027), and a hold is only the
        # one block boundary: a press written after it is seen at once.
        store = FakeStore()
        profile = store.create_profile("Alice")
        practised(store, profile.id, "d", None, presses=config.KNOWN_MIN_ATTEMPTS - 1)
        states = KeyStates(store, profile.id, now=lambda: DAY2)
        with states.held(), states.held():
            assert states.known_keys() == set()
        store.append_attempt(profile.id, "d", True, DAY2)
        assert states.known_keys() == {"d"}


class TestKeySpeed:
    """ADR-027 § Known has a speed term: how one key's speed is read."""

    def test_it_is_the_median_time_from_the_letter_being_sent(self) -> None:
        rows = [timed(ms) for ms in (900, 1000, 5000)] * 4
        assert key_speed(rows) == 1000

    def test_it_needs_no_letter_length(self) -> None:
        # The review of 2026-10-04: a child who answers every letter before it
        # ends never lets one finish, so no length is ever known, and their
        # answers must still be read. The signed column is not the speed term's.
        early = [
            Attempt(correct=True, attempted_at=DAY2, latency_ms=700, after_letter_ms=after)
            for after in (None, -500)
        ] * config.SPEED_MIN_SAMPLE
        assert key_speed(early) == 700

    def test_only_the_latest_sample_is_read(self) -> None:
        was_slow = [timed(4000)] * 60 + [timed(1000)] * config.SPEED_SAMPLE
        got_slow = [timed(1000)] * 60 + [timed(4000)] * config.SPEED_SAMPLE
        assert (key_speed(was_slow), key_speed(got_slow)) == (1000, 4000)

    def test_too_few_timed_answers_is_no_speed_at_all(self) -> None:
        untimed = [timed(None)] * 50
        assert key_speed(untimed + [timed(1000)] * (config.SPEED_MIN_SAMPLE - 1)) is None
        assert key_speed(untimed + [timed(1000)] * config.SPEED_MIN_SAMPLE) == 1000

    def test_a_wrong_press_is_never_read(self) -> None:
        # A guess made without listening is fast. If it were read, this key
        # would look three times as fast as the child is on it.
        rows = [timed(300, correct=False)] * 20 + [timed(2500)] * config.SPEED_MIN_SAMPLE
        assert key_speed(rows) == 2500

    def test_an_answer_that_sat_through_a_timeout_counts_as_the_slowest(self) -> None:
        # It has no latency, because the letter was spoken again. Left out, the
        # child who needs twelve seconds to find a key would have no slow answers.
        waited = timed(None, timeouts=1)
        assert key_speed([timed(1000)] * 16 + [waited] * 14) == 1000
        assert key_speed([timed(1000)] * 14 + [waited] * 16) == math.inf
        assert key_speed([waited] * config.SPEED_MIN_SAMPLE) == math.inf


class TestSpeedTerm:
    """ADR-027 § Known has a speed term: a ratio against the child's other practised keys."""

    def test_a_key_at_the_ratio_is_known_and_one_just_past_it_is_not(self) -> None:
        states = speeds({"f": 1000, "j": 1000, "d": RATIO * 1000, "k": RATIO * 1000 + 1})
        assert states.known_keys() == {"f", "j", "d"}
        assert states.slow_keys() == {"k"}
        assert states.state("k") is KeyState.ACTIVE

    def test_one_hunted_key_is_the_only_one_held_back(self) -> None:
        medians = dict.fromkeys("fjruvmdksl", 1100.0) | {"v": 2600.0}
        states = speeds(medians)
        assert states.slow_keys() == {"v"}
        assert states.known_keys() == set(medians) - {"v"}

    def test_the_bump_keys_have_no_speed_term(self) -> None:
        # Something has to be the root of the comparison.
        states = speeds({"f": 9000, "j": 1000, "d": 1000, "k": 1000, "s": 1000})
        assert states.slow_keys() == set()
        assert states.speed_baseline("f") is None

    def test_the_bump_keys_are_in_the_pool_before_they_meet_the_floors(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Alice")
        for name in BUMP:
            practised(store, profile.id, name, 1000, presses=config.SPEED_MIN_SAMPLE)
        practised(store, profile.id, "d", RATIO * 1000 + 1)
        states = KeyStates(store, profile.id, now=lambda: DAY2, bump_keys=BUMP)
        assert states.speed_baseline("d") == 1000
        assert states.slow_keys() == {"d"}

    def test_a_key_that_has_not_met_the_floors_is_not_in_the_pool(self) -> None:
        # Three half-practised slow keys must not lift the baseline: with them
        # in the pool its median would be 3000 and `d` would pass.
        store = FakeStore()
        profile = store.create_profile("Alice")
        for name in BUMP:
            practised(store, profile.id, name, 1000)
        for name in "xyz":
            practised(store, profile.id, name, 3000, presses=config.KNOWN_MIN_ATTEMPTS - 1)
        practised(store, profile.id, "d", 2500)
        states = KeyStates(store, profile.id, now=lambda: DAY2, bump_keys=BUMP)
        assert states.speed_baseline("d") == 1000
        assert states.slow_keys() == {"d"}

    def test_a_key_is_never_in_its_own_pool(self) -> None:
        states = speeds({"f": 1000, "j": 1000, "d": 5000})
        assert states.speed_baseline("d") == 1000

    def test_a_slow_key_that_meets_the_floors_stays_in_the_others_pool(self) -> None:
        # The case the pool was chosen for (alpha-plan #12f, the spike of
        # 2026-10-04): a child twice as fast on the two bump keys as anywhere
        # else. Judged against `f` and `j` alone nothing would ever be Known.
        # Here the others outvote the bump keys once there are three of them.
        fast_anchors = {"f": 650.0, "j": 650.0}
        two = speeds(fast_anchors | {"r": 1400.0, "u": 1400.0})
        assert two.slow_keys() == {"r", "u"}
        four = speeds(fast_anchors | dict.fromkeys("ruvm", 1400.0))
        assert four.slow_keys() == set()
        assert four.known_keys() == set("fjruvm")
        assert four.speed_baseline("r") == 1400

    def test_a_slower_group_is_held_back_while_it_is_the_minority(self) -> None:
        # The other side of the same rule, and the corner the developer asked
        # to have looked at again for Beta: a hand that is consistently slower.
        left, right = "rvds", "jumkl"
        medians = {"f": 1100.0} | dict.fromkeys(left, 2400.0) | dict.fromkeys(right, 1100.0)
        assert speeds(medians).slow_keys() == set(left)

    def test_with_nothing_to_compare_against_the_term_is_skipped(self) -> None:
        assert speeds({"d": 9000}).known_keys() == {"d"}
        # Timed keys, but none of them answered often enough to have a speed.
        store = FakeStore()
        profile = store.create_profile("Alice")
        for name in BUMP:
            practised(store, profile.id, name, 1000, presses=config.SPEED_MIN_SAMPLE - 1)
        practised(store, profile.id, "d", 9000)
        states = KeyStates(store, profile.id, now=lambda: DAY2, bump_keys=BUMP)
        assert states.speed_baseline("d") is None
        assert states.known_keys() == {"d"}

    def test_a_key_with_no_timed_answers_of_its_own_is_not_called_slow(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Alice")
        for name in BUMP:
            practised(store, profile.id, name, 1000)
        practised(store, profile.id, "d", None)
        states = KeyStates(store, profile.id, now=lambda: DAY2, bump_keys=BUMP)
        assert states.known_keys() == {"f", "j", "d"}

    def test_a_key_that_sat_through_timeouts_is_slow_with_no_latency_at_all(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Alice")
        for name in BUMP:
            practised(store, profile.id, name, 1000)
        practised(store, profile.id, "d", None, timeouts=1)
        states = KeyStates(store, profile.id, now=lambda: DAY2, bump_keys=BUMP)
        assert states.slow_keys() == {"d"}

    def test_a_key_short_of_a_floor_is_not_called_slow(self) -> None:
        # `slow_keys` is the keys that *only* speed keeps from Known.
        store = FakeStore()
        profile = store.create_profile("Alice")
        for name in BUMP:
            practised(store, profile.id, name, 1000)
        practised(store, profile.id, "d", 9000, presses=config.KNOWN_MIN_ATTEMPTS - 1)
        states = KeyStates(store, profile.id, now=lambda: DAY2, bump_keys=BUMP)
        assert states.slow_keys() == set()
        assert states.known_keys() == {"f", "j"}

    def test_the_ratio_is_the_constructors_to_set(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Alice")
        for name, ms in (("f", 1000), ("j", 1000), ("d", 1400)):
            practised(store, profile.id, name, ms)
        states = KeyStates(
            store, profile.id, now=lambda: DAY2, bump_keys=BUMP, max_latency_ratio=1.2
        )
        assert states.slow_keys() == {"d"}

    def test_known_agrees_with_the_rule_written_out_again(self) -> None:
        # The rule as the spike had it, over profiles that include what it is
        # for: keys past the ratio, and slower groups on both sides of half.
        def by_the_rule(medians: dict[str, float]) -> set[str]:
            slow = set()
            for name, ms in medians.items():
                pool = [other_ms for other, other_ms in medians.items() if other != name]
                if name not in BUMP and ms > RATIO * median(pool):
                    slow.add(name)
            return slow

        rng = random.Random(12)
        some_slow = all_pass_despite_slow_keys = 0
        for _ in range(40):
            others = rng.sample("ruvmdkslagh", rng.randint(1, 9))
            slow_share = rng.choice((0.0, 0.2, 0.5, 0.8))
            medians = {name: float(rng.randint(600, 1300)) for name in BUMP}
            for name in others:
                base = rng.randint(900, 1300)
                medians[name] = float(
                    base * (rng.choice((2, 3)) if rng.random() < slow_share else 1)
                )
            expected = by_the_rule(medians)
            states = speeds(medians)
            assert states.slow_keys() == expected
            assert states.known_keys() == set(medians) - expected
            some_slow += bool(expected)
            beyond_the_bump_keys = [
                name
                for name in others
                if medians[name] > RATIO * median(medians[bump] for bump in BUMP)
            ]
            all_pass_despite_slow_keys += bool(beyond_the_bump_keys) and not expected
        # Both sides of the rule were actually generated.
        assert some_slow >= 5
        assert all_pass_despite_slow_keys >= 5
