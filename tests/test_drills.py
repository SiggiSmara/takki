import math
import random
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from itertools import groupby, pairwise
from typing import ClassVar, TypeVar

import pytest

from takki import config
from takki.language import WordSource
from takki.lesson.drills import (
    MAX_KEY_SHARE,
    Block,
    DrillBlock,
    DrillGenerator,
    Prompt,
    PromptKind,
    plan_targets,
    presses_needed,
)
from takki.lesson.introducer import (
    IntroductionStep,
    KeyIntroduction,
    RestCell,
    base_key,
    home_anchor_keys,
)
from takki.lesson.key_state import CONFIDENCE_Z, Evidence, KeyStates, accuracy_bound
from takki.platform.layout import L_MID, Layout, build_en, build_is
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_store import FakeStore
from tests.fakes.fixed_list_source import FixedListSource
from tests.rest import READY
from tests.sessions import session_for

T = TypeVar("T")

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

# Six Active letters to drill around: the bump letters and the keys above and
# below them. Since ADR-033 they are ordinary letters; the set is only a fixture.
ANCHOR_SIX = "fjruvm"
# A bar stricter than Known's, to show the need arithmetic holds for any bar.
STRICT_BAR = 0.95


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


def make_step(layout: Layout, *names: str) -> IntroductionStep:
    return IntroductionStep(tuple(member(layout, name) for name in names))


class FirstChoice(random.Random):
    """Draws the first letter the rules allow, so a draw's sequence is the rules' alone."""

    def choice(self, seq: Sequence[T]) -> T:  # type: ignore[override]
        return seq[0]


def shown(prompt: Prompt) -> tuple[str, str]:
    """A prompt as a test reads it: its kind, and its letter or the rest keys it waits for."""
    if prompt.kind is PromptKind.REST:
        return ("rest", "+".join(prompt.owed))
    assert prompt.grapheme is not None
    return (prompt.kind.name.lower(), prompt.grapheme)


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
        rest: dict[str, RestCell] | None = None,
        rng: random.Random | None = None,
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
        self.rest = dict(READY if rest is None else rest)
        self.session = 0
        self.generator = self.new_session(rng or random.Random(seed))

    def new_session(self, rng: random.Random | None = None) -> DrillGenerator:
        """A restart: a new session and a new generator, on the same store."""
        self.session = self.store.start_session(self.profile)
        self.generator = DrillGenerator(
            self.layout,
            self.source,
            self.states,
            self.clock,
            rng or random.Random(7),
            self.store,
            self.profile,
            self.session,
            lambda: self.rest,
        )
        return self.generator

    def activate(self, grapheme: str, *, attempts: int = 1, wrong: int = 0) -> None:
        for index in range(attempts):
            correct = index >= wrong
            self.store.upsert_key_stat(self.profile, grapheme, correct)
            self.store.append_attempt(
                self.profile, session_for(self.store, self.profile), grapheme, correct
            )

    def begin(self, *names: str) -> None:
        self.store.mark_introduced(self.profile, list(names))
        assert self.generator.begin_step(make_step(self.layout, *names))

    def attempt(self, grapheme: str, correct: bool, *, latency_ms: int | None = None) -> None:
        # The store first, then the generator -- the order the session loop uses
        # (`AttemptCounter.press` writes, then `DrillGenerator.record_answer`).
        # The ladder reads these rows back, so a generator told about an
        # attempt that was never written would read the window one short.
        self.store.upsert_key_stat(self.profile, grapheme, correct)
        self.store.append_attempt(
            self.profile, self.session, grapheme, correct, latency_ms=latency_ms
        )
        self.generator.record_answer(Prompt(PromptKind.COUNTED, grapheme), correct)

    def reach(self, grapheme: str, correct: bool = True) -> None:
        self.store.append_reach_press(self.profile, grapheme, correct)
        self.generator.record_answer(Prompt(PromptKind.REACH, grapheme), correct)

    def first(self, prompt: Prompt, correct: bool) -> None:
        """A prompt's first press, written where the session loop's counter writes it."""
        if prompt.kind is PromptKind.COUNTED:
            assert prompt.grapheme is not None
            self.attempt(prompt.grapheme, correct)
        elif prompt.kind is PromptKind.REACH:
            assert prompt.grapheme is not None
            self.reach(prompt.grapheme, correct)
        else:
            self.generator.record_answer(prompt, correct)

    def run(
        self, block: Block, wrong: Callable[[int, Prompt], bool] = lambda _, __: False
    ) -> list[Prompt]:
        """Answer a whole block; `wrong(index, prompt)` decides which first presses miss."""
        issued: list[Prompt] = []
        while (prompt := block.current()) is not None:
            assert len(issued) < 1000, "a block that never ends"
            self.first(prompt, not wrong(len(issued), prompt))
            issued.append(prompt)
            block.close()
        return issued

    def ladder(self, wrong: Callable[[int, Prompt], bool] = lambda _, __: False) -> list[Prompt]:
        """Every block until the step's ramp-up has ended."""
        issued: list[Prompt] = []
        while self.generator.ramp_up is not None:
            assert len(issued) < 2000, "a ladder that never ends"
            issued += self.run(self.generator.next_block(), lambda i, p: wrong(len(issued) + i, p))
        return issued

    def steady(self) -> DrillBlock:
        block = self.generator.next_block()
        assert isinstance(block, DrillBlock)
        return block

    def answer(
        self, block_prompts: tuple[str, ...], *, correct: bool = True, seconds_each: float = 0.0
    ) -> None:
        for grapheme in block_prompts:
            self.clock.advance(seconds_each)
            self.attempt(grapheme, correct)

    def practise_all(self) -> None:
        for grapheme in sorted(self.states.active_keys()):
            self.attempt(grapheme, True)

    def levels(self, grapheme: str) -> list[tuple[str, int, int, int | None]]:
        """A letter's level runs: level, session, presses at its start and when its rule was met."""
        return [
            (r.level, r.session_id, r.started_presses, r.completed_presses)
            for r in self.store.level_records(self.profile, grapheme)
        ]

    def stable(self, grapheme: str) -> int | None:
        entries = self.store.introductions(self.profile)
        return next(e.stable_attempts for e in entries if e.key_char == grapheme)

    def to_choose(self, *names: str) -> None:
        self.begin(*names)
        for name in names:
            if self.generator.level == "reach" and name in self.reaching():
                for _ in range(config.LEVEL_UP_CORRECT):
                    self.reach(name)
        assert self.generator.level == "choose"

    def to_travel(self, *names: str) -> None:
        self.to_choose(*names)
        for name in names:
            press(self, name, config.LEVEL_UP_CORRECT)
        assert self.generator.level == "travel"

    def reaching(self) -> list[str]:
        ladder = self.generator.ramp_up
        assert ladder is not None
        return [name for name in ladder.graphemes if ladder.takes_reach(name)]


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


