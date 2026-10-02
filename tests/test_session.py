import queue
import random
from collections import Counter
from collections.abc import Callable
from itertools import pairwise
from typing import Any

import pytest

from takki import config
from takki.audio.synthetic_letters import SyntheticLetterAudioSource
from takki.audio.tts_worker import SpeechFinished, TTSWorker
from takki.events import Quit
from takki.input import KeyEvent
from takki.language import WordSource
from takki.lesson.drills import DrillGenerator
from takki.lesson.introducer import KeyIntroducer, describe, introduction_sequence
from takki.lesson.rampup import RampUpProgress
from takki.persistence import Profile
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
from tests.fakes.waiting_queue import install

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

# Every slot taken (ADR-010): six keys Active and none Known, so a session
# seeded with this introduces nothing and goes straight to steady state.
FULL_SLOTS = dict.fromkeys("fjruvm", 10)
DAY_ONE = "2026-01-01T10:00:00"
DAY_TWO = "2026-01-02T10:00:00"

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
        synthetic_letters: bool = False,
        store: FakeStore | None = None,
        profile: Profile | None = None,
        max_keys_in_progress: int = config.MAX_KEYS_IN_PROGRESS,
    ) -> None:
        self.layout = build_en()
        self.source = source or FixedListSource(words if words is not None else EN_WORDS)
        self.inbound: queue.Queue[InboundEvent] = queue.Queue()
        self.clock = FakeClock()
        self.engine = FakeTTSEngine()
        self.worker = TTSWorker(lambda: self.engine, self.inbound)
        self.letters = FakeLetterAudioSource()
        self.cues = FakeSoundCues()
        self.focus = FakeFocusSource(self.inbound)
        self.stream = ScriptedKeyStream(key_events or [], self.inbound)
        self.frames = FakeFrameLimiter()
        # A caller may pass both, to run several sessions against one profile
        # the way a child restarting Takki does (alpha-plan #12d).
        self.store = store if store is not None else FakeStore()
        self.profile = profile if profile is not None else self.store.create_profile("kid")
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
            # Production Alpha's letters go through the TTS worker; the fake
            # keeps them off it, which is simpler to assert on but cannot show
            # a letter lost there (alpha-plan #12c (1)).
            letters=SyntheticLetterAudioSource(self.worker) if synthetic_letters else self.letters,
            cues=self.cues,
            rng=random.Random(1),
            celebrant=celebrant,
            now=now,
            max_keys_in_progress=max_keys_in_progress,
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

    def opened(self) -> str:
        """The prompt now open, whichever member of the step it is.

        Stage 0's home pair is emitted in a shuffled order (ADR-024 § Ramp-up
        variability property 1), so a test about pairing, timeouts or focus asks
        which letter came up instead of assuming `f`.
        """
        self.settle()
        target = self.loop.prompt
        assert target is not None
        return target

    def partner(self, target: str) -> str:
        """The other member of Stage 0's home pair — a press that is always wrong for `target`."""
        return "j" if target == "f" else "f"

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
        # own remaining requirement (PHASE_A_STREAK). The *order* within a block
        # is shuffled (ADR-024 property 1), so each phase is checked by what it
        # asked for and how often, and by the one thing the shuffle must never
        # do: ask for the same letter twice running.
        phase_a = harness.answer(2 * config.PHASE_A_STREAK)
        assert Counter(phase_a) == {"f": config.PHASE_A_STREAK, "j": config.PHASE_A_STREAK}
        assert [a for a, b in pairwise(phase_a) if a == b] == []

        # Phase B keeps the same alternation -- the pair has no anchor behind it
        # yet -- and runs to its own bar, per member.
        phase_b = harness.answer(2 * config.PHASE_B_ATTEMPTS)
        assert Counter(phase_b) == {"f": config.PHASE_B_ATTEMPTS, "j": config.PHASE_B_ATTEMPTS}
        assert [a for a, b in pairwise(phase_b) if a == b] == []

        # Phase C: no partner is Active yet and the corpus has no f-f or j-j
        # bigram, so each member alternates solo (ADR-024 § Phase C fallback).
        phase_c = harness.answer(2 * config.PHASE_C_ATTEMPTS)
        assert Counter(phase_c) == {"f": config.PHASE_C_ATTEMPTS, "j": config.PHASE_C_ATTEMPTS}

        # Out the other side: the ramp-up has ended and there are free slots,
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
        asked = harness.answer(4)
        assert Counter(asked) == {"f": 2, "j": 2}
        assert recorded == [(name, True) for name in asked]

    def test_a_retry_press_never_reaches_record_attempt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Phase C's accuracy stops being first-attempt accuracy the moment a
        # retry counts (ADR-027 § First-Attempt Counting).
        recorded = self.spy(monkeypatch)
        harness = Harness()
        harness.loop.start()
        target = harness.opened()
        harness.press(harness.partner(target))
        harness.loop.tick()
        harness.press("u")
        harness.loop.tick()
        harness.press(target)
        harness.loop.tick()
        assert recorded == [(target, False)]
        assert harness.cues.played == ["error", "error", "correct"]

    def test_a_retry_sequence_writes_exactly_one_key_attempts_row(self) -> None:
        harness = Harness()
        harness.loop.start()
        target = harness.opened()
        harness.press(harness.partner(target))
        harness.loop.tick()
        harness.press("u")
        harness.loop.tick()
        harness.press(target)
        harness.loop.tick()
        window = harness.store.window_stats(harness.profile.id, target)
        assert (window.attempt_count, window.correct_count) == (1, 0)

    def test_an_auto_repeat_press_is_ignored_entirely(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recorded = self.spy(monkeypatch)
        harness = Harness()
        harness.loop.start()
        target = harness.opened()
        harness.press(target, release=False)
        harness.loop.tick()
        # Same key, still physically down: an OS auto-repeat.
        harness.press(target, release=False)
        harness.loop.tick()
        assert recorded == [(target, True)]
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
        target = harness.opened()
        harness.press(target)
        harness.press(harness.partner(target))
        harness.loop.tick()
        assert harness.cues.played == ["correct", "correct"]
        for name in ("f", "j"):
            assert harness.store.window_stats(harness.profile.id, name).attempt_count == 1


class TestInterruptedIntroductionScript:
    """ADR-012 Recovery: a script cut by a focus loss is held, not dropped."""

    SCRIPT = "New letter:"

    def _drain(self, harness: Harness, ticks: int = 12) -> None:
        for _ in range(ticks):
            harness.pump()
            harness.loop.tick()

    def _script_lines(self, harness: Harness) -> list[str]:
        return [line for line in harness.engine.spoken if line.startswith(self.SCRIPT)]

    def test_a_cut_script_is_respoken_whole_on_resume(self) -> None:
        harness = Harness()
        harness.loop.start()
        harness.loop.tick()  # queue the script; do not let it finish
        assert harness.loop.prompt is None

        harness.focus.lose_focus()
        self._drain(harness, 2)
        cut = self._script_lines(harness)
        # The focus loss really did truncate it: the line already handed to the
        # worker still spoke, the rest of the script was dropped from _pending.
        assert len(cut) < 2, cut

        harness.focus.gain_focus()
        self._drain(harness)
        after = self._script_lines(harness)
        # Re-spoken from the start, so every line of the script is heard --
        # the count grows past what the interrupted run managed.
        assert len(after) > len(cut), (cut, after)
        assert len(after) >= 2, after

    def test_the_prompt_waits_behind_the_respoken_script(self) -> None:
        harness = Harness()
        harness.loop.start()
        harness.loop.tick()
        harness.focus.lose_focus()
        self._drain(harness, 2)
        harness.focus.gain_focus()
        harness.loop.tick()
        # Queued, not spoken over: `_advance` holds the prompt while it speaks.
        assert harness.loop.prompt is None
        harness.settle()
        assert harness.loop.prompt is not None

    def test_a_completed_script_is_not_respoken_on_a_later_resume(self) -> None:
        # The case the decision exists to protect. Once the prompt has opened
        # the script has served its purpose, so an ordinary mid-drill pause
        # re-issues the prompt and nothing else -- with no prompt open, "a
        # script was cut" and "something else was speaking" are otherwise
        # indistinguishable.
        harness = Harness()
        harness.loop.start()
        harness.settle()
        harness.engine.spoken.clear()

        harness.focus.lose_focus()
        self._drain(harness, 2)
        harness.focus.gain_focus()
        self._drain(harness)

        assert self._script_lines(harness) == []


class TestCapsLock:
    def test_an_upper_case_answer_counts_as_correct(self) -> None:
        # ADR-027 § Case is folded at the boundary. A blind child has no Caps
        # Lock LED, so a stuck Caps Lock must not turn every prompt into a
        # silent miss -- which is exactly what it did before 2026-09-20.
        harness = Harness()
        harness.loop.start()
        harness.settle()
        asked = harness.loop.prompt
        assert asked is not None
        harness.press(asked.upper())
        harness.loop.tick()
        assert harness.cues.played == ["correct"]
        stats = harness.store.window_stats(harness.profile.id, asked)
        assert (stats.attempt_count, stats.correct_count) == (1, 1)

    def test_the_attempt_is_recorded_against_the_lower_case_key(self) -> None:
        # The stored key is the prompt target, so an upper-case answer must not
        # open a second key_stats row that no milestone or threshold reads.
        harness = Harness()
        harness.loop.start()
        harness.settle()
        asked = harness.loop.prompt
        assert asked is not None
        harness.press(asked.upper())
        harness.loop.tick()
        assert harness.store.window_stats(harness.profile.id, asked.upper()).attempt_count == 0


class TestTimeout:
    def test_the_timeout_re_prompts_without_re_latching_the_prompt(self) -> None:
        harness = Harness()
        harness.loop.start()
        target = harness.opened()
        harness.letters.played.clear()
        harness.clock.advance(config.PROMPT_TIMEOUT_SECONDS)
        harness.loop.tick()
        assert harness.letters.played == [target]
        assert harness.loop.prompt == target
        # Not a new prompt: the child's first keystroke is still a first
        # attempt, so one wrong press writes one row and no more.
        harness.press(harness.partner(target))
        harness.loop.tick()
        window = harness.store.window_stats(harness.profile.id, target)
        assert (window.attempt_count, window.correct_count) == (1, 0)

    def test_re_prompting_is_bounded_and_then_goes_quiet(self) -> None:
        harness = Harness()
        harness.loop.start()
        target = harness.opened()
        harness.letters.played.clear()
        for _ in range(config.PROMPT_MAX_REPROMPTS + 3):
            harness.clock.advance(config.PROMPT_TIMEOUT_SECONDS)
            harness.loop.tick()
        assert harness.letters.played == [target] * config.PROMPT_MAX_REPROMPTS
        # The prompt is still open through the silence.
        assert harness.loop.prompt == target

    def test_a_press_resets_the_re_prompt_budget(self) -> None:
        harness = Harness()
        harness.loop.start()
        target = harness.opened()
        for _ in range(config.PROMPT_MAX_REPROMPTS):
            harness.clock.advance(config.PROMPT_TIMEOUT_SECONDS)
            harness.loop.tick()
        harness.press(harness.partner(target))
        harness.loop.tick()
        harness.letters.played.clear()
        harness.clock.advance(config.PROMPT_TIMEOUT_SECONDS)
        harness.loop.tick()
        assert harness.letters.played == [target]

    def test_a_pause_does_not_spend_the_re_prompt_budget(self) -> None:
        # Monotonic time runs through a PAUSED interval, so a deadline left
        # armed is already in the past on the way back. Three Alt+Tabs would
        # otherwise exhaust the budget and leave the prompt silent for good.
        harness = Harness()
        harness.loop.start()
        target = harness.opened()
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
        assert harness.letters.played == [target]

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
        target = harness.opened()
        # A wrong press first, so the prompt's outcome is already decided: if
        # the resume re-latched it, the later correct press would write a
        # second row.
        harness.press(harness.partner(target))
        harness.loop.tick()
        harness.letters.played.clear()
        harness.engine.spoken.clear()

        harness.focus.lose_focus()
        harness.loop.tick()
        # The worker speaks the pause before focus returns, as the real one
        # would: without this the announcement is still queued when the resume
        # supersedes it, and announce() correctly drops it unheard.
        harness.pump()
        harness.focus.gain_focus()
        harness.loop.tick()
        # The prompt is queued behind the resume announcement, not spoken over it.
        assert harness.letters.played == []
        harness.pump()
        harness.loop.tick()
        assert harness.engine.spoken == [
            "Paused. Press Alt+Tab to come back to Takki.",
            "Back in Takki.",
        ]
        assert harness.letters.played == [target]
        assert harness.loop.prompt == target

        harness.press(target)
        harness.loop.tick()
        window = harness.store.window_stats(harness.profile.id, target)
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
        target = harness.opened()
        harness.letters.played.clear()
        harness.key(config.REREAD_KEY)
        harness.loop.tick()
        harness.key(config.REREAD_KEY, pressed=False)
        harness.loop.tick()
        assert harness.letters.played == [target]
        assert harness.loop.prompt == target

    def test_a_restart_hold_re_presents_the_whole_unit(self) -> None:
        # Steady state, where a unit is a bigram: seeded with every slot taken
        # (`FULL_SLOTS`) so the boundary introduces nothing and the block is
        # ADR-024's need-planned bigram content.
        harness = Harness(seed=FULL_SLOTS)
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
        harness = Harness(seed=FULL_SLOTS)
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
    def test_a_failed_utterance_does_not_stall_the_session(self) -> None:
        # The whole introduction script fails -- a headset lost mid-session --
        # and the prompt still opens. Before the worker survived engine
        # failures this was a running app that never asked for anything.
        harness = Harness()
        script = intro_lines(("f", "j"))
        harness.engine.fail_on = set(script)
        harness.loop.start()
        harness.settle()
        assert harness.engine.failed == script
        assert harness.engine.spoken == []
        assert harness.loop.prompt in {"f", "j"}

    def test_a_speech_finished_for_a_letter_is_dropped(self) -> None:
        harness = Harness()
        harness.loop.start()
        harness.settle()
        # An id the core never held -- a letter's, or a superseded utterance's.
        harness.inbound.put(SpeechFinished(9999, "completed"))
        harness.loop.tick()
        assert harness.loop.prompt in {"f", "j"}


class TestLateStop:
    def test_a_key_drained_ahead_of_its_letters_finish_does_not_silence_the_next_letter(
        self,
    ) -> None:
        # alpha-plan #12c (1), the exact condition RS-22c measured: the answer
        # reaches the inbound queue just before its letter ends, so one drain
        # holds [key, SpeechFinished(letter)] in that order, and that drain
        # runs while the worker has cleared its flag and waits for the next.
        harness = Harness(synthetic_letters=True)
        commands = install(harness.worker)
        harness.loop.start()
        harness.settle()
        target = harness.loop.prompt
        assert target is not None
        harness.press(target)
        harness.worker.run_one()
        spoken = list(harness.engine.spoken)
        assert spoken[-1] == target
        commands.while_waiting = harness.loop.tick
        harness.worker.run_one()
        following = harness.loop.prompt
        assert following is not None
        assert (harness.engine.spoken, harness.engine.skipped) == ([*spoken, following], [])


class TestLayerTwo:
    def test_the_unlock_predicate_is_evaluated_at_the_block_boundary(self) -> None:
        harness = Harness()
        harness.loop.start()
        # Two Active graphemes is well under LAYER_2_MIN_KEYS.
        assert harness.loop.layer_two_unlocked is False


class TestQuitEvent:
    def test_quit_is_frozen_and_comparable(self) -> None:
        assert Quit() == Quit()


class TestIntroductionPacingAcrossSessions:
    """alpha-plan #12d — every restart used to introduce the next step at once.

    The run of 2026-09-26 found four sessions against one store introducing all
    of Stage 0: the ramp-up lived only in the session that started it, so a new
    session's first block boundary found no ramp-up in progress and ADR-010's
    aggregate gate had nothing to say about a set this new.
    """

    def run_sessions(self, count: int, answers: int) -> tuple[FakeStore, list[list[str]]]:
        """Start, answer, quit — `count` times over one profile. Returns what each introduced."""
        store = FakeStore()
        profile = store.create_profile("kid")
        introduced: list[list[str]] = []
        for _ in range(count):
            before = {i.key_char for i in store.introductions(profile.id)}
            harness = Harness(store=store, profile=profile)
            harness.loop.start()
            harness.answer(answers)
            harness.loop.stop()
            introduced.append(
                sorted({i.key_char for i in store.introductions(profile.id)} - before)
            )
        return store, introduced

    def test_a_restart_mid_ramp_up_introduces_nothing_new(self) -> None:
        # The scenario from the run, with the numbers it used: four sessions,
        # each quitting well inside the first step's ramp-up.
        _, introduced = self.run_sessions(4, answers=12)
        assert introduced == [["f", "j"], [], [], []]

    def test_the_resumed_session_drills_the_step_it_left(self) -> None:
        store = FakeStore()
        profile = store.create_profile("kid")
        first = Harness(store=store, profile=profile)
        first.loop.start()
        first.answer(12)
        first.loop.stop()

        second = Harness(store=store, profile=profile)
        second.loop.start()
        asked = second.answer(8)
        # Still Stage 0's home pair, not a new letter and not the steady-state
        # mix over everything Active.
        assert set(asked) == {"f", "j"}

    def test_a_finished_ramp_up_lets_the_next_session_introduce(self) -> None:
        # The gate must not become a lock. A profile whose newest step has met
        # every bar -- Phase A + B + C worth of clean attempts on both members --
        # resumes nothing and moves on to Stage 0's second step.
        store = FakeStore()
        profile = store.create_profile("kid")
        store.mark_introduced(profile.id, ["f", "j"])
        progress = RampUpProgress(store, profile.id)
        for name in ("f", "j"):
            for bar in (
                config.PHASE_A_STREAK,
                config.PHASE_B_ATTEMPTS,
                config.PHASE_C_ATTEMPTS,
            ):
                for _ in range(bar):
                    store.upsert_key_stat(profile.id, name, True)
                    store.append_attempt(profile.id, name, True)
                assert progress.advance(progress.member(name)) is True

        harness = Harness(store=store, profile=profile)
        harness.loop.start()
        harness.settle()
        assert sorted({i.key_char for i in store.introductions(profile.id)} - {"f", "j"}) == [
            "r",
            "u",
        ]

    def test_the_phase_the_child_reached_is_recorded_and_survives_the_restart(self) -> None:
        # The durable half of the fix. Session 1 gets past Phase A's bar; the
        # completion is written, so session 2 resumes in Phase B instead of
        # re-deriving it from a window that may since have forgotten.
        store = FakeStore()
        profile = store.create_profile("kid")
        first = Harness(store=store, profile=profile)
        first.loop.start()
        first.answer(2 * config.PHASE_A_STREAK)
        first.loop.stop()
        assert store.completed_phases(profile.id, "f") == {"A": config.PHASE_A_STREAK}
        assert store.completed_phases(profile.id, "j") == {"A": config.PHASE_A_STREAK}

        second = Harness(store=store, profile=profile)
        second.loop.start()
        second.answer(4)
        # Still the same step, and no new letter -- the ramp-up is in Phase B.
        assert {i.key_char for i in store.introductions(profile.id)} == {"f", "j"}
        assert store.completed_phases(profile.id, "f") == {"A": config.PHASE_A_STREAK}

    def test_a_resumed_session_can_still_re_read_the_introduction(self) -> None:
        # The re-read key reads the script off the introducer's `last_step`, and a
        # resumed session emits no step -- so without the introducer being told,
        # a blind child's Escape between blocks answers with silence.
        store = FakeStore()
        profile = store.create_profile("kid")
        first = Harness(store=store, profile=profile)
        first.loop.start()
        first.answer(6)
        first.loop.stop()

        second = Harness(store=store, profile=profile)
        second.loop.start()
        second.settle()
        # Reading the introducer's own state rather than staging the route that
        # consumes it: `_on_reread` only reaches the script while no prompt is
        # open, which in a running session means during a celebration, and what
        # went wrong here was upstream of that -- the resumed step was never
        # given to the introducer at all, so there was nothing to speak.
        introducer = second.loop._introducer  # pyright: ignore[reportPrivateUsage]
        assert introducer is not None
        remembered = introducer.last_step
        assert remembered is not None
        assert [intro.grapheme for intro in remembered.keys] == ["f", "j"]

    def test_a_step_introduced_and_never_answered_is_introduced_again(self) -> None:
        # ADR-023 § What the introducer remembers: the script is that letter's
        # only teaching moment, so a child who heard it and typed nothing is owed
        # it again rather than dropped into drills for a key they never tried.
        store = FakeStore()
        profile = store.create_profile("kid")
        first = Harness(store=store, profile=profile)
        first.loop.start()
        first.settle()
        first.loop.stop()
        assert first.engine.spoken == intro_lines(("f", "j"))

        second = Harness(store=store, profile=profile)
        second.loop.start()
        second.settle()
        assert second.engine.spoken == intro_lines(("f", "j"))


STEPS: list[tuple[str, ...]] = [
    tuple(intro.grapheme for intro in step.keys)
    for step in introduction_sequence(build_en(), FixedListSource(EN_WORDS))
]


def steps_of(store: FakeStore, profile_id: int) -> list[tuple[str, ...]]:
    """Every step introduced so far, in order, each with its members in order."""
    entries = store.introductions(profile_id)
    return [
        tuple(e.key_char for e in entries if e.step == step)
        for step in sorted({e.step for e in entries})
    ]


def finish(
    store: FakeStore, profile_id: int, steps: list[tuple[str, ...]], known: str = ""
) -> None:
    """Steps introduced and ramped up, each key at Known's press floor on one day.

    A key named in `known` also has a press on a second day, which is all it
    lacked (ADR-027).
    """
    marks = {
        "A": config.PHASE_A_STREAK,
        "B": config.PHASE_A_STREAK + config.PHASE_B_ATTEMPTS,
        "C": config.PHASE_A_STREAK + config.PHASE_B_ATTEMPTS + config.PHASE_C_ATTEMPTS,
    }
    for step in steps:
        store.mark_introduced(profile_id, list(step))
        for name in step:
            for _ in range(config.KNOWN_MIN_ATTEMPTS):
                store.upsert_key_stat(profile_id, name, True, DAY_ONE)
                store.append_attempt(profile_id, name, True, DAY_ONE)
            for phase, attempts_at in marks.items():
                store.record_phase(profile_id, name, phase, attempts_at)
            if name in known:
                store.upsert_key_stat(profile_id, name, True, DAY_TWO)
                store.append_attempt(profile_id, name, True, DAY_TWO)


class TestSlots:
    """alpha-plan #12g — a new step needs a free slot, and Known is what frees one."""

    def started(self, steps: int, known: str = "", **kwargs: Any) -> Harness:
        store = FakeStore()
        profile = store.create_profile("kid")
        finish(store, profile.id, STEPS[:steps], known)
        harness = Harness(store=store, profile=profile, now=lambda: DAY_TWO, **kwargs)
        harness.loop.start()
        harness.settle()
        return harness

    def test_a_cold_profile_meets_all_of_stage_0_and_then_waits(self) -> None:
        # The steps that fit are read from the cap, not from the output: change
        # the cap and this asks for a different prefix. At the shipped cap it is
        # Stage 0's three pairs.
        stage_0: list[tuple[str, ...]] = []
        for step in STEPS:
            if sum(len(s) for s in stage_0) + len(step) > config.MAX_KEYS_IN_PROGRESS:
                break
            stage_0.append(step)
        harness = Harness(now=lambda: DAY_ONE)
        harness.loop.start()
        drills = harness.loop._drills  # pyright: ignore[reportPrivateUsage]
        assert drills is not None
        for _ in range(2000):
            if steps_of(harness.store, harness.profile.id) == stage_0 and drills.ramp_up is None:
                break
            harness.answer()
        else:
            raise AssertionError("Stage 0 was never fully introduced and ramped up")

        # Slots full, nothing Known on a first day: steady-state blocks over
        # those six, however long the child goes on, and no fourth script. Not
        # necessarily all six -- f and j were every later ramp-up's partners and
        # are past SESSION_KEY_CEILING by now.
        asked = harness.answer(4 * config.FIRST_BLOCK_PROMPTS)
        assert set(asked) <= {name for step in stage_0 for name in step}
        assert drills.ramp_up is None
        assert steps_of(harness.store, harness.profile.id) == stage_0
        assert harness.engine.spoken == [line for step in stage_0 for line in intro_lines(step)]

    @pytest.mark.parametrize(("known", "introduced"), [("", 0), ("f", 0), ("fj", 1), ("fjruvm", 1)])
    def test_the_step_after_stage_0_waits_for_two_known_keys(
        self, known: str, introduced: int
    ) -> None:
        # The fourth step is a pair, so one free slot is not enough -- and six
        # free slots still introduce one step, because its ramp-up then holds
        # the next one back.
        assert len(STEPS[3]) == 2
        harness = self.started(3, known)
        assert steps_of(harness.store, harness.profile.id) == STEPS[: 3 + introduced]
        assert harness.engine.spoken == [
            line for step in STEPS[3 : 3 + introduced] for line in intro_lines(step)
        ]

    @pytest.mark.parametrize(("in_progress", "introduced"), [(6, 0), (5, 1)])
    def test_a_single_key_step_needs_one_slot(self, in_progress: int, introduced: int) -> None:
        index = next(i for i, step in enumerate(STEPS) if len(step) == 1)
        earlier = [name for step in STEPS[:index] for name in step]
        harness = self.started(index, "".join(earlier[: len(earlier) - in_progress]))
        assert steps_of(harness.store, harness.profile.id) == STEPS[: index + introduced]

    def test_a_larger_cap_passed_by_construction_lets_the_next_step_in(self) -> None:
        # ADR-025: the per-profile tier will raise this for a child who can
        # carry more keys at once. Eight is room for exactly one more pair.
        harness = self.started(3, max_keys_in_progress=8)
        assert steps_of(harness.store, harness.profile.id) == STEPS[:4]

    def test_a_smaller_cap_holds_a_cold_profile_at_its_first_step(self) -> None:
        harness = Harness(now=lambda: DAY_ONE, max_keys_in_progress=2)
        harness.loop.start()
        ramp_up = config.PHASE_A_STREAK + config.PHASE_B_ATTEMPTS + config.PHASE_C_ATTEMPTS
        harness.answer(2 * ramp_up + 2 * config.FIRST_BLOCK_PROMPTS)
        assert steps_of(harness.store, harness.profile.id) == STEPS[:1]

    def test_a_key_becoming_known_mid_session_opens_the_gate_at_the_next_boundary(self) -> None:
        # Day two, all six one press short of Known. The first block's presses
        # are those presses, so the boundary after it finds free slots.
        harness = self.started(3)
        assert steps_of(harness.store, harness.profile.id) == STEPS[:3]
        for _ in range(4 * config.FIRST_BLOCK_PROMPTS):
            if len(steps_of(harness.store, harness.profile.id)) > 3:
                break
            harness.answer()
        assert steps_of(harness.store, harness.profile.id) == STEPS[:4]
