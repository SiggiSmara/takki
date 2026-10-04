from takki import config
from takki.lesson.attempts import AttemptCounter, PressOutcome
from takki.persistence import Attempt, KeyStat, WindowStats
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_store import FakeStore


class Harness:
    """One profile, one counter, and a wall clock that ticks a minute per keystroke."""

    def __init__(self) -> None:
        self.store = FakeStore()
        self.profile = self.store.create_profile("Alice")
        self.minute = 0
        self.counter = AttemptCounter(self.store, self.profile.id, self.stamp)

    def stamp(self) -> str:
        ts = f"2026-01-01T10:{self.minute:02d}:00+00:00"
        self.minute += 1
        return ts

    def stat(self, key_char: str) -> KeyStat | None:
        return self.store.key_stats(self.profile.id).get(key_char)

    def window(self, key_char: str) -> WindowStats:
        return self.store.window_stats(self.profile.id, key_char)


class TestFirstPress:
    def test_correct_first_press_counts_one_attempt_and_one_correct(self) -> None:
        h = Harness()
        h.counter.start_prompt("f")
        assert h.counter.press("f") is PressOutcome.CORRECT
        assert h.stat("f") == KeyStat(1, 1, "2026-01-01T10:00:00+00:00")
        assert h.window("f") == WindowStats(1, 1, 1)

    def test_wrong_first_press_counts_one_attempt_and_no_correct(self) -> None:
        h = Harness()
        h.counter.start_prompt("f")
        assert h.counter.press("j") is PressOutcome.WRONG
        assert h.stat("f") == KeyStat(1, 0, "2026-01-01T10:00:00+00:00")
        assert h.window("f") == WindowStats(1, 0, 1)

    def test_the_attempt_is_recorded_against_the_target_not_the_key_pressed(self) -> None:
        h = Harness()
        h.counter.start_prompt("f")
        h.counter.press("j")
        assert set(h.store.key_stats(h.profile.id)) == {"f"}
        assert h.window("j") == WindowStats(0, 0, 0)

    def test_a_prompt_alone_writes_nothing(self) -> None:
        h = Harness()
        h.counter.start_prompt("f")
        assert h.store.key_stats(h.profile.id) == {}
        assert h.window("f") == WindowStats(0, 0, 0)


class TestRejectionLoop:
    def test_wrong_then_correct_is_one_attempt_zero_correct(self) -> None:
        h = Harness()
        h.counter.start_prompt("f")
        assert h.counter.press("j") is PressOutcome.WRONG
        assert h.counter.press("f") is PressOutcome.CORRECT
        assert h.stat("f") == KeyStat(1, 0, "2026-01-01T10:01:00+00:00")
        assert h.window("f") == WindowStats(1, 0, 1)

    def test_every_press_in_the_loop_bumps_recency(self) -> None:
        h = Harness()
        h.counter.start_prompt("f")
        h.counter.press("j")
        assert h.stat("f") == KeyStat(1, 0, "2026-01-01T10:00:00+00:00")
        h.counter.press("k")
        assert h.stat("f") == KeyStat(1, 0, "2026-01-01T10:01:00+00:00")
        h.counter.press("f")
        assert h.stat("f") == KeyStat(1, 0, "2026-01-01T10:02:00+00:00")

    def test_retries_cannot_inflate_accuracy(self) -> None:
        h = Harness()
        for _ in range(10):
            h.counter.start_prompt("f")
            h.counter.press("j")
            h.counter.press("f")
        assert h.stat("f") == KeyStat(10, 0, "2026-01-01T10:19:00+00:00")
        assert h.window("f") == WindowStats(10, 0, 1)

    def test_a_press_after_the_prompt_is_resolved_writes_nothing(self) -> None:
        h = Harness()
        h.counter.start_prompt("f")
        h.counter.press("f")
        assert h.counter.press("f") is PressOutcome.IGNORED
        assert h.stat("f") == KeyStat(1, 1, "2026-01-01T10:00:00+00:00")
        assert h.window("f") == WindowStats(1, 1, 1)


