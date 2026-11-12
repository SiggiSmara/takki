"""ADR-024 § The ramp-up restated — the level rule, the one bar, and the recorded runs."""

import pytest

from takki import config
from takki.lesson import rampup
from takki.lesson.rampup import StepLadder
from takki.persistence import Attempt, Introduction, KeyStat, LevelRecord
from tests.fakes.fake_store import FakeStore
from tests.test_drills import Fixture

THROUGH = "." * config.STABLE_ATTEMPTS


def rows(pattern: str, latency_ms: int | None = None) -> list[Attempt]:
    """`.` is correct, `x` is a rejection — one row each, in order."""
    return [
        Attempt(
            correct=mark == ".", attempted_at="2026-09-29T10:00:00+00:00", latency_ms=latency_ms
        )
        for mark in pattern
    ]


def firsts(pattern: str) -> list[bool]:
    return [mark == "." for mark in pattern]


class TestLevelRule:
    def test_eight_of_the_latest_ten(self) -> None:
        right, window = config.LEVEL_UP_CORRECT, config.LEVEL_UP_WINDOW
        assert rampup.level_rule_met(firsts("." * right))
        assert not rampup.level_rule_met(firsts("." * (right - 1)))
        assert rampup.level_rule_met(firsts("x" * (window - right) + "." * right))
        assert not rampup.level_rule_met(firsts("x" * (window - right + 1) + "." * (right - 1)))

    def test_it_is_read_back_from_the_latest_press(self) -> None:
        # #12j O5: the answer depends only on recent presses, so misses long
        # gone neither hold the child back nor are paid off by a long run.
        old_misses = "x" * 20 + "." * config.LEVEL_UP_CORRECT
        assert rampup.level_rule_met(firsts(old_misses))
        recent_misses = "." * 20 + "x" * 3 + "." * 7
        assert not rampup.level_rule_met(firsts(recent_misses))

    def test_a_plain_count_of_right_presses_is_not_enough(self) -> None:
        # ADR-024: a count would move up a child who finds the key half the time.
        half = ".x" * config.LEVEL_UP_CORRECT
        assert not rampup.level_rule_met(firsts(half))

    @pytest.mark.parametrize("pattern", ["", "x", ".x.", "xx" + "." * 5, "." * 7, "xxx......."])
    def test_owed_is_exactly_the_right_presses_that_meet_the_rule(self, pattern: str) -> None:
        owed = rampup.level_owed(firsts(pattern))
        assert rampup.level_rule_met(firsts(pattern + "." * owed))
        assert owed == 1 or not rampup.level_rule_met(firsts(pattern + "." * (owed - 1)))

    def test_owed_is_never_zero(self) -> None:
        assert rampup.level_owed(firsts("." * 20)) == 1


class TestBar:
    def test_thirty_at_the_accuracy_bar(self) -> None:
        assert rampup.bar_met(rows(THROUGH))
        assert not rampup.bar_met(rows(THROUGH[:-1]))
        # 25 of 30 is 83%, under STABLE_MIN_ACCURACY; 26 is 87%.
        assert not rampup.bar_met(rows("." * 25 + "x" * 5))
        assert rampup.bar_met(rows("." * 26 + "x" * 4))

    def test_another_thirty_are_owed_when_the_bar_is_missed(self) -> None:
        missed = rows("." * 24 + "x" * 6)
        assert rampup.bar_owed(missed) == config.STABLE_ATTEMPTS
        assert rampup.bar_owed(rows("." * 10)) == config.STABLE_ATTEMPTS - 10


