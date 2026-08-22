import queue
import sys

import pytest

from takki.input import EventSink, KeyEvent, KeyEventStream
from tests.fakes.scripted_key_stream import ScriptedKeyStream


def test_key_event_fields() -> None:
    event = KeyEvent(pressed=True, char="a", name=None)
    assert event.pressed is True
    assert event.char == "a"
    assert event.name is None


def test_key_event_is_frozen() -> None:
    event = KeyEvent(pressed=True, char="a", name=None)
    with pytest.raises(Exception):
        event.pressed = False  # type: ignore[misc]


class TestScriptedKeyStream:
    def test_run_delivers_events_in_order(self) -> None:
        events = [
            KeyEvent(pressed=True, char="a", name=None),
            KeyEvent(pressed=False, char="a", name=None),
            KeyEvent(pressed=True, char=None, name="esc"),
        ]
        outbound: queue.Queue[KeyEvent] = queue.Queue()
        stream = ScriptedKeyStream(events, outbound)
        stream.run()
        delivered = [outbound.get_nowait() for _ in range(3)]
        assert delivered == events

    def test_run_one_delivers_a_single_event(self) -> None:
        events = [
            KeyEvent(pressed=True, char="a", name=None),
            KeyEvent(pressed=True, char="b", name=None),
        ]
        outbound: queue.Queue[KeyEvent] = queue.Queue()
        stream = ScriptedKeyStream(events, outbound)
        assert stream.run_one() is True
        assert outbound.get_nowait() == events[0]
        assert outbound.qsize() == 0

    def test_run_one_returns_false_once_exhausted(self) -> None:
        outbound: queue.Queue[KeyEvent] = queue.Queue()
        stream = ScriptedKeyStream([], outbound)
        assert stream.run_one() is False

    def test_run_one_can_be_interleaved_with_other_driving(self) -> None:
        events = [
            KeyEvent(pressed=True, char="a", name=None),
            KeyEvent(pressed=True, char="b", name=None),
            KeyEvent(pressed=True, char="c", name=None),
        ]
        outbound: queue.Queue[KeyEvent] = queue.Queue()
        stream = ScriptedKeyStream(events, outbound)
        stream.run_one()
        stream.run_one()
        assert outbound.qsize() == 2
        stream.run_one()
        assert outbound.qsize() == 3
        assert stream.run_one() is False

    def test_no_thread_involved(self) -> None:
        # run()/run_one() are plain synchronous calls -- no start() needed to
        # deliver events, matching concurrency-model.md's testability rule.
        outbound: queue.Queue[KeyEvent] = queue.Queue()
        stream = ScriptedKeyStream([KeyEvent(pressed=True, char="a", name=None)], outbound)
        stream.run()
        assert outbound.qsize() == 1

    def test_start_and_stop_are_recorded(self) -> None:
        outbound: queue.Queue[KeyEvent] = queue.Queue()
        stream = ScriptedKeyStream([], outbound)
        assert stream.started is False
        assert stream.stopped is False
        stream.start()
        stream.stop()
        assert stream.started is True
        assert stream.stopped is True

    def test_conforms_to_key_event_stream_protocol(self) -> None:
        stream: KeyEventStream = ScriptedKeyStream([], queue.Queue[KeyEvent]())
        assert stream is not None


def test_queue_conforms_to_event_sink_protocol() -> None:
    sink: EventSink = queue.Queue[KeyEvent]()
    assert sink is not None


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="asserts the non-Windows guard; on Windows the constructor legitimately "
    "succeeds and would build a real pynput Listener, which the default tier forbids",
)
def test_pynput_key_stream_raises_off_windows() -> None:
    # No monkeypatching: the guard is a real sys.platform branch, so this asserts
    # it on the platforms where it applies. The win32 path is covered by
    # test_pynput_stream.py (windows_only).
    from takki.input.pynput_stream import PynputKeyStream

    outbound: queue.Queue[KeyEvent] = queue.Queue()
    with pytest.raises(NotImplementedError):
        PynputKeyStream(outbound)