class TestTimeout:
    def test_a_timeout_re_prompt_counts_nothing(self) -> None:
        # A timeout re-speaks the prompt; it never calls start_prompt, and no
        # keystroke arrived, so nothing at all is written (ADR-027 § Timeouts).
        h = Harness()
        h.counter.start_prompt("f")
        assert h.store.key_stats(h.profile.id) == {}
        assert h.window("f") == WindowStats(0, 0, 0)

    def test_a_timeout_does_not_re_arm_the_first_attempt(self) -> None:
        h = Harness()
        h.counter.start_prompt("f")
        h.counter.press("j")
        # ... timeout fires here, the same prompt is re-spoken ...
        assert h.counter.press("k") is PressOutcome.WRONG
        assert h.counter.press("f") is PressOutcome.CORRECT
        assert h.stat("f") == KeyStat(1, 0, "2026-01-01T10:02:00+00:00")
        assert h.window("f") == WindowStats(1, 0, 1)


class TestHeldKeyRepeats:
    def test_a_repeat_of_a_held_correct_key_is_not_an_attempt(self) -> None:
        # The damaging case: 'f' held past the prompt it answered, its repeats
        # landing on the next prompt for 'j'. Without the rule, 'j' collects
        # wrong first attempts for a key the child never got wrong.
        h = Harness()
        h.counter.start_prompt("f")
        assert h.counter.press("f") is PressOutcome.CORRECT
        h.counter.start_prompt("j")
        assert h.counter.press("f", repeat=True) is PressOutcome.IGNORED
        assert h.counter.press("f", repeat=True) is PressOutcome.IGNORED
        assert h.stat("j") is None
        assert h.window("j") == WindowStats(0, 0, 0)
        assert h.stat("f") == KeyStat(1, 1, "2026-01-01T10:00:00+00:00")

    def test_the_prompt_is_still_open_after_the_repeats(self) -> None:
        h = Harness()
        h.counter.start_prompt("j")
        h.counter.press("f", repeat=True)
        assert h.counter.press("j") is PressOutcome.CORRECT
        assert h.stat("j") == KeyStat(1, 1, "2026-01-01T10:00:00+00:00")
        assert h.window("j") == WindowStats(1, 1, 1)

    def test_a_repeat_does_not_even_bump_recency(self) -> None:
        h = Harness()
        h.counter.start_prompt("f")
        h.counter.press("j")
        h.counter.press("j", repeat=True)
        assert h.stat("f") == KeyStat(1, 0, "2026-01-01T10:00:00+00:00")

    def test_a_doubled_letter_typed_with_a_release_counts_twice(self) -> None:
        # 'll' in "hello": the child releases between presses, so neither press
        # is flagged a repeat and both prompts count.
        h = Harness()
        h.counter.start_prompt("l")
        assert h.counter.press("l") is PressOutcome.CORRECT
        h.counter.start_prompt("l")
        assert h.counter.press("l") is PressOutcome.CORRECT
        assert h.stat("l") == KeyStat(2, 2, "2026-01-01T10:01:00+00:00")
        assert h.window("l") == WindowStats(2, 2, 1)

    def test_a_doubled_letter_produced_by_holding_counts_once(self) -> None:
        # The counter-case, decided the other way: a held 'l' is one actuation,
        # so the second 'l' of "hello" stays unanswered until the child lifts
        # the key and presses it again.
        h = Harness()
        h.counter.start_prompt("l")
        assert h.counter.press("l") is PressOutcome.CORRECT
        h.counter.start_prompt("l")
        assert h.counter.press("l", repeat=True) is PressOutcome.IGNORED
        assert h.stat("l") == KeyStat(1, 1, "2026-01-01T10:00:00+00:00")
        assert h.counter.press("l") is PressOutcome.CORRECT
        assert h.stat("l") == KeyStat(2, 2, "2026-01-01T10:01:00+00:00")
        assert h.window("l") == WindowStats(2, 2, 1)


