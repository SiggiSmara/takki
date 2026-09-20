import queue
import random
from collections.abc import Callable
from typing import Any

import pytest

from takki import config
from takki.audio.tts_worker import SpeechFinished, TTSWorker
from takki.events import Quit
from takki.input import KeyEvent
from takki.language import WordSource
from takki.lesson.drills import DrillGenerator
from takki.lesson.introducer import KeyIntroducer, describe, introduction_sequence
from takki.platform.layout import Layout, build_en
from takki.session import Celebrant, InboundEvent, SessionLoop
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_focus_source import FakeFocusSource
from tests.fakes.fake_frames import FakeFrameLimiter
from tests.fakes.fake_letters import FakeLetterAudioSource
from tests.fakes.fake_sound_cues import FakeSoundCues
from tests.fakes.fake_store import FakeStore
from tests.fakes.fake_tts import FakeTTSEngine
from tests.fakes.fixed_list_source import FixedListSource
from tests.fakes.scripted_key_stream import ScriptedKeyStream

EN_WORDS: dict[str, float] = {
    "the": 100.0,
    "and": 90.0,
    "for": 80.0,
    "fur": 70.0,
    "jam": 60.0,
    "run": 50.0,
    "very": 40.0,
    "much": 30.0,
    "five": 20.0,
    "just": 10.0,
}

# Seconds of session time each keystroke costs. Under PACE_IDLE_GAP_SECONDS so
# the pace measure stays live, and under PROMPT_TIMEOUT_SECONDS so answering
# never trips the auto-advance deadline.
KEYSTROKE_SECONDS = 1.0


def _rung_line(rung: str) -> str:
    return f"rung {rung}"


class Harness:
    def __init__(
        self,
        *,
        words: dict[str, float] | None = None,
        source: WordSource | None = None,
        celebrant: Celebrant | None = None,
        now: Callable[[], str] | None = None,
        key_events: list[KeyEvent] | None = None,
        seed: dict[str, int] | None = None,
    ) -> None:
        self.layout = build_en()
        self.source = source or FixedListSource(words if words is not None else EN_WORDS)
        self.inbound: queue.Queue[InboundEvent] = queue.Queue()
        self.clock = FakeClock()
        self.engine = FakeTTSEngine()
        self.worker = TTSWorker(self.engine, self.inbound)
        self.letters = FakeLetterAudioSource()
        self.cues = FakeSoundCues()
        self.focus = FakeFocusSource(self.inbound)
        self.stream = ScriptedKeyStream(key_events or [], self.inbound)
        self.frames = FakeFrameLimiter()
        self.store = FakeStore()
        self.profile = self.store.create_profile("kid")
        for name, count in (seed or {}).items():
            for _ in range(count):
                self.store.upsert_key_stat(self.profile.id, name, True)
                self.store.append_attempt(self.profile.id, name, True)
        self.loop = SessionLoop(
            inbound=self.inbound,
            layout=self.layout,
            source=self.source,
            store=self.store,
            profile_id=self.profile.id,
            clock=self.clock,
            frames=self.frames,
            focus=self.focus,
            keys=self.stream,
            speech=self.worker,
            letters=self.letters,
            cues=self.cues,
            rng=random.Random(1),
            celebrant=celebrant,
            now=now,
        )

    # The TTS worker runs on a thread in production; the default tier drives it
    # by hand so SpeechFinished lands on the same queue, deterministically.
    def pump(self) -> None:
        while not self.worker.idle:
            self.worker.run_one()

    def settle(self, limit: int = 60) -> None:
        """Tick until a prompt is open, letting queued speech finish first."""
        for _ in range(limit):
            if self.loop.prompt is not None or not self.loop.running:
                return
            self.pump()
            self.loop.tick()
        raise AssertionError("no prompt after settling")

    def press(self, char: str, *, release: bool = True) -> None:
        self.clock.advance(KEYSTROKE_SECONDS)
        self.inbound.put(KeyEvent(pressed=True, char=char, name=None))
        if release:
            self.inbound.put(KeyEvent(pressed=False, char=char, name=None))

    def key(self, name: str, *, pressed: bool = True) -> None:
        self.inbound.put(KeyEvent(pressed=pressed, char=None, name=name))

    def answer(self, count: int = 1) -> list[str]:
        """Answer `count` prompts correctly; returns the graphemes asked for."""
        asked: list[str] = []
        for _ in range(count):
            self.settle()
            target = self.loop.prompt
            assert target is not None
            asked.append(target)
            self.press(target)
            self.loop.tick()
        return asked


