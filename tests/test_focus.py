import queue

import pygame
import pytest

from takki.display.focus import (
    EventSink,
    FocusEvent,
    FocusGained,
    FocusLost,
    FocusSource,
    PygameFocusSource,
)
from tests.fakes.fake_focus_source import FakeFocusSource


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
        outbound: queue.Queue[FocusEvent] = queue.Queue()
        source = FakeFocusSource(outbound)
        source.gain_focus()
        assert outbound.get_nowait() == FocusGained()

    def test_lose_focus_enqueues_focus_lost(self) -> None:
        outbound: queue.Queue[FocusEvent] = queue.Queue()
        source = FakeFocusSource(outbound)
        source.lose_focus()
        assert outbound.get_nowait() == FocusLost()

    def test_request_foreground_emits_nothing_by_itself(self) -> None:
        # A raise request is not a focus change: the FocusGained (if any)
        # arrives later as a real event. 6b's refused-raise path is a test
        # that requests and then never calls gain_focus().
        outbound: queue.Queue[FocusEvent] = queue.Queue()
        source = FakeFocusSource(outbound)
        source.request_foreground()
        assert outbound.qsize() == 0

    def test_request_foreground_records_call_count(self) -> None:
        outbound: queue.Queue[FocusEvent] = queue.Queue()
        source = FakeFocusSource(outbound)
        assert source.foreground_requests == 0
        source.request_foreground()
        source.request_foreground()
        assert source.foreground_requests == 2

    def test_close_is_recorded(self) -> None:
        outbound: queue.Queue[FocusEvent] = queue.Queue()
        source = FakeFocusSource(outbound)
        assert source.closed is False
        source.close()
        assert source.closed is True

    def test_conforms_to_focus_source_protocol(self) -> None:
        source: FocusSource = FakeFocusSource(queue.Queue[FocusEvent]())
        assert source is not None


def test_queue_conforms_to_event_sink_protocol() -> None:
    sink: EventSink = queue.Queue[FocusEvent]()
    assert sink is not None


class TestPygameFocusSourceUnderDummyDriver:
    # SDL_VIDEODRIVER=dummy is set for every non-audio test by the autouse
    # headless_sdl fixture (tests/conftest.py) -- this box has no real
    # display, so this class only covers what the dummy driver can exercise:
    # construction, a no-crash poll(), and close(). Real focus transitions
    # need a real driver; see test_pygame_focus_source.py (windows_only).

    def test_constructs_a_window_under_dummy_driver(self) -> None:
        outbound: queue.Queue[FocusEvent] = queue.Queue()
        source = PygameFocusSource(outbound)
        source.close()

    def test_poll_does_not_crash_and_does_not_enqueue_spurious_events(self) -> None:
        # The dummy driver reports a constant, unfocused state -- poll()'s
        # backup check should see no change from the state read at
        # construction and therefore synthesise nothing.
        outbound: queue.Queue[FocusEvent] = queue.Queue()
        source = PygameFocusSource(outbound)
        source.poll()
        assert outbound.qsize() == 0
        source.close()

    def test_poll_leaves_events_it_does_not_own_on_the_sdl_queue(self) -> None:
        # poll() must type-filter its get(): an unfiltered drain would swallow
        # QUIT, which the core loop (session 11) owns and needs to see.
        outbound: queue.Queue[FocusEvent] = queue.Queue()
        source = PygameFocusSource(outbound)
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        source.poll()
        assert pygame.event.get(pygame.QUIT), "poll() consumed QUIT"
        source.close()

    def test_repeated_focus_events_emit_only_on_change(self) -> None:
        # Edge-triggered: Windows re-delivers WINDOWFOCUSGAINED, and the backup
        # poll re-reads the same state every tick. 6b's FSM wants transitions.
        outbound: queue.Queue[FocusEvent] = queue.Queue()
        source = PygameFocusSource(outbound)
        pygame.event.post(pygame.event.Event(pygame.WINDOWFOCUSGAINED))
        source.poll()
        assert outbound.qsize() == 1
        assert outbound.get_nowait() == FocusGained()
        pygame.event.post(pygame.event.Event(pygame.WINDOWFOCUSGAINED))
        source.poll()
        assert outbound.qsize() == 0
        source.close()

    def test_conforms_to_focus_source_protocol(self) -> None:
        outbound: queue.Queue[FocusEvent] = queue.Queue()
        source: FocusSource = PygameFocusSource(outbound)
        assert source is not None
        source.close()
