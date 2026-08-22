import queue

from takki import config
from takki.audio.tts_worker import SpeechFinished, TTSWorker
from takki.display.focus import FocusEvent, FocusGained, FocusLost
from takki.focus_model import (
    ALT_TAB_HINT,
    PAUSED_ANNOUNCEMENT,
    RESUMED_ANNOUNCEMENT,
    FocusModel,
    FocusState,
    LessonCommand,
    RereadPrompt,
    RestartWord,
    TypedCharacter,
)
from takki.input import KeyEvent
from takki.input.taxonomy import KeyBindings
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_focus_source import FakeFocusSource
from tests.fakes.fake_tts import FakeTTSEngine
from tests.fakes.scripted_key_stream import ScriptedKeyStream

HOLD = config.RESTART_HOLD_MS / 1000.0
RESUME_HOLD = config.RESUME_HOLD_MS / 1000.0
REQUEST_TIMEOUT = config.RESUME_REQUEST_TIMEOUT_MS / 1000.0


class Harness:
    """The core loop of concurrency-model.md, driven synchronously: one queue, dispatch, deadline check."""

    def __init__(self, bindings: KeyBindings | None = None) -> None:
        self.inbound: queue.Queue[KeyEvent | FocusEvent] = queue.Queue()
        self.focus = FakeFocusSource(self.inbound)
        self.engine = FakeTTSEngine()
        self.speech = TTSWorker(self.engine, queue.Queue[SpeechFinished]())
        self.clock = FakeClock()
        self.model = FocusModel(self.focus, self.speech, self.clock, bindings)
        self.commands: list[LessonCommand] = []

    def keys(self, *events: KeyEvent) -> None:
        ScriptedKeyStream(list(events), self.inbound).run()
        self.drain()

    def press(self, name: str | None = None, char: str | None = None) -> None:
        self.keys(KeyEvent(pressed=True, char=char, name=name))

    def release(self, name: str | None = None, char: str | None = None) -> None:
        self.keys(KeyEvent(pressed=False, char=char, name=name))

    def lose_focus(self) -> None:
        self.focus.lose_focus()
        self.drain()

    def gain_focus(self) -> None:
        self.focus.gain_focus()
        self.drain()

    def tick(self, advance: float = 0.0) -> None:
        self.clock.advance(advance)
        self._record(self.model.check_deadlines())

    def spoken(self) -> list[str]:
        # Drain the worker to the point of shutdown; nothing is spoken until
        # something pops the command queue, which is the point of the worker.
        self.speech.enqueue_shutdown()
        self.speech.run()
        return self.engine.spoken

    def drain(self) -> None:
        while True:
            try:
                event = self.inbound.get_nowait()
            except queue.Empty:
                return
            self._record(self.model.handle(event))

    def _record(self, command: LessonCommand | None) -> None:
        if command is not None:
            self.commands.append(command)


class TestTaxonomyDispatch:
    def test_printable_character_reaches_the_lesson(self) -> None:
        harness = Harness()
        harness.keys(
            KeyEvent(pressed=True, char="h", name=None),
            KeyEvent(pressed=False, char="h", name=None),
            KeyEvent(pressed=True, char="i", name=None),
        )
        assert harness.commands == [TypedCharacter("h"), TypedCharacter("i")]

    def test_talk_key_is_classified_and_dropped(self) -> None:
        # Alpha has no voice subsystem to route it to (ADR-020 is Beta).
        harness = Harness()
        harness.press(name=config.TALK_KEY)
        harness.release(name=config.TALK_KEY)
        assert harness.commands == []
        assert harness.spoken() == []

    def test_boundary_and_system_keys_are_ignored(self) -> None:
        harness = Harness()
        for name in ("backspace", "tab", "delete", "enter", "space", "f2", "cmd"):
            harness.press(name=name)
            harness.release(name=name)
        assert harness.commands == []

    def test_dead_key_arm_is_ignored(self) -> None:
        harness = Harness()
        harness.press(char=None, name=None)
        assert harness.commands == []