class TestStoreTimestamps:
    def test_the_counter_leaves_timestamping_to_the_store_by_default(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Alice")
        counter = AttemptCounter(store, profile.id)
        counter.start_prompt("f")
        counter.press("f")
        stat = store.key_stats(profile.id)["f"]
        assert stat.attempt_count == 1
        assert stat.last_practised_at is not None
        assert store.window_stats(profile.id, "f") == WindowStats(1, 1, 1)

    def test_attempts_land_on_the_day_they_were_typed(self) -> None:
        store = FakeStore()
        profile = store.create_profile("Alice")
        days = iter(["2026-01-01T10:00:00+00:00", "2026-01-02T10:00:00+00:00"])
        counter = AttemptCounter(store, profile.id, lambda: next(days))
        for _ in range(2):
            counter.start_prompt("f")
            counter.press("f")
        assert store.window_stats(profile.id, "f") == WindowStats(2, 2, 2)


class TestLatencyAndPredecessor:
    """ADR-011's `latency_ms` and `prev_char`, which ADR-024's Phase C bar reads."""

    def harness(self) -> tuple[Harness, FakeClock]:
        h = Harness()
        clock = FakeClock()
        h.counter = AttemptCounter(h.store, h.profile.id, h.stamp, clock)
        return h, clock

    def rows(self, h: Harness, key_char: str) -> list[Attempt]:
        return h.store.window_attempts(h.profile.id, key_char)

    def test_latency_runs_from_the_end_of_the_spoken_prompt(self) -> None:
        h, clock = self.harness()
        h.counter.start_prompt("f")
        # The letter is synthesised and played first; the child cannot answer
        # before it has been heard, so the clock starts when it has.
        clock.advance(0.60)
        h.counter.mark_audible()
        clock.advance(0.75)
        h.counter.press("f")
        assert [row.latency_ms for row in self.rows(h, "f")] == [750]

    def test_a_prompt_that_never_became_audible_is_unmeasured(self) -> None:
        h, clock = self.harness()
        h.counter.start_prompt("f")
        clock.advance(0.75)
        h.counter.press("f")
        assert [row.latency_ms for row in self.rows(h, "f")] == [None]

    def test_a_re_spoken_prompt_is_timed_from_the_version_heard(self) -> None:
        # Every re-speak route re-stamps, so a prompt left open through a pause or
        # a timeout is not recorded as a very slow answer -- and a genuinely slow
        # answer is still recorded, which is the child the speed term is for.
        h, clock = self.harness()
        h.counter.start_prompt("f")
        h.counter.mark_audible()
        clock.advance(config.PROMPT_TIMEOUT_SECONDS * 3)
        h.counter.mark_audible()
        clock.advance(2.0)
        h.counter.press("f")
        assert [row.latency_ms for row in self.rows(h, "f")] == [2000]

    def test_a_press_while_the_prompt_is_being_re_spoken_is_unmeasured(self) -> None:
        # The earlier version's stamp must not survive into the re-speak, or the
        # answer is timed across the whole timeout (alpha-plan #12j, O4).
        h, clock = self.harness()
        h.counter.start_prompt("f")
        h.counter.mark_audible()
        clock.advance(config.PROMPT_TIMEOUT_SECONDS)
        h.counter.mark_inaudible()
        clock.advance(0.30)
        h.counter.press("f")
        assert [row.latency_ms for row in self.rows(h, "f")] == [None]

    def test_a_retry_does_not_move_the_recorded_latency(self) -> None:
        # The row is written on the first press and ADR-027 counts nothing after
        # it, so the number stays the time the child took to answer first.
        h, clock = self.harness()
        h.counter.start_prompt("f")
        h.counter.mark_audible()
        clock.advance(0.20)
        h.counter.press("j")
        clock.advance(5.0)
        h.counter.press("f")
        assert [row.latency_ms for row in self.rows(h, "f")] == [200]

    def test_no_clock_measures_nothing(self) -> None:
        h = Harness()
        h.counter.start_prompt("f")
        h.counter.mark_audible()
        h.counter.press("f")
        assert [row.latency_ms for row in self.rows(h, "f")] == [None]

    def test_prev_char_names_the_prompt_before_this_one(self) -> None:
        h, _ = self.harness()
        for target in ("f", "j", "f"):
            h.counter.start_prompt(target)
            h.counter.mark_audible()
            h.counter.press(target)
        assert [row.prev_char for row in self.rows(h, "f")] == [None, "j"]
        assert [row.prev_char for row in self.rows(h, "j")] == ["f"]

    def test_a_retry_is_not_a_predecessor(self) -> None:
        # `prev_char` is the previous *prompt*, not the last key the child hit:
        # a wrong press is not something they were asked for.
        h, _ = self.harness()
        h.counter.start_prompt("f")
        h.counter.press("f")
        h.counter.start_prompt("j")
        h.counter.press("v")
        h.counter.press("j")
        h.counter.start_prompt("r")
        h.counter.press("r")
        assert [row.prev_char for row in self.rows(h, "r")] == ["j"]
