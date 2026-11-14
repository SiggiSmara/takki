from takki.display.focus import EventSink, FocusGained, FocusLost
from takki.events import Quit
from takki.input.window_keys import WindowKeyEvent


class FakeFocusSource:
    def __init__(self, outbound: EventSink) -> None:
        self._outbound = outbound
        self.closed = False

    def gain_focus(self) -> None:
        self._outbound.put(FocusGained())

    def lose_focus(self) -> None:
        self._outbound.put(FocusLost())

    def keys(self, *events: WindowKeyEvent) -> None:
        """Stand-in for the window's key events, as its reader hands them over (tests/fakes/keys.py)."""
        for event in events:
            self._outbound.put(event)

    def quit(self) -> None:
        """Stand-in for the SDL pump seeing pygame.QUIT -- the window closed."""
        self._outbound.put(Quit())

    def poll(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True