class TestEscapeTapHold:
    def test_tap_rereads_on_release(self) -> None:
        harness = Harness()
        harness.press(name=config.REREAD_KEY)
        harness.tick(HOLD / 2)
        assert harness.commands == []
        harness.release(name=config.REREAD_KEY)
        assert harness.commands == [RereadPrompt()]

    def test_hold_restarts_at_the_threshold_while_the_key_is_still_down(self) -> None:
        harness = Harness()
        harness.press(name=config.RESTART_KEY)
        harness.tick(HOLD - 0.001)
        assert harness.commands == []
        harness.tick(0.001)
        assert harness.commands == [RestartWord()]

    def test_hold_fires_once_and_the_release_does_not_also_reread(self) -> None:
        harness = Harness()
        harness.press(name=config.RESTART_KEY)
        harness.tick(HOLD)
        harness.tick(HOLD)
        harness.tick(HOLD)
        harness.release(name=config.RESTART_KEY)
        harness.tick(HOLD)
        assert harness.commands == [RestartWord()]

    def test_auto_repeat_presses_do_not_re_arm_the_hold_timer(self) -> None:
        # The OS repeats the press while the key is down. If a repeat restarted
        # the timer the restart would never fire on a steadily held key.
        harness = Harness()
        harness.press(name=config.RESTART_KEY)
        harness.tick(HOLD / 2)
        harness.press(name=config.RESTART_KEY)
        harness.press(name=config.RESTART_KEY)
        assert harness.commands == []
        harness.tick(HOLD / 2 + 0.001)
        assert harness.commands == [RestartWord()]

    def test_auto_repeat_before_an_early_release_still_rereads_once(self) -> None:
        harness = Harness()
        harness.press(name=config.REREAD_KEY)
        harness.tick(HOLD / 2)
        harness.press(name=config.REREAD_KEY)
        harness.release(name=config.REREAD_KEY)
        assert harness.commands == [RereadPrompt()]

    def test_a_second_tap_after_a_release_arms_a_fresh_gesture(self) -> None:
        harness = Harness()
        harness.press(name=config.REREAD_KEY)
        harness.release(name=config.REREAD_KEY)
        harness.press(name=config.REREAD_KEY)
        harness.tick(HOLD)
        assert harness.commands == [RereadPrompt(), RestartWord()]

    def test_release_without_an_armed_press_does_nothing(self) -> None:
        harness = Harness()
        harness.release(name=config.REREAD_KEY)
        assert harness.commands == []


class TestDistinctRecoveryKeys:
    BINDINGS = KeyBindings(reread="esc", restart="f5")

    def test_each_key_fires_on_press_with_no_hold_timing(self) -> None:
        harness = Harness(self.BINDINGS)
        harness.press(name="esc")
        assert harness.commands == [RereadPrompt()]
        harness.tick(HOLD * 10)
        harness.release(name="esc")
        assert harness.commands == [RereadPrompt()]
        harness.press(name="f5")
        assert harness.commands == [RereadPrompt(), RestartWord()]
        harness.tick(HOLD * 10)
        harness.release(name="f5")
        assert harness.commands == [RereadPrompt(), RestartWord()]

    def test_auto_repeat_does_not_re_fire_the_action(self) -> None:
        harness = Harness(self.BINDINGS)
        harness.press(name="f5")
        harness.press(name="f5")
        harness.press(name="f5")
        assert harness.commands == [RestartWord()]


class TestFocusGating:
    def test_focus_loss_pauses_and_announces(self) -> None:
        harness = Harness()
        harness.lose_focus()
        assert harness.model.state is FocusState.PAUSED
        assert harness.spoken() == [PAUSED_ANNOUNCEMENT]

    def test_focus_loss_interrupts_the_prompt_in_flight(self) -> None:
        harness = Harness()
        harness.lose_focus()
        assert harness.engine.stopped == 1

    def test_key_events_after_focus_loss_are_dropped(self) -> None:
        harness = Harness()
        harness.keys(KeyEvent(pressed=True, char="h", name=None))
        harness.lose_focus()
        harness.keys(
            KeyEvent(pressed=True, char="o", name=None),
            KeyEvent(pressed=True, char="u", name=None),
            KeyEvent(pressed=True, char=None, name=config.REREAD_KEY),
            KeyEvent(pressed=False, char=None, name=config.REREAD_KEY),
        )
        assert harness.commands == [TypedCharacter("h")]

    def test_no_hold_timing_runs_while_paused(self) -> None:
        harness = Harness()
        harness.lose_focus()
        harness.press(name=config.RESTART_KEY)
        harness.tick(HOLD * 10)
        assert harness.commands == []

    def test_a_gesture_in_flight_is_dropped_by_the_pause(self) -> None:
        # The release may never arrive — a low-level hook sees nothing on the
        # secure desktop — so the transition clears the held state.
        harness = Harness()
        harness.press(name=config.REREAD_KEY)
        harness.lose_focus()
        harness.gain_focus()
        harness.release(name=config.REREAD_KEY)
        harness.tick(HOLD * 10)
        assert harness.commands == []

    def test_a_key_still_held_across_the_pause_stays_de_repeated(self) -> None:
        # The OS keeps repeating the press throughout. None of those repeats is
        # a new press, so nothing may arm a gesture when focus comes back.
        harness = Harness()
        harness.press(name=config.REREAD_KEY)
        harness.lose_focus()
        harness.press(name=config.REREAD_KEY)
        harness.gain_focus()
        harness.press(name=config.REREAD_KEY)
        harness.tick(HOLD * 2)
        harness.release(name=config.REREAD_KEY)
        assert harness.commands == []

    def test_the_key_works_again_after_that_release(self) -> None:
        harness = Harness()
        harness.press(name=config.REREAD_KEY)
        harness.lose_focus()
        harness.gain_focus()
        harness.release(name=config.REREAD_KEY)
        harness.press(name=config.REREAD_KEY)
        harness.tick(HOLD)
        assert harness.commands == [RestartWord()]

    def test_resume_interrupts_the_stale_announcement(self) -> None:
        harness = Harness()
        harness.lose_focus()
        assert harness.engine.stopped == 1
        harness.gain_focus()
        assert harness.engine.stopped == 2

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
        harness.keys(KeyEvent(pressed=True, char="x", name=None))
        harness.gain_focus()
        harness.keys(KeyEvent(pressed=True, char="y", name=None))
        assert harness.commands == [TypedCharacter("y")]


