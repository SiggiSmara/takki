import queue
from typing import Any

import pygame
import pytest

from takki.audio.tts_worker import SpeechFinished, TTSWorker
from takki.clock import Clock
from takki.display.focus import (
    EventSink,
    FocusEvent,
    FocusGained,
    FocusLost,
    FocusSource,
    PygameFocusSource,
)
from takki.events import Quit
from takki.focus_model import FocusModel, Pressed, TypedCharacter
from takki.input.window_keys import KeyDown, KeymapChanged, KeyUp, TextTyped, WindowKeyEvent
from takki.speech import Speaker
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_focus_source import FakeFocusSource
from tests.fakes.fake_letters import FakeLetterAudioSource
from tests.fakes.fake_tts import FakeTTSEngine

Outbound = queue.Queue[FocusEvent | WindowKeyEvent | Quit]

# SDL scancodes and keycodes as the laptop reported them (research/key-capture-source.md).
SC_A, SC_L, SC_LALT = 4, 15, 226
K_A, K_L, K_LALT = 97, 108, pygame.K_LALT


def post(kind: int, **attributes: Any) -> None:
    pygame.event.post(pygame.event.Event(kind, **attributes))


def drained(outbound: "Outbound") -> list[FocusEvent | WindowKeyEvent | Quit]:
    events: list[FocusEvent | WindowKeyEvent | Quit] = []
    while not outbound.empty():
        events.append(outbound.get_nowait())
    return events


def test_focus_gained_is_frozen() -> None:
    event = FocusGained()
    with pytest.raises(Exception):
        event.x = 1  # type: ignore[attr-defined]
    assert FocusGained() == FocusGained()


def test_focus_lost_is_frozen() -> None:
    assert FocusLost() == FocusLost()
    assert FocusGained() != FocusLost()


class TestFakeFocusSource:
    def test_gain_focus_enqueues_focus_gained(self) -> None:
        outbound: queue.Queue[FocusEvent | WindowKeyEvent | Quit] = queue.Queue()
        source = FakeFocusSource(outbound)
        source.gain_focus()
        assert outbound.get_nowait() == FocusGained()

    def test_lose_focus_enqueues_focus_lost(self) -> None:
        outbound: queue.Queue[FocusEvent | WindowKeyEvent | Quit] = queue.Queue()
        source = FakeFocusSource(outbound)
        source.lose_focus()
        assert outbound.get_nowait() == FocusLost()

    def test_keys_enqueues_each_event_in_order(self) -> None:
        outbound: Outbound = queue.Queue()
        source = FakeFocusSource(outbound)
        source.keys(KeyDown(SC_A, K_A), TextTyped("a", SC_A, fresh=True), KeyUp(SC_A, K_A))
        assert drained(outbound) == [
            KeyDown(SC_A, K_A),
            TextTyped("a", SC_A, fresh=True),
            KeyUp(SC_A, K_A),
        ]

    def test_close_is_recorded(self) -> None:
        outbound: queue.Queue[FocusEvent | WindowKeyEvent | Quit] = queue.Queue()
        source = FakeFocusSource(outbound)
        assert source.closed is False
        source.close()
        assert source.closed is True

    def test_conforms_to_focus_source_protocol(self) -> None:
        source: FocusSource = FakeFocusSource(queue.Queue[FocusEvent | WindowKeyEvent | Quit]())
        assert source is not None


def test_queue_conforms_to_event_sink_protocol() -> None:
    sink: EventSink = queue.Queue[FocusEvent | WindowKeyEvent | Quit]()
    assert sink is not None