def runs(prompts: Sequence[str]) -> int:
    """The longest run of one prompt following itself."""
    return max((len(list(group)) for _, group in groupby(prompts)), default=0)


CYCLE_E = [("reach", "e"), ("rest", "d")]


class TestReach:
    """ADR-024 § Reach: the letter, then the rest cue, until 8 of the latest 10 are right."""

    def test_a_letter_with_a_reach_cycles_with_the_rest_cue_until_its_rule(self) -> None:
        fixture = Fixture(active="fj")
        fixture.begin("e")
        assert fixture.generator.level == "reach"
        # One cycle per press Reach still needs, inside the first block's target.
        assert config.FIRST_BLOCK_PROMPTS >= 2 * config.LEVEL_UP_CORRECT
        prompts = fixture.run(fixture.generator.next_block())
        assert [shown(p) for p in prompts] == CYCLE_E * config.LEVEL_UP_CORRECT
        # The cue asks back the finger the letter used, by its id.
        assert {p.fingers for p in prompts if p.kind is PromptKind.REST} == {L_MID}
        assert fixture.generator.level == "choose"

    def test_reach_presses_are_kept_apart_and_make_nothing_active(self) -> None:
        fixture = Fixture(active="fj")
        fixture.begin("e")
        fixture.run(fixture.generator.next_block())
        assert len(fixture.store.reach_presses(fixture.profile, "e")) == config.LEVEL_UP_CORRECT
        assert fixture.store.window_attempts(fixture.profile, "e") == []
        assert "e" not in fixture.store.key_stats(fixture.profile)
        assert "e" not in fixture.states.active_keys()
        # The run met its rule at the eighth press, and Choose begins with no
        # counted press behind it.
        assert fixture.levels("e") == [
            ("reach", fixture.session, 0, config.LEVEL_UP_CORRECT),
            ("choose", fixture.session, 0, None),
        ]

    def test_a_miss_is_read_back_from_the_latest_press_and_the_block_owes_what_is_left(
        self,
    ) -> None:
        fixture = Fixture(active="fj")
        fixture.begin("e")
        first = fixture.run(fixture.generator.next_block(), lambda i, _: i == 0)
        assert len(first) == 2 * config.LEVEL_UP_CORRECT
        # One miss in eight: seven right is short of the rule by one.
        assert fixture.generator.level == "reach"
        assert [shown(p) for p in fixture.run(fixture.generator.next_block())] == CYCLE_E
        assert fixture.generator.level == "choose"
        assert fixture.levels("e")[0] == (
            "reach",
            fixture.session,
            0,
            config.LEVEL_UP_CORRECT + 1,
        )

    def test_the_bump_letters_and_a_rest_letter_start_at_choose(self) -> None:
        for names, active in ((("f", "j"), ""), (("a",), "fj"), (("k",), "fj")):
            fixture = Fixture(active=active)
            fixture.begin(*names)
            assert fixture.generator.level == "choose"
            for name in names:
                assert fixture.levels(name) == [("choose", fixture.session, 0, None)]

    def test_a_non_conventional_rest_key_moves_which_letter_reaches(self) -> None:
        # The left middle finger rests on `e`: `e` is its rest letter and has
        # no Reach, and `d` reaches down from it, its cue waiting for `e`.
        rest = {**READY, L_MID: RestCell(2, 3, True)}
        fixture = Fixture(active="fj", rest=rest)
        fixture.begin("e")
        assert fixture.generator.level == "choose"
        fixture = Fixture(active="fj", rest=rest)
        fixture.begin("d")
        prompts = fixture.run(fixture.generator.next_block())
        assert [shown(p) for p in prompts] == [("reach", "d"), ("rest", "e")] * (
            config.LEVEL_UP_CORRECT
        )
        # The finger it asks back, which the guidance names (#12m session (6b)).
        assert {p.fingers for p in prompts if p.kind is PromptKind.REST} == {L_MID}

    def test_a_pair_takes_turns_left_hand_first(self) -> None:
        fixture = Fixture(active="fj")
        fixture.begin("e", "i")
        cycles = min(config.LEVEL_UP_CORRECT, -(-config.FIRST_BLOCK_PROMPTS // 4))
        prompts = fixture.run(fixture.generator.next_block())
        assert [shown(p) for p in prompts] == [*CYCLE_E, ("reach", "i"), ("rest", "k")] * cycles

    def test_a_member_with_no_reach_waits_for_choose(self) -> None:
        fixture = Fixture(active="fj")
        fixture.begin("e", "k")
        prompts = fixture.run(fixture.generator.next_block())
        assert [shown(p) for p in prompts] == CYCLE_E * config.LEVEL_UP_CORRECT
        assert fixture.levels("k") == [("choose", fixture.session, 0, None)]

    def test_a_member_ahead_keeps_being_prompted_and_its_rule_is_met_once(self) -> None:
        fixture = Fixture(active="fj")
        fixture.begin("e", "i")
        misses = 2
        seen: list[int] = []

        def wrong(_: int, prompt: Prompt) -> bool:
            if prompt.grapheme != "i":
                return False
            seen.append(1)
            return len(seen) <= misses

        first = fixture.run(fixture.generator.next_block(), wrong)
        assert len(first) == 4 * config.LEVEL_UP_CORRECT
        assert fixture.generator.level == "reach"
        second = fixture.run(fixture.generator.next_block())
        # `i` owes two right presses, and `e`, which met its rule, still reaches.
        assert [shown(p) for p in second] == [*CYCLE_E, ("reach", "i"), ("rest", "k")] * misses
        assert fixture.generator.level == "choose"
        assert fixture.levels("e")[0][3] == config.LEVEL_UP_CORRECT
        assert fixture.levels("i")[0][3] == config.LEVEL_UP_CORRECT + misses

    def test_a_block_of_one_owed_press_is_one_cycle(self) -> None:
        fixture = Fixture(active="fj")
        fixture.begin("e")
        for _ in range(config.LEVEL_UP_CORRECT - 1):
            fixture.reach("e")
        assert [shown(p) for p in fixture.run(fixture.generator.next_block())] == CYCLE_E


class TestCompositeReach:
    """Decided 2026-11-12: a composite takes Reach, and its cue waits for every finger it used."""

    def test_the_cue_waits_for_both_fingers_in_keystroke_order(self) -> None:
        layout = build_is()
        for letter, owed, fingers in (
            ("á", ("æ", "a"), "R-pink+L-pink"),
            ("é", ("æ", "d"), "R-pink+L-mid"),
        ):
            fixture = Fixture(layout, FixedListSource({"ást": 10.0, "éta": 5.0}), active="fj")
            fixture.begin(letter)
            assert fixture.generator.level == "reach"
            block = fixture.generator.next_block()
            assert block.current() == Prompt(PromptKind.REACH, letter)
            block.close()
            assert block.current() == Prompt(PromptKind.REST, owed=owed, fingers=fingers)

    def test_a_composite_paired_with_a_rest_letter_reaches_alone(self) -> None:
        layout = build_is()
        fixture = Fixture(layout, FixedListSource({"ást": 10.0, "æði": 5.0}), active="fj")
        # Two members, three physical keys (ADR-028 § Pair ramp-up, session 8c).
        step = make_step(layout, "á", "æ")
        assert sum(len(intro.keys) for intro in step.keys) == 3
        fixture.store.mark_introduced(fixture.profile, ["á", "æ"])
        fixture.generator.begin_step(step)
        prompts = fixture.run(fixture.generator.next_block())
        assert [shown(p) for p in prompts] == [("reach", "á"), ("rest", "æ+a")] * (
            config.LEVEL_UP_CORRECT
        )


class TestDraw:
    """ADR-024 § Choose and § The draw: one even draw, a cap of two, and misses asked again."""

    def test_choose_draws_the_step_and_the_bump_letters_and_ends_when_the_step_climbs(
        self,
    ) -> None:
        fixture = Fixture(active="fj", rng=FirstChoice())
        fixture.begin("a")
        prompts = fixture.run(fixture.generator.next_block())
        # The first letter the rules allow, twice, then the cap moves it on.
        # `a` meets Choose's rule at its eighth right press, and the block ends there.
        cap = config.MAX_SAME_IN_A_ROW
        cycle = ["a"] * cap + ["f"]
        drawn = cycle * config.LEVEL_UP_CORRECT
        eighth = [i for i, name in enumerate(drawn) if name == "a"][config.LEVEL_UP_CORRECT - 1]
        expected = drawn[: eighth + 1]
        assert [shown(p) for p in prompts] == [("counted", name) for name in expected]
        assert Counter(expected)["a"] == config.LEVEL_UP_CORRECT
        assert fixture.generator.level == "travel"

    def test_a_miss_is_asked_again_once_right_and_the_draw_moves_on(self) -> None:
        fixture = Fixture(active="fj", rng=FirstChoice())
        fixture.begin("a")
        prompts = fixture.run(fixture.generator.next_block(), lambda i, _: i == 0)
        assert [shown(p) for p in prompts[:5]] == [
            ("counted", "a"),
            ("reask", "a"),
            ("counted", "f"),
            ("counted", "a"),
            ("counted", "a"),
        ]

    def test_a_letter_missed_again_is_asked_again_up_to_its_limit(self) -> None:
        fixture = Fixture(active="fj", rng=FirstChoice())
        fixture.begin("a")
        misses = 1 + config.MISS_REPEATS
        prompts = fixture.run(fixture.generator.next_block(), lambda i, _: i < misses)
        assert [shown(p) for p in prompts[: misses + 1]] == [
            ("counted", "a"),
            *[("reask", "a")] * config.MISS_REPEATS,
            ("counted", "f"),
        ]

    def test_a_re_ask_is_outside_the_cap_and_the_worst_case_is_four_running(self) -> None:
        # Drawn twice, the second missed, and asked again twice (ADR-024).
        fixture = Fixture(active="fj", rng=FirstChoice())
        fixture.begin("a")
        cap = config.MAX_SAME_IN_A_ROW
        missed = range(cap - 1, cap + config.MISS_REPEATS)
        prompts = fixture.run(fixture.generator.next_block(), lambda i, _: i in missed)
        letters = [p.grapheme for p in prompts]
        assert letters[: cap + config.MISS_REPEATS + 1] == ["a"] * (cap + config.MISS_REPEATS) + [
            "f"
        ]
        assert runs([str(g) for g in letters]) == cap + config.MISS_REPEATS

    @pytest.mark.parametrize("seed", range(5))
    def test_no_drawn_prompt_follows_itself_more_than_the_cap(self, seed: int) -> None:
        # The first step, a set of two, is where the cap binds most.
        fixture = Fixture(seed=seed)
        fixture.begin("f", "j")
        drawn = [p.grapheme or "" for p in fixture.ladder() if p.kind is PromptKind.COUNTED]
        assert runs(drawn) <= config.MAX_SAME_IN_A_ROW
        assert set(drawn) == {"f", "j"}

    def test_a_restarted_draw_comes_back_as_a_re_ask(self) -> None:
        fixture = Fixture(active="fj", rng=FirstChoice())
        fixture.begin("a")
        block = fixture.generator.next_block()
        assert block.current() == Prompt(PromptKind.COUNTED, "a")
        block.restart(heard=True)
        assert block.current() == Prompt(PromptKind.REASK, "a")

    def test_a_draw_not_yet_heard_stays_a_draw_through_a_restart(self) -> None:
        # Found by #12m session (6)'s review: the next letter is drawn as soon
        # as the last one closes, and waits behind speech. A restart then
        # abandons nothing the child heard, so it must not make the press
        # that answers it uncounted.
        fixture = Fixture(active="fj", rng=FirstChoice())
        fixture.begin("a")
        block = fixture.generator.next_block()
        assert block.current() == Prompt(PromptKind.COUNTED, "a")
        block.restart(heard=False)
        assert block.current() == Prompt(PromptKind.COUNTED, "a")


class TestTravel:
    def test_travel_draws_the_step_and_the_two_most_used_active_letters(self) -> None:
        fixture = Fixture(active="fjruvm")
        fixture.to_travel("d")
        weights = fixture.source.grapheme_weights(fixture.layout)
        ranked = sorted(set("fjruvm"), key=lambda name: (-weights.get(name, 0.0), name))
        partners = set(ranked[: config.TRAVEL_PARTNERS])
        prompts = fixture.run(fixture.generator.next_block())
        assert {p.grapheme for p in prompts} == {"d"} | partners
        assert {p.kind for p in prompts} == {PromptKind.COUNTED}

    def test_the_first_step_is_one_even_draw_of_the_bump_letters_to_the_end(self) -> None:
        # E3: `f` is no longer drawn from a pool of `ff` alone.
        fixture = Fixture(source=FixedListSource({"ff": 0.0047, "jj": 0.000002}))
        fixture.begin("f", "j")
        prompts = fixture.ladder()
        assert {shown(p)[0] for p in prompts} == {"counted"}
        assert {p.grapheme for p in prompts} == {"f", "j"}
        assert fixture.stable("f") == fixture.stable("j") == config.STABLE_ATTEMPTS
        assert fixture.generator.ramp_up is None


class TestTheBar:
    def test_it_is_read_on_choose_and_travel_presses_together_once_at_travel(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.to_travel("d")
        press(fixture, "d", config.STABLE_ATTEMPTS - config.LEVEL_UP_CORRECT - 1)
        assert fixture.stable("d") is None
        press(fixture, "d", 1)
        assert fixture.stable("d") == config.STABLE_ATTEMPTS
        assert fixture.generator.ramp_up is None

    def test_below_the_accuracy_bar_another_thirty_are_owed(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.to_travel("d")
        right = math.ceil(config.STABLE_ATTEMPTS * config.STABLE_MIN_ACCURACY) - 1
        press(fixture, "d", right - config.LEVEL_UP_CORRECT)
        press(fixture, "d", config.STABLE_ATTEMPTS - right, correct=False)
        ladder = fixture.generator.ramp_up
        assert ladder is not None and fixture.stable("d") is None
        assert ladder.owed("d") == config.STABLE_ATTEMPTS
        press(fixture, "d", config.STABLE_ATTEMPTS)
        assert fixture.generator.ramp_up is None

    def test_a_new_letter_past_twice_the_bump_keys_speed_is_held(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        for name in home_anchor_keys(fixture.layout):
            press(fixture, name, config.SPEED_MIN_SAMPLE, latency_ms=1000)
        fixture.to_choose("d")
        slow = round(1000 * config.STABLE_MAX_LATENCY_RATIO) + 1
        press(fixture, "d", config.LEVEL_UP_CORRECT, latency_ms=slow)
        press(fixture, "d", config.STABLE_ATTEMPTS - config.LEVEL_UP_CORRECT, latency_ms=slow)
        assert fixture.generator.level == "travel"
        # The bar reads the median of the latest thirty, so it clears when
        # more than half of them are within the ratio.
        press(fixture, "d", config.STABLE_ATTEMPTS // 2, latency_ms=slow - 1)
        assert fixture.generator.ramp_up is not None
        press(fixture, "d", 1, latency_ms=slow - 1)
        assert fixture.generator.ramp_up is None

    def test_the_bump_letters_own_step_has_no_speed_term(self) -> None:
        # `f` nine times slower than `j` and through. Known gives `f` a
        # baseline, `j`'s (ADR-027, 2026-11-08); the bar skips it in this step.
        fixture = Fixture()
        fixture.to_travel("f", "j")
        press(fixture, "j", config.STABLE_ATTEMPTS, latency_ms=1000)
        press(fixture, "f", config.STABLE_ATTEMPTS, latency_ms=9000)
        assert fixture.states.speed_baseline("f") == 1000
        assert fixture.generator.ramp_up is None

    def test_a_member_ahead_at_choose_still_gets_travel_presses_of_its_own(self) -> None:
        # Decided 2026-11-12 (#12m session (6), from its review): `d` met
        # Choose's rule early and kept being prompted, so it reaches Travel
        # with the bar's thirty good presses; the bar waits for its own
        # LEVEL_UP_CORRECT presses at Travel.
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.to_choose("d", "k")
        press(fixture, "d", config.STABLE_ATTEMPTS)
        press(fixture, "k", config.LEVEL_UP_CORRECT)
        ladder = fixture.generator.ramp_up
        assert ladder is not None and ladder.level == "travel"
        assert fixture.stable("d") is None
        assert ladder.owed("d") == config.LEVEL_UP_CORRECT
        press(fixture, "d", config.LEVEL_UP_CORRECT - 1)
        assert fixture.stable("d") is None
        press(fixture, "d", 1)
        assert fixture.stable("d") == config.STABLE_ATTEMPTS + config.LEVEL_UP_CORRECT

    def test_a_pair_climbs_together_and_ends_when_both_meet_the_bar(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.to_choose("d", "k")
        press(fixture, "d", config.LEVEL_UP_CORRECT)
        assert fixture.generator.level == "choose"
        press(fixture, "k", config.LEVEL_UP_CORRECT)
        assert fixture.generator.level == "travel"
        press(fixture, "d", config.STABLE_ATTEMPTS - config.LEVEL_UP_CORRECT)
        assert fixture.stable("d") == config.STABLE_ATTEMPTS
        assert fixture.generator.level == "travel"
        press(fixture, "k", config.STABLE_ATTEMPTS - config.LEVEL_UP_CORRECT)
        assert fixture.generator.ramp_up is None


class TestRestart:
    """ADR-024 § What survives a restart."""

    def test_a_step_at_reach_begins_reach_again_from_nothing(self) -> None:
        fixture = Fixture(active="fj")
        fixture.begin("e")
        for _ in range(config.LEVEL_UP_CORRECT - 1):
            fixture.reach("e")
        before = fixture.session
        fixture.new_session()
        assert fixture.generator.resume_step(make_step(fixture.layout, "e"))
        assert fixture.generator.level == "reach"
        prompts = fixture.run(fixture.generator.next_block())
        assert [shown(p) for p in prompts] == CYCLE_E * config.LEVEL_UP_CORRECT
        assert fixture.levels("e") == [
            ("reach", before, 0, None),
            (
                "reach",
                fixture.session,
                config.LEVEL_UP_CORRECT - 1,
                2 * config.LEVEL_UP_CORRECT - 1,
            ),
            ("choose", fixture.session, 0, None),
        ]

    def test_a_reach_met_before_the_restart_is_history_not_progress(self) -> None:
        fixture = Fixture(active="fj")
        fixture.begin("e", "i")
        for _ in range(config.LEVEL_UP_CORRECT):
            fixture.reach("e")
        fixture.new_session()
        assert fixture.generator.resume_step(make_step(fixture.layout, "e", "i"))
        ladder = fixture.generator.ramp_up
        assert ladder is not None and ladder.level == "reach"
        assert ladder.owed("e") == config.LEVEL_UP_CORRECT

    def test_a_step_at_choose_resumes_at_choose_with_its_evidence(self) -> None:
        fixture = Fixture(active="fj")
        fixture.to_choose("e")
        press(fixture, "e", config.LEVEL_UP_CORRECT - 1)
        fixture.new_session()
        assert fixture.generator.resume_step(make_step(fixture.layout, "e"))
        assert fixture.generator.level == "choose"
        press(fixture, "e", 1)
        assert fixture.generator.level == "travel"
        # Nothing was begun again: one run per level.
        assert [run[0] for run in fixture.levels("e")] == ["reach", "choose", "travel"]

    def test_a_step_nobody_pressed_is_not_resumed(self) -> None:
        fixture = Fixture(active="fj")
        fixture.begin("e")
        fixture.new_session()
        assert not fixture.generator.resume_step(make_step(fixture.layout, "e"))

    def test_a_step_whose_members_met_the_bar_starts_nothing(self) -> None:
        fixture = Fixture(active="fj")
        fixture.to_travel("a")
        press(fixture, "a", config.STABLE_ATTEMPTS)
        fixture.new_session()
        assert not fixture.generator.resume_step(make_step(fixture.layout, "a"))
        assert fixture.generator.ramp_up is None


class TestComposites:
    def test_a_composite_climbs_like_any_letter(self) -> None:
        layout = build_is()
        fixture = Fixture(layout, FixedListSource({"úúú": 10.0, "sumar": 5.0}), active="fjus")
        fixture.to_travel("ú")
        press(fixture, "ú", config.STABLE_ATTEMPTS - config.LEVEL_UP_CORRECT)
        assert fixture.generator.ramp_up is None


class TestSteadyState:
    def test_block_is_bigrams_over_the_active_set_only(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.practise_all()
        block = fixture.steady()
        assert all(len(unit) == 2 for unit in block.units)
        assert set(block.prompts) <= set(ANCHOR_SIX)

    def test_seeded_generators_agree(self) -> None:
        blocks = []
        for _ in range(2):
            fixture = Fixture(active=ANCHOR_SIX + "dk", seed=11)
            fixture.practise_all()
            blocks.append([fixture.steady() for _ in range(3)])
        assert blocks[0] == blocks[1]

    def test_a_different_seed_gives_different_content(self) -> None:
        blocks = []
        for seed in (11, 12):
            fixture = Fixture(active=ANCHOR_SIX + "dk", seed=seed)
            fixture.practise_all()
            blocks.append(fixture.steady())
        assert blocks[0] != blocks[1]


# Every letter's only carrier is its own double, so each unit names the key it
# was planned for and a block's per-key counts are the plan's, exactly.
def doubles(letters: str) -> FixedListSource:
    return FixedListSource({letter * 2: 1.0 for letter in letters})


# What a finished ramp-up leaves in each member's window at the least (ADR-024
# § The one bar): thirty listened presses, all correct. Reach's presses are
# not attempts and leave nothing there.
RAMP_UP_PRESSES = config.STABLE_ATTEMPTS
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
        need = presses_needed(stats(RAMP_UP_PRESSES, RAMP_UP_PRESSES), STRICT_BAR)
        assert need == config.KNOWN_MIN_ATTEMPTS - RAMP_UP_PRESSES

    def test_a_perfect_key_at_the_floor_needs_nothing(self) -> None:
        floor = config.KNOWN_MIN_ATTEMPTS
        assert presses_needed(stats(floor, floor), STRICT_BAR) == 0

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
    @pytest.mark.parametrize("bar", [config.KNOWN_MIN_ACCURACY, STRICT_BAR])
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
    @pytest.mark.parametrize("bar", [config.KNOWN_MIN_ACCURACY, STRICT_BAR])
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
            fixture.store.append_attempt(
                fixture.profile,
                session_for(fixture.store, fixture.profile, stamp),
                "f",
                True,
                stamp,
            )
        return fixture

    def need(self, fixture: Fixture) -> int:
        return presses_needed(fixture.states.evidence("f"), config.KNOWN_MIN_ACCURACY)

    def test_a_key_at_its_bar_has_no_need_after_a_long_weekend(self) -> None:
        assert self.need(self.practised("2026-01-05T10:00:00+00:00")) == 0

    def test_the_same_key_has_need_again_after_half_a_year_away(self) -> None:
        need = self.need(self.practised("2026-07-01T10:00:00+00:00"))
        # More than nothing, and less than confirming a key never seen: the old
        # presses still count for something.
        from_nothing = presses_needed(
            Evidence(config.KNOWN_MIN_ATTEMPTS, 2, 0.0, 0.0), config.KNOWN_MIN_ACCURACY
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
    def test_keys_fresh_from_their_ramp_up_get_the_block(self) -> None:
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
        counts = Counter(unit[0] for unit in fixture.steady().units)
        assert counts["v"] == counts["m"] == limit
        rest = [counts[name] for name in "fjru"]
        assert sum(rest) == FIRST_SLOTS - 2 * limit
        assert max(rest) - min(rest) <= 1

    def test_the_bump_letters_are_planned_against_known_s_bar_like_any_key(self) -> None:
        # ADR-033 retires the anchor bar. Five early misses in ninety presses
        # over two days is past Known's 90%, and was short of the anchor's 95%:
        # f and j now have no need, like d k s l, and the block goes round all
        # six evenly.
        letters = "fjdksl"
        stamps = ["2026-01-01T10:00:00+00:00", "2026-01-02T10:00:00+00:00"]
        fixture = Fixture(source=doubles(letters), now=stamps[1])
        for name in letters:
            for index in range(config.KNOWN_MIN_ATTEMPTS):
                stamp = stamps[index % 2]
                fixture.store.upsert_key_stat(fixture.profile, name, index >= 5, stamp)
                fixture.store.append_attempt(
                    fixture.profile,
                    session_for(fixture.store, fixture.profile, stamp),
                    name,
                    index >= 5,
                    stamp,
                )
        evidence = fixture.states.evidence("f")
        assert presses_needed(evidence, config.KNOWN_MIN_ACCURACY) == 0
        assert presses_needed(evidence, STRICT_BAR) > 0
        counts = Counter(unit[0] for unit in fixture.steady().units)
        assert sum(counts.values()) == FIRST_SLOTS
        shares = [counts[name] for name in letters]
        assert max(shares) - min(shares) <= 1

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
            fixture.store.append_attempt(
                fixture.profile,
                session_for(fixture.store, fixture.profile, stamp),
                "f",
                True,
                stamp,
            )
        for name in "jruvm":
            fixture.activate(name)
        assert 5 * cap(FIRST_SLOTS, len(ANCHOR_SIX)) > FIRST_SLOTS
        counts = Counter(unit[0] for unit in fixture.steady().units)
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
                fixture.store.append_attempt(
                    fixture.profile,
                    session_for(fixture.store, fixture.profile, stamp),
                    name,
                    True,
                    stamp,
                    ms,
                )
        assert fixture.states.slow_keys() == ({"d"} if slow else set())
        counts = Counter(unit[0] for unit in fixture.steady().units)
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
        first = Counter(unit[0] for unit in fixture.steady().units)
        assert first["f"] == 1
        press(fixture, "f", 1)
        second = Counter(unit[0] for unit in fixture.steady().units)
        assert second["f"] == 0

    def test_a_key_at_the_session_ceiling_is_not_planned(self) -> None:
        fixture = Fixture(source=doubles("dk"))
        fixture.activate("k", attempts=RAMP_UP_PRESSES)
        fixture.activate("d")
        # Wrong every time: d needs more practice than anything, and has had
        # all this sitting should give it.
        press(fixture, "d", config.SESSION_KEY_CEILING, correct=False)
        units = fixture.steady().units
        assert len(units) == FIRST_SLOTS
        assert set(units) == {("k", "k")}

    def test_when_every_key_is_at_the_ceiling_none_is_excluded(self) -> None:
        fixture = Fixture(source=doubles("dk"))
        for name in "dk":
            fixture.activate(name)
            press(fixture, name, config.SESSION_KEY_CEILING)
        units = fixture.steady().units
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
        units = fixture.steady().units
        assert Counter(units) == {("d", "d"): 5, ("k", "k"): 5, ("l", "l"): 5}
        for name in "dkl":
            positions = [i for i, unit in enumerate(units) if unit[0] == name]
            assert [b - a for a, b in pairwise(positions)] == [3] * 4

    def test_the_fallback_partner_breaks_weight_ties_by_name(self) -> None:
        # No bigram in this corpus carries z, so its units fall back to pairing
        # it with the heaviest active letter -- and f and j weigh the same,
        # which without a name tie-break would resolve by set order.
        fixture = Fixture(source=FixedListSource({"fff": 10.0, "jjj": 10.0}), active="fjz", seed=3)
        carried = [unit for unit in fixture.steady().units if "z" in unit]
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
            block = fixture.steady()
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


class TestNoAnchorMaintenance:
    """ADR-027 2026-11-08: the lifelong hold of `f` and `j` is retired.

    A slipping bump letter is practised more through its need, as any key is,
    and carried by the language's bigrams: no reach-then-anchor return-drill.
    """

    # Doubles only, so a unit that is a reach followed by its bump letter could
    # only come from the retired maintenance path.
    def fixture(self) -> Fixture:
        fixture = Fixture(source=doubles(ANCHOR_SIX + "dk"), seed=5)
        for name in ANCHOR_SIX + "dk":
            fixture.activate(name, attempts=config.KNOWN_MIN_ATTEMPTS)
        return fixture

    def slipping(self, *graphemes: str) -> Fixture:
        fixture = self.fixture()
        for grapheme in graphemes:
            # Past the old anchor sample (25), and under its 95% bar by far.
            press(fixture, grapheme, 40, correct=False)
        return fixture

    # 15 slots, a cap of 5. Every key waits for its second day and gets one
    # slot; a slipping key takes the rest up to the cap. Two slipping keys
    # share the seven left in name order, so `j` stops one short of `f`.
    @pytest.mark.parametrize(
        "planned", [{"f": 5}, {"j": 5}, {"f": 5, "j": 4}, {"d": 5}], ids=["f", "j", "fj", "d"]
    )
    def test_a_slipping_key_is_planned_by_need_alone(self, planned: dict[str, int]) -> None:
        assert (FIRST_SLOTS, cap(FIRST_SLOTS, len(ANCHOR_SIX + "dk"))) == (15, 5)
        units = self.slipping(*planned).steady().units
        assert len(units) == FIRST_SLOTS
        assert all(len(set(unit)) == 1 for unit in units)
        counts = Counter(unit[0] for unit in units)
        assert {name: counts[name] for name in planned} == planned
        rest = [counts[name] for name in ANCHOR_SIX + "dk" if name not in planned]
        assert sum(rest) == FIRST_SLOTS - sum(planned.values())
        assert min(rest) >= 1 and max(rest) - min(rest) <= 1

    def test_a_bump_letter_left_for_months_gets_no_return_drill(self) -> None:
        # Decay gives every key need again, the bump letters no more than the rest.
        stamps = ["2026-01-01T10:00:00+00:00", "2026-01-02T10:00:00+00:00"]
        now = (datetime.fromisoformat(stamps[1]) + timedelta(days=200)).isoformat()
        letters = ANCHOR_SIX + "dk"
        fixture = Fixture(source=doubles(letters), seed=5, now=now)
        for name in letters:
            for index in range(config.KNOWN_MIN_ATTEMPTS):
                stamp = stamps[index % 2]
                fixture.store.upsert_key_stat(fixture.profile, name, True, stamp)
                fixture.store.append_attempt(
                    fixture.profile,
                    session_for(fixture.store, fixture.profile, stamp),
                    name,
                    True,
                    stamp,
                )
        units = fixture.steady().units
        assert len(units) == FIRST_SLOTS
        assert all(len(set(unit)) == 1 for unit in units)
        counts = Counter(unit[0] for unit in units)
        assert max(counts.values()) - min(counts[name] for name in letters) <= 1


class TestLanguageWeights:
    """ADR-024: the learner's need picks the key, and the language picks what carries it."""

    def test_a_keys_carrier_is_drawn_by_bigram_weight(self) -> None:
        # `fj` is a thousand to one against either double, and one in two when
        # the weights are ignored.
        source = FixedListSource({"fj": 1000.0, "ff": 1.0, "jj": 1.0})
        fixture = Fixture(source=source, active="fj")
        units = [unit for _ in range(4) for unit in fixture.steady().units]
        assert len(units) == 4 * FIRST_SLOTS
        assert len([unit for unit in units if unit[0] == unit[1]]) <= 2

    def test_a_key_no_bigram_carries_is_paired_with_the_heaviest_other_key(self) -> None:
        # j is in both words and f in one, so j is the heavier; r is in neither.
        source = FixedListSource({"fjj": 10.0, "jjj": 5.0})
        fixture = Fixture(source=source, active="fjr")
        units = fixture.steady().units
        assert {unit for unit in units if "r" in unit} == {("r", "j")}

    def test_a_lone_key_no_bigram_carries_is_doubled(self) -> None:
        fixture = Fixture(source=FixedListSource({"jjj": 1.0}), active="f")
        assert set(fixture.steady().units) == {("f", "f")}


class TestBlockLength:
    def test_first_block_uses_the_configured_default(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.practise_all()
        assert len(fixture.steady().prompts) == config.FIRST_BLOCK_PROMPTS

    def test_length_scales_with_the_measured_pace(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.practise_all()
        # 30 prompts at 2 s each = 0.5/s, over a 100 s block target.
        fixture.answer(fixture.steady().prompts, seconds_each=2.0)
        assert len(fixture.steady().prompts) == 50

    def test_blocks_end_on_a_unit_boundary(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.practise_all()
        # 30 prompts over 61.2 s -> 49.02 prompts per block, rounded to 49.
        fixture.answer(fixture.steady().prompts, seconds_each=2.04)
        block = fixture.steady()
        assert len(block.prompts) == 50
        assert all(len(unit) == 2 for unit in block.units)

    def test_time_the_child_was_not_typing_is_not_charged_to_their_pace(self) -> None:
        # A PAUSED interval, a walk-away, a conversation: monotonic time runs
        # through all of them, and charging them to the child would shrink
        # every block afterwards.
        paced, idle = (Fixture(active=ANCHOR_SIX) for _ in range(2))
        for fixture in (paced, idle):
            fixture.practise_all()
            prompts = fixture.steady().prompts
            fixture.answer(prompts[:15], seconds_each=2.0)
            if fixture is idle:
                fixture.clock.advance(300.0)
            fixture.answer(prompts[15:], seconds_each=2.0)
        assert len(idle.steady().prompts) == 50
        assert len(paced.steady().prompts) == 50

    @pytest.mark.parametrize("before_the_first_answer", [2.0, 12.0, 25.0])
    def test_what_precedes_a_blocks_first_answer_is_not_charged_to_the_pace(
        self, before_the_first_answer: float
    ) -> None:
        # Review of 2026-10-06, E5. The session builds a block right after it
        # queues the introduction script, so the script's length was the first
        # answer's gap. Every wait here is under the idle cap, which is why
        # that rule did not cover it.
        assert before_the_first_answer <= config.PACE_IDLE_GAP_SECONDS
        seconds_each = 2.0
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.practise_all()
        prompts = fixture.steady().prompts
        fixture.clock.advance(before_the_first_answer)
        fixture.answer(prompts[:1])
        fixture.answer(prompts[1:], seconds_each=seconds_each)
        assert len(fixture.steady().prompts) == round(config.BLOCK_TARGET_SECONDS / seconds_each)

    def test_a_gap_left_out_is_not_charged_to_the_pace(self) -> None:
        # The gap a rest cue's guidance was spoken in is Takki's time (ADR-024
        # § Lesson granularity, restated), however short it is.
        paced, guided = (Fixture(active=ANCHOR_SIX) for _ in range(2))
        for fixture in (paced, guided):
            fixture.practise_all()
            prompts = fixture.steady().prompts
            fixture.answer(prompts[:15], seconds_each=2.0)
            if fixture is guided:
                fixture.generator.leave_out_gap()
                fixture.clock.advance(15.0)
                fixture.answer(prompts[15:16], seconds_each=2.0)
                fixture.answer(prompts[16:], seconds_each=2.0)
            else:
                fixture.answer(prompts[15:], seconds_each=2.0)
        assert len(paced.steady().prompts) == 50
        assert len(guided.steady().prompts) == 50

    def test_a_block_nobody_answered_contributes_no_pace_sample(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        fixture.practise_all()
        fixture.answer(fixture.steady().prompts, seconds_each=2.0)
        fixture.steady()
        fixture.clock.advance(600.0)
        assert len(fixture.steady().prompts) == 50

    def test_no_active_keys_gives_an_empty_block(self) -> None:
        assert Fixture().steady() == DrillBlock(())


class TestStepShape:
    def test_a_step_of_three_members_is_refused(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        with pytest.raises(ValueError, match="one or two graphemes"):
            fixture.generator.begin_step(make_step(fixture.layout, "d", "k", "s"))

    def test_an_empty_step_is_refused(self) -> None:
        fixture = Fixture(active=ANCHOR_SIX)
        with pytest.raises(ValueError, match="one or two graphemes"):
            fixture.generator.begin_step(IntroductionStep(()))


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
