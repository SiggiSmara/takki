import queue
import random
import threading
from collections import Counter
from collections.abc import Callable
from itertools import groupby
from typing import Any

import pytest

from takki import config
from takki.audio.synthetic_letters import SyntheticLetterAudioSource
from takki.audio.tts_worker import SpeechFinished, TTSWorker
from takki.display.focus import FocusLost
from takki.events import Quit
from takki.focus_model import PAUSED_ANNOUNCEMENT, RESUMED_ANNOUNCEMENT
from takki.input import KeyEvent
from takki.language import WordSource
from takki.lesson.drills import DrillBlock, DrillGenerator, Prompt
from takki.lesson.introducer import KeyIntroducer, describe, introduction_sequence
from takki.lesson.key_state import KeyStates
from takki.persistence import Attempt, Profile, WindowStats
from takki.platform.layout import L_PINK, Grapheme, Layout, PhysicalKey, build_en
from takki.session import REST_CUE, Celebrant, InboundEvent, SessionLoop
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
from tests.rest import READY, seed_rest
from tests.sessions import session_for
from tests.test_drills import FirstChoice

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

# Every slot taken (ADR-010): the bump letters, which hold none (ADR-033), and
# six keys Active and none Known, so a session seeded with this introduces
# nothing and goes straight to steady state.
FULL_SLOTS = dict.fromkeys("fjruvmdk", 10)
DAY_ONE = "2026-01-01T10:00:00+00:00"
DAY_TWO = "2026-01-02T10:00:00+00:00"

# Seconds of session time each keystroke costs. Under PACE_IDLE_GAP_SECONDS so
# the pace measure stays live, and under PROMPT_TIMEOUT_SECONDS so answering
# never trips the auto-advance deadline.
KEYSTROKE_SECONDS = 1.0
LETTER_SECONDS = 1.2
LETTER_MS = int(LETTER_SECONDS * 1000)
SEED_VOICE = "voice"
# The letters a cold profile's first script speaks, ahead of any prompt: the
# fake letter source hears a script's letter and a prompt's alike.
HOME = ["f", "j"]
# Just inside ADR-027's floor: a press this soon after the letter was sent
# cannot be an answer to it.
TOO_EARLY_SECONDS = (config.HEARD_MIN_MS - 1) / 1000


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
        voice: str = SEED_VOICE,
        rate: float = config.TTS_RATE,
        not_ready: tuple[str, ...] = (),
        rest_keys: bool = True,
        rng: random.Random | None = None,
    ) -> None:
        self.layout = build_en()
        self.source = source or FixedListSource(words if words is not None else EN_WORDS)
        self.inbound: queue.Queue[InboundEvent] = queue.Queue()
        self.clock = FakeClock()
        self.engine = FakeTTSEngine()
        self.worker = TTSWorker(lambda: self.engine, self.inbound)
        self.letters = FakeLetterAudioSource(self.inbound)
        self.cues = FakeSoundCues()
        self.focus = FakeFocusSource(self.inbound)
        self.stream = ScriptedKeyStream(key_events or [], self.inbound)
        self.frames = FakeFrameLimiter()
        # A caller may pass both, to run several sessions against one profile
        # the way a child restarting Takki does (alpha-plan #12d).
        self.store = store if store is not None else FakeStore()
        self.profile = profile if profile is not None else self.store.create_profile("kid")
        # Nothing writes rest keys before the alignment (#12m session (7)), and
        # with none the order is empty (ADR-032 rest rule 1). A profile passed
        # back in for a second session keeps the keys it has.
        if rest_keys and not self.store.rest_keys(self.profile.id):
            seed_rest(self.store, self.profile.id, not_ready=not_ready)
        for name, count in (seed or {}).items():
            for _ in range(count):
                self.store.upsert_key_stat(self.profile.id, name, True)
                self.store.append_attempt(
                    self.profile.id, session_for(self.store, self.profile.id), name, True
                )
            # A key with a history was introduced under some voice, and that
            # is where its length was measured (ADR-011 § letter_lengths).
            self.store.append_letter_lengths(
                self.profile.id, SEED_VOICE, config.TTS_RATE, [(name, LETTER_MS)]
            )
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
            voice=voice,
            rate=rate,
            cues=self.cues,
            rng=rng or random.Random(1),
            celebrant=celebrant,
            now=now,
            max_keys_in_progress=max_keys_in_progress,
        )

    # The TTS worker runs on a thread in production; the default tier drives it
    # by hand so SpeechFinished lands on the same queue, deterministically.
    def pump(self) -> None:
        while not self.worker.idle:
            self.worker.run_one()
        self.letters.finish()

    def settle(self, limit: int = 60) -> None:
        """Tick until a prompt or a rest cue is open, letting queued speech finish first."""
        for _ in range(limit):
            if self.loop.open_prompt is not None or not self.loop.running:
                return
            self.pump()
            self.loop.tick()
        raise AssertionError("no prompt after settling")

    def press(self, char: str, *, release: bool = True, after: float = KEYSTROKE_SECONDS) -> None:
        self.clock.advance(after)
        self.inbound.put(KeyEvent(pressed=True, char=char, name=None))
        if release:
            self.inbound.put(KeyEvent(pressed=False, char=char, name=None))

    def key(self, name: str, *, pressed: bool = True) -> None:
        self.inbound.put(KeyEvent(pressed=pressed, char=None, name=name))

    def opened(self) -> str:
        """The prompt now open, whichever member of the step it is.

        The first step's pair is emitted in a shuffled order (ADR-024 § Ramp-up
        variability property 1), so a test about pairing, timeouts or focus asks
        which letter came up instead of assuming `f`.
        """
        self.settle()
        target = self.loop.prompt
        assert target is not None
        return target

    def partner(self, target: str) -> str:
        """The other bump letter — a press that is always wrong for `target`."""
        return "j" if target == "f" else "f"

    def answer(self, count: int = 1) -> list[str]:
        """Answer `count` letter prompts correctly, and every rest cue between them.

        Returns the letters asked for. A rest cue is answered by pressing the
        rest keys it waits for, and is not in the list: `walk` shows them.
        """
        return [entry for entry in self.walk(count, letters=True) if not entry.startswith("rest")]

    def walk(self, count: int, *, letters: bool = False) -> list[str]:
        """Answer `count` prompts correctly, a rest cue as `rest:<keys>`; returns what was asked.

        With `letters`, `count` counts only letter prompts.
        """
        asked: list[str] = []
        while (
            len([a for a in asked if not a.startswith("rest")]) if letters else len(asked)
        ) < count:
            self.settle()
            cue = self.loop.cue
            if cue is not None:
                asked.append("rest:" + "+".join(cue))
                for key in cue:
                    self.press(key)
                    self.loop.tick()
                continue
            target = self.loop.prompt
            assert target is not None
            asked.append(target)
            self.press(target)
            self.loop.tick()
        return asked

    def until_step(self, steps: int, limit: int = 2000) -> list[str]:
        """Answer every prompt correctly until `steps` steps have been introduced."""
        asked: list[str] = []
        while len(steps_of(self.store, self.profile.id)) < steps:
            assert len(asked) < limit, "the step never came"
            asked += self.walk(1)
        return asked


def queued(harness: Harness) -> list[InboundEvent]:
    """What is still on the inbound queue, in order. Empties it."""
    events: list[InboundEvent] = []
    while True:
        try:
            events.append(harness.inbound.get_nowait())
        except queue.Empty:
            return events


def sound(harness: Harness) -> None:
    """Run the worker dry, each letter it really speaks taking LETTER_SECONDS, then tick once."""
    while not harness.worker.idle:
        spoken = len(harness.engine.spoken)
        harness.worker.run_one()
        harness.clock.advance(LETTER_SECONDS * (len(harness.engine.spoken) - spoken))
    harness.loop.tick()


def hear_out(harness: Harness) -> None:
    """Let queued speech run to its end until a prompt opens, each letter taking LETTER_SECONDS.

    For letters that go through the worker. `settle` finishes everything in no
    time at all, so every letter it lets through measures as zero long.
    """
    for _ in range(60):
        if harness.loop.prompt is not None:
            return
        if not harness.worker.idle:
            spoken = len(harness.engine.spoken)
            harness.worker.run_one()
            if [len(text) for text in harness.engine.spoken[spoken:]] == [1]:
                harness.clock.advance(LETTER_SECONDS)
        harness.loop.tick()
    raise AssertionError("no prompt after hearing everything out")