class TestResume:
    def test_the_resume_key_is_still_seen_while_paused(self) -> None:
        harness = Harness()
        harness.lose_focus()
        harness.press(name=config.RESUME_KEY)
        harness.tick(RESUME_HOLD)
        assert harness.focus.foreground_requests == 1

    def test_the_hold_must_complete_before_a_request_is_made(self) -> None:
        harness = Harness()
        harness.lose_focus()
        harness.press(name=config.RESUME_KEY)
        harness.tick(RESUME_HOLD - 0.001)
        assert harness.focus.foreground_requests == 0

    def test_releasing_early_cancels_the_request(self) -> None:
        harness = Harness()
        harness.lose_focus()
        harness.press(name=config.RESUME_KEY)
        harness.tick(RESUME_HOLD / 2)
        harness.release(name=config.RESUME_KEY)
        harness.tick(RESUME_HOLD * 10)
        assert harness.focus.foreground_requests == 0
        assert harness.spoken() == [PAUSED_ANNOUNCEMENT]

    def test_auto_repeat_during_the_resume_hold_does_not_re_arm_it(self) -> None:
        harness = Harness()
        harness.lose_focus()
        harness.press(name=config.RESUME_KEY)
        harness.tick(RESUME_HOLD / 2)
        harness.press(name=config.RESUME_KEY)
        harness.tick(RESUME_HOLD / 2 + 0.001)
        assert harness.focus.foreground_requests == 1

    def test_the_request_is_made_once_per_hold(self) -> None:
        harness = Harness()
        harness.lose_focus()
        harness.press(name=config.RESUME_KEY)
        harness.tick(RESUME_HOLD)
        harness.tick(0.001)
        harness.tick(0.001)
        assert harness.focus.foreground_requests == 1

    def test_focus_gained_before_the_deadline_resumes(self) -> None:
        harness = Harness()
        harness.lose_focus()
        harness.press(name=config.RESUME_KEY)
        harness.tick(RESUME_HOLD)
        harness.gain_focus()
        assert harness.model.state is FocusState.ACTIVE
        harness.tick(REQUEST_TIMEOUT * 2)
        assert harness.spoken() == [PAUSED_ANNOUNCEMENT, RESUMED_ANNOUNCEMENT]

    def test_deadline_expiry_speaks_the_alt_tab_fallback(self) -> None:
        harness = Harness()
        harness.lose_focus()
        harness.press(name=config.RESUME_KEY)
        harness.tick(RESUME_HOLD)
        harness.tick(REQUEST_TIMEOUT - 0.001)
        assert harness.spoken() == [PAUSED_ANNOUNCEMENT]
        harness.tick(0.001)
        assert harness.model.state is FocusState.PAUSED
        assert harness.spoken() == [PAUSED_ANNOUNCEMENT, ALT_TAB_HINT]

    def test_the_fallback_is_spoken_once(self) -> None:
        harness = Harness()
        harness.lose_focus()
        harness.press(name=config.RESUME_KEY)
        harness.tick(RESUME_HOLD)
        harness.tick(REQUEST_TIMEOUT)
        harness.tick(REQUEST_TIMEOUT)
        harness.tick(REQUEST_TIMEOUT)
        assert harness.spoken() == [PAUSED_ANNOUNCEMENT, ALT_TAB_HINT]

    def test_alt_tab_after_a_refused_request_still_resumes(self) -> None:
        # The held key and a manual Alt+Tab converge on the same FocusGained.
        harness = Harness()
        harness.lose_focus()
        harness.press(name=config.RESUME_KEY)
        harness.tick(RESUME_HOLD)
        harness.tick(REQUEST_TIMEOUT)
        harness.gain_focus()
        assert harness.model.state is FocusState.ACTIVE
        assert harness.spoken() == [PAUSED_ANNOUNCEMENT, ALT_TAB_HINT, RESUMED_ANNOUNCEMENT]

    def test_manual_alt_tab_resumes_without_any_request(self) -> None:
        harness = Harness()
        harness.lose_focus()
        harness.gain_focus()
        assert harness.model.state is FocusState.ACTIVE
        assert harness.focus.foreground_requests == 0
        assert harness.spoken() == [PAUSED_ANNOUNCEMENT, RESUMED_ANNOUNCEMENT]

    def test_the_resume_key_has_no_meaning_while_active(self) -> None:
        harness = Harness()
        harness.press(name=config.RESUME_KEY)
        harness.tick(RESUME_HOLD * 10)
        assert harness.commands == []
        assert harness.focus.foreground_requests == 0


