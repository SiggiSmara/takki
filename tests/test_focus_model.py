import queue

from takki import config
from takki.audio.tts_worker import SpeechFinished, TTSWorker
from takki.display.focus import FocusEvent, FocusGained, FocusLost
from takki.events import Quit
from takki.focus_model import (
    PAUSED_ANNOUNCEMENT,
    RESUMED_ANNOUNCEMENT,
    FocusModel,
    FocusState,
    LessonCommand,
    Pressed,
    RereadPrompt,
    RestartWord,
    TypedCharacter,
)
from takki.input.taxonomy import KeyBindings
from takki.input.window_keys import KeyDown, KeymapChanged, KeyUp, TextTyped, WindowKeyEvent
from takki.speech import Speaker
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_focus_source import FakeFocusSource
from tests.fakes.fake_letters import FakeLetterAudioSource
from tests.fakes.fake_tts import FakeTTSEngine
from tests.fakes.keys import keystroke

HOLD = config.RESTART_HOLD_MS / 1000.0
ESC = config.REREAD_KEY
TALK = config.TALK_KEY
# SDL scan codes (research/key-capture-source.md).
BACKSPACE, TAB, DELETE, ENTER, SPACE = 42, 43, 76, 40, 44
F2, F5, LEFT_WINDOWS, LEFT_SHIFT = 59, 62, 227, 225
IS_DEAD_ACUTE = 52
ACUTE = "\u00b4"


def sc(letter: str) -> int:
    """The SDL scan code of a letter key on a US-shaped row: `a` is 4, `z` is 29."""
    return 4 + ord(letter) - ord("a")


class Harness:
    """The core loop of concurrency-model.md, driven synchronously: one queue, dispatch, deadline check."""

    def __init__(self, bindings: KeyBindings | None = None) -> None:
        self.inbound: queue.Queue[WindowKeyEvent | FocusEvent | Quit] = queue.Queue()
        self.focus = FakeFocusSource(self.inbound)
        self.engine = FakeTTSEngine()
        self.speech = TTSWorker(lambda: self.engine, queue.Queue[SpeechFinished]())
        self.speech.build_engine()
        self.letters = FakeLetterAudioSource()
        # The gate speaks through the core's Speaker, not straight at the
        # worker: one object has to know what is audible, or a gate-issued
        # stop() cancels a core sequence's utterance and the core, seeing a
        # SpeechFinished for the id it holds, advances the sequence it meant to
        # clear (alpha session 11).
        self.clock = FakeClock()
        self.speaker = Speaker(self.speech, self.letters, self.clock)
        self.model = FocusModel(self.speaker, self.clock, bindings)
        self.commands: list[LessonCommand] = []

    def keys(self, *events: WindowKeyEvent | FocusEvent) -> None:
        """Events in the order one drain of the window hands them over."""
        for event in events:
            self.inbound.put(event)
        self.drain()

    def type(self, letter: str, *, release: bool = True) -> None:
        self.keys(*keystroke(sc(letter.lower()), letter, release=release))

    def press(self, code: int) -> None:
        self.keys(KeyDown(code, 0))

    def release(self, code: int) -> None:
        self.keys(KeyUp(code, 0))

    def lose_focus(self) -> None:
        self.focus.lose_focus()
        self.drain()

    def gain_focus(self) -> None:
        self.focus.gain_focus()
        self.drain()

    def tick(self, advance: float = 0.0) -> None:
        self.clock.advance(advance)
        self._record(self.model.check_deadlines())
        self.run_worker()

    def spoken(self) -> list[str]:
        self.run_worker()
        return self.engine.spoken

    def run_worker(self) -> None:
        # The real worker is a thread that pops commands as they arrive, so it
        # has to run between steps here too. Leaving every utterance queued
        # until the end of the test made a later interrupt() cancel utterances
        # the child had already heard (alpha session 12a-2).
        while not self.speech.idle:
            self.speech.run_one()

    def drain(self) -> None:
        while True:
            try:
                event = self.inbound.get_nowait()
            except queue.Empty:
                self.run_worker()
                return
            # The gate handles key and focus events; Quit is the loop's
            # (session 11) and never reaches it.
            assert not isinstance(event, Quit)
            self._record(self.model.handle(event))

    def _record(self, command: LessonCommand | None) -> None:
        if command is not None:
            self.commands.append(command)