def intro_script(names: tuple[str, ...]) -> list[tuple[str, str, str]]:
    """A step's script as it is spoken: per member, the lead, the letter, the rest."""
    layout = build_en()
    source = FixedListSource(EN_WORDS)
    for step in introduction_sequence(layout, source, set(), READY):
        if tuple(k.grapheme for k in step.keys) == names:
            return [
                (lead, intro.grapheme, rest)
                for intro in step.keys
                for lead, rest in [describe(intro)]
            ]
    raise AssertionError(f"no step for {names}")


def intro_texts(names: tuple[str, ...]) -> list[tuple[str, str]]:
    """`describe` for each member of a step: its script without the letter."""
    return [(lead, rest) for lead, _, rest in intro_script(names)]


def member_lines(names: tuple[str, ...]) -> dict[str, list[str]]:
    """Per member, what the TTS engine speaks of that member's own script."""
    return {letter: [lead, rest] for lead, letter, rest in intro_script(names)}


def intro_lines(names: tuple[str, ...]) -> list[str]:
    """What the TTS engine speaks of a step's script while the letters go to the fake source."""
    return [text for lead, _, rest in intro_script(names) for text in (lead, rest)]


class TestStartup:
    def test_the_language_tables_are_warm_before_the_first_prompt(self) -> None:
        # concurrency-model.md § Startup: the cold build is ~1.4 s (en) against
        # a 16 ms frame budget, so it must not happen lazily inside the loop.
        calls: list[str] = []

        class Recording(FixedListSource):
            def grapheme_weights(self, layout: Layout) -> dict[str, float]:
                calls.append("grapheme_weights")
                return super().grapheme_weights(layout)

            def bigram_weights(self, layout: Layout) -> dict[str, float]:
                calls.append("bigram_weights")
                return super().bigram_weights(layout)

            def key_shares(self, layout: Layout) -> dict[str, float]:
                calls.append("key_shares")
                return super().key_shares(layout)

        harness = Harness(source=Recording(EN_WORDS))
        harness.loop.start()
        warmed = list(calls)
        harness.settle()
        assert warmed[:3] == ["grapheme_weights", "bigram_weights", "key_shares"]
        assert harness.letters.played != []

    def test_start_opens_a_session_row_and_starts_the_key_stream(self) -> None:
        harness = Harness()
        harness.loop.start()
        assert harness.stream.started is True
        assert harness.loop.running is True
        assert harness.store.sessions() == [(harness.profile.id, ANY_TS, None)]

    def test_its_attempts_take_the_practice_day_of_the_session_it_opened(self) -> None:
        # ADR-011 `sessions`, #12m session 4b. An earlier session on another
        # date has one press of `f`; the loop's session is the second day, so
        # `f` has two days only if the loop's presses went into its own.
        store = FakeStore()
        profile = store.create_profile("kid")
        earlier = store.start_session(profile.id, "2026-01-01T10:00:00+00:00")
        store.count_attempt(profile.id, earlier, "f", True, "2026-01-01T10:00:00+00:00")
        harness = Harness(store=store, profile=profile)
        harness.loop.start()
        asked = Counter(harness.answer(4))
        assert asked["f"] and asked["j"]
        assert store.practice_days_by_session(profile.id) == {earlier: 1, earlier + 1: 2}
        f, j = 1 + asked["f"], asked["j"]
        assert store.window_stats(profile.id, "f") == WindowStats(f, f, 2)
        assert store.window_stats(profile.id, "j") == WindowStats(j, j, 1)

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


class TestFirstStepEndToEnd:
    """The headline: a cold profile through the first step, the bump letters, and out again."""

    def test_a_cold_profile_runs_the_first_step_to_completion(self) -> None:
        harness = Harness()
        harness.loop.start()
        # The bump letters have no Reach (ADR-024): the first step is one even
        # draw of `f` and `j` through Choose and Travel, with no rest cue, until
        # both meet the bar. The order is drawn, so it is read by its rules.
        asked = harness.until_step(2)
        assert set(asked) == {"f", "j"}
        drawn = [name for name in asked]
        assert max(len(list(g)) for _, g in groupby(drawn)) <= config.MAX_SAME_IN_A_ROW
        for name in ("f", "j"):
            entry = next(
                e for e in harness.store.introductions(harness.profile.id) if e.key_char == name
            )
            # All right, so the bar is met at the thirtieth listened press.
            assert entry.stable_attempts == config.STABLE_ATTEMPTS
            assert [r.level for r in harness.store.level_records(harness.profile.id, name)] == [
                "choose",
                "travel",
            ]
            window = harness.store.window_stats(harness.profile.id, name)
            assert window.attempt_count == window.correct_count == Counter(asked)[name]
        # Every prompt chimed once, none errored.
        assert harness.cues.played == ["correct"] * len(asked)
        # Out the other side: the boundary introduces the second step, whose
        # letters both reach and so begin at Reach, each followed by the cue.
        assert STEPS[1] == ("r", "u")
        assert harness.walk(4) == ["r", "rest:f", "u", "rest:j"]
        # The cue's word is cut by the press that answers it: `TestRestCue`
        # lets it be heard.
        assert harness.engine.spoken == [*intro_lines(("f", "j")), *intro_lines(STEPS[1])]
        assert harness.store.key_stats(harness.profile.id).keys() == {"f", "j"}
        assert [p.correct for p in harness.store.reach_presses(harness.profile.id, "r")] == [True]
        # No rung: `rest` reads landings, which nothing writes before the
        # alignment (#12m session 7), and `third` needs eight Known letters.
        assert harness.store.achieved_milestones(harness.profile.id) == []