def intro_lines(names: tuple[str, ...]) -> list[str]:
    layout = build_en()
    source = FixedListSource(EN_WORDS)
    for step in introduction_sequence(layout, source):
        if tuple(k.grapheme for k in step.keys) == names:
            return [describe(intro) for intro in step.keys]
    raise AssertionError(f"no step for {names}")


class TestStartup:
    def test_the_language_tables_are_warm_before_the_first_prompt(self) -> None:
        # concurrency-model.md § Startup: the cold build is ~0.8 s (en) against
        # a 16 ms frame budget, so it must not happen lazily inside the loop.
        calls: list[str] = []

        class Recording(FixedListSource):
            def grapheme_weights(self, layout: Layout) -> dict[str, float]:
                calls.append("grapheme_weights")
                return super().grapheme_weights(layout)

            def bigram_weights(self, layout: Layout) -> dict[str, float]:
                calls.append("bigram_weights")
                return super().bigram_weights(layout)

        harness = Harness(source=Recording(EN_WORDS))
        harness.loop.start()
        warmed = list(calls)
        harness.settle()
        assert warmed[:2] == ["grapheme_weights", "bigram_weights"]
        assert harness.letters.played != []

    def test_start_opens_a_session_row_and_starts_the_key_stream(self) -> None:
        harness = Harness()
        harness.loop.start()
        assert harness.stream.started is True
        assert harness.loop.running is True
        assert harness.store.sessions() == [(harness.profile.id, ANY_TS, None)]

    def test_nothing_is_spoken_before_the_first_introduction(self) -> None:
        harness = Harness()
        harness.loop.start()
        harness.pump()
        # The introduction script is the session's first spoken line.
        assert harness.engine.spoken == intro_lines(("f", "j"))[:1]


class _AnyTs:
    def __eq__(self, other: object) -> bool:
        return isinstance(other, str)


ANY_TS = _AnyTs()


class TestStageZeroEndToEnd:
    """The headline: a cold profile through Stage 0's first step and out again."""

    def test_a_cold_profile_runs_stage_0_step_one_to_completion(self) -> None:
        harness = Harness()
        harness.loop.start()

        # Phase A of Stage 0 is the L-R interleave of f and j -- ADR-024 § Stage
        # 0's blocks are not ordinary ramp-up. Ten cycles, capped by the phase's
        # own remaining requirement (PHASE_A_STREAK).
        phase_a = harness.answer(2 * config.PHASE_A_STREAK)
        assert phase_a == ["f", "j"] * config.PHASE_A_STREAK

        # Phase B keeps the same alternation -- the pair has no anchor behind it
        # yet -- and runs to its own bar, per member.
        phase_b = harness.answer(2 * config.PHASE_B_ATTEMPTS)
        assert phase_b == ["f", "j"] * config.PHASE_B_ATTEMPTS

        # Phase C: no partner is Active yet and the corpus has no f-f or j-j
        # bigram, so each member alternates solo (ADR-024 § Phase C fallback).
        phase_c = harness.answer(2 * config.PHASE_C_ATTEMPTS)
        assert phase_c == ["f", "j"] * config.PHASE_C_ATTEMPTS

        # Out the other side: the ramp-up has ended and ready_for_new_key holds,
        # so the boundary asks the introducer for Stage 0's second step.
        harness.settle()
        assert harness.engine.spoken == intro_lines(("f", "j")) + intro_lines(("r", "u"))
        assert harness.loop.prompt in {"f", "r"}

        counted = config.PHASE_A_STREAK + config.PHASE_B_ATTEMPTS + config.PHASE_C_ATTEMPTS
        for name in ("f", "j"):
            window = harness.store.window_stats(harness.profile.id, name)
            assert (window.attempt_count, window.correct_count) == (counted, counted)
        # Every prompt chimed once, none errored.
        assert harness.cues.played == ["correct"] * (2 * counted)
        # The anchor rung needs all six Stage 0 keys over two calendar days.
        assert harness.store.achieved_milestones(harness.profile.id) == []