class TestLatency:
    def test_no_baseline_skips_the_term(self) -> None:
        # Every profile's first days, the bump letters' own step included: a
        # term that failed closed would hold the curriculum behind a
        # measurement that cannot be made.
        assert rampup.bar_met(rows(THROUGH, 9999), None)

    def test_within_the_ratio_passes_and_outside_it_does_not(self) -> None:
        assert rampup.bar_met(rows(THROUGH, 1000), 800.0)
        assert not rampup.bar_met(rows(THROUGH, 2000), 800.0)

    def test_unmeasured_rows_never_fail_the_bar(self) -> None:
        assert rampup.bar_met(rows(THROUGH, None), 800.0)

    def test_the_ratio_is_known_s_own(self) -> None:
        # alpha-plan #12f: one baseline and one ratio for the bar and for Known.
        assert config.STABLE_MAX_LATENCY_RATIO == config.KNOWN_MAX_LATENCY_RATIO == 2.0
        at_the_bar = round(800 * config.STABLE_MAX_LATENCY_RATIO)
        assert rampup.bar_met(rows(THROUGH, at_the_bar), 800.0)
        assert not rampup.bar_met(rows(THROUGH, at_the_bar + 1), 800.0)

    def test_the_term_reads_the_time_from_the_sending_and_no_letter_length(self) -> None:
        # alpha-plan #12f: most answers come before the letter has ended, and a
        # child who never lets one end has no letter length at all.
        answered_early = [
            Attempt(
                correct=True,
                attempted_at="2026-09-29T10:00:00+00:00",
                latency_ms=1000,
                after_letter_ms=after,
            )
            for after in [-200, None] * (config.STABLE_ATTEMPTS // 2)
        ]
        assert rampup.bar_met(answered_early, 800.0)
        assert not rampup.bar_met(answered_early, 1000.0 / config.STABLE_MAX_LATENCY_RATIO - 1)

    def test_answers_that_sat_through_a_timeout_fail_the_term(self) -> None:
        waited = [
            Attempt(correct=True, attempted_at="2026-09-29T10:00:00+00:00", timeouts=1)
            for _ in THROUGH
        ]
        assert not rampup.bar_met(waited, 800.0)
        assert rampup.bar_met(waited, None)

    def test_a_fast_wrong_press_does_not_make_the_stretch_fast(self) -> None:
        stretch = rows("." * 27, 2000) + rows("xxx", 300)
        assert not rampup.bar_met(stretch, 800.0)


class TestRecordedLevels:
    """The durable half: a level reached and a rule met are events, not re-derivations."""

    def test_a_met_rule_survives_the_window_rolling_past_its_evidence(self) -> None:
        # `key_attempts` is a window built to forget. A Choose met long ago
        # stays met when the rows that met it are gone.
        fixture = Fixture(active="fj")
        fixture.to_travel("a")
        for _ in range(config.ATTEMPT_WINDOW):
            fixture.store.upsert_key_stat(fixture.profile, "a", False)
            fixture.store.append_attempt(fixture.profile, fixture.session, "a", False)
        fixture.new_session()
        fixture.store.mark_introduced(fixture.profile, ["a"])
        ladder = StepLadder(fixture.store, fixture.profile, fixture.session, [("a", False)])
        ladder.refresh(lambda _: None)
        assert ladder.level == "travel"

    def test_choose_and_travel_are_begun_once_across_sessions(self) -> None:
        # ADR-011: the store would accept a second begin in a later session;
        # the ladder begins them only when it has no record of them.
        fixture = Fixture(active="fj")
        fixture.to_travel("a")
        for _ in range(3):
            fixture.new_session()
            ladder = StepLadder(fixture.store, fixture.profile, fixture.session, [("a", False)])
            ladder.refresh(lambda _: None)
        assert [run[0] for run in fixture.levels("a")] == ["choose", "travel"]

    def test_a_missing_begin_is_written_on_the_next_read(self) -> None:
        # A session that ended between two members' begins: the step is at the
        # highest level either has begun, and the other's begin is written then.
        store = FakeStore()
        profile = store.create_profile("kid").id
        session = store.start_session(profile)
        store.mark_introduced(profile, ["a", "k"])
        store.begin_level(profile, "a", "choose", session, 0)
        ladder = StepLadder(store, profile, session, [("a", False), ("k", False)])
        ladder.refresh(lambda _: None)
        assert ladder.level == "choose"
        assert [r.level for r in store.level_records(profile, "k")] == ["choose"]

    def test_evidence_reads_are_bounded(self) -> None:
        # A keypress must not pull the whole window back out of SQLite.
        fixture = Fixture(active="fj")
        fixture.to_travel("a")
        for _ in range(3 * rampup.EVIDENCE_ROWS):
            fixture.store.upsert_key_stat(fixture.profile, "a", False)
            fixture.store.append_attempt(fixture.profile, fixture.session, "a", False)
        ladder = fixture.generator.ramp_up
        assert ladder is not None
        ladder.refresh(lambda _: None)
        assert len(ladder.states["a"].evidence) == rampup.EVIDENCE_ROWS


class CountingStore(FakeStore):
    def __init__(self) -> None:
        super().__init__()
        self.reads: list[str] = []

    def level_records(self, profile_id: int, key_char: str) -> list[LevelRecord]:
        self.reads.append(f"levels {key_char}")
        return super().level_records(profile_id, key_char)

    def introductions(self, profile_id: int) -> list[Introduction]:
        self.reads.append("introductions")
        return super().introductions(profile_id)

    def key_stats(self, profile_id: int) -> dict[str, KeyStat]:
        self.reads.append("key_stats")
        return super().key_stats(profile_id)


class TestReadsPerPress:
    def test_a_press_that_writes_nothing_reads_each_table_once(self) -> None:
        # #12m session (6)'s review: every counted press of a step letter runs
        # a refresh, on the keypress path, after the cue has played.
        store = CountingStore()
        profile = store.create_profile("kid").id
        session = store.start_session(profile)
        store.mark_introduced(profile, ["a", "k"])
        ladder = StepLadder(store, profile, session, [("a", False), ("k", False)])
        ladder.refresh(lambda _: None)
        store.upsert_key_stat(profile, "a", True)
        store.append_attempt(profile, session, "a", True)
        store.reads.clear()
        ladder.refresh(lambda _: None)
        assert ladder.level == "choose"
        assert sorted(store.reads) == ["introductions", "key_stats", "levels a", "levels k"]