class TestRestCue:
    """ADR-024 § Reach in the loop: the cue after each Reach letter, answered by the rest key.

    #12m session (6) builds the cue's basic handling. The guidance after wrong
    presses, the script's line about the cue, and what a pause, the re-read key
    and the restart key say while one is open are session (6b)'s.
    """

    def at_reach(self) -> Harness:
        """A profile past the first step, at the second's Reach: `r`, then its cue, then `u`."""
        store = FakeStore()
        profile = store.create_profile("kid")
        finish(store, profile.id, [("f", "j")])
        harness = Harness(store=store, profile=profile)
        harness.loop.start()
        assert harness.opened() == "r"
        harness.press("r")
        harness.loop.tick()
        harness.pump()
        harness.loop.tick()
        return harness

    def test_the_cue_is_spoken_after_the_letter_and_waits_for_the_rest_key(self) -> None:
        harness = self.at_reach()
        assert harness.loop.prompt is None
        assert harness.loop.cue == ("f",)
        assert harness.engine.spoken[-1] == REST_CUE
        harness.press("f")
        harness.loop.tick()
        assert harness.cues.played == ["correct", "correct"]
        assert harness.opened() == "u"

    def test_a_wrong_key_is_rejected_and_the_cue_stays_open(self) -> None:
        harness = self.at_reach()
        spoken = len(harness.engine.spoken)
        harness.press("g")
        harness.loop.tick()
        harness.pump()
        assert harness.cues.played == ["correct", "error"]
        assert harness.loop.cue == ("f",)
        assert harness.engine.spoken[spoken:] == [REST_CUE]

    def test_a_press_on_the_cue_is_never_counted_even_on_an_active_letter(self) -> None:
        harness = self.at_reach()
        before = harness.store.window_stats(harness.profile.id, "f")
        stat = harness.store.key_stats(harness.profile.id)["f"]
        harness.press("g")
        harness.loop.tick()
        harness.press("f")
        harness.loop.tick()
        assert harness.store.window_stats(harness.profile.id, "f") == before
        assert harness.store.key_stats(harness.profile.id)["f"] == stat
        assert harness.store.window_stats(harness.profile.id, "g") == WindowStats(0, 0, 0)

    def test_a_held_key_repeating_is_not_a_press(self) -> None:
        harness = self.at_reach()
        harness.press("g", release=False)
        harness.loop.tick()
        harness.press("g", release=False)
        harness.loop.tick()
        assert harness.cues.played == ["correct", "error"]

    def test_a_timeout_speaks_the_cue_again(self) -> None:
        harness = self.at_reach()
        spoken = len(harness.engine.spoken)
        harness.clock.advance(config.PROMPT_TIMEOUT_SECONDS)
        harness.loop.tick()
        harness.pump()
        assert harness.engine.spoken[spoken:] == [REST_CUE]
        assert harness.loop.cue == ("f",)

    def test_the_restart_key_opens_the_cue_again_and_not_the_letter_before_it(self) -> None:
        harness = self.at_reach()
        spoken = len(harness.engine.spoken)
        harness.key(config.RESTART_KEY)
        harness.loop.tick()
        harness.clock.advance(config.RESTART_HOLD_MS / 1000)
        harness.loop.tick()
        harness.pump()
        harness.loop.tick()
        assert harness.loop.cue == ("f",)
        assert harness.engine.spoken[spoken:] == [REST_CUE]
        assert [p.correct for p in harness.store.reach_presses(harness.profile.id, "r")] == [True]

    def test_the_first_listened_press_after_reach_names_the_cued_finger(self) -> None:
        # ADR-011: `prev_char` after a rest cue holds the id of the finger it
        # asked for. Reach ends on `u`'s cue, which asks for the right index.
        harness = self.at_reach()
        harness.press("f")
        harness.loop.tick()
        asked = harness.walk(4 * config.LEVEL_UP_CORRECT - 2)
        assert asked[-1] == "rest:j"
        # Reach's presses are not attempts: neither letter has a row yet.
        for name in ("r", "u"):
            assert harness.store.window_attempts(harness.profile.id, name) == []
        first = harness.walk(1)[0]
        (row,) = harness.store.window_attempts(harness.profile.id, first)[-1:]
        assert row.prev_char == "R-idx"


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
        # Far enough to cross several block boundaries and two introductions.
        harness.until_step(3)
        assert built == {"introducer": 1, "drills": 1}

    def test_the_key_states_are_told_which_keys_have_the_bump(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # ADR-027 § Known has a speed term: `f` and `j` root the speed
        # baseline and have no speed term of their own. Left out, they would
        # be judged like any key and join the pool only once they met the floors.
        seen: list[tuple[str, ...]] = []

        class RecordingStates(KeyStates):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                seen.append(tuple(kwargs["bump_keys"]))
                super().__init__(*args, **kwargs)

        monkeypatch.setattr("takki.session.KeyStates", RecordingStates)
        Harness()
        assert seen == [("f", "j")]

    def test_a_block_boundary_reads_each_keys_window_once(self) -> None:
        # The boundary asks for the Known set (twice), the slow keys and every
        # key's need, and each is a pass over every Active key's window: about
        # 95 ms a pass on a full profile, between the last press and the next
        # letter (review of 2026-10-04).
        reads: Counter[str] = Counter()

        class CountingStore(FakeStore):
            def window_attempts(
                self, profile_id: int, key_char: str, limit: int | None = None
            ) -> list[Attempt]:
                reads[key_char] += 1
                return super().window_attempts(profile_id, key_char, limit)

        harness = Harness(seed=FULL_SLOTS, store=CountingStore())
        harness.loop.start()
        assert reads == dict.fromkeys(FULL_SLOTS, 1)

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
        # Choose ends when both bump letters meet its rule, and its block with it.
        asked = harness.answer(config.LEVEL_UP_CORRECT)
        while harness.loop.open_prompt is not None and len(built) == 1:
            asked += harness.answer(1)
        harness.settle()
        # One per block boundary crossed, not one per prompt.
        assert len(built) == 2
        assert len(asked) < config.FIRST_BLOCK_PROMPTS


class TestAttemptPairing:
    def spy(self, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, bool]]:
        recorded: list[tuple[str, bool]] = []

        class SpyDrills(DrillGenerator):
            def record_answer(self, prompt: Prompt, correct: bool) -> None:
                recorded.append((prompt.grapheme or "", correct))
                super().record_answer(prompt, correct)

        monkeypatch.setattr("takki.session.DrillGenerator", SpyDrills)
        return recorded

    def test_recorded_once_per_prompt_with_the_first_press_outcome(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recorded = self.spy(monkeypatch)
        harness = Harness()
        harness.loop.start()
        asked = harness.answer(4)
        assert recorded == [(name, True) for name in asked]

    def test_a_retry_press_never_reaches_record_answer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The ladder's accuracy stops being first-attempt accuracy the moment
        # a retry counts (ADR-027 § First-Attempt Counting).
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

    def test_a_correct_press_too_early_to_have_heard_moves_on_and_counts_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # ADR-027 § A press before the letter could be heard is not an attempt.
        # To the child it is an ordinary press; to every calculation it never
        # happened.
        recorded = self.spy(monkeypatch)
        harness = Harness()
        harness.loop.start()
        target = harness.opened()
        harness.press(target, after=TOO_EARLY_SECONDS)
        harness.loop.tick()
        assert harness.cues.played == ["correct"]
        assert recorded == []
        assert harness.store.key_stats(harness.profile.id) == {}
        assert harness.store.window_attempts(harness.profile.id, target) == []
        # The next prompt is open and its letter has been spoken.
        assert harness.loop.prompt is not None
        assert harness.letters.played == [*HOME, target, harness.loop.prompt]

    def test_a_wrong_press_too_early_to_have_heard_leaves_the_first_attempt_open(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recorded = self.spy(monkeypatch)
        harness = Harness()
        harness.loop.start()
        target = harness.opened()
        harness.press(harness.partner(target), after=TOO_EARLY_SECONDS)
        harness.loop.tick()
        assert harness.cues.played == ["error"]
        assert recorded == []
        assert harness.store.key_stats(harness.profile.id) == {}
        assert harness.loop.prompt == target
        assert harness.letters.played == [*HOME, target, target]
        # The press after it is the prompt's first attempt, with its own outcome.
        harness.press(target)
        harness.loop.tick()
        assert recorded == [(target, True)]
        window = harness.store.window_stats(harness.profile.id, target)
        assert (window.attempt_count, window.correct_count) == (1, 1)

    def test_a_press_at_the_floor_is_counted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        recorded = self.spy(monkeypatch)
        harness = Harness()
        harness.loop.start()
        target = harness.opened()
        harness.press(target, after=config.HEARD_MIN_MS / 1000)
        harness.loop.tick()
        assert recorded == [(target, True)]


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
        # The draw takes the first letter its rules allow, so the second prompt
        # is `f` again and the second keystroke is known before it is drawn.
        harness = Harness(rng=FirstChoice())
        harness.loop.start()
        target = harness.opened()
        assert target == "f"
        harness.press(target)
        harness.press(target)
        harness.loop.tick()
        assert harness.cues.played == ["correct", "correct"]
        # It lands, and it is not an attempt: its letter was sent in the same
        # drain, so the press cannot be an answer to it (ADR-027, alpha-plan
        # #12f). It answered a guess at what would come next.
        assert harness.letters.played == [*HOME, "f", "f", "j"]
        assert harness.store.window_stats(harness.profile.id, "f").attempt_count == 1


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


class TestLatency:
    """ADR-011's `latency_ms`, `after_letter_ms` and `timeouts` through the whole loop.

    Letters go through the worker here, as in production, because a letter's
    length is learned when its own SpeechFinished arrives.
    """

    LETTER_MS = LETTER_MS
    KEYSTROKE_MS = int(KEYSTROKE_SECONDS * 1000)

    def started(self) -> Harness:
        """A cold session whose introduction has been heard, each letter of it LETTER_SECONDS long."""
        harness = Harness(synthetic_letters=True)
        harness.loop.start()
        hear_out(harness)
        return harness

    def heard(self, harness: Harness) -> str:
        """Open a prompt and let its letter run to the end."""
        target = harness.opened()
        harness.clock.advance(LETTER_SECONDS)
        harness.pump()
        harness.loop.tick()
        return target

    def timing(self, harness: Harness, target: str) -> list[tuple[int | None, int | None, int]]:
        rows = harness.store.window_attempts(harness.profile.id, target)
        return [(row.latency_ms, row.after_letter_ms, row.timeouts) for row in rows]

    def test_an_answer_after_the_letter_is_timed_from_the_letters_end(self) -> None:
        harness = self.started()
        target = self.heard(harness)
        harness.press(target)
        harness.loop.tick()
        assert self.timing(harness, target) == [
            (self.LETTER_MS + self.KEYSTROKE_MS, self.KEYSTROKE_MS, 0)
        ]

    def test_an_answer_before_the_letter_ends_is_a_negative_latency(self) -> None:
        # alpha-plan #12f: unmeasured until now, and the ordinary answer of a
        # child who knows the key.
        harness = self.started()
        first = self.heard(harness)
        harness.press(first)
        harness.loop.tick()
        # The next letter is queued at the worker and is cut by the press.
        second = harness.opened()
        harness.press(second)
        harness.loop.tick()
        assert self.timing(harness, second)[-1] == (
            self.KEYSTROKE_MS,
            self.KEYSTROKE_MS - self.LETTER_MS,
            0,
        )

    def test_a_letter_introduced_this_session_is_counted_from_its_end_on_the_first_press(
        self,
    ) -> None:
        # alpha-plan #12l. The press cuts the prompt's own letter, so the only
        # playback that ran to its end is the one inside the introduction.
        harness = self.started()
        target = harness.opened()
        harness.press(target)
        harness.loop.tick()
        assert harness.engine.stopped == 1
        assert self.timing(harness, target) == [
            (self.KEYSTROKE_MS, self.KEYSTROKE_MS - self.LETTER_MS, 0)
        ]

    def test_an_answer_after_a_timeout_is_unmeasured_and_says_so(self) -> None:
        # The slowest answers are untimed because the letter was spoken again,
        # so the row carries how often that happened.
        harness = Harness(synthetic_letters=True)
        harness.loop.start()
        target = self.heard(harness)
        harness.clock.advance(config.PROMPT_TIMEOUT_SECONDS)
        harness.loop.tick()
        harness.clock.advance(LETTER_SECONDS)
        harness.pump()
        harness.loop.tick()
        harness.press(target)
        harness.loop.tick()
        assert self.timing(harness, target) == [(None, None, 1)]

    def test_an_answer_during_a_re_spoken_letter_is_unmeasured(self) -> None:
        # alpha-plan #12j, O4: the first version's stamp was left standing, so
        # this press was recorded as the timeout plus the keystroke.
        harness = Harness(synthetic_letters=True)
        harness.loop.start()
        target = self.heard(harness)
        harness.clock.advance(config.PROMPT_TIMEOUT_SECONDS)
        harness.loop.tick()
        # The re-spoken letter is queued at the worker and has not finished.
        harness.press(target)
        harness.loop.tick()
        assert self.timing(harness, target) == [(None, None, 1)]

    def test_an_answer_after_a_re_read_is_unmeasured_with_no_timeout(self) -> None:
        harness = Harness(synthetic_letters=True)
        harness.loop.start()
        target = self.heard(harness)
        harness.key(config.REREAD_KEY)
        harness.loop.tick()
        harness.key(config.REREAD_KEY, pressed=False)
        harness.loop.tick()
        harness.press(target)
        harness.loop.tick()
        assert self.timing(harness, target) == [(None, None, 0)]

    def test_an_answer_to_a_letter_that_failed_to_play_is_unmeasured(self) -> None:
        # alpha-plan #12j, O4: a letter the child never heard is not the start
        # of a reaction to it. A length is known here, from the first prompt,
        # so only the failure can be what leaves this one unmeasured.
        harness = Harness(synthetic_letters=True)
        harness.loop.start()
        first = self.heard(harness)
        harness.press(first)
        harness.loop.tick()
        harness.engine.fail_on = {"f", "j"}
        second = self.heard(harness)
        assert harness.engine.failed == [second]
        harness.press(second)
        harness.loop.tick()
        assert self.timing(harness, second)[-1] == (None, None, 0)

    def test_an_answer_over_the_resume_announcement_is_unmeasured(self) -> None:
        # The letter heard before the pause is not what this press answers, and
        # the time away is not reaction time.
        harness = Harness(synthetic_letters=True)
        harness.loop.start()
        target = self.heard(harness)
        harness.focus.lose_focus()
        harness.loop.tick()
        harness.pump()
        harness.clock.advance(config.PROMPT_TIMEOUT_SECONDS * 3)
        harness.focus.gain_focus()
        harness.loop.tick()
        # "Back in Takki." is still queued, so the prompt has not been re-spoken.
        harness.press(target)
        harness.loop.tick()
        assert self.timing(harness, target) == [(None, None, 0)]

    def test_a_timeout_after_a_letter_that_failed_is_not_the_childs(self) -> None:
        # Found by the review of 2026-10-04: counted, it put an answer the
        # child gave at once into the speed term as the slowest there is.
        harness = self.started()
        harness.engine.fail_on = {"f", "j"}
        target = self.heard(harness)
        assert harness.engine.failed == [target]
        harness.engine.fail_on = set()
        harness.clock.advance(config.PROMPT_TIMEOUT_SECONDS)
        harness.loop.tick()
        harness.clock.advance(LETTER_SECONDS)
        harness.pump()
        harness.loop.tick()
        harness.press(target)
        harness.loop.tick()
        assert self.timing(harness, target) == [(None, None, 0)]

    def test_the_timeout_count_stops_when_the_re_prompts_do(self) -> None:
        # The prompt goes quiet after PROMPT_MAX_REPROMPTS, and the last
        # re-prompt's own deadline is the last timeout there is to count.
        harness = Harness()
        harness.loop.start()
        target = harness.opened()
        for _ in range(config.PROMPT_MAX_REPROMPTS + 3):
            harness.clock.advance(config.PROMPT_TIMEOUT_SECONDS)
            harness.loop.tick()
        harness.press(target)
        harness.loop.tick()
        rows = harness.store.window_attempts(harness.profile.id, target)
        assert [row.timeouts for row in rows] == [config.PROMPT_MAX_REPROMPTS + 1]


class TestLetterLengths:
    """ADR-011 § letter_lengths and ADR-012 § A letter inside a sequence (alpha-plan #12l)."""

    KEYSTROKE_MS = int(KEYSTROKE_SECONDS * 1000)

    def timing(self, harness: Harness, target: str) -> list[tuple[int | None, int | None, int]]:
        rows = harness.store.window_attempts(harness.profile.id, target)
        return [(row.latency_ms, row.after_letter_ms, row.timeouts) for row in rows]

    def stored(self, harness: Harness, letter: str, voice: str = SEED_VOICE) -> list[int]:
        return harness.store.letter_lengths(harness.profile.id, letter, voice, config.TTS_RATE)

    def test_the_script_is_spoken_as_three_utterances_around_the_letter(self) -> None:
        # Through the worker, as in production: lead, the letter as a prompt
        # says it, the rest; then the next member; then the first prompt.
        harness = Harness(synthetic_letters=True)
        harness.loop.start()
        target = harness.opened()
        harness.pump()
        assert harness.engine.spoken == [
            *(part for member in intro_script(("f", "j")) for part in member),
            target,
        ]

    def test_the_scripts_letter_goes_to_the_source_a_prompt_uses(self) -> None:
        harness = Harness()
        harness.loop.start()
        target = harness.opened()
        assert harness.engine.spoken == intro_lines(("f", "j"))
        assert harness.letters.played == [*HOME, target]

    def test_what_the_script_measured_is_stored_at_the_block_boundary(self) -> None:
        harness = Harness(synthetic_letters=True)
        harness.loop.start()
        hear_out(harness)
        assert self.stored(harness, "f") == []
        block = harness.loop._block  # pyright: ignore[reportPrivateUsage]
        while harness.loop._block is block:  # pyright: ignore[reportPrivateUsage]
            harness.answer(1)
        assert (self.stored(harness, "f"), self.stored(harness, "j")) == ([LETTER_MS], [LETTER_MS])

    def test_what_was_measured_is_stored_when_the_session_ends(self) -> None:
        harness = Harness(synthetic_letters=True)
        harness.loop.start()
        hear_out(harness)
        harness.loop.shutdown()
        assert (self.stored(harness, "f"), self.stored(harness, "j")) == ([LETTER_MS], [LETTER_MS])

    def test_a_script_cut_at_its_letter_measures_only_the_pass_that_ended(self) -> None:
        # ADR-012 § Recovery re-speaks the script whole. The cut pass is no
        # length: counted, it would make the first one shorter than the voice.
        harness = Harness(synthetic_letters=True)
        harness.loop.start()
        harness.worker.run_one()
        harness.loop.tick()
        harness.clock.advance(LETTER_SECONDS / 4)
        harness.focus.lose_focus()
        harness.loop.tick()
        harness.pump()
        harness.loop.tick()
        harness.focus.gain_focus()
        hear_out(harness)
        assert harness.engine.spoken == [
            "New letter:",
            "Paused. Press Alt+Tab to come back to Takki.",
            "Back in Takki.",
            *(part for member in intro_script(("f", "j")) for part in member),
        ]
        harness.loop.shutdown()
        assert (self.stored(harness, "f"), self.stored(harness, "j")) == ([LETTER_MS], [LETTER_MS])

    def test_a_letter_from_an_earlier_session_has_its_length_on_an_early_press(self) -> None:
        # The case the stored lengths are for: nothing introduces these keys
        # today, and a press that cuts the letter measures nothing. The seeded
        # profile's lengths are in the store under this voice (`Harness`).
        harness = Harness(seed=FULL_SLOTS, synthetic_letters=True)
        harness.loop.start()
        target = harness.opened()
        harness.press(target)
        harness.loop.tick()
        assert self.timing(harness, target)[-1] == (
            self.KEYSTROKE_MS,
            self.KEYSTROKE_MS - LETTER_MS,
            0,
        )
        # The press cut it at the worker, so only the next prompt is spoken.
        following = harness.loop.prompt
        harness.pump()
        assert harness.engine.spoken == [following]

    def test_under_another_voice_a_letters_first_prompt_cannot_be_cut(self) -> None:
        # ADR-012 § A letter with no measured length. The answer counts, is
        # timed and gets its cue; the letter runs on and the next prompt waits.
        harness = Harness(seed=FULL_SLOTS, voice="another")
        harness.loop.start()
        first = harness.opened()
        before = harness.store.window_stats(harness.profile.id, first).attempt_count
        harness.press(first)
        harness.loop.tick()
        assert harness.cues.played == ["correct"]
        assert harness.letters.stopped == 0
        assert harness.store.window_stats(harness.profile.id, first).attempt_count == before + 1
        # No length yet when the row was written: the letter had not ended.
        assert self.timing(harness, first)[-1] == (self.KEYSTROKE_MS, None, 0)
        assert harness.loop.prompt is None
        assert harness.letters.played == [first]
        # It ends a fifth of a second after the press, and the next prompt opens.
        harness.clock.advance(LETTER_SECONDS - KEYSTROKE_SECONDS)
        harness.pump()
        harness.loop.tick()
        assert harness.loop.prompt is not None
        assert len(harness.letters.played) == 2
        # From here the letter has a length, and a press cuts it as always.
        while harness.opened() != first:
            harness.answer(1)
        stopped = harness.letters.stopped
        harness.press(first)
        harness.loop.tick()
        assert harness.letters.stopped == stopped + 1
        assert self.timing(harness, first)[-1] == (
            self.KEYSTROKE_MS,
            self.KEYSTROKE_MS - LETTER_MS,
            0,
        )
        harness.loop.shutdown()
        assert self.stored(harness, first, "another") == [LETTER_MS]
        # What the first voice measured is kept for a return to it.
        assert self.stored(harness, first) == [LETTER_MS]

    def test_another_rate_is_another_voice(self) -> None:
        harness = Harness(seed=FULL_SLOTS, rate=1.2)
        harness.loop.start()
        harness.press(harness.opened())
        harness.loop.tick()
        assert (harness.cues.played, harness.letters.stopped) == (["correct"], 0)
        assert harness.loop.prompt is None

    def test_a_wrong_press_does_not_cut_it_either_and_the_letter_is_then_said_again(self) -> None:
        harness = Harness(seed=FULL_SLOTS, voice="another")
        harness.loop.start()
        first = harness.opened()
        wrong = next(name for name in FULL_SLOTS if name != first)
        harness.press(wrong)
        harness.loop.tick()
        assert (harness.cues.played, harness.letters.stopped) == (["error"], 0)
        # Held behind the letter still sounding, not spoken over it.
        assert harness.letters.played == [first]
        harness.pump()
        harness.loop.tick()
        assert harness.letters.played == [first, first]
        assert harness.loop.prompt == first

    def test_a_wrong_press_too_early_to_have_heard_it_does_not_restart_the_timing(self) -> None:
        # Found by the review of 2026-10-06. The counter restarted the floor
        # and the timing as if the press had cut the letter. This one plays on,
        # so the answer after it answers a letter spoken twice: an attempt,
        # and not a timed one (ADR-011).
        harness = Harness(seed=FULL_SLOTS, voice="another")
        harness.loop.start()
        first = harness.opened()
        before = harness.store.window_stats(harness.profile.id, first).attempt_count
        wrong = next(name for name in FULL_SLOTS if name != first)
        harness.press(wrong, after=TOO_EARLY_SECONDS)
        harness.loop.tick()
        harness.pump()
        harness.loop.tick()
        assert harness.letters.played == [first, first]
        harness.press(first, after=TOO_EARLY_SECONDS)
        harness.loop.tick()
        assert harness.store.window_stats(harness.profile.id, first).attempt_count == before + 1
        assert self.timing(harness, first)[-1] == (None, None, 0)

    def test_the_re_read_key_while_the_next_prompt_waits_replays_no_introduction(self) -> None:
        # Found by the review of 2026-10-06. With the next prompt held behind
        # a letter that cannot be cut, no prompt is open inside a block, and
        # the key used to queue the whole script of the last step there.
        harness = Harness(synthetic_letters=True)
        harness.engine.fail_on = {"f", "j"}
        harness.loop.start()
        first = harness.opened()
        harness.engine.fail_on = set()
        harness.press(first)
        harness.loop.tick()
        assert harness.loop.prompt is None
        harness.key(config.REREAD_KEY)
        harness.loop.tick()
        harness.key(config.REREAD_KEY, pressed=False)
        harness.loop.tick()
        following = harness.opened()
        harness.pump()
        assert harness.engine.spoken == [*intro_lines(("f", "j")), first, following]

    def test_a_focus_steal_during_it_leaves_no_stale_announcement(self) -> None:
        # Found by the review of 2026-10-06: both announcements waited behind
        # the letter and both were spoken, the first after the child was back.
        harness = Harness(seed=FULL_SLOTS, voice="another", synthetic_letters=True)
        harness.loop.start()
        target = harness.opened()
        harness.focus.lose_focus()
        harness.loop.tick()
        harness.focus.gain_focus()
        harness.loop.tick()
        for _ in range(4):
            harness.pump()
            harness.loop.tick()
        assert harness.engine.spoken == [target, "Back in Takki.", target]
        assert harness.loop.prompt == target

    def test_the_restart_key_does_not_leave_two_letters_outstanding(self) -> None:
        # Review of 2026-10-06, C3. The restart key abandoned the prompt
        # without stopping its letter. Going back to a letter with no length,
        # which is sent so that it cannot be cut, then put a second letter at
        # the worker behind the first, and the wait was measured as its length.
        harness = Harness(seed=FULL_SLOTS, voice="another", synthetic_letters=True)
        # The unit's first letter fails to play, so it ends with no length.
        harness.engine.fail_on = set(FULL_SLOTS)
        harness.loop.start()
        first = harness.opened()
        sound(harness)
        harness.engine.fail_on = set()
        harness.press(first)
        harness.loop.tick()
        second = harness.loop.prompt
        assert second is not None and second != first
        # Its second letter is heard to its end and has one.
        sound(harness)
        # Said again, now as a letter a press can cut, and still outstanding
        # when the restart key goes back to the first.
        harness.key(config.REREAD_KEY)
        harness.loop.tick()
        harness.key(config.REREAD_KEY, pressed=False)
        harness.loop.tick()
        harness.key(config.RESTART_KEY)
        harness.loop.tick()
        harness.clock.advance(config.RESTART_HOLD_MS / 1000.0)
        harness.loop.tick()
        assert harness.loop.prompt == first
        sound(harness)
        assert harness.engine.spoken == [second, first]
        harness.loop.shutdown()
        assert self.stored(harness, first, "another") == [LETTER_MS]
        assert self.stored(harness, second, "another") == [LETTER_MS]

    def test_a_letter_the_script_failed_to_say_is_heard_out_at_its_first_prompt(self) -> None:
        # The introduction measured nothing, so the rule that covers a new
        # voice covers this too, and no letter stays without a length.
        harness = Harness(synthetic_letters=True)
        harness.engine.fail_on = {"f", "j"}
        harness.loop.start()
        target = harness.opened()
        harness.engine.fail_on = set()
        harness.press(target)
        harness.loop.tick()
        assert harness.cues.played == ["correct"]
        assert harness.engine.stopped == 0
        assert self.timing(harness, target) == [(self.KEYSTROKE_MS, None, 0)]
        harness.pump()
        harness.loop.tick()
        harness.loop.shutdown()
        assert self.stored(harness, target) == [self.KEYSTROKE_MS]


class TestRecoveryKeys:
    def test_a_re_read_tap_during_the_introduction_queues_the_script_again(self) -> None:
        # ADR-023: the key is how the child re-hears a script, while it speaks.
        harness = Harness()
        harness.loop.start()
        harness.key(config.REREAD_KEY)
        harness.loop.tick()
        harness.key(config.REREAD_KEY, pressed=False)
        harness.loop.tick()
        harness.settle()
        assert harness.engine.spoken == intro_lines(("f", "j")) * 2
        assert harness.letters.played[:4] == HOME * 2

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

    def test_a_restart_hold_during_the_introduction_leaves_the_script_whole(self) -> None:
        # No prompt is open, so the key abandons none and cuts nothing.
        harness = Harness()
        harness.loop.start()
        harness.key(config.RESTART_KEY)
        harness.loop.tick()
        harness.clock.advance(config.RESTART_HOLD_MS / 1000.0)
        harness.loop.tick()
        target = harness.opened()
        assert harness.engine.spoken == intro_lines(("f", "j"))
        assert harness.letters.played == [*HOME, target]
        assert (harness.engine.stopped, harness.letters.stopped) == (0, 0)

    def test_re_read_taps_over_the_resume_announcement_leave_it_whole(self) -> None:
        # Review of 2026-10-06, C6. A letter's stop on the real source is the
        # worker's stop, which cancels everything queued, speech included.
        # What keeps the announcement safe is that no letter is issued while
        # the speaker is busy, and on the fake source a break in that would
        # not show: its stop cancels only its own letter. Two taps, because a
        # second letter is what stops the first.
        harness = Harness(seed=FULL_SLOTS, synthetic_letters=True)
        harness.loop.start()
        target = harness.opened()
        harness.pump()
        harness.focus.lose_focus()
        harness.loop.tick()
        harness.pump()
        harness.focus.gain_focus()
        harness.loop.tick()
        for _ in range(2):
            harness.key(config.REREAD_KEY)
            harness.loop.tick()
            harness.key(config.REREAD_KEY, pressed=False)
            harness.loop.tick()
        for _ in range(3):
            harness.pump()
            harness.loop.tick()
        assert harness.engine.spoken == [
            target,
            PAUSED_ANNOUNCEMENT,
            RESUMED_ANNOUNCEMENT,
            target,
        ]
        assert (harness.engine.stopped, harness.engine.skipped) == (0, [])
        assert harness.loop.prompt == target

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
                return ("rest", "third")

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
        assert spoken == ["rest", "third"]
        assert harness.engine.spoken == ["rung rest"]

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
                return ("rest",)

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
        assert harness.engine.spoken == ["rung rest"]

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

    def test_a_stop_during_startup_is_not_lost(self) -> None:
        # The signal handlers are installed before start(), and the corpus
        # warm-up inside it is the slowest part of a launch.
        class StopsWhileWarming(FixedListSource):
            signalled = False

            def grapheme_weights(self, layout: Layout) -> dict[str, float]:
                if not self.signalled:
                    self.signalled = True
                    harness.loop.stop()
                return super().grapheme_weights(layout)

        harness = Harness(source=StopsWhileWarming(EN_WORDS))
        harness.loop.start()
        assert harness.loop.running is False
        harness.loop.run()
        harness.pump()
        assert harness.engine.spoken == []
        assert harness.store.introductions(harness.profile.id) == []
        assert harness.stream.stopped is True
        assert harness.store.sessions() == [(harness.profile.id, ANY_TS, ANY_TS)]

    def test_an_exception_in_a_tick_still_shuts_down(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = Harness()
        harness.loop.start()
        harness.settle()

        def broken() -> None:
            raise RuntimeError("tick")

        monkeypatch.setattr(harness.loop, "tick", broken)
        with pytest.raises(RuntimeError, match="tick"):
            harness.loop.run()
        assert harness.stream.stopped is True
        assert harness.focus.closed is True
        assert harness.store.sessions() == [(harness.profile.id, ANY_TS, ANY_TS)]

    def test_shutdown_cancels_speech_instead_of_waiting_behind_it(self) -> None:
        # Review of 2026-10-06, C1. The introduction's first line is at the
        # worker and nothing has run it yet. The engine is built first, as
        # the worker thread does before anything else, so the stop reaches it.
        harness = Harness()
        harness.worker.build_engine()
        harness.loop.start()
        harness.loop.shutdown()
        assert harness.engine.stopped == 1
        # The cancelled line is reported and never spoken, then the worker ends.
        assert harness.worker.run_one() is True
        assert harness.worker.run_one() is False
        assert harness.engine.spoken == []
        assert queued(harness) == [SpeechFinished(1, "cancelled")]

    def test_shutdown_ends_a_worker_thread_that_is_mid_utterance(self) -> None:
        # C1 as the review reproduced it, on a real thread: the utterance
        # lasts until it is stopped, as a long line does on SAPI.
        class SpeaksUntilStopped(FakeTTSEngine):
            def __init__(self) -> None:
                super().__init__()
                self.speaking = threading.Event()
                self.cut = threading.Event()

            def speak(self, text: str) -> None:
                self.speaking.set()
                self.cut.wait(timeout=5)
                super().speak(text)

            def stop(self) -> None:
                super().stop()
                self.cut.set()

        harness = Harness()
        engine = SpeaksUntilStopped()
        harness.engine = engine
        harness.worker.start()
        harness.loop.start()
        assert engine.speaking.wait(timeout=5)
        harness.loop.shutdown()
        thread = harness.worker._thread  # pyright: ignore[reportPrivateUsage]
        assert thread is not None and not thread.is_alive()
        assert (engine.stopped, engine.spoken) == (1, [])
        assert queued(harness) == [SpeechFinished(1, "cancelled")]

    def test_what_is_queued_behind_a_quit_is_not_handled(self) -> None:
        # Review of 2026-10-06, C2: the press was counted with its chime and
        # the pause announcement queued, in a session that had already ended.
        harness = Harness()
        harness.loop.start()
        target = harness.opened()
        harness.pump()
        harness.loop.tick()
        spoken = list(harness.engine.spoken)
        harness.focus.quit()
        harness.press(target, release=False)
        harness.focus.lose_focus()
        harness.loop.tick()
        assert harness.loop.running is False
        assert queued(harness) == [KeyEvent(pressed=True, char=target, name=None), FocusLost()]
        assert harness.cues.played == []
        assert harness.store.window_stats(harness.profile.id, target).attempt_count == 0
        harness.pump()
        assert harness.engine.spoken == spoken
        assert harness.loop.prompt == target

    def test_a_stop_as_start_sets_running_is_not_lost(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Review of 2026-10-06, C7. start() read the stop flag and then set
        # `running = True`, so a signal between the two had its
        # `running = False` overwritten and the session ran on.
        class SignalledAsItStarts(SessionLoop):
            signalled = False

            def __setattr__(self, name: str, value: object) -> None:
                if name == "running" and value is True and not self.signalled:
                    self.signalled = True
                    self.stop()
                super().__setattr__(name, value)

        monkeypatch.setattr("tests.test_session.SessionLoop", SignalledAsItStarts)
        harness = Harness()
        harness.loop.start()
        assert harness.loop.running is False
        ticks: list[None] = []

        def tick() -> None:
            ticks.append(None)
            harness.loop.running = False

        monkeypatch.setattr(harness.loop, "tick", tick)
        harness.loop.run()
        harness.pump()
        assert ticks == []
        assert harness.engine.spoken == []
        assert harness.store.introductions(harness.profile.id) == []
        assert harness.stream.stopped is True
        assert harness.focus.closed is True
        assert harness.store.sessions() == [(harness.profile.id, ANY_TS, ANY_TS)]

    def test_a_failure_in_the_stores_work_still_stops_the_threads(self) -> None:
        # C7: the SQLite work comes first in shutdown(), and when it raised
        # the worker and the key listener were left running.
        class CannotEndASession(FakeStore):
            def end_session(self, session_id: int, ended_at: str | None = None) -> None:
                raise RuntimeError("disk")

        harness = Harness(store=CannotEndASession())
        harness.worker.build_engine()
        harness.loop.start()
        with pytest.raises(RuntimeError, match="disk"):
            harness.loop.shutdown()
        assert harness.stream.stopped is True
        assert harness.focus.closed is True
        assert harness.engine.stopped == 1
        assert harness.worker.run_one() is True
        assert harness.worker.run_one() is False
        assert harness.engine.spoken == []

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
    of what was then Stage 0: the ramp-up lived only in the session that
    started it, so a new session's first block boundary found no ramp-up in
    progress and ADR-010's aggregate gate had nothing to say about a set this new.
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
        # Still the first step's pair, not a new letter and not the
        # steady-state mix over everything Active.
        assert set(asked) == {"f", "j"}

    def test_a_finished_ramp_up_lets_the_next_session_introduce(self) -> None:
        # The gate must not become a lock. A profile whose newest step has met
        # the bar on both members resumes nothing and moves on to the second step.
        store = FakeStore()
        profile = store.create_profile("kid")
        finish(store, profile.id, [("f", "j")])

        harness = Harness(store=store, profile=profile)
        harness.loop.start()
        harness.settle()
        introduced = {i.key_char for i in store.introductions(profile.id)}
        assert sorted(introduced - {"f", "j"}) == sorted(STEPS[1])

    def test_the_level_the_child_reached_is_recorded_and_survives_the_restart(self) -> None:
        # The durable half of #12d. Session 1 gets the first step past Choose;
        # the level runs are written, so session 2 resumes at Travel and begins
        # nothing again (ADR-024 § What survives a restart).
        store = FakeStore()
        profile = store.create_profile("kid")
        first = Harness(store=store, profile=profile)
        first.loop.start()
        while len(store.level_records(profile.id, "f")) < 2:
            first.answer(1)
        first.loop.stop()
        runs = {name: store.level_records(profile.id, name) for name in "fj"}
        for name in "fj":
            assert [(r.level, r.completed_presses is not None) for r in runs[name]] == [
                ("choose", True),
                ("travel", False),
            ]

        second = Harness(store=store, profile=profile)
        second.loop.start()
        second.answer(4)
        # Still the same step, and no new letter: the step is at Travel.
        assert {i.key_char for i in store.introductions(profile.id)} == {"f", "j"}
        assert {name: store.level_records(profile.id, name) for name in "fj"} == runs

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
        # And it is the script the child first heard, location clause included
        # (alpha-plan #12j, O2): the resumed step used to be rebuilt without it.
        assert [describe(intro) for intro in remembered.keys] == intro_texts(("f", "j"))

    def test_a_resumed_later_step_keeps_its_location_clauses(self) -> None:
        # The second step is located against the first, so its rebuild
        # depends on what the child had before it.
        store = FakeStore()
        profile = store.create_profile("kid")
        finish(store, profile.id, [("f", "j")])
        first = Harness(store=store, profile=profile)
        first.loop.start()
        first.answer(6)
        first.loop.stop()
        assert steps_of(store, profile.id) == STEPS[:2]

        second = Harness(store=store, profile=profile)
        second.loop.start()
        second.settle()
        introducer = second.loop._introducer  # pyright: ignore[reportPrivateUsage]
        assert introducer is not None
        remembered = introducer.last_step
        assert remembered is not None
        assert [describe(intro) for intro in remembered.keys] == intro_texts(STEPS[1])
        assert all("Reach" in rest for _, rest in intro_texts(STEPS[1]))
        # The step had not reached Choose, so it is introduced again, script
        # first, and Reach begins from nothing (ADR-024, "Two kinds of press").
        assert second.engine.spoken == intro_lines(STEPS[1])

    def test_a_resumed_step_is_described_from_todays_rest_keys(self) -> None:
        # Decided 2026-11-09 (#12m session (5b)): a rest key changed between the
        # sessions moves the description, because the finger now starts there.
        store = FakeStore()
        profile = store.create_profile("kid")
        finish(store, profile.id, STEPS[:2])
        first = Harness(store=store, profile=profile)
        first.loop.start()
        assert first.answer(1) == ["n"]
        first.loop.stop()
        assert first.engine.spoken[:2] == [
            "New letter:",
            "Use your left little finger. It is the key where that finger rests.",
        ]
        assert steps_of(store, profile.id) == STEPS[:3] and STEPS[2] == ("a", "n")
        # The left little finger now rests one row up, on `q`.
        store.choose_rest_key(profile.id, L_PINK, 2, 1, "landings")
        store.mark_rest_key_ready(profile.id, L_PINK)

        second = Harness(store=store, profile=profile)
        second.loop.start()
        second.settle()
        introducer = second.loop._introducer  # pyright: ignore[reportPrivateUsage]
        assert introducer is not None and introducer.last_step is not None
        assert [describe(i) for i in introducer.last_step.keys] == [
            (
                "New letter:",
                "Use your left little finger. Reach one row down from where that finger rests.",
            ),
            (
                "New letter:",
                "Use your right index finger. "
                "Reach one row down and one position to the left from where that finger rests.",
            ),
        ]
        # The step had not reached Choose, so the whole script is spoken again
        # (ADR-024), each member from where its finger rests today: `a` was
        # introduced as the key its finger rested on, and now takes a reach.
        assert second.engine.spoken == [
            "New letter:",
            "Use your left little finger. Reach one row down from where that finger rests.",
            "New letter:",
            "Use your right index finger. "
            "Reach one row down and one position to the left from where that finger rests.",
        ]
        assert second.letters.played[:2] == ["a", "n"]

    def test_a_half_answered_pair_is_resumed_as_a_pair(self) -> None:
        # alpha-plan #12j, O3. The session used to refuse the resume, and the
        # introducer then re-emitted the unanswered member alone: a different
        # script, a solo ramp-up for it, and no ramp-up at all for the other.
        store = FakeStore()
        profile = store.create_profile("kid")
        first = Harness(store=store, profile=profile)
        first.loop.start()
        (answered,) = first.answer(1)
        first.loop.stop()
        unanswered = first.partner(answered)

        second = Harness(store=store, profile=profile)
        second.loop.start()
        second.settle()
        # The script again for the member that was never answered, and only it,
        # in the words the child first heard.
        assert second.engine.spoken == member_lines(("f", "j"))[unanswered]
        assert second.letters.played[0] == unanswered
        drills = second.loop._drills  # pyright: ignore[reportPrivateUsage]
        assert drills is not None and drills.ramp_up is not None
        assert drills.ramp_up.graphemes == ("f", "j")
        introducer = second.loop._introducer  # pyright: ignore[reportPrivateUsage]
        assert introducer is not None and introducer.last_step is not None
        assert [describe(i) for i in introducer.last_step.keys] == intro_texts(("f", "j"))
        # Nothing new was introduced, and the pair is drilled as a pair.
        assert steps_of(store, profile.id) == [("f", "j")]
        assert set(second.answer(2 * config.LEVEL_UP_CORRECT)) == {"f", "j"}

    def half_answered(self) -> tuple[FakeStore, Profile, list[str]]:
        """One profile whose first pair was quit after one answer; returns the script still owed."""
        store = FakeStore()
        profile = store.create_profile("kid")
        first = Harness(store=store, profile=profile)
        first.loop.start()
        (answered,) = first.answer(1)
        first.loop.stop()
        return store, profile, member_lines(("f", "j"))[first.partner(answered)]

    def test_a_cut_resume_script_is_respoken_as_it_was(self) -> None:
        # The script owed to one member, cut by a focus loss, comes back as that
        # script and not as the whole step's.
        store, profile, owed = self.half_answered()
        second = Harness(store=store, profile=profile)
        second.loop.start()
        second.loop.tick()  # the script is queued and has not been spoken
        second.focus.lose_focus()
        second.loop.tick()
        second.pump()
        second.focus.gain_focus()
        second.settle()
        assert second.engine.spoken == [
            "Paused. Press Alt+Tab to come back to Takki.",
            "Back in Takki.",
            *owed,
        ]

    def test_a_celebration_comes_before_the_script_owed_on_resume(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # `_begin_block`'s order holds at session start too: what the child
        # finished is celebrated before they are told about a letter.
        from takki.lesson.milestones import MilestoneDetector

        store, profile, owed = self.half_answered()

        class OneRung(MilestoneDetector):
            fired = False

            def check(self) -> tuple[str, ...]:
                if OneRung.fired:
                    return ()
                OneRung.fired = True
                return ("rest",)

        monkeypatch.setattr("takki.session.MilestoneDetector", OneRung)
        second = Harness(store=store, profile=profile, celebrant=_rung_line)
        second.loop.start()
        second.settle()
        assert second.engine.spoken == ["rung rest", *owed]

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


BUMPS = frozenset({"f", "j"})

STEPS: list[tuple[str, ...]] = [
    tuple(intro.grapheme for intro in step.keys)
    for step in introduction_sequence(build_en(), FixedListSource(EN_WORDS), set(), READY)
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
    for step in steps:
        store.mark_introduced(profile_id, list(step))
        for name in step:
            for _ in range(config.KNOWN_MIN_ATTEMPTS):
                store.upsert_key_stat(profile_id, name, True, DAY_ONE)
                store.append_attempt(
                    profile_id, session_for(store, profile_id, DAY_ONE), name, True, DAY_ONE
                )
            # The bar met: the ramp-up has ended (ADR-024 § The one bar).
            store.record_stable(profile_id, name, config.KNOWN_MIN_ATTEMPTS)
            if name in known:
                store.upsert_key_stat(profile_id, name, True, DAY_TWO)
                store.append_attempt(
                    profile_id, session_for(store, profile_id, DAY_TWO), name, True, DAY_TWO
                )


def slots_taken(step: tuple[str, ...]) -> int:
    """The slots a step holds: the bump letters hold none (ADR-033)."""
    return len(set(step) - BUMPS)


def first_day(cap: int = config.MAX_KEYS_IN_PROGRESS) -> int:
    """How many of `STEPS` a cold profile meets before the slots are full, read from the cap."""
    taken = 0
    for count, step in enumerate(STEPS):
        taken += slots_taken(step)
        if taken > cap:
            return count
    return len(STEPS)


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

    def test_the_first_day_is_the_bump_letters_and_three_steps_after_them(self) -> None:
        # ADR-033's "three steps of one letter per hand on a first day", with
        # `f j` holding no slot (decided 2026-11-09): eight letters, not six.
        assert first_day() == 4
        assert STEPS[0] == ("f", "j")
        assert [len(step) for step in STEPS[:4]] == [2, 2, 2, 2]

    def test_a_cold_profile_meets_the_first_days_steps_and_then_waits(self) -> None:
        steps = STEPS[: first_day()]
        harness = Harness(now=lambda: DAY_ONE)
        harness.loop.start()
        drills = harness.loop._drills  # pyright: ignore[reportPrivateUsage]
        assert drills is not None
        for _ in range(3000):
            if steps_of(harness.store, harness.profile.id) == steps and drills.ramp_up is None:
                break
            harness.answer()
        else:
            raise AssertionError("the first day's steps were never introduced and ramped up")

        # Slots full, nothing Known on a first day: steady-state blocks over
        # those letters, however long the child goes on, and no further script.
        # Not necessarily all of them -- some are past SESSION_KEY_CEILING by now.
        asked = harness.answer(4 * config.FIRST_BLOCK_PROMPTS)
        assert set(asked) <= {name for step in steps for name in step}
        assert drills.ramp_up is None
        assert steps_of(harness.store, harness.profile.id) == steps
        assert harness.engine.spoken == [line for step in steps for line in intro_lines(step)]

    @pytest.mark.parametrize("known", ["", "f", "fj", "r", "ru", "fjr", "ruaneh"])
    def test_the_step_after_the_first_days_steps_waits_for_known_keys(self, known: str) -> None:
        # The first day's steps fill the cap. The next needs as many free slots
        # as it has members, and a Known bump letter frees none, because it
        # never held one. Six free slots still introduce one step, because its
        # ramp-up then holds the next one back.
        day = first_day()
        assert sum(slots_taken(step) for step in STEPS[:day]) == config.MAX_KEYS_IN_PROGRESS
        introduced = 1 if len(set(known) - BUMPS) >= slots_taken(STEPS[day]) else 0
        harness = self.started(day, known)
        assert steps_of(harness.store, harness.profile.id) == STEPS[: day + introduced]
        assert harness.engine.spoken == [
            line for step in STEPS[day : day + introduced] for line in intro_lines(step)
        ]

    @pytest.mark.parametrize(("in_progress", "introduced"), [(6, 0), (5, 1)])
    def test_a_single_key_step_needs_one_slot(self, in_progress: int, introduced: int) -> None:
        index = next(i for i, step in enumerate(STEPS) if len(step) == 1)
        earlier = [name for step in STEPS[:index] for name in step]
        known = earlier[: len(earlier) - in_progress]
        assert not BUMPS & set(earlier[len(known) :])
        harness = self.started(index, "".join(known))
        assert steps_of(harness.store, harness.profile.id) == STEPS[: index + introduced]

    def test_a_larger_cap_passed_by_construction_lets_the_next_step_in(self) -> None:
        # ADR-025: the per-profile tier will raise this for a child who can
        # carry more keys at once. Eight is room for exactly one more pair.
        day = first_day()
        harness = self.started(day, max_keys_in_progress=8)
        assert steps_of(harness.store, harness.profile.id) == STEPS[: day + 1]

    def test_a_smaller_cap_holds_a_cold_profile_after_its_first_two_steps(self) -> None:
        # The bump letters take no slot, so the step after them always fits.
        assert first_day(2) == 2
        harness = Harness(now=lambda: DAY_ONE, max_keys_in_progress=2)
        harness.loop.start()
        # Far past both steps' ramp-ups: the bar is thirty listened presses a
        # letter, and a draw of three or four letters gives each about a third.
        harness.answer(10 * config.STABLE_ATTEMPTS)
        assert all(e.stable_at for e in harness.store.introductions(harness.profile.id))
        assert steps_of(harness.store, harness.profile.id) == STEPS[:2]

    def test_a_key_becoming_known_mid_session_opens_the_gate_at_the_next_boundary(self) -> None:
        # Day two, every letter one press short of Known. The first block's
        # presses are those presses, so the boundary after it finds free slots.
        day = first_day()
        harness = self.started(day)
        assert steps_of(harness.store, harness.profile.id) == STEPS[:day]
        for _ in range(4 * config.FIRST_BLOCK_PROMPTS):
            if len(steps_of(harness.store, harness.profile.id)) > day:
                break
            harness.answer()
        assert steps_of(harness.store, harness.profile.id) == STEPS[: day + 1]


class TestRestState:
    """ADR-032 rest rules, as the loop reads them: `rest_keys` at every block boundary."""

    @pytest.mark.parametrize(
        "kwargs", [{"rest_keys": False}, {"not_ready": ("L-idx",)}, {"not_ready": ("R-idx",)}]
    )
    def test_a_cold_profile_without_both_index_fingers_ready_hears_nothing(
        self, kwargs: dict[str, Any]
    ) -> None:
        # Rest rule 1, and the state of every profile until the alignment
        # writes rest keys (#12m session (7)): no letter and nothing Active,
        # so the first boundary ends the session. What it says then is (7)'s.
        harness = Harness(**kwargs)
        harness.loop.start()
        harness.settle()
        assert harness.loop.running is False
        assert harness.engine.spoken == []
        assert harness.store.introductions(harness.profile.id) == []

    def test_a_finger_that_becomes_ready_is_read_at_the_next_boundary(self) -> None:
        # The bump letters are had and drilled; the left index finger is not
        # ready, so nothing more comes (rest rule 1) and the session drills
        # `f j`. Once the store says it is ready, the next boundary introduces.
        store = FakeStore()
        profile = store.create_profile("kid")
        finish(store, profile.id, [("f", "j")])
        harness = Harness(store=store, profile=profile, not_ready=("L-idx",))
        harness.loop.start()
        harness.settle()
        assert harness.loop.running
        assert harness.engine.spoken == []
        block = harness.loop._block  # pyright: ignore[reportPrivateUsage]
        assert isinstance(block, DrillBlock)
        assert set(harness.answer(len(block.prompts))) == {"f", "j"}
        assert steps_of(store, profile.id) == STEPS[:1]
        store.mark_rest_key_ready(profile.id, "L-idx")
        block = harness.loop._block  # pyright: ignore[reportPrivateUsage]
        assert isinstance(block, DrillBlock)
        harness.answer(len(block.prompts))
        assert steps_of(store, profile.id) == STEPS[:2]
        harness.settle()
        assert harness.engine.spoken == intro_lines(STEPS[1])


class TestEndOfTheCurriculum:
    def test_a_layout_with_nothing_left_to_introduce_keeps_drilling(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def six_index_column_letters() -> Layout:
            positions = {
                "r": (2, 4),
                "f": (3, 4),
                "v": (4, 4),
                "u": (2, 7),
                "j": (3, 7),
                "m": (4, 7),
            }
            keys = {char: PhysicalKey(char, row, col) for char, (row, col) in positions.items()}
            graphemes = {char: Grapheme(char, "direct", (char,), 1) for char in keys}
            return Layout(lang="en", keys=keys, graphemes=graphemes)

        monkeypatch.setattr("tests.test_session.build_en", six_index_column_letters)
        harness = Harness()
        harness.loop.start()
        profile = harness.profile.id

        def all_six_through_their_ramp_up() -> bool:
            done = [row.stable_at for row in harness.store.introductions(profile)]
            return len(done) == 6 and all(done)

        for _ in range(1000):
            if all_six_through_their_ramp_up():
                break
            harness.answer()
        assert all_six_through_their_ramp_up()

        # Two more blocks' worth: each boundary asks the introducer, which has
        # nothing further, and the session goes on with the keys it has.
        asked = harness.answer(2 * config.FIRST_BLOCK_PROMPTS)
        assert set(asked) <= set("fjruvm")
        assert harness.loop.running
        assert harness.engine.spoken == (
            intro_lines(("f", "j")) + intro_lines(("r", "u")) + intro_lines(("v", "m"))
        )
        introduced = [row.key_char for row in harness.store.introductions(profile)]
        assert introduced == ["f", "j", "r", "u", "v", "m"]
