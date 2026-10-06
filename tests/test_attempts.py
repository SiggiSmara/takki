from takki import config
from takki.lesson.attempts import AttemptCounter, PressOutcome
from takki.lesson.letter_lengths import LetterLengths
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


LETTER_SECONDS = 1.2
LETTER_MS = 1200


class TimedHarness(Harness):
    """A counter with a monotonic clock, driven the way `SessionLoop` drives it."""

    def __init__(self) -> None:
        super().__init__()
        self.clock = FakeClock()
        self.lengths = LetterLengths(self.store, self.profile.id, "voice", config.TTS_RATE)
        self.counter = AttemptCounter(
            self.store, self.profile.id, self.stamp, self.clock, lengths=self.lengths
        )

    def rows(self, key_char: str) -> list[Attempt]:
        return self.store.window_attempts(self.profile.id, key_char)

    def timing(self, key_char: str) -> list[tuple[int | None, int | None, int]]:
        return [(row.latency_ms, row.after_letter_ms, row.timeouts) for row in self.rows(key_char)]

    def hear(self, target: str, seconds: float = LETTER_SECONDS) -> None:
        """Open a prompt and let its letter run to the end."""
        self.counter.start_prompt(target)
        self.counter.letter_sent()
        self.clock.advance(seconds)
        self.lengths.record(target, round(seconds * 1000))

    def answer(self, target: str, after: float) -> PressOutcome:
        """Open a prompt and answer it correctly `after` seconds from the sending."""
        self.counter.start_prompt(target)
        self.counter.letter_sent()
        self.clock.advance(after)
        return self.counter.press(target)