class TestTaxonomyDispatch:
    def test_a_letter_is_its_press_and_then_its_text(self) -> None:
        # The press is for the alignment, which answers the key; the text is
        # for a lesson, which answers what it typed.
        harness = Harness()
        harness.type("h")
        harness.type("i")
        assert harness.commands == [
            Pressed(sc("h")),
            TypedCharacter("h"),
            Pressed(sc("i")),
            TypedCharacter("i"),
        ]

    def test_talk_key_is_classified_and_dropped(self) -> None:
        # Alpha has no voice subsystem to route it to (ADR-020 is Beta).
        harness = Harness()
        harness.press(TALK)
        harness.release(TALK)
        assert harness.commands == []
        assert harness.spoken() == []

    def test_keys_that_type_nothing_are_passed_on_once_per_press(self) -> None:
        # Only the alignment answers one (#12m session (7)); a release is nothing.
        harness = Harness()
        codes = (BACKSPACE, TAB, DELETE, ENTER, SPACE, F2, LEFT_WINDOWS, LEFT_SHIFT, IS_DEAD_ACUTE)
        for code in codes:
            harness.press(code)
            harness.release(code)
        assert harness.commands == [Pressed(code) for code in codes]

    def test_every_keydown_is_a_new_press(self) -> None:
        # pygame passes no auto-repeat KEYDOWN, so a second one with no release
        # between is never a repeat. Ignoring it would drop every later press
        # of the key if the down-state ever disagreed with SDL's (review of
        # #14b, decided by the developer).
        harness = Harness()
        harness.press(LEFT_SHIFT)
        harness.press(LEFT_SHIFT)
        harness.release(LEFT_SHIFT)
        assert harness.commands == [Pressed(LEFT_SHIFT), Pressed(LEFT_SHIFT)]
        assert not harness.model.is_down(LEFT_SHIFT)

    def test_the_space_bar_types_a_space_and_stays_system_by_its_key(self) -> None:
        # ADR-023: the space bar is never introduced. The window gives it the
        # text `' '`, which pynput never did (alpha-plan #14 (d)).
        harness = Harness()
        harness.keys(*keystroke(SPACE, " "))
        assert harness.commands == [Pressed(SPACE)]

    def test_text_that_is_not_printable_is_composing_and_ignored(self) -> None:
        harness = Harness()
        harness.keys(TextTyped("\u200b", sc("a"), fresh=True))
        assert harness.commands == []

    def test_a_held_key_is_down_until_it_is_released(self) -> None:
        harness = Harness()
        harness.press(LEFT_SHIFT)
        harness.type("A", release=False)
        assert harness.model.is_down(LEFT_SHIFT) and harness.model.is_down(sc("a"))
        harness.release(LEFT_SHIFT)
        harness.release(sc("a"))
        assert not harness.model.is_down(LEFT_SHIFT) and not harness.model.is_down(sc("a"))

    def test_a_layout_switch_reaches_the_gate_and_changes_nothing(self) -> None:
        # What Takki says about it is roadmap § D's (alpha-plan #14 (h)).
        harness = Harness()
        harness.keys(KeymapChanged())
        assert harness.commands == []
        assert harness.model.state is FocusState.ACTIVE
        assert harness.spoken() == []


class TestEscapeTapHold:
    def test_tap_rereads_on_release(self) -> None:
        harness = Harness()
        harness.press(ESC)
        harness.tick(HOLD / 2)
        assert harness.commands == []
        harness.release(ESC)
        assert harness.commands == [RereadPrompt()]

    def test_hold_restarts_at_the_threshold_while_the_key_is_still_down(self) -> None:
        harness = Harness()
        harness.press(ESC)
        harness.tick(HOLD - 0.001)
        assert harness.commands == []
        harness.tick(0.001)
        assert harness.commands == [RestartWord()]

    def test_hold_fires_once_and_the_release_does_not_also_reread(self) -> None:
        harness = Harness()
        harness.press(ESC)
        harness.tick(HOLD)
        harness.tick(HOLD)
        harness.tick(HOLD)
        harness.release(ESC)
        harness.tick(HOLD)
        assert harness.commands == [RestartWord()]

    def test_a_second_keydown_arms_a_fresh_hold(self) -> None:
        # Every KEYDOWN is a new press, so the hold counts from the latest one.
        harness = Harness()
        harness.press(ESC)
        harness.tick(HOLD / 2)
        harness.press(ESC)
        harness.tick(HOLD / 2 + 0.001)
        assert harness.commands == []
        harness.tick(HOLD / 2)
        assert harness.commands == [RestartWord()]

    def test_a_second_keydown_before_an_early_release_still_rereads_once(self) -> None:
        harness = Harness()
        harness.press(ESC)
        harness.tick(HOLD / 2)
        harness.press(ESC)
        harness.release(ESC)
        assert harness.commands == [RereadPrompt()]

    def test_a_second_tap_after_a_release_arms_a_fresh_gesture(self) -> None:
        harness = Harness()
        harness.press(ESC)
        harness.release(ESC)
        harness.press(ESC)
        harness.tick(HOLD)
        assert harness.commands == [RereadPrompt(), RestartWord()]

    def test_release_without_an_armed_press_does_nothing(self) -> None:
        harness = Harness()
        harness.release(ESC)
        assert harness.commands == []