class TestStartupSeed:
    def test_a_seed_focus_lost_pauses_before_any_key_arrives(self) -> None:
        # PygameFocusSource emits its initial state at construction; a window
        # that comes up unfocused must land the FSM in PAUSED, not ACTIVE.
        harness = Harness()
        harness.inbound.put(FocusLost())
        harness.inbound.put(KeyEvent(pressed=True, char="a", name=None))
        harness.drain()
        assert harness.model.state is FocusState.PAUSED
        assert harness.commands == []


class TestEventOrdering:
    def test_focus_and_key_events_are_interleaved_on_one_queue(self) -> None:
        harness = Harness()
        harness.inbound.put(KeyEvent(pressed=True, char="a", name=None))
        harness.inbound.put(FocusLost())
        harness.inbound.put(KeyEvent(pressed=True, char="b", name=None))
        harness.inbound.put(FocusGained())
        harness.inbound.put(KeyEvent(pressed=True, char="c", name=None))
        harness.drain()
        assert harness.commands == [TypedCharacter("a"), TypedCharacter("c")]
        assert harness.spoken() == [PAUSED_ANNOUNCEMENT, RESUMED_ANNOUNCEMENT]


class TestCharacterRepeats:
    def test_a_first_press_is_not_a_repeat(self) -> None:
        harness = Harness()
        harness.press(char="f")
        assert harness.commands == [TypedCharacter("f", repeat=False)]

    def test_a_held_character_repeats_are_labelled_not_swallowed(self) -> None:
        # ADR-027 § Held keys: the engine must see every repeat -- it decides
        # they are not attempts -- so the count here is three, not one.
        harness = Harness()
        harness.press(char="f")
        harness.press(char="f")
        harness.press(char="f")
        assert harness.commands == [
            TypedCharacter("f", repeat=False),
            TypedCharacter("f", repeat=True),
            TypedCharacter("f", repeat=True),
        ]

    def test_a_release_ends_the_repeat_run(self) -> None:
        harness = Harness()
        harness.press(char="l")
        harness.release(char="l")
        harness.press(char="l")
        assert harness.commands == [
            TypedCharacter("l", repeat=False),
            TypedCharacter("l", repeat=False),
        ]

    def test_repeats_are_tracked_per_character(self) -> None:
        harness = Harness()
        harness.press(char="f")
        harness.press(char="j")
        harness.press(char="f")
        assert harness.commands == [
            TypedCharacter("f", repeat=False),
            TypedCharacter("j", repeat=False),
            TypedCharacter("f", repeat=True),
        ]

    def test_a_key_held_across_a_pause_still_repeats_on_resume(self) -> None:
        harness = Harness()
        harness.press(char="f")
        harness.lose_focus()
        harness.press(char="f")
        harness.gain_focus()
        harness.press(char="f")
        assert harness.commands == [
            TypedCharacter("f", repeat=False),
            TypedCharacter("f", repeat=True),
        ]

    def test_a_key_pressed_while_paused_is_down_on_resume(self) -> None:
        harness = Harness()
        harness.lose_focus()
        harness.press(char="f")
        harness.gain_focus()
        harness.press(char="f")
        assert harness.commands == [TypedCharacter("f", repeat=True)]

    def test_a_shift_released_before_the_letter_still_clears_the_key(self) -> None:
        # pynput recomputes KeyCode.char from live modifier state, so the same
        # physical key reports "A" down and "a" up. If that leaked, the next
        # press of it would be labelled a repeat and silently ignored.
        harness = Harness()
        harness.press(char="A")
        harness.release(char="a")
        harness.press(char="A")
        assert harness.commands == [
            TypedCharacter("A", repeat=False),
            TypedCharacter("A", repeat=False),
        ]

    def test_shifting_mid_hold_does_not_hide_a_repeat(self) -> None:
        harness = Harness()
        harness.press(char="a")
        harness.press(char="A")
        assert harness.commands == [
            TypedCharacter("a", repeat=False),
            TypedCharacter("A", repeat=True),
        ]