class TestLatency:
    """ADR-011's `latency_ms`, `after_letter_ms` and `timeouts` (alpha-plan #12f)."""

    def test_latency_runs_from_the_letter_being_sent(self) -> None:
        h = TimedHarness()
        h.hear("f")
        h.clock.advance(0.75)
        h.counter.press("f")
        assert h.timing("f") == [(LETTER_MS + 750, 750, 0)]

    def test_an_answer_before_the_letter_ends_is_timed_and_negative_after_the_letter(self) -> None:
        # The ordinary answer of anyone who knows the key: 60% of the answers
        # on the 2026-09-26 run. Unmeasured before #12f.
        h = TimedHarness()
        h.hear("f")
        h.counter.press("f")
        assert h.answer("f", 0.9) is PressOutcome.CORRECT
        assert h.timing("f")[-1] == (900, 900 - LETTER_MS, 0)

    def test_a_very_early_answer_is_kept(self) -> None:
        # A blind listener may know the letter from its first sound. Only the
        # physical floor removes a press, and this one is past it.
        h = TimedHarness()
        h.hear("f")
        h.counter.press("f")
        h.answer("f", config.HEARD_MIN_MS / 1000)
        assert h.timing("f")[-1] == (config.HEARD_MIN_MS, config.HEARD_MIN_MS - LETTER_MS, 0)

    def test_an_answer_is_timed_before_any_letter_has_finished(self) -> None:
        # Found by the review of 2026-10-04. The speed term reads the time from
        # the sending, which needs no letter length. A child who answers every
        # letter before it ends never lets one finish, and was left untimed.
        h = TimedHarness()
        for after in (0.4, 0.9, 3.0):
            h.answer("f", after)
        assert h.timing("f") == [(400, None, 0), (900, None, 0), (3000, None, 0)]

    def test_a_letter_that_ended_before_the_press_is_counted_from_that_end(self) -> None:
        # alpha-plan #12l: the length is read at the press, so the playback
        # this very prompt ran to its end is already part of it.
        h = TimedHarness()
        h.counter.start_prompt("f")
        h.counter.letter_sent()
        h.clock.advance(1.5)
        h.lengths.record("f", 1200)
        h.counter.press("f")
        assert h.timing("f") == [(1500, 300, 0)]

    def test_a_press_reads_nothing_back_from_the_store(self) -> None:
        # The caller plays the cue straight after a press, and a store read
        # ahead of it is audible delay. The stored lengths are read when the
        # prompt opens, once per letter per session.
        reads: list[str] = []

        class CountingStore(FakeStore):
            def letter_lengths(
                self, profile_id: int, key_char: str, voice: str, rate: float
            ) -> list[int]:
                reads.append(key_char)
                return super().letter_lengths(profile_id, key_char, voice, rate)

            def window_attempts(
                self, profile_id: int, key_char: str, limit: int | None = None
            ) -> list[Attempt]:
                reads.append(key_char)
                return super().window_attempts(profile_id, key_char, limit)

        store = CountingStore()
        profile = store.create_profile("Alice")
        clock = FakeClock()
        lengths = LetterLengths(store, profile.id, "voice", config.TTS_RATE)
        counter = AttemptCounter(store, profile.id, None, clock, lengths=lengths)
        for target in ("f", "j", "f"):
            counter.start_prompt(target)
            counter.letter_sent()
            before = list(reads)
            clock.advance(1.0)
            counter.press(target)
            assert reads == before
        assert reads == ["f", "j"]

    def test_no_length_is_read_back_out_of_older_attempt_rows(self) -> None:
        # Before alpha-plan #12l a row's two timings were subtracted to recover
        # the length it was written with, which could be another voice's or
        # another letter's. Only a measured playback is a length now.
        h = TimedHarness()
        stamp = "2026-01-01T09:00:00+00:00"
        h.store.append_attempt(h.profile.id, "f", True, stamp, 900, None, after_letter_ms=-300)
        h.answer("f", 0.5)
        assert h.timing("f")[-1] == (500, None, 0)

    def test_the_usual_length_is_the_median_over_the_letters_finished_playbacks(self) -> None:
        h = TimedHarness()
        for seconds in (1.0, 1.2, 2.0):
            h.hear("f", seconds)
            h.counter.press("f")
        h.answer("f", 0.5)
        assert h.timing("f")[-1] == (500, 500 - 1200, 0)

    def test_a_letter_never_heard_to_the_end_borrows_no_other_letters_length(self) -> None:
        # Until alpha-plan #12l it took the median over the letters that had
        # one, and the row could not say the length was borrowed.
        h = TimedHarness()
        h.hear("f", 1.1)
        h.counter.press("f")
        h.hear("j", 1.5)
        h.counter.press("j")
        h.answer("r", 0.5)
        assert h.timing("r") == [(500, None, 0)]

    def test_an_answer_to_a_re_spoken_letter_is_unmeasured(self) -> None:
        # alpha-plan #12j, O4: the whole wait before the re-speak is not the
        # child's reaction time, and neither is the time since the re-speak.
        h = TimedHarness()
        h.hear("f")
        h.clock.advance(3.0)
        h.counter.letter_sent()
        h.clock.advance(0.3)
        h.counter.press("f")
        assert h.timing("f") == [(None, None, 0)]

    def test_an_answer_after_leaving_or_to_a_failed_letter_is_unmeasured(self) -> None:
        h = TimedHarness()
        h.hear("f")
        h.counter.press("f")
        h.counter.start_prompt("f")
        h.counter.letter_sent()
        h.clock.advance(0.5)
        h.counter.mark_inaudible()
        h.clock.advance(0.5)
        h.counter.press("f")
        assert h.timing("f")[-1] == (None, None, 0)

    def test_timeouts_before_the_first_press_are_counted_on_the_row(self) -> None:
        # The slowest answers are the ones a re-spoken prompt leaves untimed,
        # and the child a speed term exists to notice. The count says so.
        h = TimedHarness()
        h.hear("f")
        for _ in range(2):
            h.clock.advance(config.PROMPT_TIMEOUT_SECONDS)
            h.counter.timed_out()
            h.counter.letter_sent()
        h.clock.advance(1.0)
        h.counter.press("f")
        assert h.timing("f") == [(None, None, 2)]

    def test_a_timeout_after_a_letter_nobody_heard_is_not_counted(self) -> None:
        # A counted timeout stands in the speed term as the slowest answer
        # there is. This one is the voice's failure, not the child's slowness.
        h = TimedHarness()
        h.counter.start_prompt("f")
        h.counter.letter_sent()
        h.counter.mark_inaudible()
        h.clock.advance(config.PROMPT_TIMEOUT_SECONDS)
        h.counter.timed_out()
        # The re-spoken letter is heard, and the wait after it is the child's.
        h.counter.letter_sent()
        h.clock.advance(config.PROMPT_TIMEOUT_SECONDS)
        h.counter.timed_out()
        h.counter.letter_sent()
        h.counter.press("f")
        assert [row.timeouts for row in h.rows("f")] == [1]

    def test_timeouts_belong_to_one_prompt(self) -> None:
        h = TimedHarness()
        h.hear("f")
        h.counter.timed_out()
        h.counter.press("f")
        h.hear("f")
        h.counter.press("f")
        assert [row.timeouts for row in h.rows("f")] == [1, 0]

    def test_a_timeout_after_the_first_press_is_not_on_the_row(self) -> None:
        h = TimedHarness()
        h.hear("f")
        h.counter.press("j")
        h.counter.timed_out()
        h.counter.press("f")
        assert [row.timeouts for row in h.rows("f")] == [0]

    def test_a_retry_does_not_move_the_recorded_latency(self) -> None:
        # The row is written on the first press and ADR-027 counts nothing after
        # it, so the number stays the time the child took to answer first.
        h = TimedHarness()
        h.hear("f")
        h.clock.advance(0.2)
        h.counter.press("j")
        h.clock.advance(5.0)
        h.counter.press("f")
        assert h.timing("f") == [(LETTER_MS + 200, 200, 0)]

    def test_no_clock_measures_nothing(self) -> None:
        h = Harness()
        h.counter.start_prompt("f")
        h.counter.letter_sent()
        h.counter.press("f")
        row = h.store.window_attempts(h.profile.id, "f")[0]
        assert (row.latency_ms, row.after_letter_ms) == (None, None)