class TestDistinctRecoveryKeys:
    BINDINGS = KeyBindings(reread=ESC, restart=F5)

    def test_each_key_fires_on_press_with_no_hold_timing(self) -> None:
        harness = Harness(self.BINDINGS)
        harness.press(ESC)
        assert harness.commands == [RereadPrompt()]
        harness.tick(HOLD * 10)
        harness.release(ESC)
        assert harness.commands == [RereadPrompt()]
        harness.press(F5)
        assert harness.commands == [RereadPrompt(), RestartWord()]
        harness.tick(HOLD * 10)
        harness.release(F5)
        assert harness.commands == [RereadPrompt(), RestartWord()]

    def test_every_keydown_fires_the_action(self) -> None:
        harness = Harness(self.BINDINGS)
        harness.press(F5)
        harness.press(F5)
        assert harness.commands == [RestartWord(), RestartWord()]


class TestFocusGating:
    def test_focus_loss_pauses_and_announces(self) -> None:
        harness = Harness()
        harness.lose_focus()
        assert harness.model.state is FocusState.PAUSED
        assert harness.spoken() == [PAUSED_ANNOUNCEMENT]

    def test_focus_loss_interrupts_the_prompt_in_flight(self) -> None:
        harness = Harness()
        harness.speaker.letter("f")
        harness.lose_focus()
        assert harness.letters.stopped == 1

    def test_key_events_after_focus_loss_are_dropped(self) -> None:
        # A backstop: the window gets no key while another has focus (#13).
        harness = Harness()
        harness.type("h")
        harness.lose_focus()
        harness.type("o")
        harness.type("u")
        harness.press(ESC)
        harness.release(ESC)
        assert harness.commands == [Pressed(sc("h")), TypedCharacter("h")]

    def test_no_hold_timing_runs_while_paused(self) -> None:
        harness = Harness()
        harness.lose_focus()
        harness.press(ESC)
        harness.tick(HOLD * 10)
        assert harness.commands == []

    def test_sdls_release_before_the_focus_loss_clears_a_held_key(self) -> None:
        # SDL releases every held key just before it reports the focus lost, in
        # the same drain (alpha-plan #13, #14a's trace). The release reaches
        # the gate while it is still ACTIVE: a tap's re-read fires, which the
        # pause announcement cuts, and the key is up for its next press.
        harness = Harness()
        harness.keys(KeyDown(ESC, 0))
        harness.tick(HOLD / 2)
        harness.keys(KeyUp(ESC, 0), FocusLost())
        assert not harness.model.is_down(ESC)
        harness.gain_focus()
        harness.press(ESC)
        harness.tick(HOLD)
        assert harness.commands == [RereadPrompt(), RestartWord()]

    def test_a_gesture_is_dropped_by_the_pause(self) -> None:
        harness = Harness()
        harness.press(ESC)
        harness.lose_focus()
        harness.gain_focus()
        harness.tick(HOLD * 10)
        harness.release(ESC)
        assert harness.commands == []

    def test_resume_interrupts_the_stale_announcement(self) -> None:
        harness = Harness()
        harness.lose_focus()
        # Nothing was audible before the pause, so nothing was stopped for it.
        assert harness.engine.stopped == 0
        harness.gain_focus()
        assert harness.engine.stopped == 1

    def test_alt_tab_back_resumes_and_announces(self) -> None:
        harness = Harness()
        harness.lose_focus()
        harness.gain_focus()
        assert harness.model.state is FocusState.ACTIVE
        assert harness.spoken() == [PAUSED_ANNOUNCEMENT, RESUMED_ANNOUNCEMENT]

    def test_repeated_focus_loss_announces_once(self) -> None:
        harness = Harness()
        harness.lose_focus()
        harness.lose_focus()
        assert harness.spoken() == [PAUSED_ANNOUNCEMENT]

    def test_focus_gain_while_already_active_is_silent(self) -> None:
        harness = Harness()
        harness.gain_focus()
        assert harness.model.state is FocusState.ACTIVE
        assert harness.spoken() == []

    def test_typing_works_again_after_resume(self) -> None:
        harness = Harness()
        harness.lose_focus()
        harness.type("x")
        harness.gain_focus()
        harness.type("y")
        assert harness.commands == [Pressed(sc("y")), TypedCharacter("y")]


class TestStartupSeed:
    def test_a_seed_focus_lost_pauses_before_any_key_arrives(self) -> None:
        # PygameFocusSource emits its initial state at construction; a window
        # that comes up unfocused must land the FSM in PAUSED, not ACTIVE.
        harness = Harness()
        harness.keys(FocusLost(), *keystroke(sc("a"), "a"))
        assert harness.model.state is FocusState.PAUSED
        assert harness.commands == []


