from takki.display.focus import EventSink, FocusGained, FocusLost


class FakeFocusSource:
    def __init__(self, outbound: EventSink) -> None:
        self._outbound = outbound
        self.foreground_requests = 0
        self.closed = False

    def gain_focus(self) -> None:
        self._outbound.put(FocusGained())

    def lose_focus(self) -> None:
        self._outbound.put(FocusLost())

    def poll(self) -> None:
        pass

    def request_foreground(self) -> None:
        # No return: a refused raise is modelled by the test simply not calling
        # gain_focus() afterwards, which is what 6b's deadline actually sees.
        self.foreground_requests += 1

    def close(self) -> None:
        self.closed = True