class TestTooEarlyToHaveHeard:
    """ADR-027 § A press before the letter could be heard is not an attempt."""

    JUST_UNDER = (config.HEARD_MIN_MS - 1) / 1000
    AT_THE_FLOOR = config.HEARD_MIN_MS / 1000

    def test_a_correct_press_under_the_floor_writes_nothing_and_still_answers(self) -> None:
        h = TimedHarness()
        assert h.answer("f", self.JUST_UNDER) is PressOutcome.CORRECT
        assert h.counter.counted is False
        assert h.store.key_stats(h.profile.id) == {}
        assert h.rows("f") == []
        # The prompt is closed, as for any correct press.
        assert h.counter.press("f") is PressOutcome.IGNORED

    def test_a_press_at_the_floor_is_an_attempt(self) -> None:
        h = TimedHarness()
        assert h.answer("f", self.AT_THE_FLOOR) is PressOutcome.CORRECT
        assert h.counter.counted is True
        assert h.window("f") == WindowStats(1, 1, 1)

    def test_a_wrong_press_under_the_floor_leaves_the_first_attempt_open(self) -> None:
        h = TimedHarness()
        h.counter.start_prompt("f")
        h.counter.letter_sent()
        h.clock.advance(self.JUST_UNDER)
        assert h.counter.press("j") is PressOutcome.WRONG
        assert h.counter.counted is False
        assert h.store.key_stats(h.profile.id) == {}
        # The caller re-speaks the letter, and the next press is the first.
        h.counter.letter_sent()
        h.clock.advance(1.0)
        assert h.counter.press("f") is PressOutcome.CORRECT
        assert h.counter.counted is True
        assert h.window("f") == WindowStats(1, 1, 1)
        # Timed from the re-sent letter: it is the first one the child heard.
        assert h.timing("f") == [(1000, None, 0)]

    def test_every_press_under_the_floor_is_left_out_not_only_the_first(self) -> None:
        h = TimedHarness()
        h.counter.start_prompt("f")
        h.counter.letter_sent()
        for _ in range(3):
            h.clock.advance(0.05)
            assert h.counter.press("j") is PressOutcome.WRONG
            # The caller re-speaks the letter after a wrong press.
            h.counter.letter_sent()
        assert h.store.key_stats(h.profile.id) == {}

    def test_the_floor_starts_again_when_an_early_wrong_press_cut_the_letter(self) -> None:
        # Found by the review of 2026-10-04. The wrong press at 100 ms cut the
        # letter before it sounded, so the re-sent letter is the first the
        # child can hear, and a press 160 ms after it has heard nothing. From
        # the first sending it is 260 ms, over the floor, and it was counted:
        # a child hitting keys every 150 ms filled the window with guesses.
        h = TimedHarness()
        h.counter.start_prompt("f")
        h.counter.letter_sent()
        h.clock.advance(0.10)
        assert h.counter.press("j") is PressOutcome.WRONG
        h.counter.letter_sent()
        h.clock.advance(0.16)
        assert h.counter.press("k") is PressOutcome.WRONG
        assert h.counter.counted is False
        assert h.store.key_stats(h.profile.id) == {}

    def test_an_early_wrong_press_on_a_letter_that_cannot_be_cut_restarts_nothing(self) -> None:
        # Found by the review of 2026-10-06. The letter runs on and the child
        # hears all of it, so the one sent after it is a letter spoken again:
        # the answer is an attempt, counted from the first sending, and untimed.
        h = TimedHarness()
        h.counter.start_prompt("f")
        h.counter.letter_sent(cuttable=False)
        h.clock.advance(0.10)
        assert h.counter.press("j") is PressOutcome.WRONG
        h.clock.advance(1.0)
        h.counter.letter_sent()
        h.clock.advance(0.10)
        assert h.counter.press("f") is PressOutcome.CORRECT
        assert h.timing("f") == [(None, None, 0)]

    def test_the_floor_runs_from_the_first_sending_whatever_is_re_spoken(self) -> None:
        # A re-read does not give the child a second chance to be too early,
        # and does not move the moment before which nothing could be heard.
        early, late = TimedHarness(), TimedHarness()
        for h, second_wait in ((early, 0.1), (late, 0.2)):
            h.counter.start_prompt("f")
            h.counter.letter_sent()
            h.clock.advance(0.1)
            h.counter.letter_sent()
            h.clock.advance(second_wait)
            h.counter.press("f")
        assert early.rows("f") == []
        assert late.timing("f") == [(None, None, 0)]

    def test_the_floor_needs_no_measured_letter_length(self) -> None:
        # It is counted from the sending, so it holds on a session's first prompt.
        h = TimedHarness()
        h.answer("f", self.JUST_UNDER)
        assert h.rows("f") == []

    def test_a_retry_under_the_floor_is_still_engagement(self) -> None:
        # Only the first attempt is judged against the floor. Once it is
        # written, the prompt behaves as it always did.
        h = TimedHarness()
        h.hear("f")
        h.counter.press("j")
        h.counter.letter_sent()
        assert h.counter.press("f") is PressOutcome.CORRECT
        assert h.stat("f") == KeyStat(1, 0, "2026-01-01T10:01:00+00:00")

    def test_without_a_clock_there_is_no_floor(self) -> None:
        h = Harness()
        h.counter.start_prompt("f")
        h.counter.letter_sent()
        assert h.counter.press("f") is PressOutcome.CORRECT
        assert h.window("f") == WindowStats(1, 1, 1)

    def test_the_floor_is_the_constructors_to_set(self) -> None:
        h = TimedHarness()
        h.counter = AttemptCounter(h.store, h.profile.id, h.stamp, h.clock, heard_min_ms=600)
        h.answer("f", 0.5)
        assert h.rows("f") == []
        h.answer("f", 0.6)
        assert h.window("f") == WindowStats(1, 1, 1)

    def test_a_prompt_closed_under_the_floor_is_still_the_next_ones_predecessor(self) -> None:
        h = TimedHarness()
        h.answer("j", self.JUST_UNDER)
        h.answer("f", 1.0)
        assert [row.prev_char for row in h.rows("f")] == ["j"]


class TestPredecessor:
    """ADR-011's `prev_char`."""

    def harness(self) -> tuple[Harness, FakeClock]:
        h = TimedHarness()
        return h, h.clock

    def rows(self, h: Harness, key_char: str) -> list[Attempt]:
        return h.store.window_attempts(h.profile.id, key_char)

    def test_prev_char_names_the_prompt_before_this_one(self) -> None:
        h, _ = self.harness()
        for target in ("f", "j", "f"):
            h.counter.start_prompt(target)
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