class TestPygameFocusSourceUnderDummyDriver:
    # SDL_VIDEODRIVER=dummy is set for every non-audio test by the autouse
    # headless_sdl fixture (tests/conftest.py) -- this box has no real
    # display, so this class only covers what the dummy driver can exercise:
    # construction, a no-crash poll(), and close(). Real focus transitions
    # need a real driver; see test_pygame_focus_source.py (windows_only).

    def test_constructs_a_window_under_dummy_driver(self) -> None:
        outbound: queue.Queue[FocusEvent | WindowKeyEvent | Quit] = queue.Queue()
        source = PygameFocusSource(outbound)
        source.close()

    def test_construction_seeds_the_initial_focus_state(self) -> None:
        # The FSM cannot query focus, so the starting state has to arrive as an
        # event. The dummy driver's window is never focused, hence FocusLost.
        outbound: queue.Queue[FocusEvent | WindowKeyEvent | Quit] = queue.Queue()
        source = PygameFocusSource(outbound)
        assert outbound.get_nowait() == FocusLost()
        assert outbound.qsize() == 0
        source.close()

    def test_poll_does_not_crash_and_does_not_enqueue_spurious_events(self) -> None:
        # The dummy driver reports a constant, unfocused state -- poll()'s
        # backup check should see no change from the state read at
        # construction and therefore synthesise nothing beyond the seed.
        outbound: queue.Queue[FocusEvent | WindowKeyEvent | Quit] = queue.Queue()
        source = PygameFocusSource(outbound)
        outbound.get_nowait()
        source.poll()
        assert outbound.qsize() == 0
        source.close()

    def test_poll_forwards_quit_onto_the_inbound_queue(self) -> None:
        # Session 6a left QUIT on the SDL queue for "the core loop (session 11),
        # which owns it". Session 11 owns it and cannot reach pygame -- the core
        # loop talks to Protocols only (ADR-019) -- so this pump, the only thing
        # that sees QUIT, normalises it onto the one inbound stream instead.
        outbound: queue.Queue[FocusEvent | WindowKeyEvent | Quit] = queue.Queue()
        source = PygameFocusSource(outbound)
        outbound.get_nowait()
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        source.poll()
        assert outbound.get_nowait() == Quit()
        # And nothing behind it: a closing window can already read as
        # unfocused, and a synthesised FocusLost would announce a pause on the
        # way out.
        assert outbound.empty()
        source.close()

    def test_poll_discards_events_it_does_not_own(self) -> None:
        # Nothing else reads SDL's queue, so anything poll() leaves there stays
        # until the queue is full (alpha-plan #12c (3)).
        outbound: Outbound = queue.Queue()
        source = PygameFocusSource(outbound)
        outbound.get_nowait()
        post(pygame.MOUSEMOTION, pos=(1, 1))
        post(pygame.KEYDOWN, scancode=SC_A, key=K_A)
        source.poll()
        assert pygame.event.get(pump=False) == []
        assert drained(outbound) == [KeyDown(SC_A, K_A)]
        source.close()

    def test_poll_hands_every_key_event_to_the_reader_from_its_one_drain(self) -> None:
        # ADR-028 § C8: one drain, never a second get(). A letter is its press,
        # its fresh text and its release, in that order.
        outbound: Outbound = queue.Queue()
        source = PygameFocusSource(outbound)
        outbound.get_nowait()
        post(pygame.KEYDOWN, scancode=SC_A, key=K_A)
        post(pygame.TEXTINPUT, text="a")
        post(pygame.KEYUP, scancode=SC_A, key=K_A)
        post(pygame.KEYMAPCHANGED)
        source.poll()
        assert drained(outbound) == [
            KeyDown(SC_A, K_A),
            TextTyped("a", SC_A, fresh=True),
            KeyUp(SC_A, K_A),
            KeymapChanged(),
        ]
        source.close()

    def test_key_and_focus_events_interleave_in_one_tick_in_drain_order(self) -> None:
        # #14a's trace of Alt+Tab with `l` held: Alt arrives as a press, and
        # SDL's releases of it and of the held key come in the same tick as
        # the focus loss, just before it.
        outbound: Outbound = queue.Queue()
        source = PygameFocusSource(outbound)
        outbound.get_nowait()
        post(pygame.WINDOWFOCUSGAINED)
        post(pygame.KEYDOWN, scancode=SC_L, key=K_L)
        post(pygame.TEXTINPUT, text="l")
        post(pygame.TEXTINPUT, text="l")
        post(pygame.KEYDOWN, scancode=SC_LALT, key=K_LALT)
        post(pygame.KEYUP, scancode=SC_LALT, key=K_LALT)
        post(pygame.KEYUP, scancode=SC_L, key=K_L)
        post(pygame.WINDOWFOCUSLOST)
        post(pygame.QUIT)
        source.poll()
        assert drained(outbound) == [
            FocusGained(),
            KeyDown(SC_L, K_L),
            TextTyped("l", SC_L, fresh=True),
            TextTyped("l", SC_L, fresh=False),
            KeyDown(SC_LALT, K_LALT),
            KeyUp(SC_LALT, K_LALT),
            KeyUp(SC_L, K_L),
            FocusLost(),
            Quit(),
        ]
        source.close()

    def test_a_key_held_into_a_focus_loss_is_up_for_the_focus_model(self) -> None:
        # The wiring end to end: what poll() puts on the queue, handled in
        # order by the real focus model. SDL's KEYUP before WINDOWFOCUSLOST
        # clears the down-state the alignment's hold check reads (#14 (f)).
        outbound: Outbound = queue.Queue()
        source = PygameFocusSource(outbound)
        outbound.get_nowait()
        clock: Clock = FakeClock()
        speech = TTSWorker(FakeTTSEngine, queue.Queue[SpeechFinished]())
        speech.build_engine()
        model = FocusModel(Speaker(speech, FakeLetterAudioSource(), clock), clock)

        def tick() -> list[object]:
            source.poll()
            commands: list[object] = []
            for event in drained(outbound):
                assert not isinstance(event, Quit)
                command = model.handle(event)
                if command is not None:
                    commands.append(command)
            return commands

        post(pygame.WINDOWFOCUSGAINED)
        post(pygame.KEYDOWN, scancode=SC_A, key=K_A)
        post(pygame.TEXTINPUT, text="a")
        assert tick() == [Pressed(SC_A), TypedCharacter("a")]
        assert model.is_down(SC_A)
        post(pygame.KEYUP, scancode=SC_A, key=K_A)
        post(pygame.WINDOWFOCUSLOST)
        assert tick() == []
        assert not model.is_down(SC_A)
        source.close()

    def test_every_owned_event_in_a_tick_is_acted_on_not_just_the_first(self) -> None:
        # The unfiltered get() drops other types, never a second owned event.
        outbound: queue.Queue[FocusEvent | WindowKeyEvent | Quit] = queue.Queue()
        source = PygameFocusSource(outbound)
        outbound.get_nowait()
        pygame.event.post(pygame.event.Event(pygame.WINDOWFOCUSGAINED))
        pygame.event.post(pygame.event.Event(pygame.MOUSEMOTION, pos=(1, 1)))
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        source.poll()
        assert [outbound.get_nowait() for _ in range(2)] == [FocusGained(), Quit()]
        assert outbound.empty()
        source.close()

    def test_quit_still_arrives_after_more_events_than_sdl_can_queue(self) -> None:
        # E10: mouse motion alone fills SDL's 65,535-event queue in 18-20
        # minutes, and from then on SDL refuses every new event, QUIT included,
        # so the close button stops working. 1,000 a tick stands in for that
        # long run.
        outbound: queue.Queue[FocusEvent | WindowKeyEvent | Quit] = queue.Queue()
        source = PygameFocusSource(outbound)
        outbound.get_nowait()
        for _ in range(70):
            for _ in range(1_000):
                pygame.event.post(pygame.event.Event(pygame.MOUSEMOTION, pos=(1, 1)))
            source.poll()
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        source.poll()
        assert outbound.get_nowait() == Quit()
        assert outbound.empty()
        source.close()

    def test_repeated_focus_events_emit_only_on_change(self) -> None:
        # Edge-triggered: Windows re-delivers WINDOWFOCUSGAINED, and the backup
        # poll re-reads the same state every tick. 6b's FSM wants transitions.
        outbound: queue.Queue[FocusEvent | WindowKeyEvent | Quit] = queue.Queue()
        source = PygameFocusSource(outbound)
        outbound.get_nowait()
        pygame.event.post(pygame.event.Event(pygame.WINDOWFOCUSGAINED))
        source.poll()
        assert outbound.qsize() == 1
        assert outbound.get_nowait() == FocusGained()
        pygame.event.post(pygame.event.Event(pygame.WINDOWFOCUSGAINED))
        source.poll()
        assert outbound.qsize() == 0
        source.close()

    def test_conforms_to_focus_source_protocol(self) -> None:
        outbound: queue.Queue[FocusEvent | WindowKeyEvent | Quit] = queue.Queue()
        source: FocusSource = PygameFocusSource(outbound)
        assert source is not None
        source.close()
