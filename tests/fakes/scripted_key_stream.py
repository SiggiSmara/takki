from takki.input import EventSink, KeyEvent


class ScriptedKeyStream:
    def __init__(self, events: list[KeyEvent], outbound: EventSink) -> None:
        self._events = list(events)
        self._outbound = outbound
        self._index = 0
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def run_one(self) -> bool:
        """Emit the next scripted event; False once exhausted. Drivable without a thread, for tests."""
        if self._index >= len(self._events):
            return False
        self._outbound.put(self._events[self._index])
        self._index += 1
        return True

    def run(self) -> None:
        while self.run_one():
            pass