class TestEventOrdering:
    def test_focus_and_key_events_are_interleaved_on_one_queue(self) -> None:
        harness = Harness()
        harness.keys(
            *keystroke(sc("a"), "a"),
            FocusLost(),
            *keystroke(sc("b"), "b"),
            FocusGained(),
            *keystroke(sc("c"), "c"),
        )
        assert harness.commands == [
            Pressed(sc("a")),
            TypedCharacter("a"),
            Pressed(sc("c")),
            TypedCharacter("c"),
        ]
        # Only the resume is heard. The whole burst is dispatched before the
        # worker runs, so the pause announcement is still queued when the
        # resume supersedes it -- and announce() means "in place of what is
        # audible", so a pause the child never heard and is no longer in must
        # not be spoken after they are already back (alpha session 12a-2).
        assert harness.spoken() == [RESUMED_ANNOUNCEMENT]


class TestText:
    def test_fresh_text_is_no_repeat(self) -> None:
        harness = Harness()
        harness.keys(TextTyped("f", sc("f"), fresh=True))
        assert harness.commands == [TypedCharacter("f", repeat=False)]

    def test_a_held_keys_repeats_are_labelled_not_swallowed(self) -> None:
        # ADR-027 § Held keys: the engine must see every repeat -- it decides
        # they are not attempts -- so the count here is three, not one.
        harness = Harness()
        harness.keys(
            *keystroke(sc("f"), "f", release=False),
            TextTyped("f", sc("f"), fresh=False),
            TextTyped("f", sc("f"), fresh=False),
            KeyUp(sc("f"), 0),
        )
        assert harness.commands == [
            Pressed(sc("f")),
            TypedCharacter("f", repeat=False),
            TypedCharacter("f", repeat=True),
            TypedCharacter("f", repeat=True),
        ]

    def test_a_press_with_two_characters_is_one_attempt_judged_by_the_first(self) -> None:
        # A dead key that cannot combine with `k` gives the accent, then `k`, from
        # one press. The reader marks the first fresh and the second not, so the
        # second is a repeat and is no attempt (alpha-plan #14 (c)).
        harness = Harness()
        harness.keys(
            KeyDown(IS_DEAD_ACUTE, 0),
            KeyUp(IS_DEAD_ACUTE, 0),
            KeyDown(sc("k"), 0),
            TextTyped(ACUTE, sc("k"), fresh=True),
            TextTyped("k", sc("k"), fresh=False),
            KeyUp(sc("k"), 0),
        )
        assert harness.commands == [
            Pressed(IS_DEAD_ACUTE),
            Pressed(sc("k")),
            TypedCharacter(ACUTE, repeat=False),
            TypedCharacter("k", repeat=True),
        ]

    def test_a_composed_letter_is_one_character_on_its_base_key(self) -> None:
        harness = Harness()
        harness.keys(
            KeyDown(IS_DEAD_ACUTE, 0),
            KeyUp(IS_DEAD_ACUTE, 0),
            *keystroke(sc("a"), "\u00e1"),
        )
        assert harness.commands == [
            Pressed(IS_DEAD_ACUTE),
            Pressed(sc("a")),
            TypedCharacter("\u00e1", repeat=False),
        ]

    def test_text_with_no_key_down_is_a_repeat(self) -> None:
        harness = Harness()
        harness.keys(TextTyped("l", None, fresh=False))
        assert harness.commands == [TypedCharacter("l", repeat=True)]

    def test_a_shift_released_before_the_letter_still_clears_the_key(self) -> None:
        # The release names the key by scan code, never by the character, so
        # Shift's state cannot leave it down (research/key-capture-source.md § 2).
        harness = Harness()
        harness.press(LEFT_SHIFT)
        harness.type("A", release=False)
        harness.release(LEFT_SHIFT)
        harness.release(sc("a"))
        harness.type("a")
        assert harness.commands == [
            Pressed(LEFT_SHIFT),
            Pressed(sc("a")),
            TypedCharacter("a", repeat=False),
            Pressed(sc("a")),
            TypedCharacter("a", repeat=False),
        ]

    def test_the_engine_never_sees_an_upper_case_character(self) -> None:
        # ADR-027 § Case is folded at the boundary. Every character below is
        # lower case whatever Shift or Caps Lock was doing.
        harness = Harness()
        harness.keys(TextTyped("F", sc("f"), fresh=True), TextTyped("\u00c4", 52, fresh=True))
        assert harness.commands == [
            TypedCharacter("f", repeat=False),
            TypedCharacter("\u00e4", repeat=False),
        ]