class TestLifetimes:
    def test_one_introducer_and_one_drill_generator_for_the_whole_run(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A fresh KeyIntroducer forgets the last step and re-introduces it
        # (ADR-023); a fresh DrillGenerator drops a child mid-Phase-B into
        # Phase D (ADR-024). Constructing either per block or per step is a bug.
        built = {"introducer": 0, "drills": 0}

        class CountingIntroducer(KeyIntroducer):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                built["introducer"] += 1
                super().__init__(*args, **kwargs)

        class CountingDrills(DrillGenerator):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                built["drills"] += 1
                super().__init__(*args, **kwargs)

        monkeypatch.setattr("takki.session.KeyIntroducer", CountingIntroducer)
        monkeypatch.setattr("takki.session.DrillGenerator", CountingDrills)
        harness = Harness()
        harness.loop.start()
        # Far enough to cross three block boundaries and two introductions.
        harness.answer(2 * (config.PHASE_A_STREAK + config.PHASE_B_ATTEMPTS))
        assert built == {"introducer": 1, "drills": 1}

    def test_a_fresh_milestone_detector_is_built_per_check(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The opposite lifetime: it holds nothing and the stored rows are the
        # authority, so a fresh one per check is correct -- but it costs one
        # rolling-window query per Active grapheme, so it belongs at a block
        # boundary and never inside the prompt loop.
        built: list[int] = []
        from takki.lesson.milestones import MilestoneDetector

        class CountingDetector(MilestoneDetector):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                built.append(1)
                super().__init__(*args, **kwargs)

        monkeypatch.setattr("takki.session.MilestoneDetector", CountingDetector)
        harness = Harness()
        harness.loop.start()
        assert len(built) == 1
        harness.answer(2 * config.PHASE_A_STREAK)
        harness.settle()
        # One per block boundary crossed, not one per prompt.
        assert len(built) == 2


class TestAttemptPairing:
    def spy(self, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, bool]]:
        recorded: list[tuple[str, bool]] = []

        class SpyDrills(DrillGenerator):
            def record_attempt(self, grapheme: str, correct: bool) -> None:
                recorded.append((grapheme, correct))
                super().record_attempt(grapheme, correct)

        monkeypatch.setattr("takki.session.DrillGenerator", SpyDrills)
        return recorded

    def test_recorded_once_per_prompt_with_the_first_press_outcome(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recorded = self.spy(monkeypatch)
        harness = Harness()
        harness.loop.start()
        harness.answer(4)
        assert recorded == [("f", True), ("j", True), ("f", True), ("j", True)]

    def test_a_retry_press_never_reaches_record_attempt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Phase C's accuracy stops being first-attempt accuracy the moment a
        # retry counts (ADR-027 § First-Attempt Counting).
        recorded = self.spy(monkeypatch)
        harness = Harness()
        harness.loop.start()
        harness.settle()
        assert harness.loop.prompt == "f"
        harness.press("j")
        harness.loop.tick()
        harness.press("u")
        harness.loop.tick()
        harness.press("f")
        harness.loop.tick()
        assert recorded == [("f", False)]
        assert harness.cues.played == ["error", "error", "correct"]

    def test_a_retry_sequence_writes_exactly_one_key_attempts_row(self) -> None:
        harness = Harness()
        harness.loop.start()
        harness.settle()
        harness.press("j")
        harness.loop.tick()
        harness.press("u")
        harness.loop.tick()
        harness.press("f")
        harness.loop.tick()
        window = harness.store.window_stats(harness.profile.id, "f")
        assert (window.attempt_count, window.correct_count) == (1, 0)

    def test_an_auto_repeat_press_is_ignored_entirely(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recorded = self.spy(monkeypatch)
        harness = Harness()
        harness.loop.start()
        harness.settle()
        harness.press("f", release=False)
        harness.loop.tick()
        # Same key, still physically down: an OS auto-repeat.
        harness.press("f", release=False)
        harness.loop.tick()
        assert recorded == [("f", True)]
        assert harness.cues.played == ["correct"]


class TestAutoReject:
    def test_a_wrong_press_re_prompts_the_same_character(self) -> None:
        harness = Harness()
        harness.loop.start()
        harness.settle()
        harness.letters.played.clear()
        harness.press("j")
        harness.loop.tick()
        harness.pump()
        harness.loop.tick()
        # ADR-012: the same character is re-prompted, and the prompt stays open.
        assert harness.letters.played == ["f"]
        assert harness.loop.prompt == "f"


class TestKeypressInterrupt:
    def test_an_answered_press_cuts_the_prompt_audio(self) -> None:
        harness = Harness()
        harness.loop.start()
        harness.settle()
        harness.press("f")
        harness.loop.tick()
        assert harness.letters.stopped == 1

    def test_a_type_ahead_press_does_not_cut_the_introduction_script(self) -> None:
        # The script teaches a key the child has not been told about yet.
        # Cutting it on a keystroke that then does nothing else leaves them
        # prompted for a letter they never heard described.
        harness = Harness()
        harness.loop.start()
        harness.press("f")
        harness.loop.tick()
        assert harness.engine.stopped == 0
        harness.settle()
        assert harness.engine.spoken == intro_lines(("f", "j"))

    def test_an_auto_repeat_press_does_not_cut_the_re_prompt(self) -> None:
        harness = Harness()
        harness.loop.start()
        harness.settle()
        harness.press("j", release=False)
        harness.loop.tick()
        harness.settle()
        before = harness.letters.stopped
        # Same wrong key, still down: an OS auto-repeat, which counts for
        # nothing and must not truncate the re-prompt it would otherwise cut.
        harness.press("j", release=False)
        harness.loop.tick()
        assert harness.letters.stopped == before


class TestTypeAhead:
    def test_the_next_prompt_is_open_before_the_next_keystroke_is_dispatched(self) -> None:
        # roadmap § D "keystrokes typed between prompts are dropped": two
        # keystrokes queued in one drain, and the second must still land.
        harness = Harness()
        harness.loop.start()
        harness.settle()
        harness.press("f")
        harness.press("j")
        harness.loop.tick()
        assert harness.cues.played == ["correct", "correct"]
        for name in ("f", "j"):
            assert harness.store.window_stats(harness.profile.id, name).attempt_count == 1


class TestTimeout:
    def test_the_timeout_re_prompts_without_re_latching_the_prompt(self) -> None:
        harness = Harness()
        harness.loop.start()
        harness.settle()
        harness.letters.played.clear()
        harness.clock.advance(config.PROMPT_TIMEOUT_SECONDS)
        harness.loop.tick()
        assert harness.letters.played == ["f"]
        assert harness.loop.prompt == "f"
        # Not a new prompt: the child's first keystroke is still a first
        # attempt, so one wrong press writes one row and no more.
        harness.press("j")
        harness.loop.tick()
        window = harness.store.window_stats(harness.profile.id, "f")
        assert (window.attempt_count, window.correct_count) == (1, 0)

    def test_re_prompting_is_bounded_and_then_goes_quiet(self) -> None:
        harness = Harness()
        harness.loop.start()
        harness.settle()
        harness.letters.played.clear()
        for _ in range(config.PROMPT_MAX_REPROMPTS + 3):
            harness.clock.advance(config.PROMPT_TIMEOUT_SECONDS)
            harness.loop.tick()
        assert harness.letters.played == ["f"] * config.PROMPT_MAX_REPROMPTS
        # The prompt is still open through the silence.
        assert harness.loop.prompt == "f"

    def test_a_press_resets_the_re_prompt_budget(self) -> None:
        harness = Harness()
        harness.loop.start()
        harness.settle()
        for _ in range(config.PROMPT_MAX_REPROMPTS):
            harness.clock.advance(config.PROMPT_TIMEOUT_SECONDS)
            harness.loop.tick()
        harness.press("j")
        harness.loop.tick()
        harness.letters.played.clear()
        harness.clock.advance(config.PROMPT_TIMEOUT_SECONDS)
        harness.loop.tick()
        assert harness.letters.played == ["f"]

    def test_a_pause_does_not_spend_the_re_prompt_budget(self) -> None:
        # Monotonic time runs through a PAUSED interval, so a deadline left
        # armed is already in the past on the way back. Three Alt+Tabs would
        # otherwise exhaust the budget and leave the prompt silent for good.
        harness = Harness()
        harness.loop.start()
        harness.settle()
        for _ in range(config.PROMPT_MAX_REPROMPTS + 1):
            harness.focus.lose_focus()
            harness.loop.tick()
            harness.clock.advance(config.PROMPT_TIMEOUT_SECONDS * 3)
            harness.focus.gain_focus()
            harness.loop.tick()
            harness.pump()
            harness.loop.tick()
        harness.letters.played.clear()
        harness.clock.advance(config.PROMPT_TIMEOUT_SECONDS)
        harness.loop.tick()
        assert harness.letters.played == ["f"]

    def test_the_deadline_does_not_run_while_paused(self) -> None:
        harness = Harness()
        harness.loop.start()
        harness.settle()
        harness.focus.lose_focus()
        harness.loop.tick()
        harness.letters.played.clear()
        harness.clock.advance(config.PROMPT_TIMEOUT_SECONDS * 5)
        harness.loop.tick()
        assert harness.letters.played == []


class TestPausedRoundTrip:
    def test_resuming_re_issues_the_open_prompt_without_re_latching_it(self) -> None:
        harness = Harness()
        harness.loop.start()
        harness.settle()
        assert harness.loop.prompt == "f"
        # A wrong press first, so the prompt's outcome is already decided: if
        # the resume re-latched it, the later correct press would write a
        # second row.
        harness.press("j")
        harness.loop.tick()
        harness.letters.played.clear()
        harness.engine.spoken.clear()

        harness.focus.lose_focus()
        harness.loop.tick()
        harness.focus.gain_focus()
        harness.loop.tick()
        # The prompt is queued behind the resume announcement, not spoken over it.
        assert harness.letters.played == []
        harness.pump()
        harness.loop.tick()
        assert harness.engine.spoken == [
            "Paused. Takki is not the active window.",
            "Back in Takki.",
        ]
        assert harness.letters.played == ["f"]
        assert harness.loop.prompt == "f"

        harness.press("f")
        harness.loop.tick()
        window = harness.store.window_stats(harness.profile.id, "f")
        assert (window.attempt_count, window.correct_count) == (1, 0)

    def test_keystrokes_while_paused_reach_nothing(self) -> None:
        harness = Harness()
        harness.loop.start()
        harness.settle()
        harness.focus.lose_focus()
        harness.loop.tick()
        harness.press("f")
        harness.loop.tick()
        assert harness.cues.played == []
        assert harness.store.window_stats(harness.profile.id, "f").attempt_count == 0


class TestRecoveryKeys:
    def test_a_re_read_tap_re_speaks_the_open_prompt(self) -> None:
        harness = Harness()
        harness.loop.start()
        harness.settle()
        harness.letters.played.clear()
        harness.key(config.REREAD_KEY)
        harness.loop.tick()
        harness.key(config.REREAD_KEY, pressed=False)
        harness.loop.tick()
        assert harness.letters.played == ["f"]
        assert harness.loop.prompt == "f"

    def test_a_restart_hold_re_presents_the_whole_unit(self) -> None:
        # Steady state, where a unit is a bigram: seeded under
        # INTRODUCE_MIN_PRESSES so the boundary introduces nothing and the block
        # is ADR-024's frequency-weighted bigram content.
        harness = Harness(seed={"f": 10, "u": 10, "r": 10})
        harness.loop.start()
        harness.settle()
        first, second = harness.loop.prompt, None
        assert first is not None
        harness.press(first)
        harness.loop.tick()
        second = harness.loop.prompt
        assert second is not None
        harness.letters.played.clear()

        harness.key(config.RESTART_KEY)
        harness.loop.tick()
        harness.clock.advance(config.RESTART_HOLD_MS / 1000.0)
        harness.loop.tick()
        # Back to the top of the bigram, not to where the child was standing.
        assert harness.letters.played == [first]
        assert harness.loop.prompt == first

    def test_a_restart_re_counts_the_prompts_it_re_presents(self) -> None:
        harness = Harness(seed={"f": 10, "u": 10, "r": 10})
        harness.loop.start()
        harness.settle()
        first = harness.loop.prompt
        assert first is not None
        before = harness.store.window_stats(harness.profile.id, first).attempt_count
        harness.press(first)
        harness.loop.tick()
        harness.key(config.RESTART_KEY)
        harness.loop.tick()
        harness.clock.advance(config.RESTART_HOLD_MS / 1000.0)
        harness.loop.tick()
        harness.settle()
        harness.press(first)
        harness.loop.tick()
        # Each is a fresh prompt and ADR-027 counts prompts: two attempts, not
        # one. ADR-012's "the word is not counted toward session totals" has no
        # Layer-1 mechanism behind it (roadmap § D).
        after = harness.store.window_stats(harness.profile.id, first).attempt_count
        assert after - before == 2


class TestCelebration:
    def test_rungs_are_celebrated_in_ladder_order_in_one_boundary(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from takki.lesson.milestones import MilestoneDetector

        class TwoRungs(MilestoneDetector):
            fired = False

            def check(self) -> tuple[str, ...]:
                if TwoRungs.fired:
                    return ()
                TwoRungs.fired = True
                return ("anchor", "third")

        monkeypatch.setattr("takki.session.MilestoneDetector", TwoRungs)
        spoken: list[str] = []

        def celebrate(rung: str) -> str:
            spoken.append(rung)
            return f"rung {rung}"

        harness = Harness(celebrant=celebrate)
        harness.loop.start()
        harness.pump()
        # Ladder order, in the boundary that earned them, and ahead of the
        # introduction script that follows.
        assert spoken == ["anchor", "third"]
        assert harness.engine.spoken == ["rung anchor"]

    def test_a_celebration_is_not_interrupted_by_a_keypress(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from takki.lesson.milestones import MilestoneDetector

        class OneRung(MilestoneDetector):
            fired = False

            def check(self) -> tuple[str, ...]:
                if OneRung.fired:
                    return ()
                OneRung.fired = True
                return ("anchor",)

        monkeypatch.setattr("takki.session.MilestoneDetector", OneRung)
        harness = Harness(celebrant=_rung_line)
        harness.loop.start()
        # Not pumped: the celebration is enqueued and still in flight.
        harness.press("f")
        harness.loop.tick()
        # ADR-012: milestone announcements complete; the keypress is processed
        # normally, which here means dropped -- no prompt is open behind it.
        assert harness.engine.stopped == 0
        assert harness.cues.played == []
        harness.pump()
        assert harness.engine.spoken == ["rung anchor"]

    def test_no_celebrant_speaks_nothing(self) -> None:
        harness = Harness()
        harness.loop.start()
        harness.pump()
        assert harness.engine.spoken == intro_lines(("f", "j"))[:1]


class TestShutdown:
    def test_quit_stops_the_loop_and_closes_everything_down(self) -> None:
        harness = Harness()
        harness.loop.start()
        harness.settle()
        harness.focus.quit()
        harness.loop.run()
        assert harness.loop.running is False
        assert harness.stream.stopped is True
        assert harness.focus.closed is True
        assert harness.worker.run_one() is False
        assert harness.store.sessions() == [(harness.profile.id, ANY_TS, ANY_TS)]

    def test_a_signal_handler_flag_ends_the_run(self) -> None:
        harness = Harness()
        harness.loop.start()
        harness.settle()
        harness.loop.stop()
        harness.loop.run()
        assert harness.stream.stopped is True
        assert harness.focus.closed is True

    def test_shutdown_ends_the_session_row_once(self) -> None:
        harness = Harness()
        harness.loop.start()
        harness.loop.shutdown()
        harness.loop.shutdown()
        assert harness.store.sessions() == [(harness.profile.id, ANY_TS, ANY_TS)]


class TestSpeechEvents:
    def test_a_speech_finished_for_a_letter_is_dropped(self) -> None:
        harness = Harness()
        harness.loop.start()
        harness.settle()
        # An id the core never held -- a letter's, or a superseded utterance's.
        harness.inbound.put(SpeechFinished(9999, "completed"))
        harness.loop.tick()
        assert harness.loop.prompt == "f"


class TestLayerTwo:
    def test_the_unlock_predicate_is_evaluated_at_the_block_boundary(self) -> None:
        harness = Harness()
        harness.loop.start()
        # Two Active graphemes is well under LAYER_2_MIN_KEYS.
        assert harness.loop.layer_two_unlocked is False


class TestQuitEvent:
    def test_quit_is_frozen_and_comparable(self) -> None:
        assert Quit() == Quit()
